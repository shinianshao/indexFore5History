# -*- coding: utf-8 -*-
"""类传/附传补人计划的落地前清洗：剔噪声名、避 pid 冲突。

用法：python pipeline/_class_fill_prep.py <in.json> <out.json>

剔除依据（全部为人工核对原文后判定的误抽）：
- 豐校文：原文「使司空甄豐校文字部」→ 甄豐 是人名，「校文字部」是动宾，不是人名。
- 尹防：原文「儁生京兆尹防，字建公」→ 京兆尹 是官名，人是 防（司馬防，已在典）。
- 陽鴻：原文「中山觟陽鸿，字孟孫」→ 姓 觟陽，截成了后两字。
- 安孫遂：原文「文、景間，安孫遂字伯紀」→ 安孫 是「田安之孫」，人是 遂，不立三字名。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"

DROP = {"豐校文", "尹防", "陽鴻", "安孫遂"}


def used_pids() -> set[str]:
    txt = BD.read_text(encoding="utf-8")
    return set(re.findall(r'"(p_[0-9a-zA-Z_]+)"', txt))


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src
    plan = json.loads(src.read_text(encoding="utf-8"))

    used = used_pids()
    dropped = []
    renamed = []
    seen_pid: set[str] = set()
    out = []
    for r in plan.get("new") or []:
        if r["name_trad"] in DROP:
            dropped.append(r["name_trad"])
            continue
        pid = r["pid"]
        if pid in used or pid in seen_pid:
            n = 0
            while f"{pid}r{n}" in used or f"{pid}r{n}" in seen_pid:
                n += 1
            new_pid = f"{pid}r{n}"
            renamed.append((pid, new_pid))
            r["pid"] = new_pid
            pid = new_pid
        seen_pid.add(pid)
        out.append(r)

    dst.write_text(
        json.dumps({"new": out, "alias": plan.get("alias") or []},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"剔除噪声 {len(dropped)}：{'、'.join(dropped)}")
    print(f"pid 改名 {len(renamed)}：{renamed}")
    print(f"最终候选 {len(out)} -> {dst}")


if __name__ == "__main__":
    main()
