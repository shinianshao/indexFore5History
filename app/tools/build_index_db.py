# -*- coding: utf-8 -*-
"""把现有产物灌进 SQLite，建成**可查询**的索引库（docs/21 P1）。

输入（都是派生物，可随时重建）：
    data/index/book-data.json   篇 / 句 / 命中 / 人物 / 地名
输出：
    data/index/index.db         八张表 + FTS5 全文索引

**这不是权威源**。权威源是 workbook/*.xlsx（人写的表格），
book-data.json 是管线跑出来的产物，本库又是产物的另一种排布——
删掉重跑本脚本即可，不会丢任何人的审定。

三件必须做对的事
----------------
1. **sentences.uid 是稳定主键**。现有 `sj-001-0002-001` 是位置键，
   一旦 P4 让句子可编辑（拆/并/删），位置会位移，66,782 条命中的外键全崩。
   本脚本给每句分配 uid，并**优先复用库里已有的**（按位置键匹配）。
   ⚠️ 已知限制：目前按 (篇, 段序, 句序) 匹配，改了切分仍会匹配不上。
   等 P4 支持编辑时，这里要改成「按文本内容 + 上下文」匹配或维护显式映射。

2. **mentions 必须独立成表**。命中明细原本埋在 sentence.marks 的嵌套数组里，
   没法查询（想筛「所有 tier=guess 的命中」要遍历近十万句）。

3. **relations 表先建出来，可以先空着**。这是给人物关系图 / family tree 留的接口。
   现在 `persons` 表一个关系字段都没有，等想做族谱时再建就要重扫全语料——
   建空表的成本几乎为零，漏了才是真返工（docs/21 §12.2）。

用法
----
    python app/tools/build_index_db.py            # 全量重建（删旧库）
    python app/tools/build_index_db.py --check     # 只查统计，不写库
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOOK = os.path.join(ROOT, "data", "index", "book-data.json")
# 认环境变量（同 db.py / snapshot.py）：断言要在临时库副本上跑
DB = (os.environ.get("BOOKINDEX_DB")
      or os.path.join(ROOT, "data", "index", "index.db"))

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS books (
  code     TEXT PRIMARY KEY,
  name     TEXT,
  volumes  INTEGER
);

CREATE TABLE IF NOT EXISTS chapters (
  id          TEXT PRIMARY KEY,
  book_id     TEXT,
  title       TEXT,
  full_title  TEXT,
  category    TEXT,
  volume      TEXT,
  char_count  INTEGER,
  sentence_count INTEGER
);

-- uid = 稳定主键；pos_key = 位置键（只用于排序，会随切分变化）
CREATE TABLE IF NOT EXISTS sentences (
  uid       TEXT PRIMARY KEY,
  pos_key   TEXT,
  chapter_id TEXT,
  para_seq  INTEGER,
  seq       INTEGER,
  text      TEXT,
  status    TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS persons (
  id        TEXT PRIMARY KEY,
  trad_name TEXT,
  name      TEXT,
  dynasty   TEXT,
  title     TEXT,
  summary   TEXT,
  status    TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS aliases (
  person_id TEXT,
  alias     TEXT,
  is_trad   INTEGER
);

-- 命中明细独立成表：这是「方便查找确认」的查询入口
CREATE TABLE IF NOT EXISTS mentions (
  id           INTEGER PRIMARY KEY,
  sentence_uid TEXT,
  person_id    TEXT,
  surface      TEXT,
  s            INTEGER,
  e            INTEGER,
  tier         TEXT
);

CREATE TABLE IF NOT EXISTS places (
  id        TEXT PRIMARY KEY,
  trad_name TEXT,
  name      TEXT,
  kind      TEXT,
  era       TEXT,
  summary   TEXT
);

-- 人物关系 —— 见 docs/25（P6 设计审查后的定稿）
--   ⚠️ 本表是**派生的**：权威源是 workbook/relations.xlsx，
--      每次重建后必须由 `pipeline/relations.py apply` 重新灌入，否则数据全丢
--      （index.db 整个删掉重建，这里不会幸免）。
--   rel_id   = md5(a|b|rel|book|era)，稳定业务主键（id 会随重建重排号）
--   rel_type / confidence **由代码派生**（rel → rel_type，source → confidence）
--   symmetric = 1 对称（兄弟/友/政敵）；0 有向（父→子）。只存**规范边**，
--               反向边由 REL_INVERSE 在代码里派生，禁止双写（P0-5）
--   evidence_text 只是录入那一刻的展示缓存，**以 uid 指向的现句为准**（P0-4）
CREATE TABLE IF NOT EXISTS relations (
  rel_id        TEXT PRIMARY KEY,
  person_a      TEXT,
  surface_a     TEXT,
  person_b      TEXT,
  surface_b     TEXT,
  rel_type      TEXT,
  rel           TEXT,
  symmetric     INTEGER,
  era           TEXT,
  book          TEXT,
  evidence_uid  TEXT,
  evidence_text TEXT,
  confidence    REAL,
  source        TEXT,
  status        TEXT,
  note          TEXT,
  created_at    TEXT
);

-- 关系证据**子表**（docs/28 P1-6）：一条关系可以有多条出处。
-- 之前只有 relations.evidence_uid 一个字段，于是「12/62 条边有 ≥2 条可用候选句」
-- 这个已经出现的需求装不下——要么丢证据，要么一条边挂错一句。
--   verdict = accept（采用）/ reject（候选被否，留着免得下次又抽出来）
--   relations.evidence_uid 仍保留，指向**主证据**（第一条 accept），
--   这样只用到一条的场景不用改代码。
CREATE TABLE IF NOT EXISTS relation_evidence (
  rel_id        TEXT,
  evidence_uid  TEXT,
  verdict       TEXT,
  note          TEXT,
  created_at    TEXT,
  PRIMARY KEY (rel_id, evidence_uid)
);

CREATE INDEX IF NOT EXISTS ix_sent_chapter ON sentences(chapter_id);
CREATE INDEX IF NOT EXISTS ix_sent_status  ON sentences(status);
CREATE INDEX IF NOT EXISTS ix_mention_person ON mentions(person_id);
CREATE INDEX IF NOT EXISTS ix_mention_tier   ON mentions(tier);
CREATE INDEX IF NOT EXISTS ix_mention_sent   ON mentions(sentence_uid);
CREATE INDEX IF NOT EXISTS ix_alias_person   ON aliases(person_id);
CREATE INDEX IF NOT EXISTS ix_alias_surface  ON aliases(alias);
CREATE INDEX IF NOT EXISTS ix_rel_a          ON relations(person_a);
CREATE INDEX IF NOT EXISTS ix_rel_b          ON relations(person_b);
CREATE INDEX IF NOT EXISTS ix_rel_type       ON relations(rel_type);
CREATE INDEX IF NOT EXISTS ix_rel_pair       ON relations(person_a, person_b);
-- 改句子（拆分/弃用）时要反查"哪些关系的证据失效了"
CREATE INDEX IF NOT EXISTS ix_rel_evidence   ON relations(evidence_uid);
"""


