# -*- coding: utf-8 -*-
"""第四轮修补：书作用域、裸将军别名、陈王/关内侯泛称、基线与断言。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BD = ROOT / "pipeline" / "build_dict.py"
VR = ROOT / "pipeline" / "verify.py"

text = BD.read_text(encoding="utf-8")

# 1) PERSON_BOOKS 补作用域
if '"p_liuxian_hhs": ["hhs"]' not in text:
    text = text.replace(
        'PERSON_BOOKS_HHS = {\n    "p_liuxiu": ["hhs"],',
        'PERSON_BOOKS_HHS = {\n'
        '    "p_liuxian_hhs": ["hhs"],\n'
        '    "p_liuxiu": ["hhs"],',
        1,
    )
    print("scoped p_liuxian_hhs")

if "PERSON_BOOKS_HHS" in text and '"p_liuze"' not in text.split(
    "PERSON_BOOKS_HHS", 1
)[-1][:8000]:
    # liuze 不在任何表 → 全局。加进一个三书表：用 HS 表末尾扩 sj/hs/hhs 不合适。
    # 新增小表并挂进 main——已有 SJ 钩子，可扩展为通用。
    if "PERSON_BOOKS_LIUZE" not in text:
        inject = (
            "# 刘泽：西汉宗室，琅邪王/燕王不应进三国志。\n"
            'PERSON_BOOKS_LIUZE = {\n    "p_liuze": ["sj", "hs", "hhs"],\n}\n\n'
        )
        text = text.replace(
            "# ===== 《三国志》人物书作用域 =====",
            inject + "# ===== 《三国志》人物书作用域 =====",
            1,
        )
    if "if pid in PERSON_BOOKS_LIUZE:" not in text:
        text = text.replace(
            "        if pid in PERSON_BOOKS_SJ:",
            "        if pid in PERSON_BOOKS_LIUZE:\n"
            '            persons[-1]["books"] = list(PERSON_BOOKS_LIUZE[pid])\n'
            "        if pid in PERSON_BOOKS_SJ:",
            1,
        )
    print("scoped p_liuze")

# 2) 剥裸将军/关内侯别名（title 保留）
BARE2 = {
    "偏將軍", "偏将军", "前將軍", "前将军", "後將軍", "后将军",
    "關內侯", "关内侯", "關内侯",
}


def strip_list(line: str) -> str:
    m = re.search(r"\[([^\]]*)\]", line)
    if not m:
        return line
    parts = re.findall(r'"([^"]+)"', m.group(1))
    kept = [p for p in parts if p not in BARE2]
    if len(kept) == len(parts):
        return line
    return line[: m.start()] + "[" + ", ".join(f'"{p}"' for p in kept) + "]" + line[m.end() :]


lines = text.splitlines(keepends=True)
out = []
n_strip = 0
for line in lines:
    if re.match(r'\s*\("p_', line):
        new = strip_list(line)
        if new != line:
            n_strip += 1
        line = new
    out.append(line)
text = "".join(out)
print("stripped bare2 lines", n_strip)

# 3) GENERIC_MANUAL：陳王、關內侯
if '"陳王":' not in text:
    text = text.replace(
        '    "宣帝": ["p_hanxuandi", "p_simayi"],\n}',
        '    "宣帝": ["p_hanxuandi", "p_simayi"],\n'
        '    # 陈王：魏陈思王曹植 / 东汉陈敬王刘羡——按书作用域+篇主分开。\n'
        '    "陳王": ["p_caozhi", "p_liuxian_hhs"],\n'
        '    # 关内侯：庞德/黄忠（三国）与萧望之（西汉）多挂。\n'
        '    "關內侯": ["p_pangde", "p_huangzhong", "p_xiaowangzhi"],\n}',
        1,
    )
    print("GENERIC_MANUAL +陳王/關內侯")

if '"陳王": "p_caozhi"' not in text:
    text = text.replace(
        '    "武帝": "p_hanwudi",\n}',
        '    "武帝": "p_hanwudi",\n'
        '    "陳王": "p_caozhi",\n'
        '    "關內侯": "p_pangde",\n}',
        1,
    )

BD.write_text(text, encoding="utf-8")

# 4) verify 基线收紧 + 断言
vr = VR.read_text(encoding="utf-8")
old = """        if bk == "sj":
            floor = 0.75
        elif bk == "hs":
            floor = 0.60
        elif bk == "sgz":
            # 篇主补满后仍约 7%；挡住「完全无消歧」并略高于 5% 临时线
            floor = 0.07
        else:
            # 后汉书：实测 40%，从临时 10% 收紧到 35%
            floor = 0.35"""
new = """        if bk == "sj":
            floor = 0.75
        elif bk == "hs":
            floor = 0.70
        elif bk == "sgz":
            # 篇主补满 + 裸官名剥离 + 帝号泛称后约 9%
            floor = 0.09
        else:
            # 后汉书：实测约 50%
            floor = 0.45"""
if old in vr:
    vr = vr.replace(old, new, 1)
    print("verify floors updated")
else:
    # try looser replace on floors only
    vr2 = vr
    vr2 = re.sub(r"(elif bk == \"hs\":\s*\n\s+floor = )0\.60", r"\g<1>0.70", vr2)
    vr2 = re.sub(r"(elif bk == \"sgz\":[\s\S]*?floor = )0\.07", r"\g<1>0.09", vr2)
    vr2 = re.sub(r"(else:\s*\n\s+# 后汉书[^\n]*\n\s+floor = )0\.35", r"\g<1>0.45", vr2)
    if vr2 != vr:
        vr = vr2
        print("verify floors regex updated")
    else:
        print("WARN verify floors pattern not found")

# 追加断言（在最后一个 cases.append 附近插入，用零命中后）
if "sgz 文帝" not in vr and "文帝→曹丕" not in vr:
    # find a stable insertion point: after 零命中人物 assertion block
    anchor = 'cases.append(("零命中人物 ≤ 3"'
    if anchor in vr:
        inject = (
            "    # —— 本轮：sgz 官名/帝号/启 错挂回归 ——\n"
            "    wen = [m for m in DATA[\"sentences\"]\n"
            "            if m[\"chapterId\"].startswith(\"sgz-\")\n"
            "            for x in m.get(\"marks\", [])\n"
            "            if x.get(\"alias\") == \"文帝\"]\n"
            "    wen_pids = {x[\"pid\"] for x in wen}\n"
            "    cases.append((\"sgz 文帝只归曹丕（不是司马昭）\",\n"
            "                  bool(wen) and wen_pids == {\"p_caopi\"},\n"
            "                  \"n={} pids={}\".format(len(wen), sorted(wen_pids))))\n"
            "    qi_sgz = sum(\n"
            "        1 for m in DATA[\"sentences\"]\n"
            "        if m[\"chapterId\"].startswith(\"sgz-\")\n"
            "        for x in m.get(\"marks\", [])\n"
            "        if x.get(\"pid\") == \"p_qi\"\n"
            "    )\n"
            "    cases.append((\"夏后启不在三国志命中\",\n"
            "                  qi_sgz == 0, \"sgz={}\".format(qi_sgz)))\n"
            "    cheng = [x for m in DATA[\"sentences\"]\n"
            "             if m[\"chapterId\"].startswith(\"sgz-\")\n"
            "             for x in m.get(\"marks\", [])\n"
            "             if x.get(\"alias\") in (\"丞相\", \"太尉\", \"司徒\", \"太傅\", \"侍中\")]\n"
            "    cases.append((\"sgz 无裸官名 core 命中（丞相/太尉/…）\",\n"
            "                  len(cheng) == 0, \"残留 {}\".format(len(cheng))))\n"
        )
        vr = vr.replace(anchor, inject + "    " + anchor, 1)
        print("verify assertions injected")
    else:
        print("WARN no anchor for assertions")

VR.write_text(vr, encoding="utf-8")
print("done")
