# -*- coding: utf-8 -*-
"""对比 sj/hs/hhs/sgz：人物别名密度、title 不匹配、字X 缺口。"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
ZI = re.compile(r"字([一-鿿]{1,3})")
OFFICE = re.compile(
    r"(丞相|太尉|司徒|司空|太傅|侍中|太常|將軍|将军|尚書|尚书|太守|刺史|牧|太師|太师)"
)


def stats(book):
    persons = [p for p in bd["persons"] if ((p.get("byBook") or {}).get(book) or {}).get("mentionCount", 0) >= 5]
    if not persons:
        return
    al_lens = [len(p.get("aliases") or []) for p in persons]
    thin = sum(1 for n in al_lens if n <= 2)
    # title in office but not in aliases
    title_gap = 0
    zi_gap = 0
    has_zi = 0
    for p in persons:
        aliases = set(p.get("aliases") or [])
        aliases.add(p["name"])
        aliases.add(p["tradName"])
        title = (p.get("title") or "").strip()
        if title and title not in aliases and OFFICE.search(title):
            title_gap += 1
        m = ZI.search(p.get("summary") or "")
        if m:
            has_zi += 1
            z = m.group(1)
            if z not in aliases and z != p["tradName"] and len(z) >= 2:
                # 双字未收
                if z not in "".join(aliases):
                    zi_gap += 1
    print(
        f"{book}: 命中≥5 {len(persons):4}  "
        f"别名均长 {sum(al_lens)/len(al_lens):.2f}  "
        f"薄别名≤2 {thin:4} ({thin/len(persons):.0%})  "
        f"title官名缺口 {title_gap:3}  "
        f"双字未收 {zi_gap:3}/{has_zi}"
    )
    # 命中 top5
    top = sorted(persons, key=lambda p: -((p.get("byBook") or {}).get(book) or {}).get("mentionCount", 0))[:5]
    print(
        "  top:",
        ", ".join(
            f"{p['tradName']}×{((p.get('byBook') or {}).get(book) or {}).get('mentionCount')}[al={len(p.get('aliases') or [])}]"
            for p in top
        ),
    )


for b in ("sj", "hs", "hhs", "sgz"):
    stats(b)

# 生成来源注释：是否 _gen_ 自动
src = (ROOT / "pipeline" / "build_dict.py").read_text(encoding="utf-8")
print("\nbuild_dict 生成标记:")
for line in src.splitlines():
    if "自动生成" in line or "_gen_" in line or "PERSONS.extend" in line:
        if "自动" in line or "extend" in line or "_gen_" in line:
            print(" ", line.strip()[:120])
