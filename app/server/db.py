# -*- coding: utf-8 -*-
"""仓储层：只管查 SQLite，返回普通 dict / list。

刻意**不依赖任何 HTTP 类型**（不 import fastapi），这样业务逻辑能脱离 Web 单测。
控制器在 main.py，负责参数校验与响应封装。

连接策略：本地单人使用，**每次查询开一个连接**、用完就关。
SQLite 在这个规模（9.6 万句 / 6.6 万命中）下开销可忽略，
换来的是不用管连接池与并发状态。
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def db_path() -> str:
    """库路径取自环境变量，默认放 data/index/index.db。

    启动时就会校验文件存在（见 main.py 的 startup），不存在就快速失败——
    别等到用户点了搜索才报「找不到库」。
    """
    return os.environ.get("BOOKINDEX_DB") or os.path.join(
        ROOT, "data", "index", "index.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def fts_phrase(q: str) -> str:
    """与 build_index_db 的入库方式对齐：按字切分 + 短语查询。

    中文人名两字居多，必须走短语（要求相邻），否则「項羽」会匹配到
    任何同时含「項」和「羽」的句子。
    """
    return '"' + " ".join(str(q).strip()) + '"'


def stats() -> Dict[str, Any]:
    with connect() as conn:
        out = {}
        for t in ("books", "chapters", "sentences", "mentions",
                  "persons", "aliases", "places", "relations"):
            out[t] = conn.execute("SELECT COUNT(*) FROM {}".format(t)).fetchone()[0]
        out["tiers"] = {
            r[0]: r[1] for r in conn.execute(
                "SELECT tier, COUNT(*) FROM mentions GROUP BY tier ORDER BY 2 DESC")}
        return out


def search_persons(q: str, limit: int = 30) -> List[Dict[str, Any]]:
    """按正名 / 简体名 / 别名检索人物。同名异人会**都返回**，由前端提示消歧。

    消歧的关键信息是「这人主要出现在哪几本书」——同名异人往往各属一书
    （張溫：後漢書一人、三國志一人），光看朝代和头衔分不出来。
    所以顺带把分书命中数查出来（一次查询，不是 N+1）。
    """
    like = "%{}%".format(q)
    sql = """
        SELECT p.id, p.trad_name, p.name, p.dynasty, p.title, p.summary,
               (SELECT COUNT(*) FROM mentions m WHERE m.person_id = p.id) AS n
        FROM persons p
        WHERE p.trad_name LIKE ? OR p.name LIKE ?
           OR p.id IN (SELECT person_id FROM aliases WHERE alias LIKE ?)
        ORDER BY n DESC LIMIT ?
    """
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, (like, like, like, limit))]
        if not rows:
            return rows
        pids = [r["id"] for r in rows]
        # books 表的主鍵叫 `code` 不是 `id`（建庫腳本裡就是這麼定的）
        bname = {r[0]: r[1] for r in conn.execute("SELECT code, name FROM books")}
        ph = ",".join("?" * len(pids))
        dist: Dict[str, List] = {}
        for pid, bid, n in conn.execute(
                "SELECT m.person_id, c.book_id, COUNT(*) FROM mentions m "
                "JOIN sentences s ON s.uid = m.sentence_uid "
                "JOIN chapters c ON c.id = s.chapter_id "
                "WHERE m.person_id IN ({}) "
                "GROUP BY m.person_id, c.book_id".format(ph), pids):
            dist.setdefault(pid, []).append((bid, n))
        for r in rows:
            top = sorted(dist.get(r["id"], []), key=lambda x: -x[1])[:3]
            r["books"] = [{"id": b, "name": bname.get(b, b), "n": n}
                          for b, n in top]
        return rows


def person_profile(pid: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, trad_name, name, dynasty, title, summary "
            "FROM persons WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["aliases"] = [r[0] for r in conn.execute(
            "SELECT alias FROM aliases WHERE person_id=?", (pid,))]
        return out


def person_mentions(pid: str, tier: Optional[str] = None,
                    limit: int = 200) -> List[Dict[str, Any]]:
    """某人的命中，**按篇分组**返回——这是详情页右侧的主体。"""
    sql = """
        SELECT c.full_title AS chapter, s.chapter_id, s.uid, s.text,
               m.surface, m.s, m.e, m.tier
        FROM mentions m
        JOIN sentences s ON s.uid = m.sentence_uid
        LEFT JOIN chapters c ON c.id = s.chapter_id
        WHERE m.person_id = ?
    """
    args: List[Any] = [pid]
    if tier:
        sql += " AND m.tier = ?"
        args.append(tier)
    sql += " ORDER BY s.chapter_id, s.para_seq, s.seq LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def full_text_search(q: str, limit: int = 50) -> List[Dict[str, Any]]:
    """全文检索（不限人名，任意词）。命中句回带所属篇目。"""
    sql = """
        SELECT s.uid, s.text, s.chapter_id, c.full_title AS chapter
        FROM sentences_fts f
        JOIN sentences s ON s.uid = f.uid
        LEFT JOIN chapters c ON c.id = s.chapter_id
        WHERE sentences_fts MATCH ? LIMIT ?
    """
    try:
        with connect() as conn:
            return [dict(r) for r in conn.execute(sql, (fts_phrase(q), limit))]
    except sqlite3.OperationalError:
        # FTS 表不存在（建库时被跳过）时，退化成 LIKE，别让用户看到 500
        like = "%{}%".format(q)
        with connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT s.uid, s.text, s.chapter_id, c.full_title AS chapter "
                "FROM sentences s LEFT JOIN chapters c ON c.id=s.chapter_id "
                "WHERE s.text LIKE ? LIMIT ?", (like, limit))]


def chapter_sentences(cid: str, limit: int = 500) -> List[Dict[str, Any]]:
    """取一篇的原文（句子序列）。用于「读全篇」。"""
    with connect() as conn:
        meta = conn.execute(
            "SELECT id, full_title, book_id FROM chapters WHERE id=?",
            (cid,)).fetchone()
        rows = [dict(r) for r in conn.execute(
            "SELECT uid, pos_key, para_seq, seq, text FROM sentences "
            "WHERE chapter_id=? ORDER BY para_seq, seq LIMIT ?", (cid, limit))]
    return {"chapter": dict(meta) if meta else None, "sentences": rows}


def person_relations(pid: str) -> List[Dict[str, Any]]:
    """关系**接口预留**：现在返回空列表，但端点与字段已经定型。

    relations 表在 P1 就建好了（docs/21 §12.2），数据等确认关系范围后再灌。
    字段里 `confidence` 与 `evidence_uid` 是关键——图上会把没证据的边画成虚线。
    """
    sql = """
        SELECT r.id, r.person_a, r.person_b, r.rel_type, r.rel, r.direction,
               r.evidence_uid, r.evidence_text, r.confidence, r.source, r.note,
               pa.trad_name AS name_a, pb.trad_name AS name_b
        FROM relations r
        LEFT JOIN persons pa ON pa.id = r.person_a
        LEFT JOIN persons pb ON pb.id = r.person_b
        WHERE r.person_a = ? OR r.person_b = ?
    """
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, (pid, pid))]
