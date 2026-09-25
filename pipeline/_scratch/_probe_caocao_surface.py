# -*- coding: utf-8 -*-
"""量曹操常见称号在 sgz 正文+裴注中的表面频次（不限归属）。"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
pei = json.loads((ROOT / "data/index/pei-data.json").read_text(encoding="utf-8"))
corpus = ROOT / "data/corpus"

# 标题里常见表层
CANDS = [
    "曹公", "孟德", "曹孟德", "魏公", "魏王", "太祖", "武皇帝", "魏武帝",
    "武帝", "阿瞞", "阿瞒", "丞相", "相國", "相国", "操", "公", "明公",
    "明上", "大王", "王上", "陛下", "魏王操", "曹公操",
]

# 从语料正文+注里数表面（不算匹配）
surf = Counter()
pei_surf = Counter()
for path in sorted(corpus.glob("sgz-*.json")):
    doc = json.loads(path.read_text(encoding="utf-8"))
    full = []
    for para in doc["paragraphs"]:
        t = para.get("text") or ""
        full.append(t)
        n = para.get("note") or ""
        if n:
            full.append(n)
    blob = "\n".join(full)
    for c in CANDS:
        n = blob.count(c)
        if n:
            surf[c] += n
    # 裴注：note 字段或 〈〉
    notes = []
    for para in doc["paragraphs"]:
        notes.append(para.get("note") or "")
    nblob = "\n".join(notes)
    for c in CANDS:
        n = nblob.count(c)
        if n:
            pei_surf[c] += n

print("=== sgz 语料表面频次（正文 text 含〈〉 + note）===")
for c, n in surf.most_common():
    print(f"  {n:5} {c!r}")

print("\n=== 其中出现在裴注 note 里的 ===")
for c, n in pei_surf.most_common():
    print(f"  {n:5} {c!r}")

# 正文标记归曹操 vs 表面（曹操专属别名）
print("\n=== 已归 p_caocao 的标记（按别名）===")
by = Counter()
for s in bd["sentences"]:
    if not s["chapterId"].startswith("sgz-"):
        continue
    for m in s.get("marks") or []:
        if m["pid"] == "p_caocao":
            by[m["alias"]] += 1
print(dict(by))

# 曹公 全文出现后抽 3 例上下文（确认是否多为曹操）
print("\n=== 「曹公」上下文抽样（每卷最多1条）===")
shown = 0
for path in sorted(corpus.glob("sgz-*.json")):
    doc = json.loads(path.read_text(encoding="utf-8"))
    for para in doc["paragraphs"]:
        t = para.get("text") or ""
        i = t.find("曹公")
        if i < 0:
            continue
        print(f"  {path.stem}: …{t[max(0,i-10):i+16]}…")
        shown += 1
        break
    if shown >= 8:
        break

print("\n=== 「孟德」上下文抽样 ===")
shown = 0
for path in sorted(corpus.glob("sgz-*.json")):
    doc = json.loads(path.read_text(encoding="utf-8"))
    for para in doc["paragraphs"]:
        t = para.get("text") or ""
        i = t.find("孟德")
        if i < 0:
            continue
        print(f"  {path.stem}: …{t[max(0,i-10):i+16]}…")
        shown += 1
        break
    if shown >= 6:
        break

# 词典当前
p = next(x for x in bd["persons"] if x["id"] == "p_caocao")
print("\n词典 aliases:", p["aliases"])
print("title field:", p["title"])
