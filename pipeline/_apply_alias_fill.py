# -*- coding: utf-8 -*-
"""P1-P3：把 _alias_fill_plan.json 写入 build_dict.py。

- zi → 追加到对应 PERSONS 行的别名列表（繁体，已过滤）
- courtesy → 同上（缺简繁双写时由 OpenCC 推简）
- 太祖/武皇帝/魏武帝 若未进 GENERIC 则补 MANUAL
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"
PLAN = json.loads((ROOT / "pipeline" / "_alias_fill_plan.json").read_text(encoding="utf-8"))


def parse_alias_list(line: str) -> list[str] | None:
    m = re.search(r"\[([^\]]*)\]", line)
    if not m:
        return None
    return re.findall(r'"([^"]+)"', m.group(1))


def format_alias_list(items: list[str]) -> str:
    # 去重保序
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return "[" + ", ".join(f'"{x}"' for x in out) + "]"


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    by_pid: dict[str, list[str]] = {}
    for r in PLAN["zi_add"]:
        by_pid.setdefault(r["pid"], []).append(r["zi"])
    for r in PLAN["courtesy"]:
        if "pid" in r and "error" not in r:
            by_pid.setdefault(r["pid"], []).append(r["form"])

    n_line = 0
    n_add = 0
    missing = []
    for pid, forms in by_pid.items():
        # 命中该 pid 的 PERSONS 行
        hit = False
        for i, line in enumerate(lines):
            if not re.match(r'\s*\("p_', line):
                continue
            if f'"{pid}"' not in line:
                continue
            al = parse_alias_list(line)
            if al is None:
                continue
            before = len(al)
            merged = al + [f for f in forms if f not in al]
            if len(merged) == before:
                hit = True
                break
            # 替换第一个 [] 
            m = re.search(r"\[([^\]]*)\]", line)
            new_line = line[: m.start()] + format_alias_list(merged) + line[m.end() :]
            lines[i] = new_line
            n_line += 1
            n_add += len(merged) - before
            hit = True
            break
        if not hit:
            missing.append(pid)

    text2 = "".join(lines)

    # GENERIC：太祖 / 武皇帝 / 魏武帝
    if '"太祖":' not in text2:
        text2 = text2.replace(
            '    "關內侯": ["p_pangde", "p_huangzhong", "p_xiaowangzhi"],\n}',
            '    "關內侯": ["p_pangde", "p_huangzhong", "p_xiaowangzhi"],\n'
            '    # 追尊/庙号：勿挂单人 core\n'
            '    "太祖": ["p_caocao"],\n'
            '    "魏武帝": ["p_caocao"],\n'
            '    "武皇帝": ["p_hanwudi", "p_caocao"],\n}',
            1,
        )
        print("GENERIC_MANUAL +太祖/魏武帝/武皇帝")

    # 至少一人声明「太祖」「魏武帝」「武皇帝」——挂曹操/汉武帝 aliases 会重复
    # 检查：若太祖不在任何人 aliases，给 caocao 补（但会变 core——必须先进 generic_forms）
    # generic 要求声明存在：把形式挂到 aliases，annotate 会因 generic_forms 跳过 core
    need_declare = []
    for form in ("太祖", "魏武帝", "武皇帝"):
        if f'"{form}"' not in text2.split("GENERIC_MANUAL", 1)[-1][:2000] and False:
            pass
        # 是否已有人声明
        declared = False
        for line in text2.splitlines():
            if re.match(r'\s*\("p_', line) and f'"{form}"' in line:
                declared = True
                break
        if not declared:
            need_declare.append(form)

    if need_declare:
        # 插入到 p_caocao 行
        for i, line in enumerate(lines := text2.splitlines(keepends=True)):
            if re.match(r'\s*\("p_caocao"', line):
                al = parse_alias_list(line) or []
                for f in need_declare:
                    if f not in al:
                        al.append(f)
                m = re.search(r"\[([^\]]*)\]", line)
                lines[i] = line[: m.start()] + format_alias_list(al) + line[m.end() :]
                print("declare on caocao:", need_declare)
                break
        text2 = "".join(lines)

    BD.write_text(text2, encoding="utf-8")
    print("updated lines", n_line, "alias adds", n_add, "missing", missing)


if __name__ == "__main__":
    main()
