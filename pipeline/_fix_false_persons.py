# -*- coding: utf-8 -*-
"""系统清除假人名：截断官职、地名、带等、书名/词组。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"

# 用户报 + 扫描确认的假名（整行删）
DROP_EXACT = {
    "樂浪", "乐浪", "樂浪太", "乐浪太",
    "越騎校", "越骑校", "步兵校", "東羌校", "东羌校",
    "尚方", "尚于黎", "尚於黎",
    "廣陵太", "广陵太",
    "韓遂等", "韩遂等", "韓遂作", "韩遂作",
    "江京等", "郭汜等", "鄧颺等", "邓飏等", "王甫等", "段珪等",
    "朱蓋等", "朱盖等", "王臧等", "全懌等", "全怿等", "孟舒等",
    "趙胤等", "赵胤等", "車紐等", "车纽等", "霍鴻等", "霍鸿等",
    "戴羲等", "終帶等", "终带等", "郭默等", "陳達等", "陈达等",
    # 书名/词组/数量/地名误收
    "左氏傳", "左氏传", "周官", "毛詩", "毛诗", "穀梁春",
    "國政", "国政", "萬餘騎", "万余骑", "萬餘級", "万余级",
    "都長安", "都长安", "先零羌", "金紫光", "國子祭", "国子祭",
    "國子博", "国子博", "相與謀", "相与谋", "終不肯", "终不肯",
    "能直言", "時人稱", "时人称",
    "蒼梧", "苍梧", "華陽", "华阳", "祁山", "陽關", "阳关",
    "胡陵", "魏興", "魏兴", "東關", "东关", "義興", "义兴",
    "衡陽", "衡阳", "漢昌", "汉昌",
    # 更多词组/书名/截断
    "穀梁傳", "谷梁传", "公羊傳", "公羊传", "將萬騎", "将万骑",
    "言於興", "言于兴", "漢與楚", "汉与楚", "濟之間", "济之间",
    "何不速", "言大水", "衡山謀", "衡山谋", "宋之社", "曹等俱",
    "灌之屬", "灌之属", "蔡流言", "韓之邊", "韩之边", "魏之郊",
    "公子政", "王子騎", "王子骑",
}

# 形态规则：X太 / X校 / X等（截断官职、列表缀）——「向長/鄭太」等真人名不在此列
DROP_NAME_RE = re.compile(
    r"^[^等]{1,4}太$"          # 東郡太 / 汝南太（广陵太守截断）
    r"|^[^等]{1,4}校$"         # 越騎校 / 步兵校
    r"|^[^等]{1,6}等$"         # 韓遂等
)


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    dropped = 0
    for line in lines:
        drop = False
        if line.strip().startswith("(") and ("各书提及人物" in line or "散见" in line or "散見" in line):
            m = re.search(r"'([^']+)',\s*'([^']+)'", line)
            if m:
                name = m.group(2)
                if name in DROP_EXACT or DROP_NAME_RE.match(name):
                    drop = True
        if not drop and line.strip().startswith("("):
            m = re.search(r"'p_x[^']*',\s*'([^']+)'", line)
            if m and (m.group(1) in DROP_EXACT or DROP_NAME_RE.match(m.group(1))):
                drop = True
        if drop:
            dropped += 1
            continue
        out.append(line)
    # 顺带清 PERSON_BOOKS 里已删 pid（按名字反查太麻烦，只清已知模式 pid 不必要）
    BD.write_text("".join(out), encoding="utf-8")
    print("dropped lines", dropped)


if __name__ == "__main__":
    main()
