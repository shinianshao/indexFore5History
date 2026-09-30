# -*- coding: utf-8 -*-
"""挑刺（三）：关系 vs 语料——每条边附一句**真原句**，看边的方向跟原文说的一致不一致。

为什么还要有它：`_probe_rel_pairs.py` 比对的是**简介**，而简介本身可能是错的
（實例：袁湯的简介写「袁安之子」，但 hhs-45 原文是 袁安→京→彭/湯，实为**孫**）。
简介是二手的，语料才是一手。这个类错**只能靠原文发现**，机械查不出来。

用法
----
    python pipeline/_scratch/_probe_rel_corpus.py            # 每条边一句
    python pipeline/_scratch/_probe_rel_corpus.py --rel 父   # 只看某一类
    python pipeline/_scratch/_probe_rel_corpus.py --top 3    # 每边三句

关注：原句里出现的关系词，跟边声称的 rel **不是一个辈分**（说「孫」却记「父」、
说「弟」却记「子」）。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))              # pipeline/
EVI = os.path.join(os.path.dirname(HERE), "_rel_evidence.json")

# 「辈分」关系词：句中出现这些，就要跟边声称的 rel 对一下
KIN_WORDS = ("之子", "之女", "之孫", "之孫女", "之弟", "之妹", "之兄", "之姊",
             "之父", "之母", "之祖父", "之祖母", "弟曰", "子曰")


def main() -> int:
    top = 1
    rel_filter = ""
    for i, a in enumerate(sys.argv):
        if a == "--top" and i + 1 < len(sys.argv):
            top = int(sys.argv[i + 1])
        if a == "--rel" and i + 1 < len(sys.argv):
            rel_filter = sys.argv[i + 1]
    if not os.path.exists(EVI):
        raise SystemExit("缺 {}，先跑 _gen_rel_evidence.py".format(EVI))
    with open(EVI, encoding="utf-8") as f:
        data = json.load(f)

    conn = sqlite3.connect(os.path.join(ROOT, "data", "index", "index.db"))
    conn.row_factory = sqlite3.Row
    edges = {r["rel_id"]: dict(r) for r in conn.execute(
        "SELECT rel_id, person_a, person_b, rel FROM relations WHERE status='active'")}
    conn.close()

    n = 0
    for it in data["items"]:
        rid = it["rel_id"]
        if rel_filter and it["rel"] != rel_filter:
            continue
        cands = it["cands"][:top]
        print("\n[{}] {} —{}→ {}".format(rid[:8], it["name_a"], it["rel"],
                                         it["name_b"]))
        if not cands:
            print("    （语料里两人从不同句出现，本就没有共现句）")
        for c in cands:
            mark = "★" if any(w in c["text"] for w in KIN_WORDS) else " "
            print("    {}{}  {}".format(mark, c["uid"][:8], c["text"][:70]))
        n += 1
    print("\n共 {} 条（★ = 句里有辈分关系词，重点看这些）".format(n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
