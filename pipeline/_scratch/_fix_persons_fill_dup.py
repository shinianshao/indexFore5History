# -*- coding: utf-8 -*-
"""清理批量入典残留：去重复 pid / 错形合并 / 零命中假召回 / 扩跨书 books。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BD = ROOT / "pipeline" / "build_dict.py"

# 1) 整行删除（假召回/重复/零命中且无价值）
DROP_PIDS = {
    "p_x67808",      # 中山哀王 重复 A
    "p_x61094",      # 中山康王 重复 A
    "p_x03710",      # 中山頃王 重复 A
    "p_x22942",      # 公孫瓉 重复 C（保留 _2 或并入瓚）
    "p_x39145",      # 王子俚（城陽孝王子俚 截断）
    "p_x08800", "p_x39146", "p_x39147", "p_x39148",  # 王子即/林/祐/都 若有
    "p_x61759",      # 中山君 泛称性，先删
    "p_liuliang",    # 刘良 全文 0 处（已知残余，暂不入索引）
}
# 王子* 假召回：按名字串再扫一遍
DROP_NAME_SUBSTR = ("王子即", "王子林", "王子祐", "王子都", "王子俚")

# 2) 错形 → 并入既有 pid 的别名（追加到 aliases，删本行）
MERGE_ALIAS = {
    "p_x22942_2": ("p_gongsunzan", "公孫瓉"),  # 公孫瓚 异写
}

# 3) 扩 books：曹丕需覆盖后汉书（獻帝紀「魏王丕稱天子」）
BOOKS_APPEND = {
    "p_caopi": "hhs",
}


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    dropped = 0
    for line in lines:
        raw = line
        drop = False
        for pid in DROP_PIDS:
            if f"'{pid}'" in line or f'"{pid}"' in line:
                if line.strip().startswith("(") or re.match(
                    r'\s*["\']' + pid + r'["\']\s*:', line
                ):
                    drop = True
                    break
        if not drop:
            for name in DROP_NAME_SUBSTR:
                if f"'{name}'" in line and line.strip().startswith("("):
                    drop = True
                    break
        if drop:
            dropped += 1
            continue
        out.append(line)

    text = "".join(out)

    # merge alias into existing person's alias list
    for pid, (target, form) in MERGE_ALIAS.items():
        # 删本 pid 行
        text = re.sub(
            r"[ \t]*\('" + pid + r"'.*\n", "", text
        )
        text = re.sub(
            r"[ \t]*[\"']" + pid + r"[\"']\s*:.*\n", "", text
        )
        # 给 target 追加别名
        pat = re.compile(
            r'(\(\s*"' + target + r'"[^\[]*)(\[[^\]]*\])'
        )
        # PERSONS 行用单引号
        pat2 = re.compile(
            r"(\('" + target + r"',[^\[]*)(\[[^\]]*\])"
        )
        def add_form(m):
            inner = m.group(2)
            if form in inner:
                return m.group(0)
            return m.group(1) + inner[:-1] + (", " if inner != "[]" else "") + f'"{form}"]'
        # try both quote styles
        new_text, n = pat2.subn(add_form, text, count=1)
        if n == 0:
            def add_form2(m):
                inner = m.group(2)
                if form in inner:
                    return m.group(0)
                return m.group(1) + inner[:-1] + (", " if inner != "[]" else "") + f'"{form}"]'
            new_text, n = pat.subn(add_form2, text, count=1)
        text = new_text
        print("merge", pid, "→", target, form, "n=", n)

    # 扩 books 并集
    for pid, book in BOOKS_APPEND.items():
        # 在 PERSON_BOOKS_HHS 表中加/扩
        m = re.search(r"^PERSON_BOOKS_HHS\s*=\s*\{", text, re.M)
        if not m:
            print("no PERSON_BOOKS_HHS")
            continue
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        end = i - 1
        block = text[start:end]
        pat = rf'("{pid}"\s*:\s*\[)([^\]]*)(\])'
        mm = re.search(pat, block)
        if mm:
            items = re.findall(r'"([^"]+)"', mm.group(2))
            if book not in items:
                items.append(book)
            new_list = "[" + ", ".join(f'"{x}"' for x in items) + "]"
            new_block = block[: mm.start()] + f'"{pid}": ' + new_list + block[mm.end():]
        else:
            new_block = block + f'    "{pid}": ["{book}"],\n'
        text = text[:start] + new_block + text[end:]
        print("books+", pid, book)

    BD.write_text(text, encoding="utf-8")
    print("dropped lines", dropped)


if __name__ == "__main__":
    main()
