# -*- coding: utf-8 -*-
"""关系边的**性别自洽**体检：把「父/母写反」这类内容错挑出来。

为什么需要：断言只能查格式（rel 在不在词表里、有没有 uid），查不出
「驪姬 —父→ 奚齊」这种**内容错**——驪姬是奚齊的母親。
第二次独立审查（docs/28）就是靠人眼抓到「曹操页面显示父曹節」的，
这类错必须有一个机械探针替人眼先扫一遍。

判据（只报**强信号**，不猜）：
- 边起点 a 的性别与 rel 要求的性别冲突时才报（父/兄/子/夫 → a 应男；
  母/女/妻/祖母 → a 应女）。
- a 的性别用 `db.looks_female` 那套关键词 + 名字/称号/简介判断，
  只在**命中**时才下结论，命不中不报（宁可漏，不可瞎改）。

用法：python pipeline/_scratch/_probe_rel_gender.py
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "data", "index", "index.db")
sys.path.insert(0, os.path.join(ROOT, "app", "server"))
import db as DBMOD            # noqa: E402   只为复用 looks_female，不 import 关系规则

# rel → 起点 a 应有的性别
A_MALE = ("父", "祖父", "兄", "子", "夫", "外祖父", "叔", "從兄", "從子")
A_FEMALE = ("母", "祖母", "姐", "女", "妻", "外祖母", "娣", "從姊")


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    info = {}
    for r in conn.execute("SELECT id, name, trad_name, title, summary FROM persons"):
        info[r["id"]] = r

    bad = []
    for r in conn.execute(
            "SELECT rel_id, person_a, surface_a, rel, person_b, surface_b "
            "FROM relations WHERE status='active'"):
        need = ("F" if r["rel"] in A_FEMALE else
                "M" if r["rel"] in A_MALE else "")
        if not need:
            continue
        pa = info.get(r["person_a"])
        pb = info.get(r["person_b"])
        if not pa:
            continue
        # ⚠️ **不能把 summary 喂进去**：「竇太后少子」「寵驪姬」这种简介里
        # 提到的是**别人**，一喂就把梁孝王/晉獻公全判成女性（第一轮就是这样，
        # 8 处里 6 处是假阳性）。只认名字与称号。
        a_f = DBMOD.looks_female(pa["name"], pa["trad_name"], pa["title"] or "")
        # 只在**确定**是女性时才判定冲突；判不出男性（关键词没命中）就跳过
        if need == "M" and a_f:
            bad.append((r, "起点应为男性，但看着是女性",
                        "建议改成 {}".format(
                            {"父": "母", "祖父": "祖母", "子": "女",
                             "兄": "姐", "夫": "妻"}.get(r["rel"], "?"))))
        if need == "F" and not a_f:
            # 反过来：起点应为女性却毫无女性信号 → **弱信号**，只提示
            bad.append((r, "起点应为女性，但无女性信号（弱）", ""))
    print("=== 关系边性别自洽体检 ===")
    if not bad:
        print("  没有冲突（{} 条有向边）".format(
            sum(1 for _ in conn.execute(
                "SELECT 1 FROM relations WHERE status='active'"))))
        return 0
    for r, why, fix in bad:
        pa = info.get(r["person_a"])
        print("  ✗ {} —{}→ {}".format(r["surface_a"], r["rel"], r["surface_b"]))
        print("      {}（{}）　{}".format(
            why, (pa["summary"] or "")[:36], fix))
        print("      rel_id={}".format(r["rel_id"]))
    print("\n  共 {} 处待改".format(len(bad)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
