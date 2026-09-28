# -*- coding: utf-8 -*-
"""P4-0 給語料裡的每個句子打上穩定 `uid`（冪等，可反覆跑）。

為什麼要下沉到語料層
--------------------
`uid` 以前是在建庫時按位置現算的：`md5(chapterId|paraSeq|seq)[:12]`。
句子一旦可編輯（拆/併/刪），序號整體位移 → **同句算出新 uid** →
打垮全部命中外鍵、寫好的 override 錨點、以及快照 diff。

正解是讓 uid **跟著句子本身走**：在語料層就分配好，往後一路透傳
（corpus → book-data.json → index.db）。編輯時再按繼承規則維護：

| 操作 | uid 處理 |
|---|---|
| 拆一句為二 | 前半**繼承原 uid**，後半生成新 uid |
| 合併二句 | 保留第一句 uid，另一句標 `merged` |
| 棄用 | 標 `dead`，**不物理刪** |

用法
----
    python pipeline/tag_uids.py              # 補打（缺幾個補幾個）
    python pipeline/tag_uids.py --check      # 只看統計，不寫
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from common import CORPUS, stable_uid   # noqa: E402  三處共用同一算法，別各寫一份


def tag_one(path: str, dry: bool = False) -> tuple:
    """回傳 (補打數, 已有數)。"""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    cid = d.get("chapterId")
    n_new = n_old = 0
    for p in d.get("paragraphs") or []:
        for s in p.get("sentences") or []:
            if s.get("uid"):
                n_old += 1
                continue
            s["uid"] = stable_uid(cid, p.get("seq"), s.get("seq"))
            n_new += 1
    if n_new and not dry:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    return n_new, n_old


def main() -> int:
    dry = "--check" in sys.argv or "--dry-run" in sys.argv
    paths = sorted(glob.glob(os.path.join(CORPUS, "*.json")))
    if not paths:
        print("語料目錄是空的：{}".format(CORPUS))
        return 1
    t0 = time.time()
    tot_new = tot_old = 0
    for path in paths:
        a, b = tag_one(path, dry)
        tot_new += a
        tot_old += b
    print("語料 {} 篇：補打 {:,} 句 / 已有 {:,} 句（{:.1f}s）{}".format(
        len(paths), tot_new, tot_old, time.time() - t0,
        "　[--check 未寫入]" if dry else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