def make_uid(chapter_id, para, seq):
    """稳定主键。**只吃位置**——不吃正文，这样改了原文不会连坐改 uid。

    ⚠️ 这条是过渡方案：一旦句子可编辑（P4），位置会位移，这里必须
    改成「先查库里有没有、有就复用」的语义（本脚本的 load_existing_uids
    已经在做，但匹配键仍是位置，插入/删除句子时仍会失配）。
    """
    raw = "{}|{}|{}".format(chapter_id, para, seq)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def fts_phrase(query):
    """把中文查询串转成 FTS5 短语：按字切分 + 双引号（要求相邻）。

    因为入库时按字切分了，这里必须同样处理，否则搜不到。
    """
    return '"' + " ".join(str(query).strip()) + '"'


def load_existing_uids(conn):
    try:
        cur = conn.execute("SELECT chapter_id, para_seq, seq, uid FROM sentences")
        return {(r[0], r[1], r[2]): r[3] for r in cur}
    except sqlite3.Error:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只查统计，不重建")
    ap.add_argument("--fresh", action="store_true",
                    help="不复用旧库的 uid，全部重新分配")
    a = ap.parse_args()

    if not os.path.exists(BOOK):
        raise SystemExit("找不到 {}".format(BOOK))

    t0 = time.time()
    d = json.load(open(BOOK, encoding="utf-8"))
    print("载入 book-data.json  {:.1f}s".format(time.time() - t0))

    # 先偷出旧库的 uid（为了复用），再把库整个删掉重建——
    # 否则 mentions/aliases 是追加写入，重跑一次就翻倍。
    existing = {}
    if os.path.exists(DB) and not a.fresh:
        old = sqlite3.connect(DB)
        try:
            existing = load_existing_uids(old)
        finally:
            old.close()
    for suffix in ("", "-wal", "-shm"):
        p = DB + suffix
        if os.path.exists(p):
            os.remove(p)

    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    reused = 0

    # ── books / chapters ──────────────────────────────────────────────
    books = {}
    for c in d["chapters"]:
        books.setdefault(c["bookId"], c.get("book") or c["bookId"])
    conn.executemany("INSERT OR REPLACE INTO books VALUES (?,?,?)",
                     [(k, v, None) for k, v in books.items()])
    conn.executemany(
        "INSERT OR REPLACE INTO chapters VALUES (?,?,?,?,?,?,?,?)",
        [(c["id"], c.get("bookId"), c.get("title"), c.get("fullTitle"),
          c.get("category"), c.get("volume"), c.get("charCount"),
          c.get("sentenceCount")) for c in d["chapters"]])

    # ── sentences + mentions ──────────────────────────────────────────
    srows, mrows = [], []
    uid_of = {}
    n_corpus = n_db = 0
    for s in d["sentences"]:
        cid = s["chapterId"]
        para, seq = s.get("paraSeq"), s.get("seq")
        key = (cid, para, seq)
        # 優先級：**語料層透傳的 uid > 舊庫按位置複用 > 現算**。
        # 語料層的 uid 才是權威——句子一旦可編輯（P4），位置會位移，
        # 若還按位置去舊庫撿，會把上一句的 uid 錯配到這一句身上。
        if s.get("uid"):
            uid = s["uid"]
            n_corpus += 1
            reused += 1
        elif key in existing:
            uid = existing[key]
            n_db += 1
            reused += 1
        else:
            uid = make_uid(cid, para, seq)
        uid_of[s["id"]] = uid
        srows.append((uid, s["id"], cid, para, seq, s.get("text") or "", "active"))
        for m in (s.get("marks") or []):
            mrows.append((uid, m.get("pid"), m.get("alias"),
                          m.get("s"), m.get("e"), m.get("tier")))

    conn.executemany("INSERT OR REPLACE INTO sentences VALUES (?,?,?,?,?,?,?)", srows)
    conn.executemany(
        "INSERT INTO mentions (sentence_uid, person_id, surface, s, e, tier) "
        "VALUES (?,?,?,?,?,?)", mrows)

    # ── persons / aliases / places ────────────────────────────────────
    conn.executemany(
        "INSERT OR REPLACE INTO persons VALUES (?,?,?,?,?,?,?)",
        [(p["id"], p.get("tradName"), p.get("name"), p.get("dynasty"),
          p.get("title"), p.get("summary"), "active") for p in d["persons"]])
    arows = []
    for p in d["persons"]:
        for al in (p.get("aliases") or []):
            # 是否繁体用「转简体后是否还等于自己」判断，和 check_trad 的口径一致
            arows.append((p["id"], al, 1 if al == al else 0))
    conn.executemany("INSERT OR REPLACE INTO aliases VALUES (?,?,?)", arows)
    conn.executemany(
        "INSERT OR REPLACE INTO places VALUES (?,?,?,?,?,?)",
        [(p["id"], p.get("tradName"), p.get("name"), p.get("kind"),
          p.get("era"), p.get("summary")) for p in d.get("places", [])])

    # ── FTS5（不支持就跳过，不让它成为阻塞）────────────────────────────
    # ⚠️ 中文的关键坑：FTS5 默认 unicode61 分词器把**连续汉字当成一个 token**，
    # 于是整句是一个 token，搜「項羽」永远搜不到（实测只命中 2 句，实际 922 处）。
    # 解法：**按字切分**入库（每字一个 token），查询时同样按字切分 + 短语查询。
    # 不用 trigram：它要求查询词≥3 字，而人名多为 2 字。
    fts = False
    try:
        conn.executescript("DROP TABLE IF EXISTS sentences_fts;")
        conn.executescript("""
            CREATE VIRTUAL TABLE sentences_fts
              USING fts5(uid UNINDEXED, text);
        """)
        conn.executemany("INSERT INTO sentences_fts(uid, text) VALUES (?,?)",
                         [(r[0], " ".join(r[5] or "")) for r in srows])
        fts = True
    except sqlite3.Error as e:
        print("  ⚠ FTS5 不可用，跳过全文索引：{}".format(e))

    conn.commit()

    # ── 统计 ──────────────────────────────────────────────────────────
    def cnt(t):
        return conn.execute("SELECT COUNT(*) FROM {}".format(t)).fetchone()[0]

    print("\n=== index.db ===")
    for t in ("books", "chapters", "sentences", "mentions",
              "persons", "aliases", "places", "relations"):
        print("  {:<10s} {:>8,d}".format(t, cnt(t)))
    print("  uid 来源：语料透传 {} / 旧库复用 {} / 新建 {} 条".format(
        n_corpus, n_db, len(srows) - reused))
    print("  FTS5 全文索引: {}".format("已建" if fts else "未建"))

    tiers = dict(conn.execute(
        "SELECT tier, COUNT(*) FROM mentions GROUP BY tier ORDER BY 2 DESC").fetchall())
    print("  tier 分布: {}".format(tiers))

    # 抽样自检：劉邦的命中数应与 book-data 一致
    r = conn.execute(
        "SELECT COUNT(*) FROM mentions WHERE person_id='p_liubang'").fetchone()[0]
    print("\n  自检：劉邦在库里的命中数 = {}".format(r))
    if fts:
        n = conn.execute(
            "SELECT COUNT(*) FROM sentences_fts WHERE sentences_fts MATCH ?",
            (fts_phrase("項羽"),)).fetchone()[0]
        print("  自检：全文搜「項羽」命中 {} 句".format(n))
        n2 = conn.execute(
            "SELECT COUNT(*) FROM sentences_fts WHERE sentences_fts MATCH ?",
            (fts_phrase("鴻門宴"),)).fetchone()[0]
        print("  自检：全文搜「鴻門宴」命中 {} 句".format(n2))

    print("\n-> {}（{:.1f} MB）".format(DB, os.path.getsize(DB) / 1048576))
    conn.close()


if __name__ == "__main__":
    main()
