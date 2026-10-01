# -*- coding: utf-8 -*-
"""查「同一对两人出现两种辈分」的冲突边（verify_p3 [11] 抓到的那两组）。

用法：python pipeline/_scratch/_probe_rel_conflict.py
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB = os.path.join(ROOT, "data", "index", "index.db")

PAIRS = [("p_lvhou", "p_hanhuidi"), ("p_liji", "p_xiqi")]


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    for a, b in PAIRS:
        print("=== {} / {} ===".format(a, b))
        for r in conn.execute(
                "SELECT rel_id,person_a,person_b,rel,source,evidence_uid,status,note "
                "FROM relations WHERE (person_a=? AND person_b=?) OR (person_a=? AND person_b=?)",
                (a, b, b, a)):
            d = dict(r)
            print("  edge person_a={person_a} person_b={person_b} rel={rel} "
                  "src={source} ev={evidence_uid} st={status}".format(**d))
            print("        note: {}".format(d["note"]))
            if d["evidence_uid"]:
                s = conn.execute("SELECT text FROM sentences WHERE uid=?",
                                 (d["evidence_uid"],)).fetchone()
                print("        原文：{}".format(s[0] if s else "（句子不在库）"))
        for r in conn.execute("SELECT id,name,trad_name,title FROM persons WHERE id IN (?,?)",
                              (a, b)):
            print("  person:", dict(r))
        print()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
