# -*- coding: utf-8 -*-
"""清掉假人名（官职残片/地名/数量词），并收紧晋书裸「武帝」候选。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BD = ROOT / "pipeline" / "build_dict.py"

# 明确非人
DROP_PIDS = {
    "p_x09732", "p_x23407", "p_x83463", "p_x14575", "p_x57975", "p_x29786",
    "p_x68578", "p_x44747", "p_x98734", "p_x67793",  # *刺 官职残片
    "p_x47548", "p_x48634", "p_x67082", "p_x98924", "p_x80138",  # 郡 地名
    "p_x92369",  # 金銀
    "p_x08564", "p_x09123",  # 騎二萬/五千
    "p_x02179",  # 言於帝
    "p_x43697",  # 王子侯（表名）
    "p_x54340",  # 公孫帝
    "p_x91132",  # 吳郡太
    "p_x49809",  # 樂平（多为地名/封号）
    # 裸封号单人 core → 删掉（泛称已有/或过险）
    "p_x67012", "p_x51391", "p_x51790", "p_x17430", "p_x87180", "p_x89492",
    "p_x83010", "p_x29634", "p_x75953", "p_x16447", "p_x94724", "p_x50440",
    "p_x20031", "p_x18262",
}


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
        if drop:
            dropped += 1
            continue
        out.append(line)
    text = "".join(out)

    # 晋书裸「武帝」：不收汉武帝（追述用「漢武帝」长形）
    text = text.replace(
        '"js": ["p_simayan", "p_shihu", "p_liucong", "p_hanwudi"],',
        '"js": ["p_simayan", "p_shihu", "p_liucong"],',
    )
    # 孝武帝 js 同理：裸称=司马曜；汉武帝用长名
    text = text.replace(
        '"js": ["p_simayao", "p_hanwudi"],',
        '"js": ["p_simayao"],',
    )
    BD.write_text(text, encoding="utf-8")
    print("dropped", dropped)


if __name__ == "__main__":
    main()
