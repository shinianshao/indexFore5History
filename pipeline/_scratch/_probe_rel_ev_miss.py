# -*- coding: utf-8 -*-
"""**替换**掉那 24 条（取证器看不到的边）的候选句——把上一版脚本的真命中补齐。

上一版（`_probe_rel_corpus_miss.py`）只做到「报出来」，本脚本把它判成可用条目、
直接写进 `_rel_evidence.json`，好让 `_apply_rel_evidence.py` 一起落盘。

⚠️ 判据仍是共现不算：只收**带显式关系词**的句子。三条：
  - 胡遵 —父→ 胡奮 ：「胡奮，字玄威……魏車騎將軍陰密侯遵之子也」
  - 公孫糾 —父→ 宋昭公：「昭公父公孫糾」
  - 朝鮮王滿 —祖父→ 朝鮮王右渠：暂无带关系词句 → 不收

用法：
    python pipeline/_scratch/_probe_rel_ev_miss.py            # 预演
    python pipeline/_scratch/_probe_rel_ev_miss.py --apply    # 写进 _rel_evidence.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVI = os.path.join(ROOT, "pipeline", "_rel_evidence.json")

# rel_id → (uid, 依据)。uid 取自上一版脚本的实际搜索命中。
FILL = {
    "4060d6c8bd5a": ("8634ecc807d8", "胡遵 —父→ 胡奮",
                     "胡奮，字玄威，安定臨涇人也，魏車騎將軍陰密侯遵之子也。",
                     "「遵之子也」直說胡奮是胡遵之子"),
    "b6081611ae10": ("bc3b23e76a66", "公孫糾 —父→ 宋昭公",
                     "昭公父公孫糾，糾父公子褍秦，褍秦即元公少子也。",
                     "「昭公父公孫糾」直說"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    with open(EVI, encoding="utf-8") as f:
        data = json.load(f)
    n = 0
    for it in data["items"]:
        fill = FILL.get(it["rel_id"])
        if not fill:
            continue
        uid, label, text, _why = fill
        it.setdefault("cands", [])
        if any(c["uid"] == uid for c in it["cands"]):
            continue
        # 分数给 3：够引人注意，但**不到 5**，不会被自动落盘 —— 必须人工确认
        it["cands"].insert(0, {"uid": uid, "chapter": "", "text": text,
                               "score": 3, "signals": ["补搜命中（全写法交叉搜索）"],
                               "others": 0})
        print("  ✓ {}　{}".format(label, uid))
        print("      「{}」".format(text))
        n += 1
    print("可补 {} 条".format(n))
    if a.apply and n:
        with open(EVI, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print("已写", EVI)
        print("下一步：python pipeline/_gen_rel_evidence.py 重建清单，再人工判")
    return 0


if __name__ == "__main__":
    sys.exit(main())
