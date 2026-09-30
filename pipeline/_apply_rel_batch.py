# -*- coding: utf-8 -*-
"""P6-2 把判定过的关系候选落盘到 workbook/relations.xlsx。

判定优先于规则
--------------
`_rel_verdicts.json` 里显式判过的（`accept` / `reject` / 指定 pid）**以它为准**；
没判过的才走自动规则。这样数据重新生成后判定不会丢（项目一贯的做法）。

自动规则（V1，宁缺勿滥）
------------------------
1. 另一端能**唯一**解析到 pid —— 多个候选（同名异人）一律不落；
2. **裸帝号一律不落**：文帝 / 明帝 / 武帝 / 宣帝 / 元帝 / 安帝 / 光武…
   这些是典型的多义称号，「文帝之子」在汉朝是刘恒、在三国是曹丕；
   生成器按别名解析只能碰运气（实测「宣帝」被解析成司马懿）。这类留人工判定；
3. 解析不出 pid 的丢弃。

用法
----
    python pipeline/_apply_rel_batch.py            # 落盘
    python pipeline/_apply_rel_batch.py --dry-run  # 只看会落多少
"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relations as R   # noqa: E402

BATCH = os.path.join(HERE, "_rel_batch.json")
VERDICTS = os.path.join(HERE, "_rel_verdicts.json")

# 裸帝号/多义称号：不自动落，等人工判定（可配合 self 的朝代判断）
AMBIGUOUS = {
    "文帝", "明帝", "章帝", "武帝", "宣帝", "元帝", "安帝", "和帝", "順帝",
    "桓帝", "靈帝", "獻帝", "惠帝", "景帝", "昭帝", "哀帝", "平帝", "光武",
    "高帝", "高祖", "太祖", "太宗", "世祖", "顯宗", "肅宗",
}


def ambiguous_hit(name: str) -> str:
    """裸帝号/庙号守卫（docs/28 P1-4）。

    以前是 `name in AMBIGUOUS` 精确匹配，于是「孝武帝」「漢高祖」这种**带修饰字**
    的称号直接漏网——那两条结果碰巧对，但守卫等于没生效，下一个同形状的称号
    就会挂错人。判据放宽为：原名等于该称号，或**以该称号结尾**
    （前缀是朝代/修饰字：漢/魏/晉/宋/孝/昭/武…）。

    宁可多挡一条去人工判（错挡只是慢），也别放错一条进库（错一条就是误导）。
    """
    for t in AMBIGUOUS:
        if name == t or name.endswith(t):
            return t
    return ""


def load_verdicts() -> dict:
    if not os.path.exists(VERDICTS):
        return {}
    with open(VERDICTS, encoding="utf-8") as f:
        return json.load(f)


def key_of(c: dict) -> str:
    return "{}|{}|{}".format(c["self_pid"], c["other_name"], c["rel"])


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not os.path.exists(BATCH):
        raise SystemExit("缺 {}，先跑 _gen_rel_candidates.py".format(BATCH))
    with open(BATCH, encoding="utf-8") as f:
        cands = json.load(f)
    verdicts = load_verdicts()

    accepted, skipped = [], {"ambiguous": 0, "multi": 0, "unresolved": 0,
                             "rejected": 0, "exists": 0}
    # 去重判据用 (a, b, rel)，**不能用 rel_id**——同一条关系若一次带 era/book、
    # 一次不带，rel_id 会不同，按 rel_id 去重就会漏（实测就这么重复过一条）
    existing = {(r.get("person_a"), r.get("person_b"), r.get("关系(rel)"))
                for r in R._read_rows()}

    for c in cands:
        k = key_of(c)
        v = verdicts.get(k) or {}
        name = c["other_name"]

        if v.get("accept") is False:
            skipped["rejected"] += 1
            continue

        pids = v.get("other_pids") or c["other_pids"]
        if not pids:
            skipped["unresolved"] += 1
            continue
        if len(pids) > 1 and not v.get("accept"):
            skipped["multi"] += 1
            continue
        hit = ambiguous_hit(name)
        if hit and not v.get("accept"):
            skipped["ambiguous"] += 1
            if not dry:
                print("  挡下待判：{}（命中裸称号「{}」）".format(name, hit))
            continue

        other_pid = pids[0]
        if c["direction"] > 0:          # X 是长辈 → (X, rel, self)
            a, b = other_pid, c["self_pid"]
            sa, sb = name, c["self_name"]
        else:                            # 本人是长辈 → (self, rel, X)
            a, b = c["self_pid"], other_pid
            sa, sb = c["self_name"], name

        rid = R.rel_id(a, b, c["rel"], "", "")
        if (a, b, c["rel"]) in existing:
            skipped["exists"] += 1
            continue
        inv = R.REL_INVERSE.get(c["rel"])
        if inv and (b, a, inv) in existing:      # 反向边已存在，别再写一条
            skipped["exists"] += 1
            continue
        existing.add((a, b, c["rel"]))           # 同批次内也要去重
        accepted.append({
            "rel_id": rid,
            "person_a": a, "原文用字a": sa,
            "person_b": b, "原文用字b": sb,
            "关系(rel)": c["rel"],
            "rel_type": R.REL_TABLE[c["rel"]][0],
            "对称": R.REL_TABLE[c["rel"]][1],
            "时代(era)": "", "书(book)": "",
            "证据uid": "",                       # 简介不是语料句，没有 uid
            "证据原文": "",
            "来源(source)": "auto-summary",
            "置信度(confidence)": R.derive_confidence("auto-summary", False),
            "状态(status)": "active",
            "备注(note)": "简介：{}".format(c["summary"])[:120],
            "录入时间(createdAt)": R.now(),
        })

    if not dry:
        for row in accepted:
            R._append_row(row)
    print("落盘 {} 条（dry-run={}）".format(len(accepted), dry))
    print("  跳过：裸帝号待判 {} / 同名异人 {} / 解析不出 {} / 判定拒绝 {} / 已存在 {}".format(
        skipped["ambiguous"], skipped["multi"], skipped["unresolved"],
        skipped["rejected"], skipped["exists"]))
    return len(accepted)


if __name__ == "__main__":
    sys.exit(main())
