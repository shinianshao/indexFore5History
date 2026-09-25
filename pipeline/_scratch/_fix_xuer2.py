# -*- coding: utf-8 -*-
"""删掉「青徐二州」类被截成假人名的条目。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BD = ROOT / "pipeline" / "build_dict.py"

# 州部连称 / 「X二州」截断，不是人名
DROP_PIDS = {
    "p_x34546",  # 徐二州（青徐二州）
    "p_x86765",  # 徐兗二（徐兗二州）
    "p_x67318",  # 益二州
    "p_x14713",  # 梁二州
    "p_x29988",  # 冀二州
    "p_x08779",  # 雍二州
    "p_x25510",  # 冀四州
    "p_x77193",  # 江二州
    "p_x32703",  # 雍六州
    "p_x30837",  # 東海二
    "p_x20464",  # 江三州
    "p_x13828",  # 荊二州
}
DROP_NAME_RE = re.compile(
    r"^(?:[徐揚扬荊青益秦雍梁兗豫冀江東海][徐揚扬荊青益秦雍梁兗豫冀江]?)"
    r"(?:[二三四五六七八九十]州|[二三四五六七八九十]|[兗冀豫])$"
)


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    dropped = 0
    for line in lines:
        drop = False
        for pid in DROP_PIDS:
            if f"'{pid}'" in line or f'"{pid}"' in line:
                if line.strip().startswith("(") or re.match(
                    r'\s*["\']' + pid + r'["\']\s*:', line
                ):
                    drop = True
                    break
        if not drop and line.strip().startswith("(") and "各书提及人物" in line:
            m = re.search(r"'([^']+)',\s*'([^']+)'", line)
            if m and DROP_NAME_RE.search(m.group(2)):
                drop = True
        if drop:
            dropped += 1
            continue
        out.append(line)
    BD.write_text("".join(out), encoding="utf-8")
    print("dropped lines", dropped)


if __name__ == "__main__":
    main()
