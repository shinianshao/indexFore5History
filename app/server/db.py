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


def relations_graph(pid: str, degree: int = 1, rel_type: str = "",
                    book: str = "", min_conf: float = 0.0,
                    limit: int = 200) -> Dict[str, Any]:
    """以某人中心的**邻接表**，直接就是前端 `renderGraph` 要的 `{nodes, edges}`。

    为什么返回图而不是扁平行：前端契约 `renderGraph(adjacency, options)` 的输入
    固定为 `{nodes, edges}`——返回列表就等于把转换工作推给前端，而且每种调用
    各写一遍（docs/25 P0-6）。

    四个密度旋钮（docs/21 §12.4.1）：degree 度数、rel_type 关系大类、
    book 按书、min_conf 置信度下限。

    证据解析（docs/25 P0-3 / P0-4）：句子从 P4 起可编辑（拆/并/弃用），
    所以「写了 evidence_uid」**不等于「证据还站得住」**。每条边都带
    `evidence_state`：`none`（推断，本就没证据）/ `active`（有效）/
    `dead` `merged`（句子被弃用或并走，证据**已失效**）/ `missing`（uid 找不到）。
    文本**以 uid 指向的现句为准**，表里的 `evidence_text` 只是缓存——
    两者不一致时给 `evidence_stale=1`（docs/25 §四：uid 权威、快照次之）。
    """
    empty = {"nodes": [], "edges": []}
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM persons WHERE id=?", (pid,)).fetchone():
            return empty

        seen_nodes = {pid: 0}
        edges: List[Dict[str, Any]] = []
        frontier = {pid}
        for d in range(1, max(1, min(int(degree), 3)) + 1):
            if not frontier:
                break
            ph = ",".join("?" * len(frontier))
            sql = ("SELECT rel_id, person_a, surface_a, person_b, surface_b, "
                   "       rel_type, rel, symmetric, era, book, evidence_uid, "
                   "       evidence_text, confidence, source "
                   "FROM relations WHERE status='active' "
                   "AND (person_a IN ({}) OR person_b IN ({}))".format(ph, ph))
            args: List[Any] = list(frontier) * 2
            if rel_type:
                sql += " AND rel_type=?"
                args.append(rel_type)
            if book:
                sql += " AND (book=? OR book='')"      # 空 book = 不限书
                args.append(book)
            if min_conf:
                sql += " AND confidence>=?"
                args.append(min_conf)

            nxt = set()
            for r in conn.execute(sql, args):
                (rid, a, sa, b, sb, rt, rel, sym, era, bk,
                 euid, etext, conf, src) = r
                other = b if a in frontier else a
                if a not in frontier and b not in frontier:
                    continue
                # ⚠️ 起点叫 `source`、关系来源**不能也叫 source**——
                # 两个同名键写进同一个 dict，后者会把前者无声覆盖（踩过）。
                # 关系来源改叫 `origin`。
                edges.append({
                    "rel_id": rid, "source": a, "target": b, "rel": rel,
                    "rel_type": rt, "symmetric": sym, "era": era, "book": bk,
                    "evidence_uid": euid, "evidence_text": etext,
                    "confidence": conf, "origin": src,
                    "name_a": sa, "name_b": sb,
                })
                if other not in seen_nodes:
                    seen_nodes[other] = d
                    nxt.add(other)
            frontier = nxt
            if len(edges) >= limit:
                break

        if not edges:
            return {"nodes": [{"id": pid, "degree": 0}], "edges": []}

        ids = list(seen_nodes)[:limit]
        q = ",".join("?" * len(ids))
        prof = {r[0]: r for r in conn.execute(
            "SELECT id, trad_name, name, dynasty FROM persons "
            "WHERE id IN ({})".format(q), ids)}
        nodes = []
        for i in ids:
            p = prof.get(i)
            nodes.append({
                "id": i,
                "name": (p[1] if p else i),
                "name_simp": (p[2] if p else i),
                "dynasty": (p[3] if p else ""),
                "degree": seen_nodes[i],
            })

        # 证据：一次批量查，避免每条边一次查询（N+1）
        euids = [e["evidence_uid"] for e in edges if e["evidence_uid"]]
        found = {}
        if euids:
            ph = ",".join("?" * len(euids))
            for r in conn.execute(
                    "SELECT uid, chapter_id, text, status FROM sentences "
                    "WHERE uid IN ({})".format(ph), euids):
                found[r[0]] = (r[1] or "", r[2] or "", r[3] or "active")
        for e in edges:
            uid = e.get("evidence_uid") or ""
            snap = e.get("evidence_text") or ""
            if not uid:
                state, chapter, text = "none", "", snap
            elif uid not in found:
                state, chapter, text = "missing", "", snap
            else:
                chapter, text, state = found[uid]
            e["evidence_state"] = state
            e["evidence_valid"] = 1 if state == "active" else 0
            e["evidence_chapter"] = chapter
            e["evidence_text"] = text
            e["evidence_stale"] = 1 if (snap and text and snap != text) else 0

        return {"nodes": nodes, "edges": edges[:limit]}
