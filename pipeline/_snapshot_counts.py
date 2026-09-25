# -*- coding: utf-8 -*-
"""给 book-data.json 的 人物/地名 计数拍快照（id → 计数），用于改动前后逐 id 对账。

用法：
  python pipeline/_snapshot_counts.py before   # 写到 pipeline/_counts_before.json
  python pipeline/_snapshot_counts.py after    # 写到 pipeline/_counts_after.json
  python pipeline/_snapshot_counts.py diff     # 对比两者，只打印有差异的条目
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

BOOK = os.path.join(common.INDEX, "book-data.json")
BEFORE = os.path.join(common.PIPELINE, "_counts_before.json")
AFTER = os.path.join(common.PIPELINE, "_counts_after.json")


def snap():
    d = common.load_json(BOOK)
    out = {}
    for kind in ("persons", "places"):
        for e in d.get(kind, []):
            out[e["id"]] = {
                "kind": kind,
                "name": e.get("name"),
                "mentionCount": e.get("mentionCount"),
                "mentionChapterCount": e.get("mentionChapterCount"),
            }
    sents = d.get("sentences", [])
    out["__summary__"] = {
        "persons": len(d.get("persons", [])),
        "places": len(d.get("places", [])),
        "sentences": len(sents),
        "personMarks": sum(len(s.get("marks", []) or []) for s in sents),
        "placeMarks": sum(len(s.get("pmarks", []) or []) for s in sents),
    }
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "before"
    if mode == "diff":
        a = common.load_json(BEFORE)
        b = common.load_json(AFTER)
        keys = sorted(set(a) | set(b))
        n = 0
        for k in keys:
            if a.get(k) != b.get(k):
                n += 1
                print("DIFF {}".format(k))
                print("   before {}".format(a.get(k)))
                print("   after  {}".format(b.get(k)))
        print("共 {} 处差异".format(n))
        return
    path = BEFORE if mode == "before" else AFTER
    common.write_json(path, snap(), indent=1)
    print("已写入 {}".format(path))


if __name__ == "__main__":
    main()
