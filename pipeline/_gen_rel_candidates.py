# -*- coding: utf-8 -*-
"""P6-2 关系候选抽取（取证）：从人物简介里找**显式关系词**。

只收显式关系词（「司馬昭之子」「劉邦之妻」），**绝不从共现推断关系**——
同句出现两个人什么都说明不了（docs/25 P1-9）。

边的语义：`(a, rel, b)` = **a 是 b 的 rel**。规范化取「长辈/年长一方在前」，
这样「X 之弟」存成 (X, 兄, 本人)，与 (本人, 弟, X) 是同一条边的反向——
由 REL_INVERSE 保证只存一条（relations.py 会拒绝反向双写）。

用法
----
    python pipeline/_gen_rel_candidates.py            # 产出 pipeline/_rel_batch.json
    python pipeline/_gen_rel_candidates.py --stats    # 只看统计
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOOK = os.path.join(ROOT, "data", "index", "book-data.json")
OUT = os.path.join(HERE, "_rel_batch.json")

# 关系词 → (规范 rel, 方向)
#   dir=+1：X 是长辈/年长一方 → 边为 (X, rel, self)
#   dir=-1：本人是长辈一方   → 边为 (self, rel, X)
REL_WORDS = {
    "子": ("父", +1), "女": ("父", +1),
    "父": ("父", -1), "母": ("母", -1),
    "弟": ("兄", +1), "兄": ("弟", -1),
    "孫": ("祖父", +1), "姪": ("伯叔", +1), "甥": ("舅", +1),
    "妻": ("夫", +1), "夫": ("妻", +1),
}

# 「之子」「之女」…：之 + 关系词
PAT_ZHI = re.compile(
    r"([一-龥]{2,8}?)[之與及](%s)" % "|".join(sorted(REL_WORDS, key=len, reverse=True)))
# 「光武子。」这类没有「之」的：只在**去掉句读后**匹配，且前段必须是已知人名
PAT_BARE = re.compile(
    r"([一-龥]{2,4})(子|女|父|母|弟|兄|孫|姪|甥|妻|夫)$")

CLOSERS = "。，、；：！？」』）"


def build_name_index(persons):
    """人名 → pid 列表（多个就是同名异人，需要人工判定）。"""
    idx = {}
    for p in persons:
        names = {p.get("tradName") or "", p.get("name") or ""}
        names |= set(p.get("aliases") or [])
        for n in names:
            n = (n or "").strip()
            if len(n) < 2 or len(n) > 8:
                continue
            idx.setdefault(n, set()).add(p["id"])
    return idx


def resolve(idx, name: str):
    return sorted(idx.get(name, set()))


def main() -> int:
    stats = "--stats" in sys.argv
    with open(BOOK, encoding="utf-8") as f:
        d = json.load(f)
    persons = d["persons"]
    idx = build_name_index(persons)
    by_id = {p["id"]: p for p in persons}

    cands = []
    stat = Counter()
    for p in persons:
        self_pid = p["id"]
        self_name = p.get("tradName") or p.get("name") or self_pid
        s = (p.get("summary") or "").strip()
        if not s:
            continue

        # ── 模式 A：「X 之子 / 之弟 / 之妻」──
        for m in PAT_ZHI.finditer(s):
            raw_name, word = m.group(1), m.group(2)
            rel, direction = REL_WORDS[word]
            # 「劉邦與呂后之子」→ 拆成两个人，分别出候选
            parts = [x for x in re.split(r"[與及、]", raw_name) if len(x) >= 2]
            for part in parts or [raw_name]:
                if len(part) > 8:            # 太长多半不是人名
                    continue
                pids = resolve(idx, part)
                cands.append({
                    "self_pid": self_pid, "self_name": self_name,
                    "other_name": part, "other_pids": pids,
                    "rel": rel, "direction": direction,
                    "pattern": "之",
                    "raw": m.group(0), "summary": s,
                    "ai": None,
                })
                stat["之"] += 1

        # ── 模式 B：「光武子。」（无「之」）──
        bare = s.rstrip(CLOSERS)
        m = PAT_BARE.search(bare)
        if m:
            part, word = m.group(1), m.group(2)
            pids = resolve(idx, part)
            if pids:                          # 前段必须能解析成已知人名，否则丢弃
                rel, direction = REL_WORDS[word]
                cands.append({
                    "self_pid": self_pid, "self_name": self_name,
                    "other_name": part, "other_pids": pids,
                    "rel": rel, "direction": direction,
                    "pattern": "bare",
                    "raw": m.group(0), "summary": s,
                    "ai": None,
                })
                stat["bare"] += 1

    # 统计分档
    uniq = [c for c in cands if len(c["other_pids"]) == 1]
    multi = [c for c in cands if len(c["other_pids"]) > 1]
    miss = [c for c in cands if not c["other_pids"]]

    print("候选 {} 条：".format(len(cands)))
    print("  唯一匹配 {}（可自动落）".format(len(uniq)))
    print("  同名异人 {}（需判定）".format(len(multi)))
    print("  解析不出 {}（丢弃）".format(len(miss)))
    print("  按词频：{}".format(dict(stat)))
    if stats:
        return 0

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(cands, f, ensure_ascii=False, indent=1)
    print("\n已写出 {}".format(OUT))
    print("下一步：逐条判定（ai 字段留空），再落盘 workbook/relations.xlsx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
