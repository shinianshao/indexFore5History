# -*- coding: utf-8 -*-
"""比对两个版本的 `workbook/relations.xlsx`，只关心**会不会动到审定过的东西**。

为什么要有它：补证据那批（P6-5a）之后，用户问「你是不是把起点终点改了」。
xlsx 是二进制，`git diff` 只给字节数，答不上来。这个脚本逐列比对，
把变化**限定在**证据相关的几列——只要端点/关系词/状态有一处不同就报出来。

用法（先用 git 取出旧版）：
    git show HEAD:workbook/relations.xlsx > /tmp/old_rel.xlsx
    python pipeline/_scratch/_probe_rel_xlsx_diff.py /tmp/old_rel.xlsx
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import relations as R                      # noqa: E402   只为复用 _openpyxl / WORKBOOK

# 这些列是**人审定的**，脚本一个字都不该动
PROTECTED = ("rel_id", "原文用字a", "原文用字b", "关系(rel)", "person_a", "person_b",
             "朝代(era)", "书(book)", "来源(source)", "状态(status)")
# 这些列允许脚本写（证据 + 派生置信度 + 备注）
ALLOWED = ("证据uid", "证据原文", "置信度(confidence)", "备注(note)")


def load(path: str) -> dict:
    opx = R._openpyxl()
    ws = opx.load_workbook(path)["relations"]
    head = {c.value: c.column for c in ws[1]}
    out = {}
    for r in ws.iter_rows(min_row=2):
        rid = str(r[head["rel_id"] - 1].value or "").strip()
        if not rid:
            continue
        out[rid] = {k: r[head[k] - 1].value for k in head if k}
    return out


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("用法：python 本脚本 <旧版 xlsx 路径>")
    old, new = load(sys.argv[1]), load(R.WORKBOOK)
    print("旧 {} 条 / 新 {} 条".format(len(old), len(new)))
    bad = [rid for rid in set(old) ^ set(new)]
    for rid in bad:
        print("  ✗ 行有增删：{}（{}）".format(rid, "新增" if rid in new else "消失"))
    touched = []
    for rid in sorted(set(old) & set(new)):
        for k in set(old[rid]) | set(new[rid]):
            o, n = (old[rid].get(k) or ""), (new[rid].get(k) or "")
            if o == n:
                continue
            if k in PROTECTED:
                print("  ✗ {} 的【{}】被改了：{} → {}".format(rid, k, o, n))
                bad.append(rid)
            elif k in ALLOWED:
                touched.append((rid, k))
            else:
                print("  ? {} 的【{}】变了（不在白名单里）：{} → {}".format(
                    rid, k, o, n))
                bad.append(rid)
    print("\n审定列（端点/关系词/状态/朝代/书/来源）改动：{} 处".format(len(bad)))
    print("允许改的列被写了 {} 处（证据 / 派生置信度 / 备注）".format(len(touched)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
