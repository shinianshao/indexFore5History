# -*- coding: utf-8 -*-
"""挑刺：把 62 条边**站在两端**各显示成什么都打出来，人眼看有没有读反/读不出。

為什麼要有它：P0-1（有向邊全部讀反）是在 [7]/[8]/UI 冒煙**全綠**的情況下存在的。
斷言只能守住「我已經想到的那幾條」，守不住「我沒想到的那幾條」。所以隔一段時間
要把全量顯示串打出來掃一眼——**斷言是網，人眼是最後一道**。

用法
----
    python pipeline/_scratch/_probe_rel_view.py            # 全量
    python pipeline/_scratch/_probe_rel_view.py --only-a   # 只看 a 側

关注三种异常：
- **fallback**：`rel_view == rel` 且该 rel 是非对称的 → CALL_INVERSE 缺词，等于旧 bug
- **性别可疑**：对方明显是女性却读成「子 / 弟 / 姪 / 甥」（looks_female 没认出来）
- **读反**：站在 a 侧却显示「父 / 母 / 兄 / 姊 / 伯叔 / 舅 / 祖父」这类长辈称谓
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # _scratch → pipeline → 根
sys.path.insert(0, os.path.dirname(HERE))              # pipeline/
sys.path.insert(0, os.path.join(ROOT, "app", "server"))
import db                                              # noqa: E402

DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
# 站在 a 侧**不该出现**的称呼（这些是长辈/年长方的头衔，拿去称呼对方就读反了）
ELDER = ("父", "母", "兄", "姊", "伯叔", "姑", "舅", "姨", "祖父", "祖母",
         "養父", "繼母")
# 明显是女性却读成这些 = 性别没认出来
MALE_ONLY = ("子", "弟", "姪", "甥", "孫")


def main() -> int:
    only_a = "--only-a" in sys.argv
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT rel_id, person_a, person_b, rel, symmetric, confidence, "
        "source, era, book FROM relations WHERE status='active' "
        "ORDER BY rel, person_a")]
    conn.close()
    if not rows:
        print("（没有关系数据）")
        return 0

    n_fb = n_elder = n_sex = 0
    for r in rows:
        for side in (["a"] if only_a else ["a", "b"]):
            pid = r["person_a"] if side == "a" else r["person_b"]
            g = db.relations_graph(pid, 1)
            e = next((x for x in g["edges"] if x["rel_id"] == r["rel_id"]), None)
            if not e:
                print("  ✗ {} 在 {} 的一度图里取不到".format(r["rel_id"][:8], pid))
                continue
            view = e["rel_view"]
            other = e["target"] if e["source"] == pid else e["source"]
            prof = next((n for n in g["nodes"] if n["id"] == other), {})
            name = prof.get("name") or other
            flags = []
            # ⚠️ 只有站在 a 侧「照抄 rel」才是错；站在 b 侧本来就该读 rel 本身
            if (side == "a" and view == r["rel"]
                    and r["rel"] in db.CALL_INVERSE and not r["symmetric"]):
                flags.append("站在a侧却照抄rel（读反）")
                n_elder += 1
            if side == "a" and view in ELDER and not r["symmetric"]:
                flags.append("读反：{} 是长辈称谓".format(view))
                n_elder += 1
            if view == r["rel"] and r["rel"] not in db.CALL_INVERSE:
                flags.append("CALL_INVERSE 缺词（退回照抄）")
                n_fb += 1
            if view in MALE_ONLY and db.looks_female(name, ""):
                flags.append("疑似女性却读「{}」".format(view))
                n_sex += 1
            print("  {} {} —{}→ {}（{}侧：{}）{}".format(
                r["rel_id"][:8], e["name_a"] or r["person_a"], r["rel"],
                e["name_b"] or r["person_b"], side, view,
                "　⚠ " + "；".join(flags) if flags else ""))
    print("\n合计 {} 条边，异常：读反 {} / 缺词 {} / 性别可疑 {}".format(
        len(rows), n_elder, n_fb, n_sex))
    return 0


if __name__ == "__main__":
    sys.exit(main())
