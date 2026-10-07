# -*- coding: utf-8 -*-
"""仓储层：只管查 SQLite，返回普通 dict / list。

刻意**不依赖任何 HTTP 类型**（不 import fastapi），这样业务逻辑能脱离 Web 单测。
控制器在 main.py，负责参数校验与响应封装。

连接策略：本地单人使用，**每次查询开一个连接**、用完就关。
SQLite 在这个规模（9.6 万句 / 6.6 万命中）下开销可忽略，
换来的是不用管连接池与并发状态。
"""
from __future__ import annotations

import json
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


# ---------------------------------------------------------------- 三國兩漢兵爭要地與人地交集
STRATEGIC_PLACES_FILE = os.path.join(ROOT, "data", "dict", "strategic_places.json")


def load_strategic_places() -> Dict[str, Any]:
    if os.path.exists(STRATEGIC_PLACES_FILE):
        try:
            with open(STRATEGIC_PLACES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


STRATEGIC_PLACES = load_strategic_places()


def get_strategic_places() -> Dict[str, Any]:
    return STRATEGIC_PLACES


def place_top_persons(plid: str, limit: int = 8) -> List[Dict[str, Any]]:
    """某地名在語料中共同出現最頻繁的人物榜（駐跸征戰歷史人物交集）。"""
    with connect() as conn:
        sql = """
            SELECT m.person_id, p.trad_name, p.name, COUNT(DISTINCT m.sentence_uid) as c
            FROM mentions m
            JOIN place_mentions pm ON m.sentence_uid = pm.sentence_uid
            JOIN persons p ON m.person_id = p.id
            WHERE pm.place_id = ?
            GROUP BY m.person_id
            ORDER BY c DESC LIMIT ?
        """
        rows = conn.execute(sql, (plid, limit)).fetchall()
        return [{"id": r["person_id"], "trad_name": r["trad_name"], "name": r["name"], "n": r["c"]}
                for r in rows]


def person_top_places(pid: str, limit: int = 12) -> List[Dict[str, Any]]:
    """某人物在語料中共同出現最頻繁的地名榜（主要行跡與兵爭輿地交集）。"""
    with connect() as conn:
        sql = """
            SELECT pm.place_id, pl.trad_name, pl.name, pl.kind, COUNT(DISTINCT pm.sentence_uid) as c
            FROM mentions m
            JOIN place_mentions pm ON m.sentence_uid = pm.sentence_uid
            JOIN places pl ON pm.place_id = pl.id
            WHERE m.person_id = ?
            GROUP BY pm.place_id
            ORDER BY c DESC LIMIT ?
        """
        rows = conn.execute(sql, (pid, limit)).fetchall()
        return [{"id": r["place_id"], "trad_name": r["trad_name"], "name": r["name"],
                 "kind": r["kind"], "n": r["c"], "isStrategic": (r["place_id"] in STRATEGIC_PLACES)}
                for r in rows]


def person_strategic_hubs(pid: str) -> List[Dict[str, Any]]:
    """提取某人物在 43 處兵爭要衝中涉足的全部戰略要塞（無截斷，曹操 27 處全量返回）。"""
    with connect() as conn:
        sql = """
            SELECT pm.place_id, pl.trad_name, pl.name, COUNT(DISTINCT pm.sentence_uid) as c
            FROM mentions m
            JOIN place_mentions pm ON m.sentence_uid = pm.sentence_uid
            JOIN places pl ON pm.place_id = pl.id
            WHERE m.person_id = ?
            GROUP BY pm.place_id
            ORDER BY c DESC
        """
        rows = conn.execute(sql, (pid,)).fetchall()
        res = []
        for r in rows:
            plid = r["place_id"]
            if plid in STRATEGIC_PLACES:
                st = STRATEGIC_PLACES[plid]
                res.append({
                    "id": plid,
                    "trad_name": r["trad_name"],
                    "name": r["name"],
                    "n": r["c"],
                    "zone": st.get("zone", ""),
                    "connections": st.get("connections", [])
                })
        return res




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


# ---------------------------------------------------------------- 注文账本
# 裴注（三國志裴松之注）与晉書舊史注是**独立账本**，不进 mentionCount、库里没有表
# （红线之一）。所以这里从 pipeline 产出的 JSON 直接读。
#
# ⚠️ 为什么不入 db：一旦入表就得跟着 uid / 编辑 / 重建一起维护，而注文本来
# 就是「另一层文本」，与正文的句不是一套切分（items 里的 pseq 是**段**号，
# 不是句号），硬塞进 sentences 会把两个体系搅在一起。
#
# 缓存：1MB 的 JSON 每次请求重解析太浪费，用 mtime 做 key，重跑 pipeline
# 自动失效（mtime 变了就重新读，不需要手动清缓存）。
_PEI_CACHE: Dict[str, Any] = {}


def _load_note_json(filename: str) -> Dict[str, Any]:
    """读注文 JSON（带 mtime 缓存）。文件不存在就返回空壳，不报错。"""
    path = os.path.join(ROOT, "data", "index", filename)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"meta": {}, "persons": {}, "chapters": {}}
    cached = _PEI_CACHE.get(filename)
    if cached and cached.get("_mtime") == mtime:
        return cached
    import json
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["_mtime"] = mtime
    _PEI_CACHE[filename] = data
    return data


def pei_of(pid: str) -> Optional[Dict[str, Any]]:
    """某人的裴注命中：无则 None。

    返回形状与静态版 `peiOf` 一致（n / chapters / aliases / byChapter / items），
    这样前端渲染逻辑可以照静态版抄。
    """
    return _load_note_json("pei-data.json").get("persons", {}).get(pid)


def pei_meta() -> Dict[str, Any]:
    return _load_note_json("pei-data.json").get("meta", {})


def js_note_of(pid: str) -> Optional[Dict[str, Any]]:
    """某人的晉書舊史注命中。同一份 JSON 形状。"""
    return _load_note_json("js-note-data.json").get("persons", {}).get(pid)


def js_note_meta() -> Dict[str, Any]:
    return _load_note_json("js-note-data.json").get("meta", {})


