# -*- coding: utf-8 -*-
"""P6-2 生成「关系候选·人工判定清单」（docs/26）。

只列**自动规则不敢落**的两类：
1. 裸帝号（文帝/明帝/武帝/宣帝…）——同一个称号跨朝代指不同的人，
   「文帝之子」在汉朝是刘恒、在三国是曹丕，生成器只能碰运气；
2. 同名异人（另一端解析到多个 pid）。

每条自带**判定需要的证据**：简介原文、当前解析到了谁、以及所有候选人的朝代。
判不了就空着，不要为填满而硬判（docs/17 的老规矩）。

用法
----
    python pipeline/_gen_rel_review.py --out docs/26-关系候选待判.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from _apply_rel_batch import AMBIGUOUS   # noqa: E402

BATCH = os.path.join(HERE, "_rel_batch.json")
DB = os.path.join(ROOT, "data", "index", "index.db")


def candidates_of(name: str, conn) -> list:
    """称号/人名可能指的所有人（带朝代，供消歧）。"""
    like = "%{}%".format(name)
    rows = conn.execute(
        "SELECT id, trad_name, dynasty, title FROM persons "
        "WHERE trad_name LIKE ? OR name LIKE ? "
        "   OR id IN (SELECT person_id FROM aliases WHERE alias LIKE ?) "
        "LIMIT 8", (like, like, like)).fetchall()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        ROOT, "docs", "26-关系候选待判.md"))
    args = ap.parse_args()

    with open(BATCH, encoding="utf-8") as f:
        cands = json.load(f)
    conn = sqlite3.connect(DB)

    groups = {"帝号": [], "同名": [], "未解析": []}
    for c in cands:
        if c["other_name"] in AMBIGUOUS:
            groups["帝号"].append(c)
        elif len(c["other_pids"]) > 1:
            groups["同名"].append(c)
        elif not c["other_pids"]:
            groups["未解析"].append(c)

    L = []
    L.append("# 26 · 关系候选 · 人工判定清单")
    L.append("")
    L.append("> 由 `python pipeline/_gen_rel_review.py` 生成，数据变了可重跑。")
    L.append("> 只列**自动规则不敢落**的候选；判定写进 `pipeline/_rel_verdicts.json`，")
    L.append("> 再跑 `_apply_rel_batch.py` 落盘。判不了就留空，**不要硬判**。")
    L.append("")
    L.append("判定写法（verdicts 的 key 是 `本人pid|另一端名字|关系`）：")
    L.append("")
    L.append("```json")
    L.append('{ "p_liubang|文帝|父": {"accept": true, "other_pids": ["p_liuheng"], '
             '"note": "漢文帝劉恒"},')
    L.append('  "p_xxx|明帝|父": {"accept": false, "note": "存疑"} }')
    L.append("```")
    L.append("")

    for gname, items in (("帝号（裸谥号/帝号，跨朝代多义）", groups["帝号"]),
                         ("同名异人（另一端解析到多个 pid）", groups["同名"]),
                         ("解析不出（可能漏人，也可能本来就不是人名）",
                          groups["未解析"])):
        L.append("## {}　{} 条".format(gname, len(items)))
        L.append("")
        if not items:
            L.append("（无）")
            L.append("")
            continue
        L.append("| # | 本人 | 简介原文 | 关系 | 另一端 | 当前解析 | 候选（朝代） | 你的判定 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for i, c in enumerate(items, 1):
            if c["other_pids"]:
                cur = ", ".join(c["other_pids"])
            else:
                cur = "—"
            cands_txt = " / ".join(
                "{}【{}】".format(r[1], r[2] or "") for r in
                candidates_of(c["other_name"], conn)) or "—"
            L.append("| {} | {} | {} | {} | {} | {} | {} |  |".format(
                i, c["self_name"], c["summary"][:26], c["rel"],
                c["other_name"], cur, cands_txt))
        L.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    conn.close()
    print("已写出 {}（帝号 {} / 同名 {} / 未解析 {}）".format(
        args.out, len(groups["帝号"]), len(groups["同名"]),
        len(groups["未解析"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
