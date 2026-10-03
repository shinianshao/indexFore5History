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
  volumes  INTEGER,
  era_from INTEGER,   -- 本書記載的時代區間（era index）；通史（史記）為 NULL
  era_to   INTEGER
);

-- main_persons / top_places：篇主與高頻地名，id 以逗號分隔存文本。
-- 為什麼不單開關聯表：篇目一覽只要「這篇主要講誰」的**名字**做標籤，
-- 564 篇 × 3~5 個 id，為了它再 JOIN 兩張表不划算；而「誰在哪篇出現過」
-- 這種反查已經有 mentions 表了，不需要冗余一份。
CREATE TABLE IF NOT EXISTS chapters (
  id          TEXT PRIMARY KEY,
  book_id     TEXT,
  title       TEXT,
  full_title  TEXT,
  category    TEXT,
  volume      TEXT,
  char_count  INTEGER,
  sentence_count INTEGER,
  main_persons TEXT,
  top_places   TEXT
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
  era_rank  INTEGER,  -- 時代序號（pipeline 的 era_index）；NULL = 沒斷出時代
  status    TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS aliases (
  person_id TEXT,
  alias     TEXT,
  is_trad   INTEGER
);

-- 称谓分组表：人物页「完整称谓表」的数据源。
-- 数据在 annotate 阶段（pipeline/annotate.py build_alias_list）就算好了：
-- 一条 = 一个归并后的称谓（繁简异体已并成同一条），自带类别 / 次数 / 按书分账。
-- 这里**原样落表**，app 只读不重算——app/ 不能 import pipeline/，两者只在 JSON / DB 上交汇。
CREATE TABLE IF NOT EXISTS person_aliases (
  person_id TEXT,
  seq       INTEGER,   -- 组内展示顺序（pipeline 已按 kind 序 + 次数降序排好）
  w         TEXT,      -- 展示写法：取正文中实际出现最多的那一种
  simp      TEXT,      -- 归并键：异体归一 → 繁转简
  n         INTEGER,   -- 全五书合计出现次数（0 = 词典收录了但本书不用）
  kind      TEXT,      -- name / title / generic / short / other
  variants  TEXT,      -- JSON array：全部写法（繁简 + 异体）
  by_book   TEXT       -- JSON object：按书分账 {"sj": 353, "hs": 350, ...}
);
CREATE INDEX IF NOT EXISTS idx_person_aliases
  ON person_aliases(person_id, seq);

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

-- 地名命中明细（与 mentions 对称）。
-- ⚠️ 建库时曾**只灌了 marks（人物）漏了 pmarks（地名）**，结果库里查不到
-- 任何地名命中数——地名索引页因此只能去读 book-data.json，绕开了数据库。
-- 现在补上：地名索引/快捷词/篇目里的 topPlaces 一律从本表聚合。
CREATE TABLE IF NOT EXISTS place_mentions (
  id           INTEGER PRIMARY KEY,
  sentence_uid TEXT,
  place_id     TEXT,
  surface      TEXT,
  s            INTEGER,
  e            INTEGER,
  tier         TEXT
);
CREATE INDEX IF NOT EXISTS ix_pmention_place ON place_mentions(place_id);
CREATE INDEX IF NOT EXISTS ix_pmention_uid ON place_mentions(sentence_uid);

CREATE TABLE IF NOT EXISTS places (
  id        TEXT PRIMARY KEY,
  trad_name TEXT,
  name      TEXT,
  kind      TEXT,
  era       TEXT,
  summary   TEXT
);

-- 地名異體（簡體 / 異寫）—— 2026-10-03 新增
--   ⚠️ 為什麼必須有這張表：`pipeline/build_places.py` 把簡體與異寫放在
--      book-data 的 `aliases` 裡（1575 個地名中 831 個有異形），但 places 主表
--      **只有 name 一列且與 trad_name 逐行相同**（全表 0 行不同）。結果是
--      輸「邯郸」搜不到「邯鄲」——`LIKE name` 與 `LIKE trad_name` 都只匹配繁体，
--      簡體輸入整個地名庫都失明。
--      這不是檢索邏輯的問題，是**建庫漏了一列**。
--   權威源是 book-data.json 的 places[].aliases（人寫的 places.xlsx 也早有
--      「别名(竖线分隔)」列，只是從沒灌進庫）。
CREATE TABLE IF NOT EXISTS place_aliases (
  place_id TEXT,
  seq      INTEGER,
  w        TEXT,          -- 異體寫法（可能是簡體、也可能是異寫）
  n        INTEGER,       -- 該寫法在語料裡的命中次數
  by_book  TEXT,          -- JSON: {書號: 次數}
  -- ⚠️ 複合主鍵是**必需**的，不是nice-to-have（2026-10-03 審查 P1-3）：
  --    沒有主鍵時 `INSERT OR REPLACE` **退化成普通 INSERT**，重跑兩遍就出重複行，
  --    而 `place_alias_list` / `offSearchPlaces` 都會靜靜返回重複條目。
  --    判据是「注入重复灌一次，看条数翻倍」——不报错，只多一倍。
  PRIMARY KEY (place_id, w)
);
CREATE INDEX IF NOT EXISTS ix_palias_place ON place_aliases(place_id);
CREATE INDEX IF NOT EXISTS ix_palias_w ON place_aliases(w);

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
    # ⚠️ 時代區間不在 chapters 裡，只在 meta.books。缺了它「前朝」標記就沒法判。
    era = {b["code"]: (b.get("eraRange") or [None, None])
           for b in (d.get("meta") or {}).get("books") or []}
    conn.executemany("INSERT OR REPLACE INTO books VALUES (?,?,?,?,?)",
                     [(k, v, None, era.get(k, [None, None])[0],
                       era.get(k, [None, None])[1]) for k, v in books.items()])
    conn.executemany(
        "INSERT OR REPLACE INTO chapters VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(c["id"], c.get("bookId"), c.get("title"), c.get("fullTitle"),
          c.get("category"), c.get("volume"), c.get("charCount"),
          c.get("sentenceCount"),
          ",".join(c.get("mainPersons") or []),
          # topPlaces 是 [{pid, n}]，按 n 降序只留前三——標籤欄放不下更多
          ",".join(t["pid"] for t in sorted(
              (c.get("topPlaces") or []), key=lambda x: -x.get("n", 0))[:3]))
         for c in d["chapters"]])

    # ── sentences + mentions ──────────────────────────────────────────
    srows, mrows, prows = [], [], []
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
        # ⚠️ 地名在 `pmarks`（p=place），不是 `marks`。以前这行没写，
        # 于是库里查不到任何地名命中——地名索引只能绕开数据库去读 JSON。
        for m in (s.get("pmarks") or []):
            prows.append((uid, m.get("pid"), m.get("alias"),
                          m.get("s"), m.get("e"), m.get("tier")))

    conn.executemany("INSERT OR REPLACE INTO sentences VALUES (?,?,?,?,?,?,?)", srows)
    conn.executemany(
        "INSERT INTO mentions (sentence_uid, person_id, surface, s, e, tier) "
        "VALUES (?,?,?,?,?,?)", mrows)
    conn.executemany(
        "INSERT INTO place_mentions (sentence_uid, place_id, surface, s, e, tier) "
        "VALUES (?,?,?,?,?,?)", prows)

    # ── persons / aliases / places ────────────────────────────────────
    conn.executemany(
        "INSERT OR REPLACE INTO persons VALUES (?,?,?,?,?,?,?,?)",
        [(p["id"], p.get("tradName"), p.get("name"), p.get("dynasty"),
          p.get("title"), p.get("summary"), p.get("eraRank"), "active")
         for p in d["persons"]])
    # variant → 是否繁体（供 aliases.is_trad 用；见下方 aliases 灌入处的说明）
    trad_of = {}
    for p in d["persons"]:
        for g in (p.get("aliasList") or []):
            for v in (g.get("variants") or []):
                trad_of[(p["id"], v)] = 0 if v == g.get("simp") else 1
    arows = []
    for p in d["persons"]:
        for al in (p.get("aliases") or []):
            # 是否繁体：别写 `al == al` 那种恒真式（以前就是这么错的，整列全填 1）。
            # 这里用 annotate 已经算好的归并键——variants 里不等于 `simp` 的就是
            # 繁体写法（`simp` 是 t2s(norm(raw)) 的结果），语料是繁体所以兜底给 1。
            arows.append((p["id"], al, trad_of.get((p["id"], al), 1)))
    conn.executemany("INSERT OR REPLACE INTO aliases VALUES (?,?,?)", arows)

    # ── 称谓分组表（人物页「完整称谓表」，见 SCHEMA 注释）──────────────
    parows = []
    for p in d["persons"]:
        for i, g in enumerate(p.get("aliasList") or []):
            parows.append((p["id"], i, g.get("w"), g.get("simp"),
                           int(g.get("n") or 0), g.get("kind"),
                           json.dumps(g.get("variants") or [], ensure_ascii=False),
                           json.dumps(g.get("byBook") or {}, ensure_ascii=False)))
    conn.executemany(
        "INSERT OR REPLACE INTO person_aliases VALUES (?,?,?,?,?,?,?,?)", parows)
    conn.executemany(
        "INSERT OR REPLACE INTO places VALUES (?,?,?,?,?,?)",
        [(p["id"], p.get("tradName"), p.get("name"), p.get("kind"),
          p.get("era"), p.get("summary")) for p in d.get("places", [])])

    # ── 地名異體表（檢索簡體 / 異寫用）────────────────────────────────
    # ⚠️ 次數與分書**現算**而不是照抄 aliases：aliases 只是「登了哪些寫法」，
    #    不帶次數（person_aliases 的 n 來自 annotate，place 側沒有那一步）。
    #    語料裡實際用的是哪個寫法，只有 place_mentions.surface 知道。
    #    「異體表列了但一次沒被用過」是正常狀態（例如『邯郸』這條只在簡體檢索時
    #    才有意義，語料全繁體），別因此把 n=0 的行濾掉——那就白建這張表了。
    prows_by_id: dict = {}
    for uid, pid, surf in conn.execute(
            "SELECT sentence_uid, place_id, surface FROM place_mentions"):
        prows_by_id.setdefault(pid, []).append((uid, surf))
    book_of: dict = {}
    for uid, bid in conn.execute(
            "SELECT s.uid, c.book_id FROM sentences s "
            "JOIN chapters c ON c.id = s.chapter_id"):
        book_of[uid] = bid
    palias = []
    for p in d.get("places", []):
        pid = p["id"]
        # 寫法順序：正名在前，其後按 aliases 原序去重（別排序，順序是 pipeline 的語義）
        forms = [p.get("tradName") or ""]
        for a in (p.get("aliases") or []):
            if a and a not in forms:
                forms.append(a)
        n_by_form: dict = {}
        bk_by_form: dict = {}
        for uid, surf in prows_by_id.get(pid, []):
            key = (surf or "").strip() or (p.get("tradName") or "")
            n_by_form[key] = n_by_form.get(key, 0) + 1
            b = book_of.get(uid)
            if b:
                bk_by_form.setdefault(key, {})
                bk_by_form[key][b] = bk_by_form[key].get(b, 0) + 1
        # ⚠️ 語料裡**實際用過**的寫法必須併進來（2026-10-03 審查 P1-1）。
        #    漏这一步的後果有兩個，且**都不報錯**：
        #      ① 檢索失明——`河閒` 96 處、`雒` 89 處、`關内` 41 處……共 61 種寫法
        #         從沒進過 places[].aliases，於是 place_aliases 裡沒有它們，
        #         `search_places('河閒')` 返回 0（正名「河間」能搜到，但那 96 處
        #         記在 surface='河閒' 上，用戶按語料寫法找不到）。
        #      ② Σ n 對不齊——只統計「登過的寫法」，所以 60 個地名
        #         COUNT(place_mentions) != SUM(alias.n)（pl_hejian_jun 342 vs 246）。
        #    順序：正名 → aliases 原序 → 語料實測（按次數降序，只為可讀性）。
        for w, _n in sorted(n_by_form.items(), key=lambda kv: -kv[1]):
            if w and w not in forms:
                forms.append(w)
        for i, w in enumerate(f for f in forms if f):
            palias.append((pid, i, w, n_by_form.get(w, 0),
                           json.dumps(bk_by_form.get(w, {}), ensure_ascii=False)))
    conn.executemany(
        "INSERT OR REPLACE INTO place_aliases (place_id, seq, w, n, by_book) "
        "VALUES (?,?,?,?,?)", palias)

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
              "persons", "aliases", "person_aliases", "places", "relations"):
        print("  {:<14s} {:>8,d}".format(t, cnt(t)))
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
    # 称谓分组表：劉邦应有「漢王 ×N」这类带次数的条目，且条数与 book-data 对齐
    na = conn.execute(
        "SELECT COUNT(*) FROM person_aliases WHERE person_id='p_liubang'").fetchone()[0]
    top1 = conn.execute(
        "SELECT w, n FROM person_aliases WHERE person_id='p_liubang' "
        "ORDER BY n DESC LIMIT 1").fetchone()
    print("  自检：劉邦称谓 {} 条，最高频「{} ×{}」".format(na, top1[0], top1[1]))
    # 地名同理：秦的命中数应与 book-data 的 places 一致（以前这张表是空的）
    rp = conn.execute(
        "SELECT COUNT(*) FROM place_mentions WHERE place_id='pl_qin'").fetchone()[0]
    print("  自检：秦（地名）在库里的命中数 = {}".format(rp))
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
