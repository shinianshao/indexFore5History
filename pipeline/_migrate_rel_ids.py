# -*- coding: utf-8 -*-
"""P2 阶段架构重构：关系表 rel_id 契约重构与原子迁移。

将 rel_id 从历史依赖 book/era 的复合哈希，重构为由语义三元组 (person_a, person_b, rel)
决定的稳定业务主键。
同步完成：
1. workbook/relations.xlsx 主表 rel_id 列迁移；
2. workbook/relations.xlsx 证据子表 relation_evidence 外键 rel_id 迁移；
3. pipeline/_rel_evidence_verdicts.json 判定配置键迁移。
遵循 safe_save_workbook 原子替换铁律。
"""
import os
import sys
import json
import shutil
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pipeline.relations as R
from pipeline.common import safe_save_workbook

WORKBOOK = os.path.join(ROOT, "workbook", "relations.xlsx")
VERDICTS = os.path.join(HERE, "_rel_evidence_verdicts.json")


def main():
    print("=== 开始执行关系表 rel_id 契约重构与原子迁移 ===")
    wb = openpyxl.load_workbook(WORKBOOK)
    ws_main = wb["relations"] if "relations" in wb.sheetnames else wb.active
    headers_main = [c.value for c in ws_main[1]]
    rid_col = headers_main.index("rel_id") + 1
    a_col = headers_main.index("person_a") + 1
    b_col = headers_main.index("person_b") + 1
    rel_col = headers_main.index("关系(rel)") + 1
    stat_col = headers_main.index("状态(status)") + 1

    mapping = {}
    updated_main = 0

    for row_idx in range(2, ws_main.max_row + 1):
        old_rid = str(ws_main.cell(row=row_idx, column=rid_col).value or "").strip()
        a = str(ws_main.cell(row=row_idx, column=a_col).value or "").strip()
        b = str(ws_main.cell(row=row_idx, column=b_col).value or "").strip()
        rel = str(ws_main.cell(row=row_idx, column=rel_col).value or "").strip()
        if not old_rid or not a or not b or not rel:
            continue
        new_rid = R.rel_id(a, b, rel)
        mapping[old_rid] = new_rid
        if old_rid != new_rid:
            ws_main.cell(row=row_idx, column=rid_col, value=new_rid)
            updated_main += 1

    print(f"1. 主表 relations 迁移：共 {ws_main.max_row - 1} 行，更新 rel_id {updated_main} 行。")

    # 证据子表迁移
    updated_ev = 0
    if R.EV_SHEET in wb.sheetnames:
        ws_ev = wb[R.EV_SHEET]
        headers_ev = [c.value for c in ws_ev[1]]
        ev_rid_col = headers_ev.index("rel_id") + 1
        for row_idx in range(2, ws_ev.max_row + 1):
            old_rid = str(ws_ev.cell(row=row_idx, column=ev_rid_col).value or "").strip()
            if not old_rid:
                continue
            new_rid = mapping.get(old_rid)
            if not new_rid:
                raise RuntimeError(f"子表第 {row_idx} 行的 rel_id {old_rid} 无法在主表中找到映射！")
            if old_rid != new_rid:
                ws_ev.cell(row=row_idx, column=ev_rid_col, value=new_rid)
                updated_ev += 1
        print(f"2. 证据子表 relation_evidence 迁移：共 {ws_ev.max_row - 1} 行，更新 rel_id {updated_ev} 行。")

    # 安全原子保存 Excel
    safe_save_workbook(wb, WORKBOOK)
    print(f"   已安全保存工作簿：{WORKBOOK}")

    # 3. 迁移 pipeline/_rel_evidence_verdicts.json
    if os.path.exists(VERDICTS):
        shutil.copy2(VERDICTS, VERDICTS + ".bak")
        with open(VERDICTS, encoding="utf-8") as f:
            v_data = json.load(f)
        new_v_data = {}
        updated_v = 0
        for k, v in v_data.items():
            if k.startswith("_"):
                new_v_data[k] = v
            else:
                new_k = mapping.get(k, k)
                if new_k != k:
                    updated_v += 1
                new_v_data[new_k] = v
        with open(VERDICTS, "w", encoding="utf-8") as f:
            json.dump(new_v_data, f, ensure_ascii=False, indent=2)
        print(f"3. 判定配置 _rel_evidence_verdicts.json 迁移：更新键 {updated_v} 个。")

    print("=== rel_id 契约重构与原子迁移完成 ===")


if __name__ == "__main__":
    main()
