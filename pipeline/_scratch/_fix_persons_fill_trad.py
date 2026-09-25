# -*- coding: utf-8 -*-
"""清理散见人物脏条目：去非人/地名/官职残片，繁名修到 to_trad 不动点。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))  # 已移入 _scratch/，补回 pipeline/ 以便导入 common / trad
from trad import to_trad  # noqa: E402

BD = ROOT / "pipeline" / "build_dict.py"

DROP_PIDS = {
    "p_x53755",  # 荊州
    "p_x03939",  # 荊州刺
    "p_x15014",  # 郁林
    "p_x69435",  # 唐咨等
    "p_x52981",  # 弘农太
    "p_x78933",  # 于窴（于阗）
}
RENAME = {
    "p_x04792": ("唐咨", "唐諮"),
    "p_x55993": ("段干木", "段幹木"),
    "p_x56275": ("公子于", "公子於"),
    "p_x21359": ("公子弃", "公子棄"),
    "p_x94926": ("公子爲", "公子為"),
    "p_x41599": ("公孫于", "公孫於"),
    "p_x07455": ("王子于", "王子於"),
    "p_x63464": ("王子择", "王子擇"),
}


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    removed = 0
    for line in lines:
        hit_drop = False
        for pid in DROP_PIDS:
            if f"'{pid}'" in line or f'"{pid}"' in line:
                if line.strip().startswith("(") or re.match(
                    r'\s*["\']' + pid + r'["\']\s*:', line
                ):
                    removed += 1
                    hit_drop = True
                    break
        if hit_drop:
            continue
        for pid, (old, new) in RENAME.items():
            if f"'{pid}'" in line or f'"{pid}"' in line:
                line = line.replace(old, new)
        out.append(line)
    text2 = "".join(out)
    BD.write_text(text2, encoding="utf-8")
    print("removed lines", removed)
    for pid, (o, n) in RENAME.items():
        assert to_trad(n) == n, (pid, n, to_trad(n))
        print(pid, n, "ok")
    for pid in DROP_PIDS:
        print("drop", pid, "left", pid in text2)


if __name__ == "__main__":
    main()