def person_notes_payload(pid: str) -> Dict[str, Any]:
    """人物页附带的注文区块（联机端点与离线导出共用这一份）。

    ⚠️ 刻意**不含**「把注文并进总数」的开关：docs/29 §六-3 定了注文只作独立区块，
    合计要标【裴N】。合并逻辑放前端（显示层），数据层保持两本账分清——
    一旦在这里相加，红线就破了而没人知道。

    `chapterTitles`：注文的 byChapter 只有篇号，前端得有篇名才能显示。
    联机模式前端没有「篇号 → 篇名」表（那个表 CHAPT 只在离线快照里填），
    所以这里把用到的篇名一并带上前端，不必让前端自己建映射。
    """
    pei = pei_of(pid)
    js = js_note_of(pid)
    cids = set()
    for note in (pei, js):
        if note:
            cids |= set(note.get("byChapter") or {})
    titles: Dict[str, str] = {}
    if cids:
        # 一次查完，别在循环里开连接（曹操 49 篇 → 49 次连接，sqlite 每次
        # 都要 parse + 打开文件，慢得没道理）
        qs = ",".join("?" * len(cids))
        with connect() as conn:
            for cid, ft in conn.execute(
                    "SELECT id, full_title FROM chapters WHERE id IN (" + qs + ")",
                    tuple(cids)):
                titles[cid] = ft
        for cid in cids:                 # 查不到的（弃用篇）退回篇号本身
            titles.setdefault(cid, cid)
    return {"pei": pei, "peiMeta": pei_meta(),
            "jsNote": js, "jsNoteMeta": js_note_meta(),
            "chapterTitles": titles}


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


# ---------------------------------------------------------------- 索引页
#
# 静态版 web/ 的四块（人物索引 / 地名索引 / 篇目一覽 / 快捷词）在新版里一直没做，
# 因为 index.db 当初**漏了把地名命中入库**（`pmarks` 没写），只能绕开数据库读 JSON。
# 现在补了 `place_mentions` 表，这几块就能正经从库里查了。
#
# 排序口径与静态版一致：**按提及篇数（.c）默认，可切按次数（.n）**。
# ⚠️ 不是拼音序——拼音只是 Excel 里给人看排序用的辅助列，界面从来没按它排过。

# 地名按类型分组展示。顺序与 pipeline/annotate_places.py 的 KIND_ORDER 一致。
PLACE_KIND_ORDER = ["国", "州", "郡", "县", "关", "山", "川", "湖", "域", "外"]
PLACE_KIND_LABEL = {"国": "国/朝代", "州": "州部", "郡": "郡", "县": "县邑都城", "关": "关隘",
                    "山": "山", "川": "川", "湖": "湖", "域": "地域",
                    "外": "其他"}



def _parse_book_filter(book: Any) -> List[str]:
    """解析单书号或逗号分隔多书号为列表。"""
    if not book:
        return []
    if isinstance(book, (list, set, tuple)):
        return [str(b).strip() for b in book if str(b).strip()]
    return [b.strip() for b in str(book).split(",") if b.strip()]


def _book_counts(conn, table: str, key_col: str,
                 book: str = "") -> Dict[str, Dict[str, Dict]]:
    """一次 GROUP BY 取回「按书命中数 n + 篇数 c」，避免 N+1。

    ⚠️ n 和 c 必须在**同一遍**里取出来。第一版写了两遍同样的 GROUP BY
    （第二遍只为拿 c），白白多花一倍时间——COUNT(DISTINCT) 和 COUNT(*)
    在一条 SELECT 里就能同时算，没理由分开查。
    """
    b_list = _parse_book_filter(book)
    where = ""
    args: List[Any] = []
    if len(b_list) == 1:
        where = "WHERE ch.book_id = ?"
        args = [b_list[0]]
    elif len(b_list) > 1:
        placeholders = ",".join("?" * len(b_list))
        where = "WHERE ch.book_id IN ({})".format(placeholders)
        args = list(b_list)
    sql = """
        SELECT m.{k} AS kid, ch.book_id AS bid,
               COUNT(*) AS n, COUNT(DISTINCT s.chapter_id) AS c
        FROM {t} m
        JOIN sentences s ON s.uid = m.sentence_uid
        JOIN chapters ch ON ch.id = s.chapter_id
        {w}
        GROUP BY m.{k}, ch.book_id
    """.format(t=table, k=key_col, w=where)
    out: Dict[str, Dict[str, Dict]] = {}
    for kid, bid, n, c in conn.execute(sql, args):
        out.setdefault(kid, {})[bid] = {"n": n, "c": c}
    return out


def _narrow(counts: Dict[str, Dict[str, Dict]], book: str) -> Dict[str, Dict[str, Dict]]:
    """把「全五書」的按書計數收窄到指定的單書或多本書。

    與「帶 `WHERE ch.book_id=?` 或 IN 再查一遍」**結果完全一致**。
    支持單書或逗號分隔多書號（如 'hs,hhs'）。
    """
    b_list = _parse_book_filter(book)
    if not b_list:
        return counts
    b_set = set(b_list)
    return {
        k: {b: v[b] for b in b_list if b in v}
        for k, v in counts.items()
        if any(b in v for b in b_set)
    }


def all_counts(conn) -> tuple:
    """一次算完人物 / 地名兩張命中表的按書計數（不帶 WHERE），供 `_narrow` 複用。"""
    return (_book_counts(conn, "mentions", "person_id", ""),
            _book_counts(conn, "place_mentions", "place_id", ""))


def _scope(bk: Dict[str, Dict]) -> Dict[str, int]:
    """把按书计数压成 (nAll, cAll)。

    篇数可以放心相加：一篇只属一书（`chapters.book_id` 是单值），
    所以同一篇不会被两本书重复计。
    """
    return {"nAll": sum(v["n"] for v in bk.values()),
            "cAll": sum(v["c"] for v in bk.values())}


