# -*- coding: utf-8 -*-
"""类传/附传覆盖率与缺人候选探针。只读。

为什么需要它
------------
P1-b：类传（儒林/文苑/忠義/孝友/隱逸/藝術/列女/循吏/酷吏…）与合传里的
**从属人物**没有独立传记，词典编目时最容易整批漏掉——他们只在篇内被提到一两次。
本脚本回答两件事：
  1. 这些篇目现在被标注了多少（覆盖率），哪几篇是洼地；
  2. 篇内「没被任何标注覆盖」的高频串里，哪些像人名（缺人候选）。

用法
----
    python pipeline/_probe_class_chapters.py              # 全部类传篇目
    python pipeline/_probe_class_chapters.py --book js    # 只看晋书
    python pipeline/_probe_class_chapters.py --min 3      # 候选至少出现 3 次
    python pipeline/_probe_class_chapters.py --cover 60   # 只列覆盖率 <60% 的篇

产出只用于人工判断与批量入典计划（见 `_gen_persons_fill.py`）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]

# 类传/群体传的篇名关键词（五书通用；四夷传也算——里面有一堆部族首领）
CLASS_KEYS = (
    "儒林", "文苑", "循吏", "良吏", "酷吏", "忠義", "孝友", "隱逸", "逸民",
    "藝術", "方術", "列女", "獨行", "黨錮", "宦者", "貨殖", "游俠", "佞幸",
    "刺客", "滑稽", "日者", "龜策", "外戚", "宗室", "四夷", "夷", "蠻",
    "戎", "狄", "匈奴", "鮮卑", "烏桓", "西域", "東夷", "南蠻", "西羌",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=None)
    ap.add_argument("--min", type=int, default=3, help="候选最少出现次数")
    ap.add_argument("--cover", type=int, default=100, help="只列覆盖率低于该百分比的篇")
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()

    # 人名形态闸复用 `_gen_persons_fill.is_person_name`（同一套姓表/噪声表，
    # 不另抄一份——抄了就会两边漂移）。该模块导入时会读 people.json，稍慢。
    sys.path.insert(0, str(ROOT / "pipeline"))
    try:
        import _gen_persons_fill as gpf
        gate = gpf.is_person_name
    except Exception as exc:            # 闸门不可用时宁可不筛，也不要静默全收
        print("（人名闸门未启用：{}）".format(exc))
        gate = None

    bd = json.loads((ROOT / "data" / "index" / "book-data.json").read_text(encoding="utf-8"))
    chapters = {c["id"]: c for c in bd["chapters"]}
    persons = {p["id"]: p for p in bd["persons"]}
    known = set()
    for p in bd["persons"]:
        known.add(p["name"])
        known.update(p.get("aliases") or [])

    # 1. 类传篇目 + 覆盖率
    targets = {}
    for cid, ch in chapters.items():
        if a.book and ch["bookId"] != a.book:
            continue
        if not any(k in ch["title"] for k in CLASS_KEYS):
            continue
        targets[cid] = ch

    sents_by_ch = defaultdict(list)
    for s in bd["sentences"]:
        cid = s.get("chapterId")
        if cid in targets:
            sents_by_ch[cid].append(s)

    print("类传/群体传篇目 {} 篇\n".format(len(targets)))
    print("| 篇目 | 句 | 有人物句 | 覆盖率 | 已入典人物数 |")
    print("|---|---:|---:|---:|---:|")
    low = []
    for cid in sorted(targets):
        ss = sents_by_ch[cid]
        withp = sum(1 for x in ss if x.get("marks"))
        cov = round(100 * withp / len(ss)) if ss else 0
        pids = {m.get("pid") for x in ss for m in (x.get("marks") or [])}
        ch = targets[cid]
        print("| {} | {} | {} | {}% | {} |".format(
            ch["fullTitle"], len(ss), withp, cov, len(pids)))
        if cov < a.cover:
            low.append(cid)
    print("\n覆盖率 < {}% 的篇：{} 篇".format(a.cover, len(low)))

    # 2. 篇内未标注的高频串（缺人候选）
    cand = Counter()
    sample = {}
    for cid in sorted(targets):
        for s in sents_by_ch[cid]:
            text = s.get("text") or ""
            occ = set()
            for m in s.get("marks") or []:
                for i in range(m.get("s", 0), m.get("e", 0)):
                    occ.add(i)
            # 未覆盖的连续汉字段
            seg, start = "", 0
            for i, chx in enumerate(text + "。"):
                if "一" <= chx <= "鿿" and i not in occ:
                    if not seg:
                        start = i
                    seg += chx
                else:
                    if 2 <= len(seg) <= 3:
                        cand[seg] += 1
                        sample.setdefault(seg, (cid, text[max(0, start - 8):start + 12]))
                    seg = ""

    print("\n篇内未标注高频串（≥{} 次，前 {}）\n".format(a.min, a.top))
    print("| 串 | 次 | 篇目 | 上下文 |")
    print("|---|---:|---|---|")
    n = 0
    for w, c in cand.most_common():
        if c < a.min or n >= a.top:
            continue
        if w in known:
            continue
        if gate and not gate(w):      # 人名形态闸（姓+名 / 非官职非虚词）
            continue
        cid, ctx = sample[w]
        n += 1
        print("| {} | {} | {} | {} |".format(
            w, c, targets[cid]["fullTitle"], ctx.replace("|", "｜")))
    # 3. 传主/附传人物句式：「X字Y」「X，Y人也」「X者，Y人也」
    #    命中而**该处没有任何标注** = 没入典的人（这才是 P1-b 的真缺口）
    print("\n【传主句式未标注】（X字Y / X，Y人也）\n")
    pat_zi = re.compile(r"([一-鿿]{2,3})[，、]?字([一-鿿]{1,2})")
    pat_ren = re.compile(r"([一-鿿]{2,3})(?:者)?[，、]([一-鿿]{2,6}?)人也")
    miss = []
    for cid in sorted(targets):
        for s in sents_by_ch[cid]:
            text = s.get("text") or ""
            occ = set()
            for m in s.get("marks") or []:
                for i in range(m.get("s", 0), m.get("e", 0)):
                    occ.add(i)
            for pat in (pat_zi, pat_ren):
                for mt in pat.finditer(text):
                    i, j = mt.span(1)
                    if any(k in occ for k in range(i, j)):
                        continue                      # 已标注，不缺
                    name = mt.group(1)
                    if name in known:
                        continue                      # 词典里有（可能本篇没命中而已）
                    if gate and not gate(name):
                        continue
                    miss.append((name, mt.group(2), targets[cid]["fullTitle"],
                                 text[max(0, i - 6):j + 10]))
    cnt = Counter(x[0] for x in miss)
    print("| 姓名 | 次 | 字/籍 | 篇目 | 上下文 |")
    print("|---|---:|---|---|---|")
    shown = 0
    for name, c in cnt.most_common():
        if c < a.min or shown >= a.top:
            continue
        zi, title, ctx = next(x[1:] for x in miss if x[0] == name)
        shown += 1
        print("| {} | {} | {} | {} | {} |".format(
            name, c, zi, title, ctx.replace("|", "｜")))
    print("\n候选姓名 {} 个（去重），其中出现 ≥{} 次 {} 个".format(
        len(cnt), a.min, sum(1 for _, c in cnt.items() if c >= a.min)))
    print("\nDONE")


if __name__ == "__main__":
    main()
