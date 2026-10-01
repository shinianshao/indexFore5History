# -*- coding: utf-8 -*-
"""关系数据的「存量 / 缺口 / 外债」快照，用来排后续工作的顺序。

只**读**，不写任何东西。四项：
1. 现有边的量与有据率
2. 简介里还有多少关系词没出边（剩余可抽池）
3. pid 外债：占位 id 有多少、被关系引用多少、重名条目多少
4. 证据缺口：无据边里有多少在 docs/27 里有候选句（补得回来 vs 补不回来）

用法：python pipeline/_scratch/_probe_rel_backlog.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "data", "index", "index.db")
DOCS26 = os.path.join(ROOT, "docs", "26-关系候选待判.md")
DOCS27 = os.path.join(ROOT, "docs", "27-关系证据待判.md")

# 关系词（与 _gen_rel_candidates.py 保持一致才不会自说自话）
REL_WORDS = ["之子", "之孫", "之弟", "之兄", "之父", "之母", "之妻", "之夫",
             "之女", "之子弟", "之從弟", "之從兄", "之叔", "之姪", "之外孫"]


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ---------- 1. 存量 ----------
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM relations WHERE status='active'")]
    ev = {}
    for r in conn.execute(
            "SELECT rel_id, COUNT(*) n FROM relation_evidence "
            "WHERE verdict<>'reject' GROUP BY rel_id"):
        ev[r[0]] = r[1]
    with_ev = sum(1 for r in rows if (r["evidence_uid"] or "") or ev.get(r["rel_id"]))
    print("=== 1. 存量 ===")
    print("  活跃边 {} 条；有据 {} 条（{:.0f}%）；证据总行数 {}".format(
        len(rows), with_ev, 100.0 * with_ev / max(1, len(rows)),
        sum(ev.values()) + sum(1 for r in rows
                               if (r["evidence_uid"] or "") and not ev.get(r["rel_id"]))))
    pids = set()
    for r in rows:
        pids.add(r["person_a"]); pids.add(r["person_b"])
    print("  牵涉人物 {} 人（占全部 {} 人的 {:.1f}%）".format(
        len(pids),
        conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0],
        100.0 * len(pids) / max(1, conn.execute(
            "SELECT COUNT(*) FROM persons").fetchone()[0])))

    # ---------- 2. 剩余可抽池 ----------
    print("\n=== 2. 简介里还有多少关系词没变成边 ===")
    covered = set()
    for r in rows:
        covered.add((r["person_a"], r["person_b"]))
    hit = miss = 0
    for p in conn.execute("SELECT id, name, summary FROM persons"):
        s = p["summary"] or ""
        if not any(w in s for w in REL_WORDS):
            continue
        # 有边 = 这条简介的主人公出现在某条边的任一端
        if any(p["id"] in (a, b) for a, b in covered):
            hit += 1
        else:
            miss += 1
    print("  简介含关系词 {} 条：已出边 {} / 未出边 {}".format(hit + miss, hit, miss))

    # ---------- 3. pid 外债 ----------
    print("\n=== 3. pid 外债 ===")
    allp = [r[0] for r in conn.execute("SELECT id FROM persons")]
    ph = [x for x in allp if re.match(r"^p_x[0-9a-f]+$", x)]
    in_rel = [x for x in ph if x in pids]
    print("  占位 pid（p_xNNNNN）{} 个，其中被关系引用 {} 个".format(len(ph), len(in_rel)))
    dup = {}
    for r in conn.execute("SELECT id, name FROM persons"):
        dup.setdefault(r["name"], []).append(r["id"])
    dups = {k: v for k, v in dup.items() if len(v) > 1}
    print("  同名不同 pid {} 组".format(len(dups)))
    for k, v in list(dups.items())[:10]:
        print("    {} ← {}".format(k, " / ".join(v)))
    if len(dups) > 10:
        print("    …（共 {} 组）".format(len(dups)))

    # ---------- 4. 证据缺口 ----------
    print("\n=== 4. 证据缺口（多少边补得回来） ===")
    d27 = ""
    if os.path.exists(DOCS27):
        with open(DOCS27, encoding="utf-8") as f:
            d27 = f.read()
    names27 = set(re.findall(r"^\| \d+ \| ([^|]+?) —", d27, re.M))
    noev = [r for r in rows
            if not (r["evidence_uid"] or "") and not ev.get(r["rel_id"])]
    # ⚠️ 不能用名字匹配：docs/27 里的「漢高祖」在库里叫「劉邦」，surface_a 也叫「劉邦」，
    # 名字对不上会得出「0 条补得回来」的假结论。唯一可靠的键是 **rel_id**，
    # 它只在取证产物 `pipeline/_rel_evidence.json` 里（清单正文里没有）。
    evj = os.path.join(ROOT, "pipeline", "_rel_evidence.json")
    items = []
    if os.path.exists(evj):
        with open(evj, encoding="utf-8") as f:
            items = json.load(f).get("items", [])
    by_rid = {i["rel_id"]: i for i in items}
    noev_ids = {r["rel_id"] for r in noev}
    rescuable = sum(1 for r in noev
                    if (by_rid.get(r["rel_id"]) or {}).get("cands"))
    print("  取证产物覆盖 {} 条边（清单 {} 行）".format(len(items), len(names27)))
    print("  无据边 {} 条，其中取证器找到候选句 {} 条（{:.0f}%）".format(
        len(noev), rescuable, 100.0 * rescuable / max(1, len(noev))))
    hard = sum(1 for i in items
               if i.get("cands") and i["cands"][0].get("score", 0) >= 5)
    print("  其中硬句式（score≥5，可自动落）{} 条".format(hard))

    # ---------- 5. 两份清单的实际条数 ----------
    print("\n=== 5. 待判清单 ===")
    for path, label in ((DOCS26, "docs/26 关系候选"), (DOCS27, "docs/27 关系证据")):
        if not os.path.exists(path):
            print("  {} 不存在".format(label)); continue
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        n = len(re.findall(r"^\| \d+ \|", txt, re.M))
        print("  {}：{} 条".format(label, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
