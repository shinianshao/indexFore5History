# -*- coding: utf-8 -*-
"""`verify_p3.py` 的 **[19] 組（命中數口徑與篩選 · P0-丙）快速版**（~30s）。

為什麼要單獨一份：`verify_p3.py` 全跑 4–5 分鐘。改完篩選就想驗一次，
等 5 分鐘的結果是人會先去幹別的、回頭忘了看紅不紅——那正是斷言失去意義的方式
（與 `verify_p3_mark.py` / `verify_p3_overrides.py` 同一套規矩）。

用法
----
    python app/tools/verify_p3_mfilter.py

注入驗證（故意改壞，本檔案必須變紅）：
    bash app/tools/verify_p3_mfilter_inject.sh
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_p3 as V                                  # noqa: E402


def main() -> int:
    print("=== [19] 命中數口徑與篩選（P0-丙）· 快速版 ===")
    V.test_mention_filter()
    ok = sum(1 for _, v in V.CHECKS if v)
    for name, passed in V.CHECKS:
        if not passed:
            print("  ✗ " + name)
    print("\n  {}/{} 通過".format(ok, len(V.CHECKS)))
    return 0 if ok == len(V.CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
