#!/usr/bin/env python
"""只跑 `verify_p3` 的 [17]（地名檢索與詳情），其餘 [1]–[16] 跳過。

為什麼要有這個：`verify_p3` 單跑要 4–5 分鐘（[2]/[3]/[4] 真的重建全量）。
但改地名檢索 / 詳情頁時**每次都要驗一遍**——等 5 分鐘才看到結果，迭代成本太高，
遲早會養成「改完先提交、跑完再看红不红」的習慣，那正是斷言失去意義的方式。
（與 `verify_p3_overrides.py` 同理，那個管 [16]。）

    $ python app/tools/verify_p3_place.py     # 全綠 -> 退出碼 0
    $ python app/tools/verify_p3_place.py     # 有紅 -> 退出碼 1

⚠️ 它**不是**回歸的一部分。真正的門是 `verify_p3.py` 全跑（+ `scripts/run_all.sh`），
這個只是讓人改得動的手邊工具。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "app", "tools"))

import verify_p3 as V                                        # noqa: E402


def main() -> int:
    V.test_place_search()
    ok = sum(1 for _, v in V.CHECKS if v)
    print("\n  {}/{} 通過（只跑了 [17]；完整回歸請跑 verify_p3.py）".format(
        ok, len(V.CHECKS)))
    return 0 if ok == len(V.CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