def list_persons(book: str = "", sort: str = "c", limit: int = 0,
                 counts: Optional[Dict[str, Dict[str, Dict]]] = None
                 ) -> Dict[str, Any]:
    """人物索引：当前书作用域内**有命中**的人物，按篇数/次数降序。

    `counts` 是**不带 WHERE 的全量**按书计数（见 `all_counts`），传了就按 `book`
    收窄复用，不再查一遍。不传＝自己查（联机单次请求的正常路径）。
    """
    with connect() as conn:
        counts = _narrow(counts, book) if counts is not None else \
            _book_counts(conn, "mentions", "person_id", book)
        rows = []
        for r in conn.execute(
                "SELECT id, trad_name, name, dynasty, title, summary, era_rank "
                "FROM persons WHERE status='active'"):
            bk = counts.get(r["id"]) or {}
            st = _scope(bk)
            if st["nAll"] <= 0:
                continue
            rows.append({
                "id": r["id"], "name": r["trad_name"] or r["name"],
                "dynasty": r["dynasty"] or "", "title": r["title"] or "",
                "summary": r["summary"] or "",
                # 時代序號（NULL = 沒斷出時代）。前端拿它跟當前書的 eraRange 比，
                # 標出「前朝」——斷代史裡出現的前朝人（如《漢書》裡的孔子）。
                # ⚠️ 比大小是前端做的，理由同 aliasScopeN：離線版沒有服務端。
                "eraRank": r["era_rank"],
                "n": st["nAll"], "c": st["cAll"],
                "books": sorted(
                    [{"id": b, "n": v["n"], "c": v["c"]} for b, v in bk.items()],
                    key=lambda x: -x["n"]),
            })
    rows.sort(key=lambda x: (-(x["c"] if sort == "c" else x["n"]), -x["n"]))
    return {"total": len(rows), "items": rows[:limit] if limit else rows}


def list_places(book: str = "", sort: str = "c", limit: int = 0,
                counts: Optional[Dict[str, Dict[str, Dict]]] = None
                ) -> Dict[str, Any]:
    """地名索引：按类型分组（国/郡/县/关/山/川/湖/域/外）。`counts` 同上。"""
    with connect() as conn:
        counts = _narrow(counts, book) if counts is not None else \
            _book_counts(conn, "place_mentions", "place_id", book)
        rows = []
        for r in conn.execute(
                "SELECT id, trad_name, name, kind, era, summary FROM places"):
            bk = counts.get(r["id"]) or {}
            st = _scope(bk)
            if st["nAll"] <= 0:
                continue
            kind = r["kind"] or "外"
            rows.append({
                "id": r["id"], "name": r["trad_name"] or r["name"],
                "kind": kind, "kindLabel": PLACE_KIND_LABEL.get(kind, kind),
                "era": r["era"] or "", "summary": r["summary"] or "",
                "n": st["nAll"], "c": st["cAll"],
            })
    rows.sort(key=lambda x: (-(x["c"] if sort == "c" else x["n"]), -x["n"]))
    return {"total": len(rows), "items": rows[:limit] if limit else rows}


def list_chapters(book: str = "") -> Dict[str, Any]:
    """篇目一覽：按书分组，书内按卷序；附篇主/高频地名標籤。

    篇目行上那兩個 tag（「這篇主要講誰」「地：xx」）是靜態版就有的，
    缺了它 564 篇就只剩一串篇名，挑不出想讀的那篇。
    """
    with connect() as conn:
        books = [{"id": r[0], "name": r[1]} for r in conn.execute(
            "SELECT code, name FROM books ORDER BY code")]
        # id → 顯示名：兩張小表一次讀進內存，別在 564 篇的循環裡逐條查
        pname = {r[0]: (r[1] or r[2]) for r in conn.execute(
            "SELECT id, trad_name, name FROM persons")}
        lname = {r[0]: (r[1] or r[2]) for r in conn.execute(
            "SELECT id, trad_name, name FROM places")}
        rows = []
        sql = ("SELECT id, book_id, title, full_title, category, volume, "
               "char_count, sentence_count, main_persons, top_places "
               "FROM chapters")
        args: List[Any] = []
        b_list = _parse_book_filter(book)
        if len(b_list) == 1:
            sql += " WHERE book_id=?"
            args.append(b_list[0])
        elif len(b_list) > 1:
            placeholders = ",".join("?" * len(b_list))
            sql += " WHERE book_id IN ({})".format(placeholders)
            args.extend(b_list)
        sql += " ORDER BY book_id, volume, id"
        def names(ids: str, tbl: Dict[str, str]) -> List[str]:
            """逗號分隔的 id → 顯示名；id 不在表裡（人被合併/改名）就靜默跳過，
            別讓一個髒 id 把整篇的標籤欄弄壞。"""
            return [tbl[i] for i in (ids or "").split(",") if i and i in tbl]

        for r in conn.execute(sql, args):
            rows.append({
                "id": r["id"], "book": r["book_id"], "title": r["title"],
                "fullTitle": r["full_title"], "category": r["category"] or "",
                "volume": r["volume"],
                "charCount": r["char_count"] or 0,
                "sentenceCount": r["sentence_count"] or 0,
                "mainPersons": names(r["main_persons"], pname),
                "topPlaces": names(r["top_places"], lname),
            })
    return {"books": books, "items": rows}


def _top_by_book(conn, table: str, key_col: str, ref_tbl: str,
                 book: str, limit: int) -> List[Dict[str, Any]]:
    """Top N 直接在 SQL 层取，不跑全量聚合——全量要 0.6~1.2s，取 Top 只要几十毫秒。

    姓名在 persons / places 主表里，命中表里只有 id，所以要 JOIN 回去取名字。
    """
    b_list = _parse_book_filter(book)
    where = ""
    args: List[Any] = []
    if len(b_list) == 1:
        where = "WHERE ch.book_id = ?"
        args.append(b_list[0])
    elif len(b_list) > 1:
        placeholders = ",".join("?" * len(b_list))
        where = "WHERE ch.book_id IN ({})".format(placeholders)
        args.extend(b_list)
    sql = """
        SELECT m.{k} AS id, MAX(r.trad_name) AS name,
               COUNT(DISTINCT s.chapter_id) AS c, COUNT(*) AS n
        FROM {t} m
        JOIN {rt} r ON r.id = m.{k}
        JOIN sentences s ON s.uid = m.sentence_uid
        JOIN chapters ch ON ch.id = s.chapter_id
        {w}
        GROUP BY m.{k}
        ORDER BY c DESC, n DESC
        LIMIT ?
    """.format(t=table, k=key_col, rt=ref_tbl, w=where)
    args.append(limit)
    return [{"id": r["id"], "name": r["name"], "c": r["c"], "n": r["n"]}
            for r in conn.execute(sql, args)]


