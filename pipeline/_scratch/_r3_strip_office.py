# -*- coding: utf-8 -*-
"""R3：从 build_dict 的 PERSONS 别名剥离裸官职串。

保留：
  - 官+名/官+姓 强专属（丞相斯、大將軍光、飛將軍、蕭相國、賈太傅…）
  - 误报人名（伊尹、李牧）
剥离：
  - 裸官职/军号（含繁简）：破虜將軍、騎都尉、參軍、征西大將軍、陳留太守…
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BD = ROOT / "pipeline" / "build_dict.py"

# —— 必须剥离（裸官职 / 地名+官职）——
STRIP = {
    # 多人共用
    "安汉将军", "安漢將軍",
    "破虏将军", "破虜將軍",
    "荡寇将军", "蕩寇將軍",
    "鎮軍大將軍", "镇军大将军",
    # 单人裸官职（title 可留，aliases 不留）
    "上大将军", "上大將軍",
    "军师祭酒", "軍師祭酒",
    "南郡太守",
    "参军", "參軍",
    "奋威将军", "奮威將軍",
    "威越校尉",
    "安北将军", "安北將軍",
    "征西大将军", "征西大將軍",
    "折冲将军", "折衝將軍",
    "昭德将军", "昭德將軍",
    "昭文将军", "昭文將軍",
    "楼船将军", "樓船將軍",
    "横江将军", "橫江將軍",
    "武卫将军", "武衛將軍",
    "秉忠将军", "秉忠將軍",
    "討逆將軍", "讨逆将军",
    "鎮北將軍", "镇北将军",
    "鎮南大將軍", "镇南大将军",
    "鎮軍將軍", "镇军将军",
    "陈留太守", "陳留太守",
    # 历史遗留裸官职（#C 已剥过，防回流）
    "丞相", "太尉", "太傅", "太保", "司徒", "司空", "侍中",
    "尚書", "尚书", "大將軍", "大将军", "將軍", "将军",
    "太守", "刺史", "騎都尉", "骑都尉", "都尉", "校尉",
    "大司馬", "大司马", "相國", "相国",
}

# —— 明确保留（官+专名，匹配安全）——
KEEP = {
    "丞相斯",  # 李斯
    "大将军光", "大將軍光",  # 霍光
    "太保舜",  # 王舜
    "李将军", "李將軍", "飛將軍", "飞将军",  # 李广
    "萧相国", "蕭相國",  # 萧何
    "曹相国", "曹相國",  # 曹参
    "贾太傅", "賈太傅",  # 贾谊
    "锺太傅", "鍾太傅",  # 锺繇
    "貳師將軍", "贰师将军",  # 李广利
    "伊尹", "李牧",  # 人名误报
    "军师", "軍師",  # 荀攸等作衔；若共用则下一轮再论——先看是否裸
}


def parse_alias_list(line: str):
    m = re.search(r"\[([^\]]*)\]", line)
    if not m:
        return None
    return re.findall(r'"([^"]+)"', m.group(1))


def format_alias_list(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return "[" + ", ".join(f'"{x}"' for x in out) + "]"


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    n_line = n_del = 0
    dropped = []
    for i, line in enumerate(lines):
        if not re.match(r'\s*\("p_', line):
            continue
        al = parse_alias_list(line)
        if not al:
            continue
        keep = []
        for a in al:
            if a in KEEP:
                keep.append(a)
                continue
            if a in STRIP:
                dropped.append(a)
                n_del += 1
                continue
            keep.append(a)
        if len(keep) != len(al):
            m = re.search(r"\[([^\]]*)\]", line)
            lines[i] = line[: m.start()] + format_alias_list(keep) + line[m.end() :]
            n_line += 1
    BD.write_text("".join(lines), encoding="utf-8")
    print(f"改动 {n_line} 行 / 删除别名 {n_del}")
    from collections import Counter
    print("删除明细:", Counter(dropped).most_common(30))


if __name__ == "__main__":
    main()
