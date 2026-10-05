# -*- coding: utf-8 -*-
"""
安全更新 workbook/persons.xlsx：
支持第五类（汉晋宗室）与第六类（春秋诸侯公侯号）
使用 openpyxl 完整保护样式并自检大小
"""
import openpyxl
import os

EXCEL_PATH = "workbook/persons.xlsx"

wb = openpyxl.load_workbook(EXCEL_PATH)
ws = wb["人物"]

# 获取表头映射
headers = [cell.value for cell in ws[1]]
col_map = {name: idx + 1 for idx, name in enumerate(headers)}
print("表头映射:", col_map)

# 待更新实体清单与变更规则
updates = {
    "p_caofang": {
        "aliases_append": ["齊王"],
    },
    "p_simaxing": {
        "aliases_append": ["梁孝王"],
    },
    "p_liuwu": {
        "fields": {"in_js": "FALSE"},
    },
    "p_qijinggong": {
        "aliases_set": "景公|齐景公",
    },
    "p_luyimgong": {
        "aliases_set": "隱公|鲁隐公",
    },
    "p_qinxiaogong": {
        "aliases_set": "孝公|秦孝公",
    },
    "p_zhaowuling": {
        "aliases_append": ["主父", "赵武灵王"],
    },
    "p_zhufuyan": {
        "aliases_append": ["主父"],
    },
    "p_weiwenhou": {
        "aliases_set": "文侯|魏文侯",
    },
}

modified_count = 0
for row_idx in range(2, ws.max_row + 1):
    pid_val = str(ws.cell(row=row_idx, column=col_map["id"]).value or "")
    if pid_val in updates:
        cfg = updates[pid_val]
        alias_col = col_map["别名(竖线分隔)"]
        curr_aliases = str(ws.cell(row=row_idx, column=alias_col).value or "").strip()
        if curr_aliases in ("None", ""):
            alias_list = []
        else:
            alias_list = [a.strip() for a in curr_aliases.split("|") if a.strip()]
        
        # 1. aliases_set
        if "aliases_set" in cfg:
            new_aliases = cfg["aliases_set"]
            ws.cell(row=row_idx, column=alias_col).value = new_aliases
            print(f"[{pid_val}] 设置别名: '{curr_aliases}' -> '{new_aliases}'")
            modified_count += 1
        
        # 2. aliases_append
        if "aliases_append" in cfg:
            for item in cfg["aliases_append"]:
                if item not in alias_list:
                    alias_list.append(item)
            new_aliases = "|".join(alias_list)
            ws.cell(row=row_idx, column=alias_col).value = new_aliases
            print(f"[{pid_val}] 追加别名: '{curr_aliases}' -> '{new_aliases}'")
            modified_count += 1
        
        # 3. fields
        if "fields" in cfg:
            for f_name, f_val in cfg["fields"].items():
                f_col = col_map[f_name]
                old_val = ws.cell(row=row_idx, column=f_col).value
                ws.cell(row=row_idx, column=f_col).value = f_val
                print(f"[{pid_val}] 修改字段 {f_name}: '{old_val}' -> '{f_val}'")
                modified_count += 1

print(f"总计修改条目: {modified_count}")

# 安全保存
wb.save(EXCEL_PATH)
wb.close()

# 校验文件大小
size = os.path.getsize(EXCEL_PATH)
print(f"保存完成，文件大小: {size} 字节")
assert size > 50000, f"文件过小可能损坏: {size}"
print("✓ workbook/persons.xlsx 安全校验通过！")