def index_payload(book: str = "", sort: str = "c",
                  counts: Optional[tuple] = None) -> Dict[str, Any]:
    """`/api/index` 的响应体。

    ⚠️ 这个函数被**两处**调用：main.py 的联机端点，和 `app/tools/export_static.py`
    的离线快照导出。当初只在端点里拼，导出那边就得照抄一遍——四块的聚合口径
    有一处改了另一处不知道，离线版就悄悄跟联机版不一致。共用一个函数，**只有一份**。

    `counts` = `all_counts()` 的结果，导出时六个书作用域共用一次计算结果。
    """
    sort = "n" if sort == "n" else "c"
    pc, lc = counts if counts else (None, None)
    return {
        "book": book,
        "sort": sort,
        "persons": list_persons(book=book, sort=sort, counts=pc),
        "places": list_places(book=book, sort=sort, counts=lc),
        "chapters": list_chapters(book=book),
        "quick": quick_words(book=book),
        "strategicPlaces": STRATEGIC_PLACES,
    }


def sgz_breakdown(pid: str, pei_info: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """某人在《三國志》魏書（卷1-30）、蜀書（卷31-45）、吳書（卷46-65）的正文與裴注統計。

    若該人物在三國志（正文與裴注）均無命中，返回 None。
    """
    with connect() as conn:
        rows = conn.execute("""
            SELECT s.chapter_id, COUNT(*) AS n, COUNT(DISTINCT s.chapter_id) AS c
            FROM mentions m
            JOIN sentences s ON s.uid = m.sentence_uid
            JOIN chapters ch ON ch.id = s.chapter_id
            WHERE m.person_id = ? AND ch.book_id = 'sgz'
            GROUP BY s.chapter_id
        """, (pid,)).fetchall()

    wei_main_n, wei_main_c = 0, 0
    shu_main_n, shu_main_c = 0, 0
    wu_main_n, wu_main_c = 0, 0

    for r in rows:
        cid = r[0]
        cnt = int(r[1] or 0)
        try:
            vol = int(cid.split("-")[1])
        except (IndexError, ValueError):
            continue
        if 1 <= vol <= 30:
            wei_main_n += cnt
            wei_main_c += 1
        elif 31 <= vol <= 45:
            shu_main_n += cnt
            shu_main_c += 1
        elif 46 <= vol <= 65:
            wu_main_n += cnt
            wu_main_c += 1

    main_tot_n = wei_main_n + shu_main_n + wu_main_n
    main_tot_c = wei_main_c + shu_main_c + wu_main_c

    # 裴注
    pei_info = pei_info or pei_of(pid) or {}
    by_chap = pei_info.get("byChapter", {})

    wei_pei_n, wei_pei_c = 0, 0
    shu_pei_n, shu_pei_c = 0, 0
    wu_pei_n, wu_pei_c = 0, 0

    for cid, cnt in by_chap.items():
        if not cid.startswith("sgz-"):
            continue
        try:
            vol = int(cid.split("-")[1])
        except (IndexError, ValueError):
            continue
        cnt_val = int(cnt or 0)
        if 1 <= vol <= 30:
            wei_pei_n += cnt_val
            wei_pei_c += 1
        elif 31 <= vol <= 45:
            shu_pei_n += cnt_val
            shu_pei_c += 1
        elif 46 <= vol <= 65:
            wu_pei_n += cnt_val
            wu_pei_c += 1

    pei_tot_n = wei_pei_n + shu_pei_n + wu_pei_n
    pei_tot_c = wei_pei_c + shu_pei_c + wu_pei_c

    comb_tot_n = main_tot_n + pei_tot_n
    if comb_tot_n == 0:
        return None

    return {
        "main": {
            "wei": {"n": wei_main_n, "c": wei_main_c},
            "shu": {"n": shu_main_n, "c": shu_main_c},
            "wu": {"n": wu_main_n, "c": wu_main_c},
            "total": {"n": main_tot_n, "c": main_tot_c},
        },
        "pei": {
            "wei": {"n": wei_pei_n, "c": wei_pei_c},
            "shu": {"n": shu_pei_n, "c": shu_pei_c},
            "wu": {"n": wu_pei_n, "c": wu_pei_c},
            "total": {"n": pei_tot_n, "c": pei_tot_c},
        },
        "combined": {
            "wei": {"n": wei_main_n + wei_pei_n},
            "shu": {"n": shu_main_n + shu_pei_n},
            "wu": {"n": wu_main_n + wu_pei_n},
            "total": {"n": comb_tot_n},
        }
    }


def person_payload(pid: str, limit: int = 200, book: Optional[str] = None,
                   era: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """`/api/person/{pid}` 的响应体（同上：联机端点与离线导出共用）。

    查不到人返回 None，由调用方翻成 404 / 跳过。

    ⚠️ `mentions` 是**被 limit 截断**的，所以它 `.length` 是「本次載入了幾條」，
    **不是「這人有幾處」**——曾经前端直接拿它当命中数显示，于是
    「正文命中 200 處」跟搜索卡的 2,064 處自相矛盾（docs/34 P0-3）。
    真正的全量在 `mentionByBook`（按书的分布，五项之和 = 全量）。
    """
    profile = person_profile(pid)
    if not profile:
        return None
    notes = person_notes_payload(pid)
    return {
        "profile": profile,
        "mentions": person_mentions(pid, None, limit, book=book, era=era),
        # 直接给图（{nodes, edges}），与前端 renderGraph 的契约一致
        "relations": relations_graph(pid, 1, limit=limit),
        # 注文（裴注 / 晉書舊史注）：**独立账本**，与上面的正文命中分开算。
        # 前端合计时要把注文分量标成【裴N】，不能混进 mentionCount。
        "notes": notes,
        # 三国志魏蜀吴分卷与裴注统计（学术多重视角）
        "sgzBreakdown": sgz_breakdown(pid, notes.get("pei")),
        # 正文命中的**全量**分布（不受 limit / 篩選影響）。
        # 前端拿它算「共 N 處」和每个筛选桶的条数——联机只给 200 条，
        # 光靠 mentions 算不出来；离线同理吃这一份，两边口径才不会分叉。
        "mentionByBook": mention_by_book(pid),
        # 時代名（下標 = eraRank）。前端不再自己抄一份時代表。
        "eraNames": ERA_NAMES,
        # 主要行跡與兵爭輿地交集
        "topPlaces": person_top_places(pid, 12),
        "strategicHubs": person_strategic_hubs(pid),
    }


# 時代序 → 名稱。與 pipeline/annotate.py::ERA_ORDER **必須逐字一致**，
# app/ 不能 import pipeline/，只能抄這一份——verify_p3 [16] 用正則把兩邊對一遍。
ERA_NAMES = ["上古", "夏", "商", "西周", "東周", "春秋",
             "戰國", "秦", "秦末", "西漢", "新", "東漢",
             "三國", "西晉", "東晉", "十六國"]


def quick_words(book: str = "", np: int = 20, nl: int = 10) -> Dict[str, Any]:
    """快捷词：当前书作用域内 Top N 人物 + Top N 地名。

    与静态版同口径——换书后快捷词跟着换，不会出现「选了漢書，头一排全是漢書里
    查不到的人」。人物与地名在界面上分色（赭石 / 青碧），所以分两个数组返回。
    """
    with connect() as conn:
        persons = _top_by_book(conn, "mentions", "person_id", "persons", book, np)
        places = _top_by_book(conn, "place_mentions", "place_id", "places", book, nl)
    return {"persons": persons, "places": places}


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
        # 完整称谓表（含次数 / 类别 / 按书分账）——「这个别名靠不靠谱」全靠它判断。
        out["aliasList"] = person_alias_list(pid)
        return out


# 称谓类别的展示顺序与 pipeline/annotate.py::build_alias_list 的 KIND_ORDER 对齐。
# ⚠️ 若 pipeline 新增类别而这里没跟上，它会被排到最后。见 verify_p3 [14]。
ALIAS_KINDS = ("name", "title", "generic", "short", "other")


def person_alias_list(pid: str) -> List[Dict[str, Any]]:
    """某人的完整称谓清单（人物页「完整称谓表」的数据源）。

    顺序、归并（繁简异体并成一条）、类别、次数都由 pipeline 的 `build_alias_list`
    算好，经 `build_index_db` 原样灌进 `person_aliases` 表——**这里只读不重算**
    （app/ 不能 import pipeline/，两者只在 JSON / DB 上交汇）。

    ⚠️ **`n` 恒为全五书合计，按书收窄由前端用 `byBook` 算**。别给这个函数加 `book`
    参数：离线版没有服务端可问，请求里带 book 也只会被离线路由当成查询串忽略，
    理应收窄时收不到等值结果，两边就悄悄不一致了（这正是「响应体组装放在 db 层」
    那条红线想防的事）。让联机与离线跑**同一段前端结算代码**才是真的一致，见
    `app/web/app.js` 的 `aliasScopeN`。
    前端敢这么算的前提是 `n == sum(byBook.values())` 对每行成立——verify_p3 [14] 守着。
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT w, simp, n, kind, variants, by_book FROM person_aliases "
            "WHERE person_id=? ORDER BY seq", (pid,)).fetchall()
    return _decode_alias_rows(rows)


def person_alias_lists() -> Dict[str, List[Dict[str, Any]]]:
    """批量版：**一趟查完全部人的称谓表**（离线导出用）。

    按「每人一次」调用 `person_alias_list` 会在 2240 人身上开 2240 次连接，
    慢；但解码必须复用同一个 `_decode_alias_rows`，否则又成了「导出抄一遍」。
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT person_id, w, simp, n, kind, variants, by_book "
            "FROM person_aliases ORDER BY person_id, seq").fetchall()
    grouped: Dict[str, List] = {}
    for pid, *rest in rows:
        grouped.setdefault(pid, []).append(tuple(rest))
    return {pid: _decode_alias_rows(v) for pid, v in grouped.items()}


def _decode_alias_rows(rows) -> List[Dict[str, Any]]:
    """`(w, simp, n, kind, variants_json, by_book_json)` → 前端要的形状。

    只有这一份解码。联机端点、离线导出、断言都走它——多写一份就会在某个接口上
    悄悄分叉（「响应体组装放在 db 层」那条红线要防的就是这个）。
    """
    out = []
    for w, simp, n, kind, variants, by_book in rows:
        try:
            vs = json.loads(variants) if variants else []
        except (TypeError, ValueError):
            vs = []
        try:
            bb = json.loads(by_book) if by_book else {}
        except (TypeError, ValueError):
            bb = {}
        out.append({
            "w": w,
            "simp": simp,
            "kind": kind if kind in ALIAS_KINDS else "other",
            "n": int(n or 0),
            "variants": vs,
            "byBook": bb,
        })
    return out


def book_codes() -> List[str]:
    """库里真有的书号（按 code 排序）。端点校验 `?book=` 用它，别手写常量。"""
    with connect() as conn:
        return [r[0] for r in conn.execute("SELECT code FROM books ORDER BY code")]


def _by_book(table: str, id_col: str, pid: str) -> Dict[str, int]:
    """命中**按书分布**（全量，不受 limit / 篩選影響）。人物側與地名側共用。

    五本书都给键（没命中就是 0）——前端要靠它渲染筛选桶，缺键会静默不显示。
    """
    with connect() as conn:
        codes = [r[0] for r in conn.execute("SELECT code FROM books ORDER BY code")]
        got = {r["b"]: r["n"] for r in conn.execute(
            "SELECT c.book_id AS b, COUNT(*) AS n FROM {} m "
            "JOIN sentences s ON s.uid = m.sentence_uid "
            "JOIN chapters c ON c.id = s.chapter_id "
            "WHERE m.{} = ? GROUP BY c.book_id".format(table, id_col), (pid,))}
    return {c: int(got.get(c, 0)) for c in codes}


def mention_by_book(pid: str) -> Dict[str, int]:
    """某人的正文命中按书分布。语义见 `_by_book`。"""
    return _by_book("mentions", "person_id", pid)


def place_mention_by_book(pid: str) -> Dict[str, int]:
    """某地名的命中按书分布。语义见 `_by_book`。"""
    return _by_book("place_mentions", "place_id", pid)


def person_mentions(pid: str, tier: Optional[str] = None,
                    limit: int = 200, book: Optional[str] = None,
                    era: Optional[int] = None) -> List[Dict[str, Any]]:
    """某人的命中，**按篇分组**返回——这是详情页右侧的主体。

    ⚠️ `m.s` / `m.e` 是 pipeline 用 Python 算的**Unicode 码位**下标
    （不是字节、也不是 UTF-16 碼元），且 `text[s:e] == surface` 全量成立
    （verify_p3_mark.py 每次都断这一条）。
    前端**不能**用 `text.indexOf(surface)` 代替——同一句裡同一個詞多次出現時
    會標到第一處（實測 8319/182128條標錯）；也**不能**直接 `text.slice(s,e)`
    ——古籍含非 BMP 字（U+24CF9 等），JS 的碼元下標會偏（會新造 63 條錯）。
    正確做法見 app/web/app.js 的 `hitSpan`（三級回退）。
    """
    sql = """
        SELECT c.full_title AS chapter, s.chapter_id, s.uid, s.text,
               m.surface, m.s, m.e, m.tier, c.book_id AS book
        FROM mentions m
        JOIN sentences s ON s.uid = m.sentence_uid
        LEFT JOIN chapters c ON c.id = s.chapter_id
        WHERE m.person_id = ?
    """
    args: List[Any] = [pid]
    if tier:
        sql += " AND m.tier = ?"
        args.append(tier)
    b_list = _parse_book_filter(book)
    if len(b_list) == 1:
        sql += " AND c.book_id = ?"
        args.append(b_list[0])
    elif len(b_list) > 1:
        placeholders = ",".join("?" * len(b_list))
        sql += " AND c.book_id IN ({})".format(placeholders)
        args.extend(b_list)
    if era is not None:
        # 時代篩選 = 「句子所在書的記載區間含這個時代」。
        # ⚠️ 史記是通史（era_from IS NULL）→ **不屬於任何具體時代**，
        #    它單獨佔「按書 = 史記」那一桶。若把 NULL 當成「含全部時代」，
        #    每個時代桶都會被史記灌滿，篩選就失去意義。
        sql += (" AND c.book_id IN (SELECT code FROM books "
                "WHERE era_from IS NOT NULL AND era_from <= ? AND era_to >= ?)")
        args += [era, era]
    sql += " ORDER BY s.chapter_id, s.para_seq, s.seq LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def mention_nth(uid: str, s: Any, e: Any, surface: str,
                pid: str = "") -> Optional[int]:
    """一处命中 → `overrides` 要的 nth（**该句内第几个命中**，1-based）。

    为什么必须由后端算，不能让前端传
    --------------------------------
    前端（人物页/地名页）看到的是「这个人在本句里的第几条」，而 nth 是
    「本句**所有人/地名**的命中里的第几条」。一句常同时挂着好几个实体，
    两个序号根本不是一回事。
    """
    table = "place_mentions" if (pid and str(pid).startswith("pl_")) else "mentions"
    id_col = "place_id" if table == "place_mentions" else "person_id"
    with connect() as conn:
        rows = conn.execute(
            "SELECT {}, surface, s, e FROM {} "
            "WHERE sentence_uid=? ORDER BY s, e".format(id_col, table), (uid,)).fetchall()
    if not rows:
        return None
    # 先精确（串 + 偏移），与 overrides.cmd_apply 的匹配顺序保持一致
    for i, r in enumerate(rows, 1):
        if r["surface"] == surface and r["s"] == s and r["e"] == e:
            return i
    # 偏移对不上（这句被拆过 / 并过，或者前端给的是旧数据）：退回同串
    for i, r in enumerate(rows, 1):
        if r["surface"] != surface:
            continue
        if pid and r[id_col] != pid:
            continue
        return i
    for i, r in enumerate(rows, 1):
        if r["surface"] == surface:
            return i
    return None


