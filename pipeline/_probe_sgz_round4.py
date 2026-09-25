# -*- coding: utf-8 -*-
"""Round4：更宽的错配扫描——侯/王/单字/core 多 pid/sgz 高频可疑别名。"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
persons = {p["id"]: p for p in bd["persons"]}

# declare map
decl = defaultdict(list)
for p in bd["persons"]:
    for a in p.get("aliases", []):
        decl[a].append(p["id"])


def split(alias, book):
    c = Counter()
    samples = []
    for s in bd["sentences"]:
        if not s["chapterId"].startswith(book + "-"):
            continue
        for m in s.get("marks") or []:
            if m.get("alias") != alias:
                continue
            c[m["pid"]] += 1
            if len(samples) < 2:
                t = s.get("text") or ""
                i = m.get("s", 0)
                samples.append(
                    f"{s['chapterId']}/{m.get('tier')}: …{t[max(0,i-12):i+len(alias)+18]}…"
                )
    return c, samples


print("=== A. resolve 报告的高错位称号在各书 ===")
for a in (
    "關內侯", "楚王", "陳王", "武侯", "琅邪王", "濟南王", "清河王",
    "河間王", "文君", "舞陽侯", "安平侯", "竇皇后", "博陸侯", "郭皇后",
):
    if a not in decl and a not in {p["tradName"] for p in bd["persons"]}:
        # try generic
        pass
    row = []
    for book in ("sj", "hs", "hhs", "sgz"):
        c, _ = split(a, book)
        if sum(c.values()) >= 3:
            tops = ",".join(
                f"{persons.get(p,{}).get('tradName',p)}:{n}"
                for p, n in c.most_common(3)
            )
            row.append(f"{book}={sum(c.values())}({tops})")
    print(f"  {a}: decl={decl.get(a, [])[:4]} | {' | '.join(row) or 'no hits'}")

print("\n=== B. sgz core 别名：单别名多 pid 或 n>=20 且非常见人名 ===")
alias_pid = defaultdict(Counter)
for s in bd["sentences"]:
    if not s["chapterId"].startswith("sgz-"):
        continue
    for m in s.get("marks") or []:
        if m.get("tier") in ("core", "scoped") and m.get("alias"):
            alias_pid[m["alias"]][m["pid"]] += 1

# multi-pid core (should be rare if not generic)
multi = [
    (a, pc)
    for a, pc in alias_pid.items()
    if len(pc) >= 2 and sum(pc.values()) >= 8
]
multi.sort(key=lambda x: -sum(x[1].values()))
print(f"  multi-pid core aliases n>=8: {len(multi)}")
for a, pc in multi[:30]:
    tops = ", ".join(
        f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in pc.most_common(4)
    )
    print(f"    {a!r} n={sum(pc.values())}: {tops}")

print("\n=== C. 裸「侯/王/公」两字 core（非泛称表）===")
for a, pc in sorted(alias_pid.items(), key=lambda x: -sum(x[1].values())):
    if re.fullmatch(r".{1,2}[侯王公伯君]", a) and sum(pc.values()) >= 10:
        tops = ", ".join(
            f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in pc.most_common(3)
        )
        print(f"  {a!r} n={sum(pc.values())}: {tops}")

print("\n=== D. sgz 高频 core 但 title 含将/牧/令/守 的残留 ===")
suspicious = []
for a, pc in alias_pid.items():
    n = sum(pc.values())
    if n < 15:
        continue
    # if alias is exactly an office-like word
    if re.search(r"(將軍|将军|太守|刺史|牧|太傅|太尉|司徒|司空|令|僕射|尚书|尚書)$", a) and len(a) <= 6:
        suspicious.append((a, pc))
suspicious.sort(key=lambda x: -sum(x[1].values()))
for a, pc in suspicious[:20]:
    tops = ", ".join(
        f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in pc.most_common(3)
    )
    print(f"  {a!r} n={sum(pc.values())}: {tops}")

print("\n=== E. 同名 core 在 sgz 的样本（取 n 最大的 15 个两字别名）===")
two = [
    (a, pc)
    for a, pc in alias_pid.items()
    if len(a) == 2 and sum(pc.values()) >= 30 and len(pc) >= 1
]
two.sort(key=lambda x: -sum(x[1].values()))
for a, pc in two[:15]:
    tops = ", ".join(
        f"{persons.get(p,{}).get('tradName',p)}×{n}" for p, n in pc.most_common(3)
    )
    c, samples = split(a, "sgz")
    print(f"  {a!r} n={sum(pc.values())}: {tops}")
    if len(pc) >= 2:
        print("    ", samples[0][:150] if samples else "")

print("\n=== F. 泛称基线（新）===")
GEN = ("owner", "related", "sentence", "paragraph", "chapter", "era", "guess")
ch_book = {c["id"]: c.get("bookId", "") for c in bd["chapters"]}
bt = defaultdict(lambda: [0, 0])
for s in bd["sentences"]:
    bk = ch_book.get(s["chapterId"], "")
    for m in s.get("marks") or []:
        if m.get("tier") in GEN:
            bt[bk][0] += 1
            if m["tier"] != "guess":
                bt[bk][1] += 1
for bk in sorted(bt):
    tot, conf = bt[bk]
    print(f"  {bk}: {conf/max(tot,1):.0%} ({conf}/{tot})")
