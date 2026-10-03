#!/usr/bin/env python
"""只跑 `verify_p3` 的 [16]（網頁標錯入口），其餘 [1]–[15] 跳過。

為什麼要有這個：`verify_p3` 單跑要 4–5 分鐘（[2]/[3]/[4] 真的重建全量）。
但改纠错逻辑时**每次都要驗一遍**——等 5 分鐘才看到結果，迭代成本太高，
遲早會養成「改完先提交、跑完再看红不红」的习惯，那正是断言失去意义的方式。

    $ python app/tools/verify_p3_overrides.py     # 全绿 -> 退出码 0
    $ python app/tools/verify_p3_overrides.py     # 有红 -> 退出码 1

⚠️ 它**不是**回归的一部分。真正的门是 `verify_p3.py` 全跑（+ `scripts/run_all.sh`），
这个只是让人改得动的手边工具。基线：23 条。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "app", "tools"))

import verify_p3 as V                                        # noqa: E402


def main() -> int:
    V.test_override_api()
    V.purge_test_rows()      # 自造的测试行自己收走（含 finally 之外的路径）
    ok = sum(1 for _, v in V.CHECKS if v)
    print("\n  {}/{} 通過（只跑了 [16]；完整回归请跑 verify_p3.py）".format(
        ok, len(V.CHECKS)))
    return 0 if ok == len(V.CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