def _as_int(v) -> Optional[int]:
    """xlsx 单元格可能是 `17` 也可能是 `17.0`（Excel 里手改过就会变 float）。

    不统一的话，前端拼的 key（`uid|s|e|surface`）与库里对不上，
    **徽章会静默消失**——不报错，只是看不见。
    """
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def override_states(rows: List[Dict[str, Any]]) -> List[bool]:
    """每条纠错**是否已经体现在库里**（与 `rows` 同序）。

    为什么要算
    ----------
    `overrides.xlsx` 里的行永远 `active`（revoke 只改状态、不删行，为了留痕），
    所以「已生效」和「待重建」在表里长得一模一样。不算的话后果有两个：

    1. 顶栏永远写「已記錄 N 條糾錯，重建後生效」，**N 永不归零**——
       界面在骗人，而且会反复诱导你按重建（重建完还是这句）。
    2. 改归生效之后，那条命中已经属于**别人**了，于是这个人的页面也会挂出
       「已標錯 → 某人」的徽章，看着像还没做。

    判据就是拿行去问库（一次查完，别一条一条问）：
      `drop`     → 这处命中已经不在了
      `reassign` → 这处命中已经归到 `to` 那个人/地名
      `keep`     → 不改数据，永远算「待重建」（它只是个标记）
    """
    uids = sorted({str(r.get("uid") or "").strip() for r in rows} - {""})
    hit: Dict[Any, str] = {}
    if uids:
        ph = ",".join("?" * len(uids))
        with connect() as conn:
            for uid, s, e, surface, pid in conn.execute(
                    "SELECT sentence_uid, s, e, surface, person_id FROM mentions "
                    "WHERE sentence_uid IN ({})".format(ph), uids):
                hit[(uid, s, e, surface)] = pid
            for uid, s, e, surface, plid in conn.execute(
                    "SELECT sentence_uid, s, e, surface, place_id FROM place_mentions "
                    "WHERE sentence_uid IN ({})".format(ph), uids):
                hit[(uid, s, e, surface)] = plid
    out = []
    for r in rows:
        key = (str(r.get("uid") or "").strip(), _as_int(r.get("s")),
               _as_int(r.get("e")), r.get("surface"))
        pid = hit.get(key)
        action = str(r.get("action") or "").strip()
        if action == "drop":
            out.append(pid is None)
        elif action == "reassign":
            out.append(pid is not None
                       and pid == str(r.get("to") or "").strip())
        else:
            out.append(False)
    return out


