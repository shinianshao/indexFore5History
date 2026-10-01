# -*- coding: utf-8 -*-
"""把「X 與 Y 之子」拆分造成的三条错边（母亲落了『父』）标成 dead。

背景：`docs/28` §2.2 P0-2 —— `_gen_rel_candidates.py` 拆并列父母时不看性别，
母亲也拿到「父」，于是页面上出现「呂后 父 劉盈」「驪姬 父 奚齊」「魯元公主 父 魯元王」。
生成器已修（按各人性别判 父/母），**xlsx 里那三条旧错边还得清掉**。

⚠️ 为什么不用 `relations.py revoke --rel-id`：`docs/28` P1-8 记着 rel_id 撞车——
同一个 `bee417f977f9` 在表里有两行（一行 dead 一行 active），revoke 按 rel_id 匹配
会**一次误伤两行**。所以这里按「行号 + person_a/b/rel」精确标 dead。

用法
----
    python pipeline/_fix_rel_mother_parent.py            # 预演
    python pipeline/_fix_rel_mother_parent.py --apply     # 写入
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))     # ⚠️ 在 _scratch/ 下要多退一层
XLSX = os.path.join(ROOT, "workbook", "relations.xlsx")

# (person_a, person_b, 错的 rel) —— 必须是**并列父母的性别判错**这一种
WRONG = {
    ("p_lvhou", "p_hanhuidi", "父"),
    ("p_liji", "p_xiqi", "父"),
    ("p_luyuangongzhu", "p_luyuanwang", "父"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(XLSX)
    ws = wb["relations"] if "relations" in wb.sheetnames else wb.active
    hdr = [c.value for c in ws[1]]
    ia, ib = hdr.index("person_a") + 1, hdr.index("person_b") + 1
    ir, ist = hdr.index("关系(rel)") + 1, hdr.index("状态(status)") + 1
    isrc = hdr.index("来源(source)") + 1
    imark = hdr.index("备注(note)") + 1

    note = "作廢：並列父母性別判錯（docs/28 P0-2），已改生成器按性別判 父/母"
    hits = []
    for row in range(2, ws.max_row + 1):
        key = (ws.cell(row, ia).value, ws.cell(row, ib).value, ws.cell(row, ir).value)
        if key in WRONG and ws.cell(row, ist).value == "active":
            hits.append(row)

    print("命中 {} 行（会标 dead）：".format(len(hits)))
    for row in hits:
        print("  第{}行 {} {} {} src={}".format(
            row, ws.cell(row, ia).value, ws.cell(row, ir).value,
            ws.cell(row, ib).value, ws.cell(row, isrc).value))

    if not args.apply:
        print("\n（预演。加 --apply 才写。）")
        return 0
    if not hits:
        print("没有要改的行。")
        return 0

    bak = XLSX.replace(".xlsx", ".bak-{}.xlsx".format(time.strftime("%m%d-%H%M%S")))
    shutil.copy2(XLSX, bak)
    print("\n已备份 → {}".format(os.path.basename(bak)))
    for row in hits:
        ws.cell(row, ist).value = "dead"
        old = ws.cell(row, imark).value or ""
        ws.cell(row, imark).value = (old + "；" if old else "") + note
    wb.save(XLSX)
    print("已写入 {}".format(XLSX))
    return 0


if __name__ == "__main__":
    sys.exit(main())
