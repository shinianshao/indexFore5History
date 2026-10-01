# -*- coding: utf-8 -*-
"""关系证据的「判定作业纸」：`docs/27` 里那 59 条待判，逐条摆出候选句与信号。

跟 `docs/27` 的区别：那份清单是给人在浏览器里看的，本脚本额外给出
**rel_id**（回填 verdicts 需要的键）和**每句的出处篇目**，判完能直接写 JSON。

用法：
    python pipeline/_scratch/_probe_rel_ev_sheet.py                # 全部
    python pipeline/_scratch/_probe_rel_ev_sheet.py --only-cands   # 只列有候选句的
    python pipeline/_scratch/_probe_rel_ev_sheet.py --out 文档.md
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVI_JSON = os.path.join(ROOT, "pipeline", "_rel_evidence.json")
DB = os.path.join(ROOT, "data", "index", "index.db")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-cands", action="store_true", help="只列取证器找到候选句的")
    ap.add_argument("--max-cands", type=int, default=3)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    with open(EVI_JSON, encoding="utf-8") as f:
        items = json.load(f)["items"]
    conn = sqlite3.connect(DB)
    ch = {}
    for r in conn.execute("SELECT uid, chapter_id FROM sentences"):
        ch[r[0]] = r[1]
    ev = {r[0] for r in conn.execute(
        "SELECT rel_id FROM relations WHERE status='active' AND evidence_uid<>''")}
    ev |= {r[0] for r in conn.execute(
        "SELECT rel_id FROM relation_evidence WHERE verdict<>'reject'")}

    lines = []
    n = 0
    for it in items:
        if it["rel_id"] in ev:
            continue                       # 已经有证据了，不用判
        cands = it.get("cands") or []
        if a.only_cands and not cands:
            continue
        n += 1
        lines.append("### {}　{} —{}→ {}".format(
            it["rel_id"], it["name_a"], it["rel"], it["name_b"]))
        if not cands:
            lines.append("　　（取证器没找到候选句，补不回来）")
            lines.append("")
            continue
        for i, c in enumerate(cands[:a.max_cands], 1):
            lines.append("　{}. score={}　{}　`{}`".format(
                i, c.get("score", 0), "；".join(c.get("signals") or []),
                c["uid"]))
            lines.append("　　　篇 {}：「{}」".format(
                ch.get(c["uid"], "?"), c["text"][:70]))
        lines.append("")
    head = "# 关系证据判定作业纸（{} 条）\n".format(n)
    out = head + "\n".join(lines)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out)
        print("已写 {}（{} 条）".format(a.out, n))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