def person_names(pids) -> Dict[str, str]:
    """pid → 正名，**一次查完**而不是 N+1。

    网页「已標錯 → 項羽」要显示人名；`/api/overrides` 里存的是 pid，
    直接显示会变成 `→ p_xiangyu`。
    """
    pids = [p for p in (pids or []) if p]
    if not pids:
        return {}
    ph = ",".join("?" * len(pids))
    with connect() as conn:
        return {r[0]: r[1] for r in conn.execute(
            "SELECT id, trad_name FROM persons WHERE id IN ({})".format(ph),
            pids)}


def place_names(plids) -> Dict[str, str]:
    """place_id → 正名，**一次查完**而不是 N+1。"""
    plids = [p for p in (plids or []) if p and str(p).startswith("pl_")]
    if not plids:
        return {}
    ph = ",".join("?" * len(plids))
    with connect() as conn:
        return {r[0]: r[1] for r in conn.execute(
            "SELECT id, trad_name FROM places WHERE id IN ({})".format(ph),
            plids)}


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


# ------------------------------------------------------------------ 地名侧
#
# 地名原来只有「一列名字 + 计数」：`/api/search` 只查 persons，点地名条会落到
# 人物搜索上，而地名永远不在那儿 → **搜「長安」0 条**（places 里明明有 1346 处）。
# 下面这几个函数把地名补成与人物同构的第二套入口。
#
# 为什么这么便宜：`place_mentions` 与 `mentions` 的结构**完全对称**
# （`sentence_uid / {place_id,person_id} / surface / s / e / tier`），
# 所以查询语句能照抄，不用另立一套口径。


