# -*- coding: utf-8 -*-
"""R3b 载记专项探针：篇主、漏人、王号。只读。"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v = json.loads((ROOT / "data/dict/volumes/js.json").read_text(encoding="utf-8"))
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
by_id = {p["id"]: p for p in bd["persons"]}

print("=== 载记 121-130 开头 ===")
for n in range(121, 131):
    s = "{:03d}".format(n)
    d = json.loads((ROOT / f"data/corpus/js-{s}.json").read_text(encoding="utf-8"))
    t = "".join(p.get("text") or "" for p in (d.get("paragraphs") or [])[:3])
    print(s, v[s], "…", t[:90].replace("\n", " "))

print("\n=== 载记密度与篇主 ===")
for n in range(101, 131):
    s = "{:03d}".format(n)
    sents = [x for x in bd["sentences"] if x.get("chapterId") == "js-" + s]
    withp = sum(1 for x in sents if x.get("persons"))
    ch = next(c for c in bd["chapters"] if c["id"] == "js-" + s)
    owners = [by_id.get(p, {}).get("name", p) for p in ch.get("mainPersons") or []]
    print(f"{s} {v[s][:18]:18} sents={len(sents):4} withp={withp:4} owners={owners}")

CAND = re.compile(r"([一-鿿]{2,3})(?=曰|云)")
freq = Counter()
for s in bd["sentences"]:
    cid = s.get("chapterId") or ""
    if not cid.startswith("js-"):
        continue
    num = int(cid.split("-")[1])
    if not (101 <= num <= 130):
        continue
    t = s.get("text") or ""
    occ = set()
    for m in s.get("marks") or []:
        for i in range(m["s"], m["e"]):
            occ.add(i)
    for m in CAND.finditer(t):
        name = m.group(1)
        if any(i in occ for i in range(m.start(), m.end())):
            continue
        freq[name] += 1
print("\n载记未标注 X曰 top30:")
for n, c in freq.most_common(30):
    print(f"  {n} ×{c}")

print("\n载记 marks tier/alias top:")
guess = Counter()
for s in bd["sentences"]:
    cid = s.get("chapterId") or ""
    if not cid.startswith("js-"):
        continue
    num = int(cid.split("-")[1])
    if not (101 <= num <= 130):
        continue
    for m in s.get("marks") or []:
        guess[(m.get("tier"), m.get("alias"), m.get("pid"))] += 1
for (tier, a, p), n in guess.most_common(30):
    nm = by_id.get(p, {}).get("name", p)
    print(f"  {tier:8} {a}→{nm} ×{n}")

print("\nDONE")
