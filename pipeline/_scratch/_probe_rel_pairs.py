# -*- coding: utf-8 -*-
"""挑刺（二）：关系**内容**对不对——把每条边的两端简介并排打印，人眼核。

为什么还要有它：`_probe_rel_view.py` 只能查「显示串有没有读反」，查不出
「这条关系本身就是错的」。审查（docs/28）在 62 条里抽样就查出一条世系错
（袁安—父→袁湯，实为祖父）。显示全绿 ≠ 内容对。

判据（机械部分）：边的方向是 (a, rel, b) = 「a 是 b 的 rel」。
所以 b 的简介里应当出现「a 之子/之女/之弟…」，或 a 的简介里出现「b 之父/之兄…」。
两端简介**互相都不提**的那几条，机械查不了，必须人眼——这里把它们排在最前面。

用法
----
    python pipeline/_scratch/_probe_rel_pairs.py            # 可疑优先
    python pipeline/_scratch/_probe_rel_pairs.py --all      # 全量
    python pipeline/_scratch/_probe_rel_pairs.py --rel 父   # 只看某一类
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")


def name_variants(row) -> list:
    """一个人的可引用写法：正名 + 原文用字（边里记的 surface）。"""
    out = []
    for v in (row["trad_name"], row["name"], row["title"]):
        if v and v not in out:
            out.append(v)
    return out


def main() -> int:
    show_all = "--all" in sys.argv
    rel_filter = ""
    for i, a in enumerate(sys.argv):
        if a == "--rel" and i + 1 < len(sys.argv):
            rel_filter = sys.argv[i + 1]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT rel_id, person_a, surface_a, person_b, surface_b, rel, "
        "confidence, source FROM relations WHERE status='active' ORDER BY rel")]
    prof = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, trad_name, name, dynasty, title, summary FROM persons")}
    conn.close()

    sus, ok = [], []
    for r in rows:
        if rel_filter and r["rel"] != rel_filter:
            continue
        pa, pb = prof.get(r["person_a"]), prof.get(r["person_b"])
        if not pa or not pb:
            sus.append((r, pa, pb, "pid 查不到人"))
            continue
        sa, sb = (pa.get("summary") or ""), (pb.get("summary") or "")
        va = name_variants(pa) + ([r["surface_a"]] if r["surface_a"] else [])
        vb = name_variants(pb) + ([r["surface_b"]] if r["surface_b"] else [])
        # 互相提不提：任意一种写法出现在对方简介里就算「提了」
        a_in_b = any(v and v in sb for v in va)
        b_in_a = any(v and v in sa for v in vb)
        if a_in_b or b_in_a:
            ok.append((r, pa, pb, ""))
        else:
            sus.append((r, pa, pb, "两端简介互不相提（机械查不了，必须人眼）"))

    def dump(items, title):
        print("\n=== {}（{} 条）===".format(title, len(items)))
        for r, pa, pb, why in items:
            print("  [{}] {} —{}→ {}".format(
                r["rel_id"][:8], pa["trad_name"], r["rel"], pb["trad_name"]))
            print("      a：{}".format((pa.get("summary") or "—")[:90]))
            print("      b：{}".format((pb.get("summary") or "—")[:90]))
            if why:
                print("      ⚠ {}".format(why))

    dump(sus, "可疑：需人眼核")
    if show_all:
        dump(ok, "两端简介互有提及")
    print("\n合计 {} 条：可疑 {} / 有互提 {}".format(
        len(rows), len(sus), len(ok)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
