# -*- coding: utf-8 -*-
"""索引库查询小工具（docs/21 P1 的配套）——「查找确认」的第一把钥匙。

数据库化之前，想回答「這兩個稱呼是不是判給同一個人」「還有哪些是推斷的」
只能临时写 `_probe_*` 脚本；现在直接查就行。

用法
----
    python app/tools/query.py 劉邦                查某人的命中（按篇分组）
    python app/tools/query.py 劉邦 --tier guess   只看推斷檔（待確認的那批）
    python app/tools/query.py --fts 鴻門          全文檢索（任意詞，不限人名）
    python app/tools/query.py --tier guess -n 30  全庫推斷命中，抽 30 條
    python app/tools/query.py --stats             庫的規模一覽

輸出刻意做成「能直接判斷對錯」的形態：篇名 + 原文 + 命中串標出來，
因為這個庫的用途就是**讓人核對**，不是給機器讀。
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "data", "index", "index.db")

TIER_NOTE = {
    "core": "正名/別名直接命中",
    "owner": "篇主推定",
    "chapter": "篇目推定",
    "era": "時代推定",
    "sentence": "句內推定",
    "paragraph": "段內推定",
    "related": "關聯推定",
    "scoped": "限定作用域",
    "guess": "★泛稱推斷，待確認",
}


def fts_phrase(q):
    """與 build_index_db 的入庫方式對齊：按字切分 + 短語查詢。"""
    return '"' + " ".join(str(q).strip()) + '"'


def find_pids(conn, name):
    cur = conn.execute(
        "SELECT id, trad_name, dynasty, title FROM persons "
        "WHERE trad_name=? OR name=?", (name, name))
    rows = cur.fetchall()
    if rows:
        return rows
    return conn.execute(
        "SELECT DISTINCT p.id, p.trad_name, p.dynasty, p.title "
        "FROM persons p JOIN aliases a ON a.person_id=p.id WHERE a.alias=?",
        (name,)).fetchall()


def show_person(conn, pids, tier, limit):
    for pid, tn, dyn, title in pids:
        n = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id=?",
                         (pid,)).fetchone()[0]
        print("\n■ {} 【{}】{}　命中 {} 處　({})".format(
            tn, dyn or "", title or "", n, pid))
        # uid 一定要帶：這是「看見一條可疑命中 → 寫 override 糾錯」的入口
        sql = ("SELECT c.full_title, s.text, m.surface, m.tier, s.uid "
               "FROM mentions m JOIN sentences s ON s.uid=m.sentence_uid "
               "LEFT JOIN chapters c ON c.id=s.chapter_id "
               "WHERE m.person_id=?")
        args = [pid]
        if tier:
            sql += " AND m.tier=?"
            args.append(tier)
        sql += " LIMIT ?"
        args.append(limit)
        last = None
        for full, text, surf, tr, uid in conn.execute(sql, args):
            if full != last:
                print("  《{}》".format(full))
                last = full
            mark = "「{}」".format(surf) if surf in (text or "") else "[{}]".format(surf)
            print("    {}  {}  {}".format(
                uid,
                (text or "").replace(surf, mark, 1)[:64],
                "" if tr == "core" else "…{}".format(TIER_NOTE.get(tr, tr))))


def show_fts(conn, word, limit):
    rows = conn.execute(
        "SELECT uid FROM sentences_fts WHERE sentences_fts MATCH ? LIMIT ?",
        (fts_phrase(word), limit)).fetchall()
    print("\n全文「{}」：{} 句".format(word, len(rows)))
    for (uid,) in rows:
        r = conn.execute(
            "SELECT s.text, c.full_title FROM sentences s "
            "LEFT JOIN chapters c ON c.id=s.chapter_id WHERE s.uid=?",
            (uid,)).fetchone()
        if r:
            print("  《{}》{}".format(r[1], r[0][:64]))


def show_tier(conn, tier, limit):
    rows = conn.execute(
        "SELECT m.surface, s.text, c.full_title, s.uid "
        "FROM mentions m JOIN sentences s ON s.uid=m.sentence_uid "
        "LEFT JOIN chapters c ON c.id=s.chapter_id "
        "WHERE m.tier=? LIMIT ?", (tier, limit)).fetchall()
    print("\ntier={}（{}）：抽 {} 條".format(
        tier, TIER_NOTE.get(tier, tier), len(rows)))
    print("  （uid 是糾錯入口：python app/tools/overrides.py show --uid <uid>）")
    for surf, text, full, uid in rows:
        print("  {} 《{}》{}".format(
            uid, full, text.replace(surf, "「{}」".format(surf), 1)[:64]))


def show_stats(conn):
    print("\n=== index.db ===")
    for t in ("books", "chapters", "sentences", "mentions",
              "persons", "aliases", "places", "relations"):
        print("  {:<10s} {:>8,d}".format(
            t, conn.execute("SELECT COUNT(*) FROM {}".format(t)).fetchone()[0]))
    print("\n  tier 分佈：")
    for tr, n in conn.execute(
            "SELECT tier, COUNT(*) FROM mentions GROUP BY tier ORDER BY 2 DESC"):
        print("    {:<10s} {:>7,d}  {}".format(tr, n, TIER_NOTE.get(tr, tr)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", help="人名/稱謂（可用別名）")
    ap.add_argument("--fts", help="全文檢索詞（不限人名）")
    ap.add_argument("--tier", help="只看某個 tier，如 guess")
    ap.add_argument("-n", type=int, default=20, help="每類顯示條數")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(DB):
        raise SystemExit("找不到 {}，先跑 build_index_db.py".format(DB))
    conn = sqlite3.connect(DB)

    if a.stats:
        show_stats(conn)
    if a.fts:
        show_fts(conn, a.fts, a.n)
    elif a.name:
        pids = find_pids(conn, a.name)
        if not pids:
            print("查不到「{}」".format(a.name))
        elif len(pids) > 1:
            print("「{}」對應 {} 個人（同名異人）：".format(a.name, len(pids)))
            for r in pids:
                print("   {} 【{}】{}".format(r[1], r[2] or "", r[3] or ""))
        else:
            show_person(conn, pids, a.tier, a.n)
    elif a.tier:
        show_tier(conn, a.tier, a.n)

    if not (a.stats or a.fts or a.name or a.tier):
        ap.print_help()
    conn.close()


if __name__ == "__main__":
    main()
