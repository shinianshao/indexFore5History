# -*- coding: utf-8 -*-
"""R1 诊断：仲達/司馬懿/宣帝 为何漏召。只读。"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ppl = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))

# 1) 谁声明了 仲達 / 司馬懿 / 宣帝
want = ["仲達", "仲达", "司馬懿", "司马懿", "宣帝", "司馬仲達", "晋宣帝", "晉宣帝", "子元", "子上"]
print("=== 别名声明 ===")
for p in ppl["persons"]:
    hits = [a for a in (p.get("aliases") or []) if a in want]
    if hits or p.get("tradName") in ("司馬懿", "庞参", "龐參", "p_pangcan", "p_simayi"):
        print(p["id"], p.get("tradName"), "books=", p.get("books"), "aliases=", p.get("aliases"))

# 2) generic 宣帝
print("\n=== generic 宣帝 ===")
for g in ppl.get("genericAliases") or []:
    if g.get("alias") == "宣帝":
        print(g)

# 3) 语料上下文
print("\n=== sgz 正文 仲達/司馬懿 上下文 ===")
ctx_re = re.compile(r".{0,12}(?:仲達|司馬懿|司馬仲達|宣帝).{0,12}")
for fp in sorted((ROOT / "data/corpus").glob("sgz-*.json")):
    doc = json.loads(fp.read_text(encoding="utf-8"))
    for i, para in enumerate(doc.get("paragraphs") or []):
        t = para.get("text") or ""
        if "仲達" in t or "司馬懿" in t or "司馬仲達" in t:
            for m in ctx_re.finditer(t):
                print(f"{doc['chapterId']}#{i}: …{m.group()}…")

# 4) 产物 aliasList
print("\n=== 产物 aliasList ===")
for p in bd["persons"]:
    if p.get("tradName") in ("司馬懿", "龐參", "庞参", "劉詢", "司马懿"):
        print(p["id"], p.get("tradName"), "byBook", p.get("byBook"), "mention", p.get("mentionCount"))
        for a in p.get("aliasList") or []:
            print(" ", a.get("w"), "n=", a.get("n"), a.get("byBook"))

# 5) marks 里有没有仲達
print("\n=== sentences marks 含 仲達 ===")
n = 0
for s in bd["sentences"]:
    for m in s.get("marks") or []:
        if m.get("alias") in ("仲達", "司馬懿", "司馬仲達") or m.get("w") in ("仲達", "司馬懿"):
            n += 1
            if n <= 15:
                print(s.get("chapterId"), m, s.get("text", "")[:40])
print("total marks", n)

print("\nDONE")
