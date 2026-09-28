# -*- coding: utf-8 -*-
"""补充探针：泛称、疑似漏召、残余官名共用、有若。只读。"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
ppl = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
meta = bd["meta"]

print("=== meta.tierStat / generic ===")
print("tierStat:", meta.get("tierStat"))
print("genericAliasCount", meta.get("genericAliasCount"),
      "genericMarks", meta.get("genericMarks"),
      "genericConfident", meta.get("genericConfident"))

# person titles structure
p0 = next(p for p in bd["persons"] if p.get("aliasList"))
print("aliasList sample keys", p0["aliasList"][0].keys() if p0.get("aliasList") else None)
# find person with titles-like field
for k in ("titles", "titleStat", "genericTitles"):
    hits = [p for p in bd["persons"] if p.get(k)]
    print(k, len(hits))

# genericAliases sample
ga = bd.get("genericAliases") or []
print("genericAliases n", len(ga), "sample", ga[:2])

print("\n=== 司馬懿 / 宣帝 / 仲達 表面频次 vs 归属 ===")
# scan corpus sgz for surfaces
corpus = ROOT / "data/corpus"
surfaces = ["司馬懿", "司马懿", "仲達", "仲达", "宣帝", "晉宣帝", "晋宣帝", "太傅懿", "司馬仲達"]
for book in ("sgz", "hhs"):
    freq = Counter()
    for fp in sorted(corpus.glob(f"{book}-*.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        paras = data.get("paragraphs") or []
        texts = []
        for para in paras:
            t = para.get("text") if isinstance(para, dict) else str(para)
            note = para.get("note") if isinstance(para, dict) else ""
            texts.append(t or "")
            if note:
                texts.append(note)
        blob = "\n".join(texts)
        for s in surfaces:
            freq[s] += blob.count(s)
    print(book, dict(freq))

# byBook for simayi family
for name in ("司馬懿", "司馬師", "司馬昭", "司馬炎", "諸葛亮", "諸葛瑾", "諸葛瞻", "龐統", "法正", "黃忠", "趙雲", "馬超", "張飛", "關羽", "許褚", "典韋", "夏侯惇", "夏侯淵", "張遼", "徐晃", "張郃", "于禁", "樂進", "李典"):
    p = next((x for x in bd["persons"] if x.get("tradName") == name or x.get("name") == name), None)
    if not p:
        print(f"  {name}: MISSING FROM INDEX")
        continue
    bb = {k: v.get("mentionCount") for k, v in (p.get("byBook") or {}).items() if v and v.get("mentionCount")}
    print(f"  {name}: al={p.get('aliases')} books={p.get('books')} byBook={bb}")

print("\n=== 有若/有子 当前 ===")
for name in ("有若", "有子", "有若氏"):
    p = next((x for x in bd["persons"] if x.get("tradName") == name or x.get("name") == name or name in (x.get("aliases") or [])), None)
    if p:
        bb = {k: v.get("mentionCount") for k, v in (p.get("byBook") or {}).items() if v and v.get("mentionCount")}
        print(name, p["id"], p.get("tradName"), p.get("aliases"), bb, "total", p.get("mentionCount"))

print("\n=== 字缺口 TOP（hhs/sgz 命中≥10 且双字字未进 aliases）===")
ZI = re.compile(r"字([一-鿿]{2,3})")
for book in ("sj", "hs", "hhs", "sgz"):
    rows = []
    for p in bd["persons"]:
        n = ((p.get("byBook") or {}).get(book) or {}).get("mentionCount", 0)
        if n < 10:
            continue
        m = ZI.search(p.get("summary") or "")
        if not m:
            continue
        z = m.group(1)
        aliases = set(p.get("aliases") or []) | {p.get("name"), p.get("tradName")}
        if z not in aliases and z not in "".join(aliases):
            rows.append((n, p["tradName"], z, p.get("aliases")))
    rows.sort(reverse=True)
    print(f"{book}: {len(rows)}")
    for r in rows[:15]:
        print(" ", r)

print("\n=== 残余官名共用别名明细 ===")
alias_to = defaultdict(set)
for p in ppl["persons"]:
    for a in p.get("aliases") or []:
        if a:
            alias_to[a].add(p["id"])
id2 = {p["id"]: p for p in ppl["persons"]}
for a, pids in sorted(alias_to.items()):
    if len(pids) < 2:
        continue
    if re.search(r"(將軍|将军|大司馬|大司马|太傅|太尉|司徒|司空|丞相|尚書|尚书|侍中|州牧|牧$)", a):
        names = [id2[p].get("tradName") for p in sorted(pids)]
        print(f"  {a!r} → {names}")

print("\n=== 高命中但 aliases=0/1（漏尊称）hhs/sgz ===")
for book in ("hhs", "sgz"):
    rows = []
    for p in bd["persons"]:
        n = ((p.get("byBook") or {}).get(book) or {}).get("mentionCount", 0)
        if n >= 15 and len(p.get("aliases") or []) <= 1:
            rows.append((n, p["tradName"], p.get("aliases"), p.get("title")))
    rows.sort(reverse=True)
    print(book, len(rows))
    for r in rows[:15]:
        print(" ", r)

print("\n=== 篇主：hhs 空篇主分类 ===")
for b in ("sj", "hs", "hhs", "sgz"):
    empty = [c for c in bd["chapters"] if c.get("bookId") == b and not c.get("mainPersons")]
    cats = Counter(c.get("category") for c in empty)
    print(b, dict(cats), "total", len(empty))

print("\nDONE2")
