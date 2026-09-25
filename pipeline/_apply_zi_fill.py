# -*- coding: utf-8 -*-
"""把 _zi_ok.json 里的「可补」表字写进 build_dict.py 的别名表。

只写 **ok** 那一档（同句共现 ≥2 且共现率 ≥0.7）；**low** 档不写，
那批要靠人工/AI 逐条判（见 docs/17-条目-表字长尾.md）。

用法：python pipeline/_apply_zi_fill.py [plan.json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"
plan_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "pipeline" / "_zi_ok.json"
PLAN = json.loads(plan_path.read_text(encoding="utf-8"))

try:
    from opencc import OpenCC
    t2s = OpenCC("t2s")
except Exception:
    t2s = None


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    written, skipped = [], []
    for row in PLAN.get("ok") or []:
        pid, zi = row["pid"], row["zi"]
        forms = [zi]
        s = t2s.convert(zi) if t2s else zi
        if s != zi:
            forms.append(s)
        hit = False
        for i, line in enumerate(lines):
            # PERSONS 主表用双引号，批量补齐块用单引号——两种都要认
            if not re.match(r"\s*\(['\"]p_", line):
                continue
            if "'{}'".format(pid) not in line and '"{}"'.format(pid) not in line:
                continue
            m = re.search(r"\[([^\]]*)\]", line)
            if not m:
                continue
            cur = re.findall(r'"([^"]+)"', m.group(1))
            added = [f for f in forms if f not in cur]
            if not added:
                skipped.append(row["name"] + "·" + zi + "（已在）")
                hit = True
                break
            new_list = "[" + ", ".join('"{}"'.format(x) for x in cur + added) + "]"
            lines[i] = line[: m.start()] + new_list + line[m.end():]
            written.append("{}·{}".format(row["name"], zi))
            hit = True
            break
        if not hit:
            skipped.append(row["name"] + "·" + zi + "（找不到行）")

    BD.write_text("".join(lines), encoding="utf-8")
    print("写入 {} 条：{}".format(len(written), "、".join(written)))
    if skipped:
        print("跳过 {} 条：{}".format(len(skipped), "、".join(skipped)))


if __name__ == "__main__":
    main()
