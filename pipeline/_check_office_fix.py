# -*- coding: utf-8 -*-
"""检查官名剥离 + PERSON_BOOKS_SJ + 啟守卫是否到位。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = (ROOT / "pipeline" / "build_dict.py").read_text(encoding="utf-8")
AN = (ROOT / "pipeline" / "annotate.py").read_text(encoding="utf-8")

OFFICE = {
    "丞相", "司徒", "司空", "太尉", "太傅", "太保", "侍中", "太常",
    "光祿勳", "衛尉", "大司農", "大鴻臚", "大司馬", "大將軍",
    "車騎將軍", "驃騎將軍", "衛將軍", "尚書令", "中書令", "廷尉",
    "司隸校尉", "太僕", "御史大夫", "尚書", "大司农", "大将军",
    "车骑将军", "骠骑将军", "卫将军", "尚书令", "中书令", "太傅",
}

print("PERSON_BOOKS_SJ defined:", "PERSON_BOOKS_SJ" in BD)
print("main hooks SJ:", "PERSON_BOOKS_SJ[pid]" in BD)
print("p_qi entry:")
for line in BD.splitlines():
    if re.match(r'\s*\("p_qi"', line):
        print(" ", line.strip())

remain = []
for line in BD.splitlines():
    if not re.match(r'\s*\("p_', line):
        continue
    m = re.search(r"\[([^\]]*)\]", line)
    if not m:
        continue
    parts = re.findall(r'"([^"]+)"', m.group(1))
    bad = [p for p in parts if p in OFFICE]
    if bad:
        remain.append((line.strip()[:130], bad))
print(f"\nremaining bare-office person lines: {len(remain)}")
for s, b in remain:
    print(" ", b, s)

print("\nannotate SINGLE_CHAR_PRE 啟:", bool(re.search(r'"啟"\s*:\s*set\(', AN)))
# show 啟 entry snippet
m = re.search(r'"啟":\s*set\([^\)]*\)', AN)
print("snippet:", (m.group(0)[:120] + "...") if m else "MISSING")

# sample known offenders
for pid in ("p_guyyong", "p_sunlin", "p_jiangji", "p_zhugeke", "p_qi"):
    for line in BD.splitlines():
        if f'"{pid}"' in line and line.strip().startswith('("'):
            print("sample", line.strip()[:140])
            break
