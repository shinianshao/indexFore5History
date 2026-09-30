# -*- coding: utf-8 -*-
"""挑刺（四）：关系图**内部**自洽吗——三类机械可查的矛盾。

1. **同一对两人两种辈分**：(A父B) 与 (A祖父B) 同时存在 → 必有一条错。
2. **世系成环**：A 是 B 的长辈、B 又是 A 的长辈（含 A→B→C→A）→ 必错。
3. **祖父边缺中间一代**：A—祖父→C，却没有 A—父→X—父/母→C → 不一定错
   （中间那代可能没条目），但值得列出来看一眼。

为什么机械查这些：袁湯那条（简介写「之子」实为「之孫」）是**内容错**，
机器查不出；但一旦它跟别的边撞在一起，就会露出马脚。先把能查的查干净。

用法
----
    python pipeline/_scratch/_probe_rel_consistency.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")

# 有向的「长辈 → 晚辈」边，辈分差用来算世代
GEN = {"父": 1, "母": 1, "祖父": 2, "祖母": 2, "養父": 1, "繼母": 1,
       "伯叔": 1, "姑": 1, "舅": 1, "姨": 1}


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT rel_id, person_a, person_b, rel FROM relations WHERE status='active'")]
    names = {r["id"]: r["trad_name"] for r in conn.execute(
        "SELECT id, trad_name FROM persons")}
    conn.close()

    def nm(pid):
        return names.get(pid, pid)

    # 1. 同一对两人多种 rel
    pair = defaultdict(list)
    for r in rows:
        pair[(r["person_a"], r["person_b"])].append(r)
    dup = [(k, v) for k, v in pair.items() if len(v) > 1]
    print("=== ① 同一对两人多条边（{} 处）===".format(len(dup)))
    for (a, b), v in dup:
        print("  {} / {}：{}".format(nm(a), nm(b), [x["rel"] for x in v]))

    # 2. 世系成环（只走 GEN 边）
    down = defaultdict(list)          # 长辈 → 晚辈
    for r in rows:
        if r["rel"] in GEN:
            down[r["person_a"]].append(r["person_b"])
    cycles = []
    seen = set()

    def walk(start, cur, path):
        for nxt in down.get(cur, []):
            if nxt == start:
                cycles.append(path + [nxt])
                continue
            if nxt in path or (start, nxt) in seen:
                continue
            seen.add((start, nxt))
            walk(start, nxt, path + [nxt])

    for p in list(down):
        walk(p, p, [p])
    print("\n=== ② 世系成环（{} 处）===".format(len(cycles)))
    for c in cycles:
        print("  " + " → ".join(nm(x) for x in c))

    # 3. 祖父边缺中间一代
    parent_of = defaultdict(set)      # 晚辈 → 长辈集合
    for r in rows:
        if r["rel"] in GEN:
            parent_of[r["person_b"]].add(r["person_a"])
    missing = []
    for r in rows:
        if r["rel"] not in ("祖父", "祖母"):
            continue
        a, c = r["person_a"], r["person_b"]
        mid = any(a in parent_of.get(x, set()) for x in parent_of.get(c, ()))
        if not mid:
            missing.append(r)
    print("\n=== ③ 祖孫邊缺中間一代（{} 處，未必錯）===".format(len(missing)))
    for r in missing:
        print("  {} —{}→ {}".format(nm(r["person_a"]), r["rel"],
                                    nm(r["person_b"])))

    print("\n合计 {} 条边".format(len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
