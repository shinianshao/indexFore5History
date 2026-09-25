# -*- coding: utf-8 -*-
"""Round2+：帝号/裸称号/官名残留在四书的归属抽样。"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
persons = {p["id"]: p for p in bd["persons"]}
chapters = {c["id"]: c for c in bd["chapters"]}

# who declares which alias
decl = defaultdict(list)  # alias -> [pid]
for p in bd["persons"]:
    for a in p.get("aliases", []):
        decl[a].append(p["id"])
    decl[p["tradName"]].append(p["id"])
    decl[p["name"]].append(p["id"])


def split_by_book(alias: str, book: str):
    c = Counter()
    samples = []
    for s in bd["sentences"]:
        if not s["chapterId"].startswith(book + "-"):
            continue
        for m in s.get("marks") or []:
            if m.get("alias") != alias:
                continue
            c[m["pid"]] += 1
            if len(samples) < 3:
                t = s.get("text") or ""
                i = m.get("s", 0)
                samples.append(
                    f"{s['chapterId']} {persons.get(m['pid'],{}).get('tradName',m['pid'])}"
                    f"/{m.get('tier')}: …{t[max(0,i-15):i+len(alias)+20]}…"
                )
    return c, samples


print("=== 1. 帝号声明者 ===")
for a in ("文帝", "武帝", "明帝", "景帝", "宣帝", "高祖", "太祖", "世宗", "烈祖"):
    print(f"  {a}: decl={decl.get(a, [])}")

print("\n=== 2. sgz 帝号实际归属 ===")
for a in ("文帝", "武帝", "明帝", "景帝", "宣帝", "高祖", "太祖"):
    c, samples = split_by_book(a, "sgz")
    if not c:
        print(f"  {a}: (无)")
        continue
    tops = ", ".join(
        f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in c.most_common(5)
    )
    print(f"  {a} n={sum(c.values())}: {tops}")
    for s in samples:
        print("   ", s)

print("\n=== 3. 裸官名残留在 sgz（仍作为 core 别名）===")
BARE = [
    "丞相", "司徒", "司空", "太尉", "太傅", "侍中", "太常", "大將軍",
    "大司馬", "車騎將軍", "驃騎將軍", "尚書令", "中書令", "衛尉",
    "大司農", "益州牧", "荊州牧", "豫州牧", "揚州牧", "徐州牧",
]
for a in BARE:
    c, samples = split_by_book(a, "sgz")
    if not c:
        continue
    tops = ", ".join(
        f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in c.most_common(3)
    )
    print(f"  {a} n={sum(c.values())}: {tops}")
    if samples:
        print("   ", samples[0][:160])

print("\n=== 4. hs/hhs 是否也有裸官名残留（抽丞相/太尉/侍中）===")
for book in ("hs", "hhs", "sj"):
    for a in ("丞相", "太尉", "侍中", "太傅"):
        c, _ = split_by_book(a, book)
        if sum(c.values()) >= 5:
            tops = ", ".join(
                f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in c.most_common(3)
            )
            print(f"  {book} {a} n={sum(c.values())}: {tops}")

print("\n=== 5. 同一 alias 多 pid 且表面像专名（sgz core，n>=10）===")
alias_pid = defaultdict(Counter)
for s in bd["sentences"]:
    if not s["chapterId"].startswith("sgz-"):
        continue
    for m in s.get("marks") or []:
        if m.get("tier") not in ("core", "scoped", "title"):
            continue
        if m.get("alias"):
            alias_pid[m["alias"]][m["pid"]] += 1
multi = []
for a, pc in alias_pid.items():
    if len(pc) >= 2 and sum(pc.values()) >= 10:
        # skip if it's a known generic (short titles)
        if a in {
            "文帝", "武帝", "明帝", "景帝", "宣帝", "高祖", "太祖",
            "先主", "後主", "后主", "丞相", "太尉",
        }:
            multi.append((a, pc))
        elif len(pc) >= 2 and max(pc.values()) >= 5:
            multi.append((a, pc))
multi.sort(key=lambda x: -sum(x[1].values()))
for a, pc in multi[:25]:
    tops = ", ".join(
        f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in pc.most_common(4)
    )
    print(f"  {a!r} n={sum(pc.values())} split: {tops}")

print("\n=== 6. p_qi / 夏后启 全书 ===")
qi = next(p for p in bd["persons"] if p["id"] == "p_qi")
print(" books", qi.get("books"), "mention", qi.get("mentionCount"), "byBook", qi.get("byBook"))

print("\n=== 7. 零命中 / 低命中新补人抽样 ===")
new_ids = [
    "p_zhongyao_sg", "p_huaxin_sg", "p_wanglang_sg", "p_weikan_sg",
    "p_chenqun_sg", "p_hanji_sg", "p_wangxiu_sg", "p_zhugeke",
]
for pid in new_ids:
    p = persons.get(pid)
    if not p:
        print("  MISSING", pid)
        continue
    print(
        f"  {pid} {p['tradName']} total={p.get('mentionCount')} "
        f"byBook={p.get('byBook')}"
    )
