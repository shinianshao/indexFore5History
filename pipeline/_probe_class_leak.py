# -*- coding: utf-8 -*-
"""类传补人的「书外漏召」体检。

类传/附传传主是按检测到的那本书入典的（books 是硬闸门），所以
「鍾會 books=sgz」这种会在《晉書》里漏标。本脚本量出漏了多少：
对每个人，把五书语料里该名字的**字面出现数**与已标注的分书命中对比，
书外的出现数就是漏召。

用法：
    python pipeline/_probe_class_leak.py                 # 默认读 _class_fill_final.json
    python pipeline/_probe_class_leak.py --top 30
    python pipeline/_probe_class_leak.py --min 5         # 只看书外 ≥5 处的
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
BOOK_OF_PREFIX = {"sj": "sj", "hs": "hs", "hhs": "hhs", "sgz": "sgz", "js": "js"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(ROOT / "pipeline" / "_class_fill_final.json"))
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--min", type=int, default=1, help="只报书外出现 ≥ N 的")
    a = ap.parse_args()

    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    D = json.loads((ROOT / "data" / "index" / "book-data.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in D["persons"]}

    # 各书语料全文（只取正文句，够数字面出现）
    corpus = {}
    for f in glob.glob(str(ROOT / "data" / "corpus" / "*.json")):
        code = os.path.basename(f).split("-")[0]
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        buf = []
        for para in d.get("paragraphs") or []:
            for s in para.get("sentences") or []:
                buf.append(s.get("text") or "")
        for para in d.get("paragraphs") or []:
            buf.append(para.get("text") or "")
        corpus.setdefault(code, []).append("\n".join(buf))

    rows = []
    for r in plan.get("new") or []:
        pid, name = r["pid"], r["name_trad"]
        p = by_id.get(pid)
        if not p:
            continue
        scoped = set(p.get("books") or [])
        bb = p.get("byBook") or {}
        leak = 0
        detail = []
        for code, parts in corpus.items():
            if code in scoped:
                continue
            n = sum(t.count(name) for t in parts)
            if n:
                leak += n
                detail.append((code, n))
        if leak >= a.min:
            rows.append((leak, name, scoped, detail,
                         {k: (v.get("mentionCount") or 0) for k, v in bb.items()}))

    rows.sort(reverse=True, key=lambda x: x[0])
    print("书外漏召 {} 人（阈值 ≥{}）".format(len(rows), a.min))
    print("{:<8} {:<6} {:<16} {}".format("书外", "人名", "已限定", "书外分布"))
    for leak, name, scoped, detail, bb in rows[: a.top]:
        print("{:<8} {:<6} {:<16} {}   已标={}".format(
            leak, name, ",".join(sorted(scoped)), detail, bb))
    print("\n合计书外漏召 {} 处".format(sum(r[0] for r in rows)))


if __name__ == "__main__":
    main()
