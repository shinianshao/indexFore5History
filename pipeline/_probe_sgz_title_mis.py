# -*- coding: utf-8 -*-
"""只读探针：sgz 官名/称号错配 + 「启」归属。"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
people = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
chapters = {c["id"]: c for c in bd["chapters"]}
persons = {p["id"]: p for p in bd["persons"]}
by_trad = {}
for p in bd["persons"]:
    by_trad.setdefault(p["tradName"], []).append(p["id"])
    by_trad.setdefault(p["name"], []).append(p["id"])
    for a in p.get("aliases", []):
        by_trad.setdefault(a, []).append(p["id"])

print("=== 启 / 啟 / 夏后启 ===")
for key in ("启", "啟", "啓", "夏后启", "夏后啟"):
    ids = by_trad.get(key, [])
    print(f"  alias {key!r} -> {ids}")
for p in bd["persons"]:
    if "启" in p["name"] or "啟" in p["tradName"] or "啓" in p["tradName"] or p["id"] == "p_qi":
        # count sgz hits
        n_sgz = (p.get("byBook") or {}).get("sgz", {}).get("mentionCount", 0)
        if "qi" in p["id"] or "啟" in p["tradName"] or "啓" in p["tradName"] or p["name"] in ("启", "启"):
            print(
                f"  person {p['id']} {p['tradName']}/{p['name']} "
                f"dyn={p.get('dynasty')} books={p.get('books')} "
                f"sgz={n_sgz} total={p.get('mentionCount')} aliases={p.get('aliases')[:8]}"
            )

# 启 hits in sgz
print("\n=== 正文/命中里含「启」「啟」的 sgz marks ===")
qi_hits = Counter()
qi_samples = defaultdict(list)
for s in bd["sentences"]:
    cid = s["chapterId"]
    if not cid.startswith("sgz"):
        continue
    text = s.get("text") or ""
    for m in s.get("marks") or []:
        alias = m.get("alias") or ""
        if alias in ("启", "啟", "啓", "夏后启", "夏后啟") or (
            m.get("pid") in ("p_qi", "p_xiahouqi")
        ):
            qi_hits[(m.get("pid"), alias, m.get("tier"))] += 1
            if len(qi_samples[(m.get("pid"), alias)]) < 3:
                i = m.get("s", 0)
                qi_samples[(m.get("pid"), alias)].append(
                    f"{cid}…{text[max(0,i-12):i+20]}…"
                )
for k, n in qi_hits.most_common(20):
    print(" ", k, n)
    for smp in qi_samples[(k[0], k[1])]:
        print("   ", smp)

# 官名/称号类别名在 sgz 的归属分布
print("\n=== sgz 里高疑官名/称号别名（声明在 PERSONS 别名且短）===")
# collect aliases that look like office/title
OFFICE_HINTS = (
    "丞相", "太尉", "司徒", "司空", "太傅", "太保", "大将軍", "大將軍",
    "车骑将军", "車騎將軍", "卫将军", "衛將軍", "尚书令", "尚書令",
    "中书令", "中書令", "侍中", "太常", "光禄勋", "光祿勳", "司隶校尉",
    "司隸校尉", "荆州牧", "荊州牧", "益州牧", "扬州刺史", "揚州刺史",
    "豫州刺史", "御史大夫", "大司农", "大司農", "廷尉", "大鸿胪", "大鴻臚",
    "驃騎", "车骑", "車騎", "大司马", "大司馬", "大都督", "都督",
)
# Prefer aliases that are pure office without name
office_alias_hits = Counter()
office_alias_pid = defaultdict(Counter)
office_samples = defaultdict(list)
generic_office = [
    "丞相", "太尉", "司徒", "司空", "太傅", "大司馬", "大将军", "大將軍",
    "車騎將軍", "驃騎將軍", "侍中", "尚書令", "中書令", "太常",
    "光祿勳", "司隸校尉", "大司農", "廷尉", "衛尉", "太僕",
]
for s in bd["sentences"]:
    cid = s["chapterId"]
    if not cid.startswith("sgz"):
        continue
    text = s.get("text") or ""
    for m in s.get("marks") or []:
        alias = m.get("alias") or ""
        if alias not in generic_office and alias not in OFFICE_HINTS:
            continue
        if len(alias) < 2:
            continue
        office_alias_hits[alias] += 1
        office_alias_pid[alias][m.get("pid")] += 1
        if len(office_samples[alias]) < 2:
            i = m.get("s", 0)
            office_samples[alias].append(
                f"{cid}/{m.get('pid')}/{m.get('tier')}: …{text[max(0,i-10):i+len(alias)+15]}…"
            )

for alias, n in office_alias_hits.most_common(40):
    tops = office_alias_pid[alias].most_common(4)
    names = [
        f"{persons.get(pid, {}).get('tradName', pid)}×{c}" for pid, c in tops
    ]
    print(f"  {alias!r} n={n} -> {', '.join(names)}")
    for smp in office_samples[alias]:
        print("    ", smp)

# 称号类：魏帝文帝/明帝、宣帝、景帝、文帝 等在 sgz 的归属
print("\n=== 帝号/谥号称谓在 sgz 的多归属 ===")
for alias in (
    "文帝", "明帝", "景帝", "宣帝", "武帝", "高祖", "先主", "后主", "後主",
    "大帝", "武侯", "文帝", "司馬宣王", "宣王",
):
    # find pid splits
    pids = Counter()
    n = 0
    for s in bd["sentences"]:
        if not s["chapterId"].startswith("sgz"):
            continue
        for m in s.get("marks") or []:
            if m.get("alias") == alias:
                pids[m.get("pid")] += 1
                n += 1
    if n:
        tops = ", ".join(
            f"{persons.get(pid, {}).get('tradName', pid)}×{c}"
            for pid, c in pids.most_common(5)
        )
        print(f"  {alias!r} n={n} split: {tops}")

# GENERIC 里 sgz 出现的称号
print("\n=== genericAliases 在 sgz 的 pid 分布（前 15）===")
gen = Counter()
gen_pid = defaultdict(Counter)
for s in bd["sentences"]:
    if not s["chapterId"].startswith("sgz"):
        continue
    for m in s.get("marks") or []:
        if m.get("tier") in (
            "owner", "related", "sentence", "paragraph", "chapter", "era", "guess"
        ):
            gen[m.get("alias")] += 1
            gen_pid[m.get("alias")][m.get("pid")] += 1
for alias, n in gen.most_common(15):
    tops = ", ".join(
        f"{persons.get(pid, {}).get('tradName', pid)}×{c}"
        for pid, c in gen_pid[alias].most_common(3)
    )
    print(f"  {alias!r} n={n}: {tops}")
