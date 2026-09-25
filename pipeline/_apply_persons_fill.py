# -*- coding: utf-8 -*-
"""把 _persons_fill_plan.json 写入 build_dict.py。

- new → 追加 PERSONS.extend 块 + PERSON_BOOKS_* 对应书作用域
- alias → 给既有 pid 的别名表追加繁体形，并扩 books 并集
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"
# 计划文件可换（默认散见补齐；类传/附传用 _gen_class_fill.py 产出的计划）
_plan_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    ROOT / "pipeline" / "_persons_fill_plan.json"
PLAN = json.loads(_plan_path.read_text(encoding="utf-8"))

BOOKS_TABLE = {
    "sj": "PERSON_BOOKS_SJ",
    "hs": "PERSON_BOOKS_HS",
    "hhs": "PERSON_BOOKS_HHS",
    "sgz": "PERSON_BOOKS_SGZ",
    "js": "PERSON_BOOKS_JS",
}


def parse_alias_list(line: str) -> list[str] | None:
    m = re.search(r"\[([^\]]*)\]", line)
    if not m:
        return None
    return re.findall(r'"([^"]+)"', m.group(1))


def format_alias_list(items: list[str]) -> str:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return "[" + ", ".join(f'"{x}"' for x in out) + "]"


def merge_books_into_tables(text: str, pid: str, books: list[str]) -> str:
    """把 pid 的 books 并进各 PERSON_BOOKS_* 表（并集，不覆盖）。"""
    for b in books:
        table = BOOKS_TABLE[b]
        # 找到表定义块，在末尾前插入/合并
        # 简化：若表里已有该 pid 行则扩展列表，否则在表的 `}` 前插入
        m = re.search(rf"^({table}\s*=\s*\{{)", text, re.M)
        if not m:
            continue
        # 找该表的结束 `}` —— 从 m.end() 起配对
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        end = i - 1  # closing }
        block = text[start:end]
        # 已有 pid？
        pat = rf'("{pid}"\s*:\s*\[)([^\]]*)(\])'
        mm = re.search(pat, block)
        if mm:
            existing = re.findall(r'"([^"]+)"', mm.group(2))
            merged = existing[:]
            for b2 in books:
                if b2 not in merged:
                    merged.append(b2)
            new_list = "[" + ", ".join(f'"{x}"' for x in merged) + "]"
            # 替换整段
            new_block = block[: mm.start()] + f'"{pid}": ' + new_list + block[mm.end() :]
            text = text[:start] + new_block + text[end:]
        else:
            insert = f'    "{pid}": [{", ".join(chr(34)+x+chr(34) for x in books)}],\n'
            # 插在表块末尾（closing 前）
            text = text[:end] + insert + text[end:]
    return text


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    n_alias = 0
    n_alias_form = 0
    # 合并启发不可靠：仅当 form 含该人繁名/或该人繁名含 form 时才写入
    for row in PLAN.get("alias") or []:
        pid, form = row["pid"], row["form"]
        # 在 build_dict 里找该 pid 的繁名
        trad = None
        for line in lines:
            if f'"{pid}"' in line and re.match(r'\s*\("p_', line):
                m = re.match(r'\s*\("p_[^"]+",\s*"([^"]*)",\s*"([^"]*)"', line)
                if m:
                    trad = m.group(2)
                break
        if not trad or (form not in trad and trad not in form):
            continue
        hit = False
        for i, line in enumerate(lines):
            if not re.match(r'\s*\("p_', line):
                continue
            if f'"{pid}"' not in line:
                continue
            al = parse_alias_list(line)
            if al is None:
                continue
            if form not in al:
                al = al + [form]
                m = re.search(r"\[([^\]]*)\]", line)
                lines[i] = line[: m.start()] + format_alias_list(al) + line[m.end() :]
                n_alias_form += 1
            hit = True
            break
        if hit:
            n_alias += 1
        text_tmp = "".join(lines)
        text = merge_books_into_tables(text_tmp, pid, row.get("books") or [])
        lines = text.splitlines(keepends=True)

    # ---- 新人物 ----
    new_rows = PLAN.get("new") or []
    if new_rows:
        try:
            from opencc import OpenCC
            t2s = OpenCC("t2s")
        except Exception:
            t2s = None
        block = ["\n# ===== 散见人物批量补齐（_gen_persons_fill.py，勿手改）=====\nPERSONS.extend([\n"]
        for r in new_rows:
            aliases = list(r.get("aliases_trad") or [])
            if r["name_trad"] not in aliases:
                aliases = [r["name_trad"]] + aliases
            alias_lit = ", ".join(f'"{a}"' for a in aliases)
            name_simp = t2s.convert(r["name_trad"]) if t2s else r["name_trad"]
            block.append(
                '    ({pid!r}, {name!r}, {trad!r}, {dyn!r}, {title!r}, {summ!r}, [{alias}]),\n'.format(
                    pid=r["pid"],
                    name=name_simp,
                    trad=r["name_trad"],
                    dyn=r["dynasty"],
                    title=r["title"],
                    summ=r["summary"],
                    alias=alias_lit,
                )
            )
        block.append("])\n")
        # 插在 GENERIC_CORES 之前
        marker = "\n# 手工声明的泛称"
        if marker not in text:
            marker = "\nGENERIC_MANUAL = {"
        idx = text.find(marker)
        if idx < 0:
            text = text + "\n" + "".join(block)
        else:
            text = text[:idx] + "".join(block) + text[idx:]

    # books tables for new
    for r in new_rows:
        text = merge_books_into_tables(text, r["pid"], r.get("books") or [])

    BD.write_text(text, encoding="utf-8")
    print(f"alias rows={n_alias} forms+={n_alias_form}; new persons={len(new_rows)}")


if __name__ == "__main__":
    main()
