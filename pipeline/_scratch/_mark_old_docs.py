# -*- coding: utf-8 -*-
"""给 docs/01–18 加「历史档案」横幅（内容一字不动，只在最前面加一段）。

为什么要它
----------
`docs/01–18` 是 2026-09 及更早的推演记录，里面的**规模数字互相打架**
（句数 / 人数 / 命中数每个阶段都不同）。项目里已经形成口头规矩
「别读 01–18，看 30/31/DEV.md」，但**规矩只写在 MEMORY.md 里**——
打开这些文档的人看不见它，看不出自己读到的是过时数字。

所以：不改内容（推演过程有史料价值），只在最前面挂一块牌子，
把人指到当前的事实源去。

⚠️ **docs/17 整批跳过**：它不是推演记录，是**还在用的流程模板与人工判定清单**
（`17-待办-人工判断清单.md` 被 `.mimocode/skills/person-alias-coverage` 引用；
`17-条目-*.md` 是生成器产出、等着人勾的清单）。给它挂「历史档案」是错的。

用法
----
    python pipeline/_scratch/_mark_old_docs.py            # 预演（列出会改哪些）
    python pipeline/_scratch/_mark_old_docs.py --apply    # 真写
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOCS = os.path.join(ROOT, "docs")

MARK = "> ⚠️ **本文是历史档案（2026-09 及更早）。**"

BANNER = (
    "> ⚠️ **本文是历史档案（2026-09 及更早），里面的规模数字与结论可能已过时。**\n"
    "> 当前状态看 `docs/31-交接文档-*.md`（还欠什么）与 `app/DEV.md`（施工入口）；\n"
    "> 规模盘点看 `docs/30`。**本文保留的是当时的推演过程**，不是事实源。\n"
    "\n"
)


def main() -> int:
    apply = "--apply" in sys.argv
    todo, kept = [], []
    for name in sorted(os.listdir(DOCS)):
        if not name.endswith(".md"):
            continue
        num = name.split("-", 1)[0]
        if not (num.isdigit() and 1 <= int(num) <= 18):
            continue
        if num == "17":          # 流程模板 + 待勾清单，仍在用，别标成档案
            kept.append(name + "（docs/17 跳过：仍在用）")
            continue
        path = os.path.join(DOCS, name)
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        if MARK in text[:400]:          # 已经挂过牌子
            kept.append(name)
            continue
        todo.append(name)
        if apply:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(BANNER + text)
    print("会加横幅 {} 份{}".format(len(todo), "" if apply else "（预演，未写）"))
    for n in todo:
        print("  + " + n)
    if kept:
        print("已有横幅 {} 份（跳过）".format(len(kept)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
