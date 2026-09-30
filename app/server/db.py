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


# ---------------------------------------------------------------- 称呼反向
#
# ⚠️ 这两张表与 `pipeline/relations.py` 里的同名表**必须逐字一致**——
# app/ 与 pipeline/ 刻意不互相 import（docs/23 §7.1），代价就是这里要抄一份，
# 由 `app/tools/verify_p3.py` 的断言守着（不一致就红）。
#
# CALL_INVERSE 是「称呼反向」：站在 a 的视角，对方该被称作什么。
# 它跟 REL_INVERSE（反向边表，用于禁止双写）不是一回事——对称边也需要它。
# 值是 (男, 女) 候选：`父 → (子, 女)`，选哪个看对方性别。
CALL_INVERSE = {
    "父": ("子", "女"), "母": ("子", "女"),
    "子": ("父", "母"), "女": ("父", "母"),
    "祖父": ("孫", "孫女"), "祖母": ("孫", "孫女"),
    "孫": ("祖父", "祖母"), "孫女": ("祖父", "祖母"),
    "兄": ("弟", "妹"), "弟": ("兄", "姊"),
    "姊": ("妹", "弟"), "妹": ("兄", "姊"),
    "夫": ("妻",), "妻": ("夫",),
    "伯叔": ("姪",), "姑": ("姪",), "姪": ("伯叔", "姑"),
    "舅": ("甥",), "姨": ("甥",), "甥": ("舅", "姨"),
    "養父": ("子", "女"), "繼母": ("子", "女"),
}
FEMALE_HINT = ("太后", "皇后", "公主", "王后", "夫人", "姬", "妃",
               "后", "女", "母", "婦", "妻", "娣", "娥")
NO_EVIDENCE_CAP = 0.4      # 与 relations.NO_EVIDENCE_CAP 一致（断言守着）


def looks_female(*texts) -> bool:
    s = "".join(str(t or "") for t in texts)
    return any(w in s for w in FEMALE_HINT)


def rel_view(rel: str, other_female: bool) -> str:
    """站在 a 的视角，把对方称作什么。展示与取证共用同一套词表。"""
    cands = CALL_INVERSE.get(rel)
    if not cands:
        return rel
    if len(cands) > 1:
        return cands[1] if other_female else cands[0]
    return cands[0]


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

        # 书号校验（docs/28 P1-3）：以前 `AND (book=? OR book='')` 让**任何**书号
        # 都能通过——`book=zzz` 照样返回全部边，旋钮是摆设还骗人。不存在的书号
        # 直接报错，由端点翻成 400。
        if book:
            known = {r[0] for r in conn.execute(
                "SELECT DISTINCT book_id FROM chapters")}
            if book not in known:
                raise ValueError("未知書號：{}（有效：{}）".format(
                    book, "/".join(sorted(known))))

        # 「按书看」的正确语义不是 `book` 列（61/62 条是空的——关系天然跨书，
        # 跟人物一样，见 docs/21），而是**这条关系在该书里有出处**：
        # 有证据句且证据句属于该书的边，也算命中。
        ev_rel: set = set()
        if book:
            for rid, in conn.execute(
                    "SELECT r.rel_id FROM relations r "
                    "JOIN sentences s ON s.uid=r.evidence_uid "
                    "JOIN chapters c ON c.id=s.chapter_id "
                    "WHERE r.status='active' AND r.evidence_uid<>'' "
                    "  AND c.book_id=?", (book,)):
                ev_rel.add(rid)

        seen_nodes = {pid: 0}
        edges: List[Dict[str, Any]] = []
        seen_rel = set()          # 按 rel_id 去重：第 2 轮 BFS 会把「中心↔一跳」再捞一遍
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
                # 空 book = 未标注（跨书），不因此被滤掉；但要么 `book` 列命中，
                # 要么证据句落在这本书里（ev_rel），二者都不是才排除。
                sql += " AND (book=? OR (book='' AND rel_id IN ({})))".format(
                    ",".join("?" * len(ev_rel)) or "''")
                args.append(book)
                args.extend(ev_rel)
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
                if rid in seen_rel:
                    continue          # 同一条边不进第二次（degree≥2 时否则会翻倍）
                seen_rel.add(rid)
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
            "SELECT id, trad_name, name, dynasty, title FROM persons "
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

        # 证据**子表**（docs/28 P1-6）：一条关系可以挂多条出处。
        # 只取 verdict<>'reject' 的——被人工否掉的候选留着是为了下轮不再抽出来，
        # 不是拿来当证据用的。
        ev_by_rel: Dict[str, list] = {}
        rids = [e["rel_id"] for e in edges]
        if rids:
            ph = ",".join("?" * len(rids))
            for r in conn.execute(
                    "SELECT rel_id, evidence_uid, verdict FROM relation_evidence "
                    "WHERE rel_id IN ({}) AND verdict<>'reject'".format(ph), rids):
                ev_by_rel.setdefault(r[0], []).append((r[1], r[2] or "accept"))

        # 证据：一次批量查，避免每条边一次查询（N+1）
        euids = {e["evidence_uid"] for e in edges if e["evidence_uid"]}
        for lst in ev_by_rel.values():
            euids.update(u for u, _ in lst)
        euids = sorted(euids)
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

            # 该边的全部证据（子表优先；子表没写就退化成主表那一条）
            lst = ev_by_rel.get(e["rel_id"]) or ([(uid, "accept")] if uid else [])
            evs = []
            for u, vd in lst:
                if u not in found:
                    st, ch, tx = "missing", "", ""
                else:
                    ch, tx, st = found[u]
                evs.append({"uid": u, "chapter": ch, "text": tx, "state": st,
                            "valid": 1 if st == "active" else 0,
                            "verdict": vd,
                            "stale": 1 if (u == uid and snap and tx
                                           and snap != tx) else 0})
            e["evidences"] = evs
            e["evidence_count"] = len(evs)
            # 「证据站不站得住」看的是**有没有任何一条还活着**，不是只看主证据：
            # 主证据那句被弃用、但另有出处时，这条关系仍是有据的。
            if evs:
                if any(x["state"] == "active" for x in evs):
                    state = "active"
                elif state == "none":
                    state = evs[0]["state"]
            e["evidence_state"] = state
            e["evidence_valid"] = 1 if state == "active" else 0
            e["evidence_chapter"] = chapter
            e["evidence_text"] = text
            e["evidence_stale"] = 1 if (snap and text and snap != text) else 0
            # 证据失效了，置信度就得跟着掉回去（docs/28 P1-7）：
            # 原来因为「有证据」拿到的 0.6，证据句被弃用后不该还顶着。
            if uid and not e["evidence_valid"]:
                e["confidence"] = min(float(e["confidence"] or 0), NO_EVIDENCE_CAP)
                e["confidence_fallen"] = 1

            # 展示用词：站在**中心**的视角，对方该被称作什么。
            # 有向边在这里最容易读反——(a,父,b) 在 a 的页面上是「女 b」，不是「父 b」。
            a, b = e["source"], e["target"]
            other = b if a == pid else a
            po = prof.get(other)
            e["rel_view"] = e["rel"] if a != pid else rel_view(
                e["rel"], looks_female(po[1] if po else other,
                                       po[4] if po else ""))
            na = prof.get(a)[1] if prof.get(a) else e["name_a"]
            nb = prof.get(b)[1] if prof.get(b) else e["name_b"]
            e["rel_desc"] = "{} 是 {} 之{}".format(na, nb, e["rel"])

        return {"nodes": nodes, "edges": edges[:limit]}