def search_places(q: str, limit: int = 30) -> List[Dict[str, Any]]:
    """按正名 / 简体名 / 異體寫法檢索地名。

    ⚠️ **別只 LIKE `places.name`**：那列與 `trad_name` 逐行相同（全表 0 行不同），
    只查它等於「簡體輸入整個地名庫失明」——輸「邯郸」搜不到「邯鄲」。
    異體寫法在 `place_aliases` 表裡（2026-10-03 新增，見 SCHEMA 註釋）。
    這與人物側查 `aliases` 表是同一個道理，別寫成兩個口徑。

    與 `search_persons` 的差別只有一點，是**故意的**：人物返回**全部**同名異人
    交由前端消歧；地名實測無重名（`trad_name` 無重複），所以直接按命中數排序返回。
    """
    like = "%{}%".format(q)
    sql = """
        SELECT p.id, p.trad_name, p.name, p.kind, p.era, p.summary,
               (SELECT COUNT(*) FROM place_mentions m
                 WHERE m.place_id = p.id) AS n
        FROM places p
        WHERE p.trad_name LIKE ? OR p.name LIKE ?
           OR p.id IN (SELECT place_id FROM place_aliases WHERE w LIKE ?)
        ORDER BY n DESC LIMIT ?
    """
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, (like, like, like, limit))]
        if not rows:
            return rows
        pids = [r["id"] for r in rows]
        # books 表的主键叫 `code` 不是 `id`（建库脚本里就是这么定的）
        bname = {r[0]: r[1] for r in conn.execute("SELECT code, name FROM books")}
        ph = ",".join("?" * len(pids))
        dist: Dict[str, List] = {}
        for pid, bid, n in conn.execute(
                "SELECT m.place_id, c.book_id, COUNT(*) FROM place_mentions m "
                "JOIN sentences s ON s.uid = m.sentence_uid "
                "JOIN chapters c ON c.id = s.chapter_id "
                "WHERE m.place_id IN ({}) "
                "GROUP BY m.place_id, c.book_id".format(ph), pids):
            dist.setdefault(pid, []).append((bid, n))
        for r in rows:
            top = sorted(dist.get(r["id"], []), key=lambda x: -x[1])[:3]
            r["kindLabel"] = PLACE_KIND_LABEL.get(r["kind"] or "外", r["kind"] or "外")
            r["books"] = [{"id": b, "name": bname.get(b, b), "n": n}
                          for b, n in top]
        return rows


