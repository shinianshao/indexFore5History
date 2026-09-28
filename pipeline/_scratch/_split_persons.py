# -*- coding: utf-8 -*-
"""一次性：把 PERSONS 数据从 build_dict.py 抽到 persons_data.py。

这是 docs/21 P0 第 3 步的**前半段**——纯重构，管线行为必须**完全不变**。
拆完 build_dict.py 只留规则（GENERIC_MANUAL / CONTEXT_RULES / SCOPED_ALIASES …），
数据单独成模块，为「改成读 xlsx」铺路。

为什么必须先拆模块、不直接改成读 xlsx：
    people.json 是 build_dict 的**产物**，而 xlsx 现在是从 people.json 导出的。
    若一步到位让 build_dict 读 xlsx，就成了
        build_dict → people.json → xlsx → build_dict
    的循环依赖。先把源数据独立出来，链条才是单向的。

用法
----
    python pipeline/_split_persons.py            # 预演
    python pipeline/_split_persons.py --apply    # 真拆
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "pipeline" / "build_dict.py"
DST = ROOT / "pipeline" / "persons_data.py"
PEOPLE = ROOT / "data" / "dict" / "people.json"


def blocks_of(src):
    """找出所有顶层 PERSONS 赋值 / PERSONS.extend(...) 的行区间（含紧邻的前置注释）。"""
    lines = src.splitlines()
    tree = ast.parse(src)
    out = []
    for node in tree.body:
        hit = False
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PERSONS" for t in node.targets):
            hit = True
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if (isinstance(f, ast.Attribute) and f.attr == "extend"
                    and isinstance(f.value, ast.Name) and f.value.id == "PERSONS"):
                hit = True
        if not hit:
            continue
        lo, hi = node.lineno, node.end_lineno
        # 往上吃掉紧邻的注释行（数据块的说明应跟着数据走）
        while lo - 1 >= 1 and lines[lo - 2].lstrip().startswith("#"):
            lo -= 1
        out.append((lo, hi))
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    src = SRC.read_text(encoding="utf-8")
    lines = src.splitlines()
    blocks = blocks_of(src)

    # 重叠检查：块之间不能相交，否则删行会删错
    for (l1, h1), (l2, h2) in zip(blocks, blocks[1:]):
        if l2 <= h1:
            raise SystemExit("PERSONS 块区间重叠：{}~{} 与 {}~{}\n".format(l1, h1, l2, h2)
                             + "先去 build_dict.py 里看清楚再拆。")

    moved = []
    for lo, hi in blocks:
        moved.append("\n".join(lines[lo - 1:hi]))
    n_lines = sum(hi - lo + 1 for lo, hi in blocks)

    print("找到 {} 个 PERSONS 块，共 {} 行".format(len(blocks), n_lines))
    for lo, hi in blocks:
        print("   {:>5}–{:<5} {}".format(lo, hi, lines[lo - 1][:60]))

    before = hashlib.md5(PEOPLE.read_bytes()).hexdigest() if PEOPLE.exists() else None
    print("\n拆分前 people.json md5: {}".format(before))

    header = ('# -*- coding: utf-8 -*-\n'
              '"""PERSONS 数据（由 pipeline/_split_persons.py 从 build_dict.py 抽出）。\n\n'
              '这是**数据**，不是规则。规则留在 build_dict.py\n'
              '（GENERIC_MANUAL / GENERIC_CONTEXT_RULES / SCOPED_ALIASES / BOOK_CANDIDATES /\n'
              ' PERSON_BOOKS_* / OFFICE_WORDS）——它们适合 git diff，继续由代码维护。\n\n'
              '⚠️ 本文件当前仍是「从源码搬过来的」，尚未与 Excel 打通。\n'
              '   打通后（docs/21 P0 后半）它会由 workbook/persons.xlsx 生成，\n'
              '   那时 Excel 才是权威源，本文件降为中间产物。\n\n'
              '格式：(id, 简体名, 繁体名, 朝代, 头衔, 简介, [别名...])\n'
              '"""\n\n')
    dst_text = header + "\n\n".join(moved) + "\n"

    # 新 build_dict.py：删掉这些区间，在原位放 import
    drop = set()
    for lo, hi in blocks:
        drop.update(range(lo - 1, hi))
    first = blocks[0][0] - 1          # 第一个块的起始下标
    imp = ("# PERSONS 数据已抽到 persons_data.py（docs/21 P0）；本文件只留规则。\n"
           "from persons_data import PERSONS          # noqa: E402\n")
    new_lines = []
    for i, ln in enumerate(lines):
        if i in drop:
            if i == first:
                new_lines.extend(imp.splitlines())
            continue
        new_lines.append(ln)
    new_src = "\n".join(new_lines) + "\n"

    # 语法自检：两边都必须能解析，否则不写盘
    ast.parse(dst_text)
    ast.parse(new_src)
    print("\n语法自检通过（persons_data.py / build_dict.py）")

    if not a.apply:
        print("\n（预演：加 --apply 才写文件）")
        return

    DST.write_text(dst_text, encoding="utf-8")
    SRC.write_text(new_src, encoding="utf-8")
    print("\n已写出 {}".format(DST))
    print("已改写 {}（删 {} 行，加 {} 行 import）".format(SRC, len(drop), 2))
    print("\n下一步：")
    print("  python pipeline/build_dict.py && python pipeline/verify.py --check")
    print("  并确认 people.json 的 md5 与拆分前一致（行为必须完全不变）")


if __name__ == "__main__":
    main()
