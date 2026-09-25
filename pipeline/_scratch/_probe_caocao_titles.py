# -*- coding: utf-8 -*-
"""只读：曹操在正文/裴注两侧的别名与命中是否齐全。"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
pei = json.loads((ROOT / "data/index/pei-data.json").read_text(encoding="utf-8"))
people = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))

PID = "p_caocao"
p = next(x for x in bd["persons"] if x["id"] == PID)
print("=== 词典 / 正文产物里的曹操 ===")
print("name", p["name"], p["tradName"], "dyn", p.get("dynasty"), "title", p.get("title"))
print("books", p.get("books"))
print("aliases", p.get("aliases"))
print("aliasList kinds:")
for a in p.get("aliasList") or []:
    print(" ", a.get("kind"), a.get("w"), "n=", a.get("n"), "byBook=", a.get("byBook"))
print("mentionCount", p.get("mentionCount"), "chapters", p.get("mentionChapterCount"))
print("byBook", p.get("byBook"))

# 正文 sgz 标记按 alias
core = Counter()
tiers = Counter()
for s in bd["sentences"]:
    if not s["chapterId"].startswith("sgz-"):
        continue
    for m in s.get("marks") or []:
        if m.get("pid") != PID:
            continue
        core[m.get("alias")] += 1
        tiers[m.get("tier")] += 1
print("\n=== 三国志正文曹操命中按写法 ===")
for a, n in core.most_common():
    print(f"  {n:4} {a!r}")
print(" tiers", dict(tiers), "total", sum(core.values()))

# 裴注
print("\n=== 裴注曹操 ===")
pei_p = (pei.get("persons") or {}).get(PID)
if not pei_p:
    print(" 裴注无 p_caocao")
else:
    print(" n", pei_p.get("n"), "chapters", pei_p.get("chapters"))
    print(" aliases", pei_p.get("aliases"))
    print(" byChapter top", sorted((pei_p.get("byChapter") or {}).items(), key=lambda x: -x[1])[:8])

# 词典 source of caocao entry in build_dict
src = (ROOT / "pipeline" / "build_dict.py").read_text(encoding="utf-8")
for line in src.splitlines():
    if 'p_caocao"' in line and line.strip().startswith('("'):
        print("\nbuild_dict:", line.strip()[:200])

# 常见曹操称号是否在 aliases / 命中里
CANDIDATES = [
    "曹公", "孟德", "魏公", "魏王", "武帝", "魏武帝", "太祖", "武皇帝",
    "曹丞相", "丞相", "操", "阿瞞", "阿瞒", "吉利", "孫子", "亂世之梟雄",
    "治世之能臣", "漢相國", "相國", "武王", "曹公操", "魏太祖",
    "太皇帝", "高皇帝", "曹孟德", "德祖",
]
alias_set = set(p.get("aliases") or [])
alias_set.add(p["name"])
alias_set.add(p["tradName"])
print("\n=== 常见称号是否进词典别名 ===")
for c in CANDIDATES:
    # 繁简都可能
    hits = [c]  # 用户候选本身
    in_dict = any(c in a or a in c for a in alias_set if len(a) >= 1 and (a == c or c in a or a in c))
    # 更简单：精确或双向包含
    in_dict = c in alias_set or any(a == c for a in alias_set)
    body_n = core.get(c, 0)
    # 繁体正文可能写法
    # 统计正文/裴注里这些表面形式出现次数（不限 pid）
    print(f"  {c!r:12} 词典={'Y' if in_dict else 'N'}  正文归操={body_n}")

# 正文里以这些表面形式出现、但归了别人或未归的抽样
print("\n=== 正文里这些表面出现过但未全归曹操 ===")
surface_all = Counter()
surface_caocao = Counter()
for s in bd["sentences"]:
    if not s["chapterId"].startswith("sgz-"):
        continue
    for m in s.get("marks") or []:
        a = m.get("alias") or ""
        if a in CANDIDATES or a in ("曹公", "孟德", "魏公", "魏王", "操", "阿瞞", "阿瞒", "曹孟德", "魏武帝", "太祖"):
            surface_all[a] += 1
            if m.get("pid") == PID:
                surface_caocao[a] += 1
for a, n in surface_all.most_common(30):
    print(f"  {a!r:10} 总命中={n:4} 归曹操={surface_caocao.get(a,0):4} 缺口={n - surface_caocao.get(a,0)}")

# 词典 people.json generic / scoped 涉及曹
print("\n=== people.json 中含曹公/孟德/魏王 的声明 ===")
for x in people["persons"]:
    al = " ".join([x["name"], x["tradName"]] + (x.get("aliases") or []))
    for key in ("曹公", "孟德", "魏公", "阿瞞", "阿瞒", "曹孟德", "武帝", "太祖", "魏王"):
        if key in al:
            print(f"  {x['id']} {x['tradName']} 含 {key} books={x.get('books')} aliases={x.get('aliases')[:12]}")
