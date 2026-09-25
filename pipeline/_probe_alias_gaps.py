# -*- coding: utf-8 -*-
"""系统扫描：三国志主要人物的常见表层写法 vs 词典别名缺口。

对每个 sgz 有人物：
  - 词典 aliases
  - 语料正文中「姓名前2字」类高风险表层：
    字X、X公、X侯、X王、X将军… 用启发式不够稳——
  改为：从 PARTS 高频候选里，用 surname+given 模式 + 常见尊称后缀
  统计「文本里出现但未在 aliases」的专属写法。

更实用做法：
  1) 对每个 sgz 人物，取 tradName 全文出现次数
  2) 若有 title 字段（称号），统计称号在语料出现
  3) 从 summary 抽「字X」
  4) 对 top 80 高命中人物，统计「X公」「X侯」「X王」等
     与其名字共享姓氏的 2-3 字串在语料中频次，且当前 aliases 没有
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
people = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))

# 收集 sgz 语料全文（含注）按卷
corpus = {}
for path in (ROOT / "data/corpus").glob("sgz-*.json"):
    doc = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for p in doc["paragraphs"]:
        parts.append(p.get("text") or "")
        if p.get("note"):
            parts.append(p["note"])
    corpus[path.stem] = "\n".join(parts)
ALL = "\n".join(corpus.values())

# 人物：在 sgz 有命中的
persons = []
for p in bd["persons"]:
    bb = (p.get("byBook") or {}).get("sgz") or {}
    if bb.get("mentionCount", 0) >= 5:
        persons.append(p)
persons.sort(key=lambda x: -((x.get("byBook") or {}).get("sgz") or {}).get("mentionCount", 0))

# 字X 从 summary
ZI = re.compile(r"字([一-鿿]{1,3})")

# 常见尊称/自称后缀（通用，误报要人工看）
SUFFIX = (
    "公", "侯", "王", "將軍", "将军", "丞相", "太尉", "司徒", "司空",
    "太傅", "侍中", "尚書", "尚书", "君", "卿", "明公", "使君",
    "將", "侯", "公",
)

def count_phrase(s: str) -> int:
    if not s:
        return 0
    return ALL.count(s)

rows = []
for p in persons:
    sgz_n = ((p.get("byBook") or {}).get("sgz") or {}).get("mentionCount", 0)
    aliases = set(p.get("aliases") or [])
    aliases.add(p["name"])
    aliases.add(p["tradName"])
    # 简体也在（匹配用繁简，缺口看繁体正文）
    title = (p.get("title") or "").strip()
    summary = p.get("summary") or ""
    zi_m = ZI.search(summary)
    zi = zi_m.group(1) if zi_m else ""
    trad = p["tradName"]
    # 姓（取 trad 首1-2字，复姓可能2字）
    # 已知复姓
    compound = (
        "皇甫", "司馬", "司马", "諸葛", "诸葛", "夏侯", "欧阳", "歐陽",
        "鐘離", "鐘離", "令狐", "上官", "東方", "南宮",
    )
    surname = trad[:2] if any(trad.startswith(c) for c in compound) else trad[0]
    # 候选表层
    cands = []
    # 字
    if zi:
        cands.append(zi)
        cands.append(surname + zi if len(surname) == 1 else trad)
    # title 整串（若像称号）
    if title and title not in aliases and len(title) <= 6:
        cands.append(title)
    # 姓+常见
    for s in ("公", "侯", "王", "將軍", "将军", "丞相", "明公", "使君"):
        cands.append(surname + s)
    # 名字中的常见组合：全名已算
    # 魏武帝类 title 里没有的：从特殊表
    # 去重
    seen = set()
    gaps = []
    for c in cands:
        if not c or c in seen or c in aliases:
            continue
        seen.add(c)
        # 与本人相关性：含姓 或 是字 或 是 title
        related = (
            c == zi
            or c == title
            or (surname and c.startswith(surname) and len(c) <= 5)
            or c == trad
        )
        if not related:
            continue
        n = count_phrase(c)
        if n >= 8:  # 阈值
            # 过滤：若 c 是全名则已有
            gaps.append((c, n))

    # 字 单独高频
    if zi and zi not in aliases:
        n = count_phrase(zi)
        if n >= 8 and (zi, n) not in gaps:
            # 字可能重名，仍列出
            gaps.append((zi, n))

    # 算法缺口：title 在语料多但不在 aliases
    if title and title not in aliases:
        n = count_phrase(title)
        if n >= 10:
            if (title, n) not in gaps:
                gaps.append((title, n))

    if gaps:
        gaps.sort(key=lambda x: -x[1])
        rows.append((p, sgz_n, zi, title, gaps[:8]))

print(f"sgz 命中≥5 的人物: {len(persons)}；有明显表层缺口: {len(rows)}\n")
print("=== 缺口最大 TOP 30（按最高频表层）===")
rows.sort(key=lambda r: -max(g[1] for g in r[4]))
for p, sgz_n, zi, title, gaps in rows[:30]:
    gtxt = ", ".join(f"{c}×{n}" for c, n in gaps[:6])
    print(
        f"  {p['tradName']:8} sgz={sgz_n:4} 字={zi or '-':4} "
        f"title={title or '-':6} 缺: {gtxt}"
    )

print("\n=== 分类汇总：title 是官名却在语料高频、却不在 aliases ===")
office_re = re.compile(
    r"(丞相|太尉|司徒|司空|太傅|侍中|太常|將軍|将军|尚書|尚书|太守|刺史|牧)"
)
n_title_gap = 0
examples = []
for p in bd["persons"]:
    bb = (p.get("byBook") or {}).get("sgz") or {}
    if bb.get("mentionCount", 0) < 5:
        continue
    title = (p.get("title") or "").strip()
    aliases = set(p.get("aliases") or [])
    if not title or title in aliases:
        continue
    if not office_re.search(title) and not title.endswith("公") and not title.endswith("侯"):
        continue
    n = count_phrase(title)
    if n >= 15:
        n_title_gap += 1
        if len(examples) < 25:
            examples.append((p["tradName"], title, n, "title" in aliases or title in aliases))
print(f"  共 {n_title_gap} 人（例）")
for name, title, n, _ in examples:
    print(f"    {name:8} title={title:10} 语料×{n}（title 不进匹配）")

print("\n=== 字X 单字/双字不在词典、语料≥10 ===")
zi_gaps = []
for p in persons:
    zi = ZI.search(p.get("summary") or "")
    if not zi:
        continue
    z = zi.group(1)
    aliases = set(p.get("aliases") or [])
    if z in aliases or p["tradName"] in aliases and z in p["tradName"]:
        continue
    # 全名含字则 skip（名字就是字很少见）
    if z == p["tradName"] or z == p["name"]:
        continue
    n = count_phrase(z)
    if n >= 15:
        zi_gaps.append((p["tradName"], z, n))
zi_gaps.sort(key=lambda x: -x[2])
for name, z, n in zi_gaps[:25]:
    print(f"  {name:8} 字 {z:4} ×{n}")

print("\n=== 与曹操同型：别名≤2 且 sgz 命中≥20 ===")
thin = []
for p in persons:
    sgz_n = ((p.get("byBook") or {}).get("sgz") or {}).get("mentionCount", 0)
    al = p.get("aliases") or []
    if sgz_n >= 20 and len(al) <= 3:
        thin.append((p, sgz_n, al))
thin.sort(key=lambda x: -x[1])
for p, n, al in thin[:40]:
    print(f"  {p['tradName']:8} sgz={n:4} aliases={al} title={p.get('title')}")
print(f"\n合计 thin: {len(thin)} / 命中≥5: {len(persons)}")
