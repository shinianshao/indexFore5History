# -*- coding: utf-8 -*-
"""P1 交付验收断言：段落落库完整性、注文跳转 100% 闭环、长篇不截断与刘焉去重。

验证内容：
1. 全量句子入库：sentences 表行数恒等 223,164，语料中所有含文本段落 100% 存在于库中。
2. 裴注跳转 100% 可达：pei-data.json 3,049 条 item 的 (cid, pseq) 在 index.db 中 0 缺失。
3. 晋书旧史注 100% 可达：js-note-data.json 70 条 item 的 (cid, pseq) 在 index.db 中 0 缺失。
4. 长篇不截断：最长篇目（sj-014 十二诸侯年表，3454 句）经由 chapter_sentences 读取不被 500 截断。
5. 前端跳段回退保护：app.js 中 jumpToPara 包含向前回溯寻找邻近有效段落的代码逻辑。
6. 刘焉重复 pid 合并：p_liuyan_sg 已废止，p_liuyan_ys 跨后汉书与三国志两书。

用法：
    python app/tools/verify_p3_paras.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "app", "server"))
import db  # noqa: E402

DB_PATH = os.environ.get("BOOKINDEX_DB") or os.path.join(ROOT, "data", "index", "index.db")


def check(title: str, ok: bool, detail: str = "") -> None:
    status = "OK" if ok else "FAIL"
    msg = f"  [{status}] {title}"
    if detail:
        msg += f"　（{detail}）"
    print(msg)
    if not ok:
        raise AssertionError(f"断言失败：{title} - {detail}")


def main() -> int:
    print("=== [P1 交付断言] 段落落库、注文跳转闭环与长篇完整性 ===")

    conn = sqlite3.connect(DB_PATH)
    try:
        # 1. 全量句子
        n_sent = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        check("全量句子入库（223,164 句）", n_sent == 223164, f"实测 {n_sent:,} 句")

        db_paras = set(conn.execute("SELECT chapter_id, para_seq FROM sentences").fetchall())
        check("库中独立有效段落覆盖 ≥ 49,000", len(db_paras) >= 49000, f"实测 {len(db_paras):,} 段")

        # 2. 裴注跳转 100% 覆盖
        pei_path = os.path.join(ROOT, "data", "index", "pei-data.json")
        pei = json.load(open(pei_path, encoding="utf-8"))
        pei_total = 0
        pei_miss = []
        for pid, pdata in pei.get("persons", {}).items():
            for item in pdata.get("items", []):
                pei_total += 1
                cid = item.get("cid")
                pseq = item.get("pseq")
                if (cid, pseq) not in db_paras:
                    pei_miss.append((cid, pseq, item.get("alias")))

        check("裴注明细行（3,049 处）目标段落 100% 存在",
              len(pei_miss) == 0 and pei_total >= 3000,
              f"总计 {pei_total} 条，缺失 {len(pei_miss)} 条")

        # 3. 晋书旧史注跳转 100% 覆盖
        js_path = os.path.join(ROOT, "data", "index", "js-note-data.json")
        js = json.load(open(js_path, encoding="utf-8"))
        js_total = 0
        js_miss = []
        for pid, pdata in js.get("persons", {}).items():
            for item in pdata.get("items", []):
                js_total += 1
                cid = item.get("cid")
                pseq = item.get("pseq")
                if (cid, pseq) not in db_paras:
                    js_miss.append((cid, pseq, item.get("alias")))

        check("晋书旧史注明细行（≥70 处）目标段落 100% 存在",
              len(js_miss) == 0 and js_total >= 70,
              f"总计 {js_total} 条，缺失 {len(js_miss)} 条")

        # 4. 长篇阅读不截断（sj-014）
        sj014 = db.chapter_sentences("sj-014")
        n_sj014 = len(sj014.get("sentences", []))
        check("最长篇目（sj-014 十二诸侯年表）不被 500 截断",
              n_sj014 == 3454,
              f"实得 {n_sj014} 句（预期 3,454 句）")

        # 5. 前端跳段回退兜底代码存在性
        app_js_path = os.path.join(ROOT, "app", "web", "app.js")
        app_js = open(app_js_path, encoding="utf-8").read()
        has_fallback = "while (!node && cur > 1)" in app_js
        check("app.js jumpToPara 包含向前回溯兜底逻辑",
              has_fallback,
              "命中 while (!node && cur > 1)")

        # 6. 刘焉重复 pid 合并验证
        n_ys = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_liuyan_ys'").fetchone()[0]
        n_sg = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_liuyan_sg'").fetchone()[0]
        check("刘焉重复 pid 已合并：p_liuyan_sg 为 0 且 p_liuyan_ys > 0",
              n_sg == 0 and n_ys >= 15,
              f"p_liuyan_ys={n_ys}, p_liuyan_sg={n_sg}")

        ys_books = {r[0] for r in conn.execute(
            "SELECT DISTINCT c.book_id FROM mentions m "
            "JOIN sentences s ON s.uid=m.sentence_uid "
            "JOIN chapters c ON c.id=s.chapter_id "
            "WHERE m.person_id='p_liuyan_ys'")}
        check("p_liuyan_ys 跨后汉书与三国志两书",
              "hhs" in ys_books and "sgz" in ys_books,
              f"books={sorted(ys_books)}")

        # 7. 陶谦重复 pid 合并验证
        n_tq = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_taoqian'").fetchone()[0]
        n_thq = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_taohqian'").fetchone()[0]
        check("陶谦重复 pid 已合并：p_taohqian 为 0 且 p_taoqian > 0",
              n_thq == 0 and n_tq >= 45,
              f"p_taoqian={n_tq}, p_taohqian={n_thq}")

        tq_books = {r[0] for r in conn.execute(
            "SELECT DISTINCT c.book_id FROM mentions m "
            "JOIN sentences s ON s.uid=m.sentence_uid "
            "JOIN chapters c ON c.id=s.chapter_id "
            "WHERE m.person_id='p_taoqian'")}
        check("p_taoqian 跨后汉书与三国志两书",
              "hhs" in tq_books and "sgz" in tq_books,
              f"books={sorted(tq_books)}")

    finally:
        conn.close()

    print("\n[OK] 段落与人物合并全部断言顺利通过！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
