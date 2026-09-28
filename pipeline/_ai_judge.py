# -*- coding: utf-8 -*-
"""AI 概率判定闭环 · 第 3 段：把判定表合并进 `_ai_verdicts.json`。

为什么判定要单独存一份
----------------------
`_ai_batch.json` 每次重生成都会**整体覆盖**，判定写在里面会丢。
判定按 **条目 id** 存（`_ai_verdicts.json`），批次重生成时由
`_gen_ai_batch.py` 按 id 合并回去——数据变了，判定还在。

判定表格式（TAB 分隔，5 列；空行与 # 开头的行忽略）
--------------------------------------------------
    <id>\\t<action>\\t<prob>\\t<target>\\t<依据>

- action ∈ alias / reject / ctxrule / bookcand / default / unknown
  （含义见 `_gen_ai_batch.py` 的 ACTIONS）
- prob   0–1；**<0.5 一律当 unknown 处理**，不硬归
- target 目标 pid；reject / unknown 写 `-`
- 依据   **必填**——只吐标签的判定无法沉淀成守卫规则

用法
----
    python pipeline/_ai_judge.py --file pipeline/_ai_judged/01.txt
    python pipeline/_ai_judge.py --file a.txt --file b.txt
    python pipeline/_ai_judge.py --stats          # 看已判概况
    python pipeline/_ai_judge.py --drop <id>      # 撤一条判定
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ROOT / "pipeline" / "_ai_verdicts.json"
VALID_ACTIONS = {"alias", "reject", "ctxrule", "bookcand", "default", "drop", "keep", "unknown"}


def load():
    return json.loads(VERDICTS.read_text(encoding="utf-8")) if VERDICTS.exists() else {}


def save(v):
    VERDICTS.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=[])
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--drop", default=None)
    a = ap.parse_args()

    v = load()

    if a.drop:
        v.pop(a.drop, None)
        save(v)
        print("已撤销 {}".format(a.drop))
        return

    if a.stats or not a.file:
        stat = Counter()
        for k, d in v.items():
            stat[(k.split("|")[0], d.get("action"))] += 1
        print("已判 {} 条：".format(len(v)))
        for k, n in sorted(stat.items()):
            print("  {}·{} = {}".format(k[0], k[1], n))
        hi = [k for k, d in v.items() if (d.get("prob") or 0) >= 0.9]
        mid = [k for k, d in v.items() if 0.5 <= (d.get("prob") or 0) < 0.9]
        lo = [k for k, d in v.items() if (d.get("prob") or 0) < 0.5]
        print("\n三堆：高(≥0.9)={}  中(0.5–0.9)={}  低(<0.5)={}".format(
            len(hi), len(mid), len(lo)))
        return

    added = skipped = 0
    for f in a.file:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                print("  ! 列数不足，跳过：{}".format(line[:60]))
                skipped += 1
                continue
            iid, action, prob, target, ev = parts[:5]
            # 第 6 列可选：form —— 实际要写进词典的**繁体**形。
            # 语料里混着简体形（「季产」「汉盛」），别名铁律只写繁体，
            # 判定人在这里把规范形补上，应用器优先用它。
            form = parts[5].strip() if len(parts) >= 6 else ""
            iid, action = iid.strip(), action.strip()
            if action not in VALID_ACTIONS:
                print("  ! action 非法：{}".format(action))
                skipped += 1
                continue
            try:
                prob = float(prob)
            except ValueError:
                print("  ! prob 非数字：{}".format(prob))
                skipped += 1
                continue
            if not ev.strip():
                print("  ! 无依据，拒绝写入：{}".format(iid))
                skipped += 1
                continue
            rec = {"action": action, "prob": prob,
                   "target": target.strip(), "evidence": ev.strip()}
            if form:
                rec["form"] = form
            v[iid] = rec
            added += 1
    save(v)
    print("写入 {} 条（跳过 {}），累计 {} 条 → {}".format(added, skipped, len(v), VERDICTS))


if __name__ == "__main__":
    main()
