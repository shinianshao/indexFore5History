# -*- coding: utf-8 -*-
"""修复 sgz 官名错挂 + 夏后启单字误伤。

1. 剥掉 PERSONS 行里裸官名别名（title 字段保留作展示）。
2. p_qi 挂 PERSON_BOOKS_SJ = ["sj"]，单字「啟」只在史记匹配。
3. annotate.SINGLE_CHAR_PRE 给「啟」加前接守卫（防史记内部部分误伤）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"
AN = ROOT / "pipeline" / "annotate.py"

BARE_OFFICES = {
    "丞相", "相國", "相国", "司徒", "司空", "太尉", "太傅", "太保",
    "侍中", "太常", "光祿勳", "光禄勋", "光祿大夫", "光禄大夫",
    "衛尉", "卫尉", "大司農", "大司农", "大鴻臚", "大鸿胪",
    "大司馬", "大司马", "大將軍", "大将军",
    "車騎將軍", "车骑将军", "驃騎將軍", "骠骑将军",
    "衛將軍", "卫将军", "撫軍將軍", "抚军将军",
    "尚書令", "尚书令", "尚書", "尚书", "中書令", "中书令",
    "中書監", "中书监", "廷尉", "司隸校尉", "司隶校尉",
    "太僕", "太仆", "左僕射", "左仆射", "右僕射", "右仆射",
    "御史大夫", "奉常", "大理", "郎中令",
}


def strip_build_dict() -> int:
    lines = BD.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    changed = 0
    for line in lines:
        if re.match(r'\s*\("p_', line):
            m = re.search(r"\[([^\]]*)\]", line)
            if m:
                parts = re.findall(r'"([^"]+)"', m.group(1))
                kept = [p for p in parts if p not in BARE_OFFICES]
                if len(kept) != len(parts):
                    new_list = "[" + ", ".join(f'"{p}"' for p in kept) + "]"
                    line = line[: m.start()] + new_list + line[m.end() :]
                    changed += 1
        out.append(line)
    text = "".join(out)

    # PERSON_BOOKS_SJ for p_qi
    if "PERSON_BOOKS_SJ" not in text:
        inject = (
            "# 夏后启：单字「啟」在三国/晋正文常是「开启」义，书作用域钉史记。\n"
            "# 多字别名（夏后啟/帝啟）仍写在 PERSONS 里，跨书只靠多字命中。\n"
            "PERSON_BOOKS_SJ = {\n    \"p_qi\": [\"sj\"],\n}\n\n"
        )
        anchor = "# ===== 《三国志》人物书作用域 ====="
        if anchor in text:
            text = text.replace(anchor, inject + anchor, 1)
        else:
            text = text.replace(
                "PERSON_BOOKS_SGZ = {",
                inject + "PERSON_BOOKS_SGZ = {",
                1,
            )

    if "if pid in PERSON_BOOKS_SJ:" not in text:
        needle = "        if pid in PERSON_BOOKS_HS:"
        if needle in text:
            text = text.replace(
                needle,
                "        if pid in PERSON_BOOKS_SJ:\n"
                '            persons[-1]["books"] = list(PERSON_BOOKS_SJ[pid])\n'
                + needle,
                1,
            )
        else:
            raise SystemExit("cannot hook PERSON_BOOKS_SJ")

    BD.write_text(text, encoding="utf-8")
    return changed


def patch_annotate() -> None:
    ant = AN.read_text(encoding="utf-8")
    if '"啟"' in ant and "SINGLE_CHAR_PRE" in ant:
        # already has entry?
        if re.search(r'"啟"\s*:\s*set\(', ant):
            print("annotate 啟 PRE already present")
            return
    if 'SINGLE_CHAR_PRE = {' not in ant:
        raise SystemExit("no SINGLE_CHAR_PRE")
    ant = ant.replace(
        'SINGLE_CHAR_PRE = {',
        'SINGLE_CHAR_PRE = {\n'
        '    # 「啟」：前接开启/否定等，不是夏后启（首啟/大啟/啟閉/不憤不啟…）\n'
        '    "啟": set("首大不憤閉時並難也無未將既欲可足自深廣高發思惟興道治成\n'
        '               進出終本輕重緩急深淺大小遠近強弱厚薄新故今古來往上下\n'
        '               左右前後內外表裏精粗源流標本先后條貫綱紀制度文武帝王\n'
        '               聖賢善惡安危成敗廢得失處窮通利害禍福吉凶祥災瑞符命\n'
        '               革除興啟創基業垂統緒胤嗣胄裔苗裔枝葉根本末節\n'
        '               ".replace(" ", "").replace("\\n", "")),\n',
        1,
    )
    AN.write_text(ant, encoding="utf-8")
    print("annotate.py 啟 PRE patched")


def main() -> None:
    n = strip_build_dict()
    print("stripped office alias lines:", n)
    patch_annotate()


if __name__ == "__main__":
    main()
