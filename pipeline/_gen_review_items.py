# -*- coding: utf-8 -*-
"""生成「人工判断清单」条目——**带原文上下文**，让人能判，而不是让人猜。

为什么要有它
------------
泛称（裸帝号/王号/官号）在算法层只能靠 default 硬兜，兜错了就是「张冠李戴」。
这类问题最终必须人来看，但以前的清单只写「高祖 js×31 兜刘邦」——
没有原文、没有篇目、没有候选人的时代，人根本判不了。

本脚本把判定所需的证据一次性抽齐：命中处数、归属分布、tier 构成、
**每一处的原文上下文（【】标出命中串）**、候选人的朝代。
产出即 `docs/17` §二「条目模板」的实例，写进 `docs/17-条目-<批次>.md` 供勾选。

用法
----
    python pipeline/_gen_review_items.py --list
        # 列出所有泛称：按「guess 处数」降序，先看哪些最该人判

    python pipeline/_gen_review_items.py --alias 高祖
        # 全库生成「高祖」的判定条目（按书分组）

    python pipeline/_gen_review_items.py --alias 高祖 --book js
        # 只看晋书

    python pipeline/_gen_review_items.py --alias 元帝 --per 8
        # 每书取 8 条上下文（默认 6）

    python pipeline/_gen_review_items.py --alias 高祖 --alias 惠帝 \
        --book js --per 6 --out "docs/17-条目-晋书帝号.md"
        # 多个称号一次生成并落盘（推荐：留下生成命令可复现）

约定
----
- 只读：不碰 people.json / book-data.json，只写 --out 指定的文件。
- 「真漏标」= 正文里出现了该串、且没有任何标注覆盖（是证据，不是噪声）。
- 「被更长别名接管」= 漢高祖 之类由长名命中（长名优先，属正确行为，不计漏标）。
- 上下文默认前后各 14 字，命中串用【】括起来；按 pid 轮转取样，避免证据全落在第一人身上。
- 模板与流程见 `docs/17-待办-人工判断清单.md`。
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
BOOK_DATA = ROOT / "data" / "index" / "book-data.json"
CTX = 14

TIER_ORDER = ["core", "owner", "related", "sentence", "paragraph", "chapter", "era", "guess"]


def load():
    d = json.load(open(BOOK_DATA, encoding="utf-8"))
    chapters = {c["id"]: c for c in d["chapters"]}
    persons = {p["id"]: p for p in d["persons"]}
    generics = {}
    for g in d.get("genericAliases", []):
        generics[g["alias"]] = g
        for f in g.get("forms", []):
            generics.setdefault(f, g)
    return d, chapters, persons, generics


def scan(alias: str, book_filter: str | None):
    """扫描全库，收集该串的命中与上下文。"""
    d, chapters, persons, generics = load()
    g = generics.get(alias)
    forms = set(g["forms"]) if g else {alias}
    forms.add(alias)

    # 只按规范形（繁体）扫正文，避免简繁两形把同一处数两遍
    core = g["alias"] if g else alias

    # book -> stat
    stat = defaultdict(lambda: {
        "total": 0, "chapters": set(), "byPid": Counter(), "byTier": Counter(),
        "samples": defaultdict(list), "unmarked": [], "byLong": Counter(),
    })

    for s in d["sentences"]:
        ch = chapters.get(s["chapterId"])
        if not ch:
            continue
        bk = ch["bookId"]
        if book_filter and bk != book_filter:
            continue
        st = stat[bk]
        text = s["text"]
        marks = s.get("marks", [])
        hit_marks = [m for m in marks if m.get("alias") in forms]

        for m in hit_marks:
            st["total"] += 1
            st["chapters"].add(ch["id"])
            st["byPid"][m.get("pid") or "(未标)"] += 1
            st["byTier"][m.get("tier") or "?"] += 1
            a, b = m.get("s", 0), m.get("e", 0)
            ctx = text[max(0, a - CTX):a] + "【" + text[a:b] + "】" + text[b:b + CTX]
            st["samples"][m.get("pid") or "(未标)"].append({
                "fullTitle": ch["fullTitle"], "ctx": ctx,
                "tier": m.get("tier") or "?", "alias": m.get("alias"),
            })

        # 正文中出现该串、但没有被「本泛称」标上的位置：
        # 区分「被更长别名接管」（如 漢高祖 → 刘邦，长名优先，是正确行为）
        # 与「真的漏标」——两者混为一谈会把人引向错误结论。
        j = text.find(core)
        while j >= 0:
            cover = next((m for m in marks if m.get("s", 0) <= j < m.get("e", 0)), None)
            if cover is None:
                st["unmarked"].append({
                    "fullTitle": ch["fullTitle"],
                    "ctx": text[max(0, j - CTX):j] + "【" + core + "】"
                          + text[j + len(core): j + len(core) + CTX],
                })
            elif cover.get("alias") not in forms:
                st["byLong"][cover.get("alias")] += 1
            j = text.find(core, j + 1)

    return d, persons, generics, dict(stat)


def pname(persons, pid, with_dyn=False):
    """with_dyn=True 时带朝代——判「高祖是刘邦还是司马懿」靠的就是这个。"""
    if pid == "(未标)" or pid is None:
        return "(未标)"
    p = persons.get(pid)
    if not p:
        return pid
    s = "{} {}".format(pid, p["name"])
    if with_dyn and p.get("dynasty"):
        s += "（{}）".format(p["dynasty"])
    return s


def tier_str(counter):
    return " / ".join("{}{}".format(k, counter[k]) for k in TIER_ORDER if counter.get(k))


def round_robin(samples_by_pid, per):
    """按 pid 轮转取样，保证证据覆盖多个归属，而不是全落在第一人身上。"""
    pids = sorted(samples_by_pid, key=lambda k: -len(samples_by_pid[k]))
    out, i = [], 0
    while len(out) < per:
        added = False
        for pid in pids:
            lst = samples_by_pid[pid]
            if i < len(lst):
                out.append((pid, lst[i]))
                added = True
                if len(out) >= per:
                    break
        if not added:
            break
        i += 1
    return out


def render(alias: str, book_filter, per: int) -> str:
    d, persons, generics, stat = scan(alias, book_filter)
    g = generics.get(alias)
    L = []
    L.append("## 「{}」\n".format(alias))
    if g:
        L.append("- **当前 default**：{}".format(pname(persons, g.get("default"), True)))
        L.append("- **候选（GENERIC）**：{}\n".format(
            "、".join(pname(persons, c, True) for c in (g.get("candidates") or []))))
    else:
        L.append("- ⚠ 该串不在 `genericAliases` 里（可能是单人 core 或根本没收录）\n")

    if not stat:
        L.append("\n（全库无命中）\n")
        return "\n".join(L)

    for bk in sorted(stat):
        st = stat[bk]
        L.append("\n### @{书籍} · {n} 处 / {c} 篇".format(书籍=bk, n=st["total"], c=len(st["chapters"])))
        L.append("\n**归属分布**\n")
        L.append("| 当前归属 | 处 | tier 构成 |")
        L.append("|---|---:|---|")
        for pid, n in st["byPid"].most_common():
            L.append("| {} | {} | {} |".format(
                pname(persons, pid, True), n, tier_str(
                    Counter(x["tier"] for x in st["samples"][pid]))))
        if st["byLong"]:
            L.append("\n> 另有 {} 处被**更长的别名**接管（长名优先，属正确行为，无需处理）：{}".format(
                sum(st["byLong"].values()),
                "、".join("「{}」×{}".format(k, v) for k, v in st["byLong"].most_common(4))))
        if st["unmarked"]:
            L.append("\n> ⚠ **{} 处真漏标**（正文有该串、无任何标注）——见文末样本".format(len(st["unmarked"])))

        picked = round_robin(st["samples"], per)
        L.append("\n**原文上下文**（【】为命中串，前后各 {} 字）\n".format(CTX))
        L.append("| # | 篇目 | 原文 | 当前归属·tier | 你的判定 |")
        L.append("|---|---|---|---|---|")
        for i, (pid, s) in enumerate(picked, 1):
            L.append("| {} | {} | {} | {}·{} |  |".format(
                i, s["fullTitle"], s["ctx"].replace("|", "｜"),
                pname(persons, pid).split(" ", 1)[-1], s["tier"]))

        if st["unmarked"]:
            L.append("\n**真漏标样本**（最多 5 条）\n")
            for i, u in enumerate(st["unmarked"][:5], 1):
                L.append("{}. {}　{}".format(i, u["fullTitle"], u["ctx"].replace("|", "｜")))

        L.append("\n**你的判定**（勾一个）\n")
        L.append("- [ ] 归 `____`（写 pid 或人名）")
        L.append("- [ ] 按书分：`{bk}`=____、其他书=____（走 `GENERIC_BOOK_CANDIDATES`）".format(bk=bk))
        L.append("- [ ] **未知**：不硬归，改 `none` 或保留 `guess` + UI「歸屬存疑」")
        L.append("- [ ] **不标**：整串出索引（确认不是人名）\n")
        L.append("**回填动作**（执行方填）\n")
        L.append("- 改哪个字段：`GENERIC_MANUAL` / `GENERIC_DEFAULT` / `GENERIC_BOOK_CANDIDATES` / 某人 `core`")
        L.append("- 加哪条断言：`verify.py`")
    return "\n".join(L)


def cmd_list(top=25):
    d, _, _, _ = load()
    forms_of = {}
    for g in d.get("genericAliases", []):
        forms_of.setdefault(g["alias"], set()).update(g.get("forms", []) + [g["alias"]])
    guess = Counter()
    total = Counter()
    for s in d["sentences"]:
        for m in s.get("marks", []):
            a = m.get("alias")
            if a in forms_of:
                total[a] += 1
                if m.get("tier") == "guess":
                    guess[a] += 1
    print("泛称共 {} 个。按 guess（硬兜 default，最需要人判）降序：\n".format(len(forms_of)))
    print("| 称号 | 总处 | guess | guess 占比 |")
    print("|---|---:|---:|---:|")
    for a, n in guess.most_common(top):
        t = total[a]
        print("| {} | {} | {} | {:.0%} |".format(a, t, n, n / t if t else 0))
    print("\n生成清单：`python pipeline/_gen_review_items.py --alias <称号>`")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", action="append", default=[])
    ap.add_argument("--book", default=None)
    ap.add_argument("--per", type=int, default=6, help="每本书取几条上下文")
    ap.add_argument("--out", default=None)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list or not a.alias:
        cmd_list()
        return

    cmd = "python pipeline/_gen_review_items.py"
    for al in a.alias:
        cmd += " --alias " + al
    if a.book:
        cmd += " --book " + a.book
    cmd += " --per {}".format(a.per)
    parts = ["<!-- 自动生成，勿手改；改数据后重跑本命令即可刷新 -->",
             "<!-- {} · {} -->".format(datetime.date.today().isoformat(), cmd),
             ""]
    for al in a.alias:
        parts.append(render(al, a.book, a.per))
        parts.append("\n---\n")
    out = "\n".join(parts)

    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print("已写入 {}".format(a.out))
    else:
        print(out)


if __name__ == "__main__":
    main()
