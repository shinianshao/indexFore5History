# -*- coding: utf-8 -*-
"""统一清除五书残留假人名，并补韩遂。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"

DROP_EXACT = {
    "時人號", "时人号", "羊萬餘", "羊万余",
    "公子書", "公子书",
    "王子守", "公孫守", "公孙守",
}


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    dropped = 0
    for line in lines:
        drop = False
        if line.strip().startswith("("):
            m = re.search(r"'p_x[^']*',\s*'([^']+)'", line)
            if m and m.group(1) in DROP_EXACT:
                drop = True
        if drop:
            dropped += 1
            continue
        out.append(line)
    text = "".join(out)

    # 补 韓遂（三国志/后汉书常见，原先只误收了「韓遂等」）
    if '"p_hansui"' not in text and "'p_hansui'" not in text:
        marker = "\n# ===== 散见人物批量补齐"
        entry = (
            "\n# 韓遂（误收「韓遂等」清理后补正）\n"
            "PERSONS.extend([\n"
            '    ("p_hansui", "韩遂", "韓遂", "东汉", "凉州军阀", "字文约，与马腾等起兵。", ["韓遂", "文約", "文约"]),\n'
            "])\n"
        )
        if marker in text:
            text = text.replace(marker, entry + marker, 1)
        else:
            text += entry
        # books
        for table in ("PERSON_BOOKS_HHS", "PERSON_BOOKS_SGZ", "PERSON_BOOKS_JS"):
            m = re.search(rf"^({table}\s*=\s*\{{)", text, re.M)
            if not m:
                continue
            start = m.end()
            depth, i = 1, start
            while i < len(text) and depth:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            end = i - 1
            block = text[start:end]
            if '"p_hansui"' not in block:
                book = {"PERSON_BOOKS_HHS": "hhs", "PERSON_BOOKS_SGZ": "sgz", "PERSON_BOOKS_JS": "js"}[table]
                block = block + f'    "p_hansui": ["{book}"],\n'
                text = text[:start] + block + text[end:]

    BD.write_text(text, encoding="utf-8")
    print("dropped", dropped, "hansui", "p_hansui" in text)


if __name__ == "__main__":
    main()
