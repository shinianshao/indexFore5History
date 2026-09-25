# -*- coding: utf-8 -*-
"""全书系统排查：帝号/王号/谥号/庙号类错挂、跨书误归、子串误配。只读。"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
ppl = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
by_id = {p["id"]: p for p in bd["persons"]}
dict_by = {p["id"]: p for p in ppl["persons"]}

TITLEY = re.compile(
    r"^(.{1,2})(帝|王|公|侯|后|太后|皇后|皇帝|世祖|太祖|太宗|高祖|烈祖|中宗|世宗|孝武|孝惠|孝文|孝景|孝宣)$"
)
BOOKS = ("sj", "hs", "hhs", "sgz", "js")

print("=== 1. 裸帝号/王号/庙号仍在单人 core（应泛称）===")
generic_forms = set()
for g in ppl.get("genericAliases") or []:
    for f in g.get("forms") or ():
        generic_forms.add(f)

core_titley = []
for p in ppl["persons"]:
    books = p.get("books") or []
    for a in p.get("aliases") or []:
        if a in generic_forms:
            continue
        if TITLEY.match(a) or a in (
            "武帝", "文帝", "惠帝", "元帝", "成帝", "明帝", "哀帝", "安帝", "恭帝",
            "宣帝", "景帝", "孝武帝", "孝惠", "高祖", "太祖", "太宗", "中宗",
            "世祖", "世宗", "烈祖", "文王", "武王", "周公", "齊王", "楚王", "梁王",
        ):
            core_titley.append((p["id"], p.get("tradName"), a, books, p.get("dynasty")))
for row in core_titley:
    print(" ", row)

print("\n=== 2. 同一裸称号被多书高频命中且归属单一（跨书疑错）===")
# alias → pid counts per book
for alias in (
    "武帝", "文帝", "惠帝", "元帝", "成帝", "明帝", "孝武帝", "高祖", "太祖",
    "宣帝", "景帝", "文王", "武王", "周公", "齊王", "梁王", "楚王", "趙王",
    "燕王", "秦王", "漢王", "吳王", "代王",
):
    hits = defaultdict(Counter)  # book -> pid
    for s in bd["sentences"]:
        book = s.get("chapterId", "").split("-")[0]
        for m in s.get("marks") or []:
            if m.get("alias") == alias:
                hits[book][m.get("pid")] += 1
    if not hits:
        continue
    parts = []
    for b in BOOKS:
        if b in hits:
            top = hits[b].most_common(3)
            parts.append(f"{b}:" + ",".join(f"{by_id.get(p, {}).get('name', p) or p}×{n}" for p, n in top))
    print(f"  {alias} → " + " | ".join(parts))

print("\n=== 3. 汉/周人物在 js 侧高命中（疑晋书误归）===")
for p in bd["persons"]:
    dyn = (dict_by.get(p["id"]) or {}).get("dynasty") or p.get("dynasty") or ""
    if dyn in ("西汉", "东汉", "西周", "商", "春秋", "战国"):
        js = ((p.get("byBook") or {}).get("js") or {}).get("mentionCount") or 0
        if js >= 30:
            print(f"  {p.get('tradName')}({dyn}) js={js} aliases={p.get('aliases')[:6]}")

print("\n=== 4. 子串误配：短称号嵌在长王号里 ===")
# find marks where alias is short and surrounded by title chars
surround = Counter()
for s in bd["sentences"]:
    t = s.get("text") or ""
    for m in s.get("marks") or []:
        a = m.get("alias") or ""
        if len(a) < 2 or len(a) > 3:
            continue
        if a not in ("文王", "武王", "周公", "梁王", "楚王", "齊王", "趙王", "燕王", "吳王"):
            continue
        i, j = m.get("s", 0), m.get("e", 0)
        pre = t[i - 1] if i > 0 else ""
        post = t[j] if j < len(t) else ""
        if pre in "章元成宣平景武文哀沖質桓靈獻懷愍安恭簡孝烈順穆敬僖昭襄匡定惠" or post in "公侯":
            surround[(a, pre + "|" + post, m.get("pid"))] += 1
print("  短称号带前后缀 top:")
for k, n in surround.most_common(20):
    print(" ", n, k)

print("\n=== 5. 泛称 default 落在书外（应 none 或换人）===")
for g in ppl.get("genericAliases") or []:
    d = g.get("default")
    if not d:
        continue
    dd = dict_by.get(d) or {}
    books = dd.get("books") or []
    # 非默认的其它候选
    print(f"  {g['alias']}: default={dd.get('tradName', d)} books={books} cands={[dict_by.get(c, {}).get('tradName', c) for c in g.get('candidates') or []]}")

print("\nDONE")
