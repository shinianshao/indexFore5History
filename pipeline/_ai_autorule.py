# -*- coding: utf-8 -*-
"""AI 概率判定闭环 · 「可计算信号」自动层。

docs/19 §三① 的第 3 条：**先让可计算的代理信号筛一遍，AI 只看剩下的**。
这一层就是那个筛子——把「证据已经算得死死的」条目直接定掉，
人（和 AI）的注意力留给真正有歧义的那些。

当前只有一条规则，且**刻意保守**：

  **R1 共现率 100%**
      该表字在语料里每一处出现，都与本人（全名或「姓+表字」）同句共现。
      既然每一处都贴着本人出现，就不存在跨词边界或同字他人的空间。
      → alias, p=0.95

为什么不写更多规则：共现率 0.5–0.9 那一段才是最难的（同字他人、
跨词边界都混在里面），**规则判不了，只能看原文**，交给 AI/人工。

用法
----
    python pipeline/_ai_autorule.py            # 只跑规则，写入 _ai_verdicts.json
    python pipeline/_ai_autorule.py --dry      # 只看会定掉哪些，不写
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "pipeline" / "_ai_batch.json"
VERDICTS = ROOT / "pipeline" / "_ai_verdicts.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    b = json.loads(BATCH.read_text(encoding="utf-8"))
    v = json.loads(VERDICTS.read_text(encoding="utf-8")) if VERDICTS.exists() else {}

    hit = []
    for it in b["items"]:
        if it["kind"] != "zi" or it["id"] in v:
            continue
        s = it["signals"]
        if s["共现率"] >= 1.0 and s["命中处数"] >= 1:
            hit.append((it,
                        "R1 共現率100%：{} 處命中全部與本人同句共現，無跨詞邊界/"
                        "同字他人空間".format(s["命中处数"])))

    for it, ev in hit:
        v[it["id"]] = {"action": "alias", "prob": 0.95,
                       "target": it["person"]["pid"], "evidence": ev, "auto": True}
        print("  {} 「{}」→ {}".format(it["id"], it["surface"], it["person"]["name"]))

    print("\nR1 定掉 {} 条".format(len(hit)))
    if not a.dry:
        VERDICTS.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        print("累计 {} 条 → {}".format(len(v), VERDICTS))


if __name__ == "__main__":
    main()
