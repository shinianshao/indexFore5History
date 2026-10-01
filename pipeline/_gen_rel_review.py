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
from _apply_rel_batch import ambiguous_hit as AMBIG_HIT   # noqa: E402


BATCH = os.path.join(HERE, "_rel_batch.json")
VERDICTS = os.path.join(HERE, "_rel_verdicts.json")
DB = os.path.join(ROOT, "data", "index", "index.db")


def vkey(c: dict) -> str:
    """verdicts 的 key：`本人pid|另一端名字|关系`（与 _apply_rel_batch 一致）。"""
    return "{}|{}|{}".format(c["self_pid"], c["other_name"], c["rel"])


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
    # ⚠️ 已判定的条目要**从作业纸上撤掉**（2026-10-01 补）。
    # 之前不读 verdicts，判完 40 条帝号后重跑，清单原样还是 40 条——
    # 下一轮进来的人会**从头再判一遍**（_gen_rel_evidence.py 早就防了这个坑，
    # 这支生成器漏了）。判过的（含 reject）都不再列。
    judged: dict = {}
    if os.path.exists(VERDICTS):
        with open(VERDICTS, encoding="utf-8") as f:
            judged = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    skipped_judged = sum(1 for c in cands if vkey(c) in judged)
    cands = [c for c in cands if vkey(c) not in judged]
    conn = sqlite3.connect(DB)
    # 「库里同名」列：判断帝号时最需要知道的是**这个称号在库里到底指谁**。
    # ⚠️ 光按 `name` 精确查等于白查——库里存的是**本名**（「劉恆」），
    # 帝号在 `title` 列（「漢文帝」）。第一次按 name 查，整列全是「—」，
    # 人还是判不了。所以两边都查：name 精确 + title 子串。
    # 例：「武帝」在库里指 12 个人（漢武帝/晉武帝/光武帝/後趙武帝…），
    # 这才是「裸帝号跨朝代多义」这句话的**实证**，而不是清单上的一句按语。
    same: dict = {}
    for r in conn.execute("SELECT id, name FROM persons"):
        same.setdefault(r[1], []).append(r[0])
    titled: list = [(r[0], r[1], r[2] or "") for r in
                    conn.execute("SELECT id, name, title FROM persons")]

    def title_hits(term: str) -> list:
        h = [(i, n) for i, n, t in titled if term and term in t and t != term]
        # 完全等于该称号的排最前（那才是「原名就叫这个」的人）
        h.sort(key=lambda x: (titled_dict.get(x[0], "") != term, x[0]))
        return h

    titled_dict = {i: t for i, _, t in titled}

    # ⚠️ 两条分类纪律（2026-10-01 补，之前用不上、判定时才发现会漏）：
    # 1. **带修饰字的帝号也要进帝号组**：`孝武帝`/`漢高祖` 不在 `AMBIGUOUS` 集合里，
    #    之前直接掉进「不属任何一组」，等于**从清单上消失**——人根本不知道有这条。
    #    分类要跟落盘用的守卫（`ambiguous_hit`，判据是**后缀**）保持同一套，
    #    否则「守卫生效了但清单没列」= 这条候选从此没人管。
    # 2. **单个已解析 pid 也要看是否撞名**：帝号组里 38 条有 36 条只解析出 1 个 pid，
    #    人判的时候正需要知道「这个名字库里还指谁」。只给一个 pid 等于不给判据。
    groups = {"帝号": [], "同名": [], "未解析": []}
    for c in cands:
        if AMBIG_HIT(c["other_name"]):
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
        L.append("| # | 本人 | 简介原文 | 关系 | 另一端 | 当前解析 | 库里同名 | 候选（朝代） | 你的判定 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for i, c in enumerate(items, 1):
            if c["other_pids"]:
                cur = ", ".join(c["other_pids"])
            else:
                cur = "—"
            # 「库里同名」列：只解析出 1 个 pid 时人最需要这列——
            # 同一个名字在库里还指谁，是判断「是不是该指向另一个 pid」的唯一线索。
            hits = title_hits(c["other_name"])
            same_txt = "、".join(
                "{}({}){}".format(n, i, "＊" if titled_dict.get(i) == c["other_name"]
                                  else "") for i, n in hits[:6]) or "—"
            if len(hits) > 6:
                same_txt += " 等 {} 人".format(len(hits))
            cands_txt = " / ".join(
                "{}【{}】".format(r[1], r[2] or "") for r in
                candidates_of(c["other_name"], conn)) or "—"
            L.append("| {} | {} | {} | {} | {} | {} | {} | {} |  |".format(
                i, c["self_name"], c["summary"][:26], c["rel"],
                c["other_name"], cur, same_txt, cands_txt))
        L.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    conn.close()
    print("已写出 {}（帝号 {} / 同名 {} / 未解析 {}；已判定撤下 {}）".format(
        args.out, len(groups["帝号"]), len(groups["同名"]),
        len(groups["未解析"]), skipped_judged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
