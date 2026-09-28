# -*- coding: utf-8 -*-
"""裸帝号/王号的**按篇**归属分布，用来判断「chapter tier 是否把帝紀拖到載記那边」。

用法：
    python pipeline/_probe_generic_bychapter.py 武帝 js
    python pipeline/_probe_generic_bychapter.py 高祖 js --tier chapter
    python pipeline/_probe_generic_bychapter.py 武帝 js --top 20
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = json.loads((ROOT / "data" / "index" / "book-data.json").read_text(encoding="utf-8"))
NAMES = {p["id"]: p.get("tradName") or p.get("name") for p in D["persons"]}
CH = {c["id"]: c for c in D["chapters"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("alias")
    ap.add_argument("book", nargs="?", default=None, help="sj/hs/hhs/sgz/js；不给=全部")
    ap.add_argument("--tier", default=None)
    ap.add_argument("--grep", default=None, help="只统计篇名含该词的篇（帝紀/載記/志/列傳）")
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()

    # pid -> 篇 -> 处
    tbl = defaultdict(lambda: Counter())
    for s in D["sentences"]:
        cid = s["chapterId"]
        if a.book and not cid.startswith(a.book + "-"):
            continue
        if a.grep and a.grep not in (CH.get(cid, {}).get("title") or ""):
            continue
        for m in s.get("marks") or []:
            if m.get("alias") != a.alias:
                continue
            if a.tier and m.get("tier") != a.tier:
                continue
            tbl[m.get("pid")][cid] += 1

    print("裸「{}」{} · 按篇分布".format(a.alias, ("@" + a.book) if a.book else ""))
    for pid, cc in sorted(tbl.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(cc.values())
        print("\n■ {}  {} 处 / {} 篇".format(NAMES.get(pid, pid), total, len(cc)))
        for cid, n in cc.most_common(a.top):
            ch = CH.get(cid, {})
            print("    {:<10} {:>4}  {}".format(cid, n, ch.get("title", "")))


if __name__ == "__main__":
    main()
