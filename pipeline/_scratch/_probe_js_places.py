# -*- coding: utf-8 -*-
"""R4：从晋书地理志提取郡县，筛后生成待补清单。只读。"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
places = bd.get("places") or []
known = set()
for p in places:
    for a in (p.get("aliases") or []) + [p.get("name"), p.get("tradName")]:
        if a:
            known.add(a)

# 人物名占用
person_names = set()
for p in bd["persons"]:
    for a in (p.get("aliases") or []) + [p.get("name"), p.get("tradName")]:
        if a and len(a) >= 2:
            person_names.add(a)

blob = []
for s in ("014", "015"):
    d = json.loads((ROOT / f"data/corpus/js-{s}.json").read_text(encoding="utf-8"))
    for p in d.get("paragraphs") or []:
        blob.append(p.get("text") or "")
text = "\n".join(blob)

# 郡名：XX郡
jun = Counter(re.findall(r"([一-鿿]{2,4})郡", text))
# 縣名：紧跟「統縣N，」后的名单——粗提 2–4 字地名后接 統縣 / 戶 / 〈
# 更稳：从「統縣N：」式与顿号分隔的清单
# 简化：扫 「縣」 前 2-4 字
xian = Counter()
for m in re.finditer(r"([一-鿿]{2,3})縣", text):
    xian[m.group(1)] += 1
# 顿号分隔的县名单（地理志体例：高陵……陽陵……）
for seg in re.findall(r"(?:統縣[一二三四五六七八九十]+[，、]?)([^〈〉]{5,80})", text):
    for name in re.split(r"[、，。\s〈〉]+", seg):
        if 2 <= len(name) <= 3 and re.fullmatch(r"[一-鿿]{2,3}", name):
            xian[name] += 1

print("=== 未收录 郡 top ===")
n = 0
for name, c in jun.most_common():
    if name in known or name in person_names or c < 1:
        continue
    if len(name) < 2:
        continue
    print(f"  {name}郡 ×{c}")
    n += 1
    if n >= 25:
        break

print("=== 未收录 县候选 top（≥2 次）===")
n = 0
for name, c in xian.most_common():
    if name in known or name in person_names or c < 2:
        continue
    if len(name) < 2:
        continue
    # 排官职/常用词
    if name in ("統縣", "諸縣", "屬縣", "郡縣", "州縣"):
        continue
    print(f"  {name} ×{c}")
    n += 1
    if n >= 40:
        break

print("\nDONE")