def place_alias_list(pid: str) -> List[Dict[str, Any]]:
    """某地名的全部寫法（正名 + 異體），帶語料實際命中次數。

    與 `place_payload` 一起給前端：詳情頁要能說清「這裡的『邯鄲』在語料裡也寫作
    『邯郸』」，否則用戶輸入簡體沒命中會以為這個地名不存在。
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT w, n, by_book FROM place_aliases "
            "WHERE place_id=? ORDER BY seq", (pid,)).fetchall()
    out = []
    for w, n, by_book in rows:
        try:
            bb = json.loads(by_book) if by_book else {}
        except (TypeError, ValueError):
            bb = {}
        out.append({"w": w, "n": int(n or 0), "byBook": bb})
    return out


def place_profile(pid: str) -> Optional[Dict[str, Any]]:
    """地名详情页的「档案」部分。查不到返回 None（由调用方翻成 404）。"""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, trad_name, name, kind, era, summary "
            "FROM places WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    out = dict(row)
    kind = out["kind"] or "外"
    out["kind"] = kind
    out["kindLabel"] = PLACE_KIND_LABEL.get(kind, kind)
    out["era"] = out["era"] or ""
    out["summary"] = out["summary"] or ""
    return out


def place_mentions(pid: str, limit: int = 200, book: Optional[str] = None,
                   era: Optional[int] = None) -> List[Dict[str, Any]]:
    """某地名的命中，**按篇分组**返回（与 `person_mentions` 同构）。

    照抄人物侧是有意的：详情页的渲染代码（分篇标题 / 标命中 / 点句进原文层）
    照着 `renderPerson` 写一遍就行，两边形状一致。

    ⚠️ 单字地名（「江」「河」「淮」）一开口就是上千处，**必须**有 limit；
    前端人物页的「只看相关段落」也依赖 mentions 带 uid，口径与人物页一致。

    ⚠️ `m.s` / `m.e` 的语义（Python **碼位**下标、前端不能拿 indexOf 或
    裸 slice 代替）見 `person_mentions` 的 docstring——兩側同一套，不要只改一邊。
    """
    sql = """
        SELECT c.full_title AS chapter, s.chapter_id, s.uid, s.text,
               m.surface, m.s, m.e, m.tier, c.book_id AS book
        FROM place_mentions m
        JOIN sentences s ON s.uid = m.sentence_uid
        LEFT JOIN chapters c ON c.id = s.chapter_id
        WHERE m.place_id = ?
    """
    args: List[Any] = [pid]
    b_list = _parse_book_filter(book)
    if len(b_list) == 1:
        sql += " AND c.book_id = ?"
        args.append(b_list[0])
    elif len(b_list) > 1:
        placeholders = ",".join("?" * len(b_list))
        sql += " AND c.book_id IN ({})".format(placeholders)
        args.extend(b_list)
    if era is not None:
        # 與 `person_mentions` 同一條規則（史記是通史，不屬任何具體時代）
        sql += (" AND c.book_id IN (SELECT code FROM books "
                "WHERE era_from IS NOT NULL AND era_from <= ? AND era_to >= ?)")
        args += [era, era]
    sql += " ORDER BY s.chapter_id, s.para_seq, s.seq LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def place_books(pid: str) -> List[Dict[str, Any]]:
    """该地名在五书里的命中分布（详情页「見於哪些書」）。

    ⚠️ 刻意**不带 `book` 参数**、`n` 给全量，原因同 `person_alias_list`：
    「按当前书作用域变化」的数字一律由**前端**算（离线版没有服务端可问，
    请求里带 book 也只会被离线路由当成查询串忽略），数据由后端给全。
    """
    with connect() as conn:
        bname = {r[0]: r[1] for r in conn.execute("SELECT code, name FROM books")}
        rows = [{"id": b, "name": bname.get(b, b), "n": n} for b, n in conn.execute(
            "SELECT c.book_id, COUNT(*) FROM place_mentions m "
            "JOIN sentences s ON s.uid = m.sentence_uid "
            "JOIN chapters c ON c.id = s.chapter_id "
            "WHERE m.place_id = ? GROUP BY c.book_id", (pid,))]
    return sorted(rows, key=lambda x: -x["n"])


def place_payload(pid: str, limit: int = 200, book: Optional[str] = None,
                  era: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """`/api/place/{pid}` 的响应体（**联机端点与离线导出共用**，同 `person_payload`）。

    把这一步放在 db 层而不是端点里，是为了让 `export_static.py` 能直接抄——
    否则离线版就得把三块组装逻辑再写一遍，哪天改了一处另一处不知道，
    **两边悄悄不一致且不报错**。
    """
    profile = place_profile(pid)
    if not profile:
        return None
    return {
        "profile": profile,
        "mentions": place_mentions(pid, limit, book=book, era=era),
        "books": place_books(pid),
        # 與人物側同名的兩個欄位（同源同形，`renderPlace` 與 `renderPerson`
        # 共用同一段篩選/計數代碼）：全量分布 + 時代名。
        "mentionByBook": place_mention_by_book(pid),
        "eraNames": ERA_NAMES,
        # 寫法清單：讓詳情頁能說清「邯鄲也寫作邯郸」。少了它，用戶輸簡體沒命中
        # 會以為這個地名不存在（而 places.name 與 trad_name 逐行相同，沒這份
        # 資料就無從解釋）。
        "aliases": place_alias_list(pid),
        # 宋杰三國兩漢兵爭要地與戰略樞紐考據
        "strategic": STRATEGIC_PLACES.get(pid),
        # 駐跸征戰歷史人物交集
        "topPersons": place_top_persons(pid, 8),
    }



def chapter_sentences(cid: str, limit: int = 5000) -> Dict[str, Any]:
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
        b_list = _parse_book_filter(book)
        if b_list:
            known = {r[0] for r in conn.execute(
                "SELECT DISTINCT book_id FROM chapters")}
            unknown = [b for b in b_list if b not in known]
            if unknown:
                raise ValueError("未知書號：{}（有效：{}）".format(
                    "/".join(unknown), "/".join(sorted(known))))

        # 「按书看」的正确语义不是 `book` 列（61/62 条是空的——关系天然跨书，
        # 跟人物一样，见 docs/21），而是**这条关系在该书里有出处**：
        # 有证据句且证据句属于该书的边，也算命中。
        ev_rel: set = set()
        if b_list:
            ph_b = ",".join("?" * len(b_list))
            for rid, in conn.execute(
                    "SELECT r.rel_id FROM relations r "
                    "JOIN sentences s ON s.uid=r.evidence_uid "
                    "JOIN chapters c ON c.id=s.chapter_id "
                    "WHERE r.status='active' AND r.evidence_uid<>'' "
                    "  AND c.book_id IN ({})".format(ph_b), b_list):
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
            if b_list:
                # 空 book = 未标注（跨书），不因此被滤掉；但要么 `book` 列命中，
                # 要么证据句落在这本书里（ev_rel），二者都不是才排除。
                ph_b = ",".join("?" * len(b_list))
                sql += " AND (book IN ({}) OR (book='' AND rel_id IN ({})))".format(
                    ph_b, ",".join("?" * len(ev_rel)) or "''")
                args.extend(b_list)
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
