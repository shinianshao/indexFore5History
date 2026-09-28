# -*- coding: utf-8 -*-
"""AI 概率判定闭环 · 第 1 段：把待判池导出成**结构化 JSON**。

为什么要有它
------------
docs/19 §三① 定的三条：
  1. **AI 必须给依据，不只给标签**——「納婁敬」三个字就是「这是汉典」的依据，
     它同时能直接变成守卫规则；只吐标签的判定**无法沉淀**。
  2. **按置信度分三堆**：≥0.9 批量回填并写成规则；0.5–0.9 只给用户看这一堆；
     <0.5 标「未知」+ UI「歸屬存疑」，不硬归。
  3. **先让可计算的代理信号筛一遍**（共现率、按篇分布、长名接管数、真漏标数），
     AI 只看剩下的。

本脚本只负责第 1 步：把两类待判池导出成机器可读、人也能读的 JSON。

  - `zi`   表字长尾：某人的表字在语料里出现 1–10 次，要不要收进别名
           （`_gen_zi_fill.py` 已用「同句共现率 ≥0.7 且 ≥2 处」自动收了一批，
           收不了的那批在这里）
  - `gen`  泛称 guess 池：裸帝号/王号/爵号在算法层只能 hard-default 兜，
           兜错了就是张冠李戴

判定存在哪儿
------------
**不写在批次文件里**——批次文件每次重生成都会被覆盖。
判定另存 `pipeline/_ai_verdicts.json`（key = 条目 id），本脚本按 id 合并回来。
这样「数据重跑 → 批次刷新」时判定不会丢，也便于 git 追踪判定的变化。

用法
----
    python pipeline/_gen_ai_batch.py                       # 导出全部待判
    python pipeline/_gen_ai_batch.py --kind zi --per 8     # 只看表字，每条 8 个上下文
    python pipeline/_gen_ai_batch.py --gen-top 12          # 泛称只取 guess 最多的 12 个
    python pipeline/_gen_ai_batch.py --unjudged            # 只导出还没判的（续判时用）
    python pipeline/_gen_ai_batch.py --md docs/17-条目-AI复核.md   # 另出人读的清单
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
ZI_PLAN = ROOT / "pipeline" / "_zi_fill_plan.json"
ZI_OK = ROOT / "pipeline" / "_zi_ok.json"
VERDICTS = ROOT / "pipeline" / "_ai_verdicts.json"
BATCH = ROOT / "pipeline" / "_ai_batch.json"
CTX = 14

# 「判定」的取值域——写死在这里，AI 与人都照这个填，避免自由发挥
ACTIONS = {
    "alias": "确认是此人表字/称谓，补进 PERSONS 别名",
    "reject": "确认不是（跨词边界 / 同字他人 / 亲属称谓 / 更长串片段），不收",
    "ctxrule": "泛称：加 GENERIC_CONTEXT_RULES（⓪ 级上下文硬证据）",
    "bookcand": "泛称：收束 GENERIC_BOOK_CANDIDATES（按书限定候选）",
    "default": "泛称：改 GENERIC_DEFAULT 兜底归属",
    "drop": "整串出索引：确认不是人名（爵位/官名/篇名等），从泛称表与别名里摘掉",
    "keep": "现状可接受：抽查无误挂，不动（同样是结论，避免重复劳动）",
    "unknown": "判不了：保留 guess / 转 none，不硬归",
}


# ---------------------------------------------------------------------------
def load_all():
    d = json.loads(BOOK_DATA.read_text(encoding="utf-8"))
    chapters = {c["id"]: c for c in d["chapters"]}
    persons = {p["id"]: p for p in d["persons"]}
    generics = {}
    for g in d.get("genericAliases", []):
        generics[g["alias"]] = g
        for f in g.get("forms", []):
            generics.setdefault(f, g)
    return d, chapters, persons, generics


def clip(text, i, j, ctx=CTX):
    """命中串用【】标出，前后各 ctx 字。"""
    return text[max(0, i - ctx):i] + "【" + text[i:j] + "】" + text[j:j + ctx]


def pinfo(persons, pid):
    p = persons.get(pid)
    if not p:
        return {"pid": pid, "name": "(未收录)", "dynasty": "", "books": []}
    return {"pid": pid, "name": p.get("tradName") or p.get("name") or "",
            "dynasty": p.get("dynasty") or "",
            # books 决定「误挂能不能发生」：限书的人只在指定书内匹配
            # （annotate.py 书作用域），书外的同形串根本不会被他吃掉。
            "books": p.get("books") or []}


# ---------------------------------------------------------------------------
# 表字长尾
# ---------------------------------------------------------------------------
def build_zi(d, chapters, persons, per):
    plan = json.loads(ZI_PLAN.read_text(encoding="utf-8")) if ZI_PLAN.exists() else []
    okfile = json.loads(ZI_OK.read_text(encoding="utf-8")) if ZI_OK.exists() else {}
    ok_ids = {(r["pid"], r["zi"]) for r in (okfile.get("ok") or [])}

    # 该串已被谁登记为别名（**同字他人**是最常见的误收原因）
    alias_of = defaultdict(list)
    for p in d["persons"]:
        for a in p.get("aliases") or []:
            alias_of[a].append(p["id"])

    # 所有已登记的**更长**名（人名本体 + 别名，≥2 字）。
    # 用来检测「待判串是某个更长名的片段」——申**叔時**、王**季思**慮、
    # 博士弟**子治** 都是这类，加进去必然误挂。
    longer = set()
    for p in d["persons"]:
        longer.update(x for x in ([p.get("tradName"), p.get("name")] + (p.get("aliases") or []))
                      if x and len(x) >= 2)

    items = []
    for row in plan:
        pid, zi = row["pid"], row["zi"]
        if (pid, zi) in ok_ids:
            continue          # 共现率闸门已经收了的，不用再判
        p = persons.get(pid)
        if not p:
            continue
        name = p.get("tradName") or p.get("name") or ""
        if not name or not zi:
            continue
        surname, full = name[0], name

        hits, co = [], []
        zi_style = 0        # 「X字Y」句式命中数（最强正信号）
        zi_style_self = 0   # **本人**「全名+字+表字」整串出现（决定性）
        longer_hit = 0      # 命中处是某个更长已登记名的片段
        books = Counter()
        chaps = set()
        my_books = p.get("books") or []
        in_book = out_book = 0
        for s in d["sentences"]:
            t = s.get("text") or ""
            if zi not in t:
                continue
            ch = chapters.get(s["chapterId"], {})
            bk = ch.get("bookId", "?")
            books[bk] += 1
            chaps.add(s["chapterId"])
            if my_books and bk not in my_books:
                out_book += 1
            else:
                in_book += 1
            is_co = (full in t) or ((surname + zi) in t)
            k0 = t.find(zi)
            rec = {"title": ch.get("fullTitle", s["chapterId"]),
                   "ctx": clip(t, k0, k0 + len(zi)),
                   "co": is_co,
                   "book": bk}
            (co if is_co else hits).append(rec)
            # 「字」紧邻在表字前，或「全名+字+表字」整串出现
            k = t.find(zi)
            while k >= 0:
                if k > 0 and t[k - 1] == "字":
                    zi_style += 1
                if t.startswith(full + "字" + zi, max(0, k - len(full) - 1)):
                    zi_style += 1
                    zi_style_self += 1
                if (t[max(0, k - 1): k + len(zi)] in longer
                        or t[k: k + len(zi) + 1] in longer):
                    longer_hit += 1
                k = t.find(zi, k + 1)
        n = len(hits) + len(co)
        if n == 0:
            continue

        # 取样：先给共现的（证明"是"），再给不共现的（暴露跨词边界）
        picked = co[: max(1, per // 2)] + hits[: per - min(len(co), max(1, per // 2))]
        items.append({
            "id": "zi|{}|{}".format(pid, zi),
            "kind": "zi",
            "q": "「{}」是不是{}（{}）的表字？收进别名会不会误挂？".format(
                zi, name, p.get("dynasty") or "?"),
            "surface": zi,
            "person": pinfo(persons, pid),
            "signals": {
                "命中处数": n,
                "同句共现": len(co),
                "共现率": round(len(co) / n, 2),
                "本人字X句式": zi_style_self,
                "他人字X句式": zi_style - zi_style_self,
                "被更长名包含": longer_hit,
                "书内命中": in_book if my_books else n,
                "书外命中": out_book,
                "分布书": dict(books),
                "分布篇数": len(chaps),
                "已被他人登记为别名": [x for x in alias_of.get(zi, []) if x != pid],
            },
            "contexts": picked,
            "ai": None,
        })
    items.sort(key=lambda it: (-it["signals"]["命中处数"], -it["signals"]["共现率"]))
    return items


# ---------------------------------------------------------------------------
# 泛称 guess 池
# ---------------------------------------------------------------------------
def build_generic(d, chapters, persons, generics, top, per):
    forms_of = {}
    for g in d.get("genericAliases", []):
        forms_of.setdefault(g["alias"], set()).update(g.get("forms", []) + [g["alias"]])

    guess = Counter()
    total = Counter()
    for s in d["sentences"]:
        for m in s.get("marks") or []:
            a = m.get("alias")
            if a in forms_of:
                total[a] += 1
                if m.get("tier") == "guess":
                    guess[a] += 1

    items = []
    for alias, gn in guess.most_common(top):
        forms = forms_of[alias]
        # 按书分组：断代史里裸称的含义往往与书绑定（晋书「武帝」≠漢書「武帝」）
        by_book = defaultdict(lambda: {
            "total": 0, "guess": 0, "chapters": set(),
            "byPid": Counter(), "byTier": Counter(),
            "samples": defaultdict(list), "unmarked": 0,
        })
        for s in d["sentences"]:
            ch = chapters.get(s["chapterId"], {})
            bk = ch.get("bookId", "?")
            st = by_book[bk]
            t = s.get("text") or ""
            hit = [m for m in (s.get("marks") or []) if m.get("alias") in forms]
            for m in hit:
                st["total"] += 1
                st["chapters"].add(s["chapterId"])
                st["byPid"][m.get("pid") or "(未标)"] += 1
                st["byTier"][m.get("tier") or "?"] += 1
                if m.get("tier") == "guess":
                    st["guess"] += 1
                st["samples"][m.get("pid") or "(未标)"].append({
                    "title": ch.get("fullTitle", s["chapterId"]),
                    "ctx": clip(t, m.get("s", 0), m.get("e", 0)),
                    "pid": m.get("pid"), "tier": m.get("tier"),
                })
            j = t.find(alias)
            while j >= 0:
                if not any(m.get("s", 0) <= j < m.get("e", 0) for m in (s.get("marks") or [])):
                    st["unmarked"] += 1
                j = t.find(alias, j + 1)

        for bk in sorted(by_book):
            st = by_book[bk]
            if st["total"] == 0:
                continue
            picked = round_robin(st["samples"], per)
            items.append({
                "id": "gen|{}|{}".format(alias, bk),
                "kind": "gen",
                "q": "《{}》里的裸「{}」该归谁？".format(bk, alias),
                "surface": alias,
                "book": bk,
                "default": pinfo(persons, (generics.get(alias) or {}).get("default")),
                "candidates": [pinfo(persons, c)
                               for c in ((generics.get(alias) or {}).get("candidates") or [])],
                "signals": {
                    "总处": st["total"],
                    "guess处": st["guess"],
                    "guess占比": round(st["guess"] / st["total"], 2),
                    "篇数": len(st["chapters"]),
                    "真漏标": st["unmarked"],
                    "归属分布": {k: v for k, v in st["byPid"].most_common()},
                    "tier构成": {k: v for k, v in st["byTier"].most_common()},
                },
                "contexts": picked,
                "ai": None,
            })
    return items


def round_robin(samples_by_pid, per):
    """按 pid 轮转取样——证据不能全落在当前 default 一个人身上。"""
    pids = sorted(samples_by_pid, key=lambda k: -len(samples_by_pid[k]))
    out, i = [], 0
    while len(out) < per:
        added = False
        for pid in pids:
            lst = samples_by_pid[pid]
            if i < len(lst):
                out.append(lst[i])
                added = True
                if len(out) >= per:
                    break
        if not added:
            break
        i += 1
    return out


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="all", choices=["all", "zi", "gen"])
    ap.add_argument("--per", type=int, default=6, help="每条取几个上下文")
    ap.add_argument("--gen-top", type=int, default=10, help="泛称取 guess 最多的几个")
    ap.add_argument("--out", default=str(BATCH))
    ap.add_argument("--verdicts", default=str(VERDICTS))
    ap.add_argument("--unjudged", action="store_true", help="只导出还没判的")
    ap.add_argument("--md", default=None, help="另产出人读的 markdown 清单")
    ap.add_argument("--md-min", type=float, default=0.0, help="md 只列概率 ≤ 该值的")
    a = ap.parse_args()

    d, chapters, persons, generics = load_all()
    items = []
    if a.kind in ("all", "zi"):
        items += build_zi(d, chapters, persons, a.per)
    if a.kind in ("all", "gen"):
        items += build_generic(d, chapters, persons, generics, a.gen_top, a.per)

    # 合并已有判定（按 id）——批次文件重生成时判定不丢
    v = json.loads(Path(a.verdicts).read_text(encoding="utf-8")) \
        if Path(a.verdicts).exists() else {}
    judged = 0
    for it in items:
        if it["id"] in v:
            it["ai"] = v[it["id"]]
            judged += 1
    if a.unjudged:
        items = [it for it in items if not it["ai"]]

    Path(a.out).write_text(json.dumps(
        {"generated": datetime.date.today().isoformat(),
         "actions": ACTIONS, "items": items},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("待判 {} 条（已判 {} 条）→ {}".format(len(items), judged, a.out))
    by_kind = Counter(it["kind"] for it in items)
    print("  分类：{}".format(dict(by_kind)))

    if a.md:
        write_md(items, a.md, a.md_min)
        print("-> {}".format(a.md))


def write_md(items, path, md_min):
    L = ["# AI 判定复核清单", "",
         "> 生成器：`python pipeline/_gen_ai_batch.py --md <路径>`　"
         "生成日期：见文末。",
         "> 这里只列 **AI 判定置信度 ≤ {}** 的条目——高置信的那批已批量回填成规则，"
         "不用人看。".format(md_min),
         "> 每条自带：代理信号（可计算的那部分）+ 原文上下文 + AI 给的判定与依据。",
         "> **依据是重点**：没有依据的判定无法沉淀成守卫规则。",
         "",
         "| # | 条目 | AI 判定 | 概率 | 依据 | 原文上下文 | 你的判定 |",
         "|---:|---|---|---:|---|---|---|"]
    n = 0
    for it in items:
        ai = it.get("ai")
        if ai is None:
            continue
        if ai.get("prob", 0) > md_min:
            continue
        n += 1
        ctxs = " ／ ".join(c["ctx"].replace("|", "｜") for c in it["contexts"][:4])
        L.append("| {} | {} | {} | {} | {} | {} |  |".format(
            n, it["q"], ai.get("target", ""), ai.get("prob", ""),
            (ai.get("evidence") or "").replace("|", "｜"), ctxs))
    L += ["", "---", "",
          "（共 {} 条待复核）".format(n), "",
          "<!-- {} -->".format(datetime.date.today().isoformat())]
    Path(path).write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
