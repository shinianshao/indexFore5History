# -*- coding: utf-8 -*-
"""P3-2 快照與 diff：記住每次重建的命中集，下次能報出「變在哪」。

為什麼獨立成一個庫
------------------
`index.db` 的定位是**可刪重建**的產物（`build_index_db.py` 是
「偷舊 uid → 刪庫 → 重建」），把不可再生的歷史快照放進去會被重建沖掉。
所以快照放 `data/index/snapshots.db`，兩邊互不干擾，`index.db` 照樣隨時可刪。

比較鍵
------
`uid + s + e + surface`——四元組唯一確定「這一處命中」。
（`s/e` 是字符偏移，P4 開放改句子邊界後會失效，屆時靠 `nth` 兜，見 docs/24。）

四類變化
--------
| kind          | 含義                             |
|---------------|----------------------------------|
| `added`       | 原本沒標、現在標上了             |
| `removed`     | 原本標了、現在沒標 ← **最該看**  |
| `pid_changed` | 同一處從 A 改判給 B              |
| `tier_changed`| 歸屬沒變，置信度變了（改詞典常只動這個） |

用法
----
    python app/tools/snapshot.py dump --label rebuild   # 存一份快照
    python app/tools/snapshot.py list                   # 列已有快照
    python app/tools/snapshot.py diff                   # 最近兩次比
    python app/tools/snapshot.py diff --base 3 --new 5
    python app/tools/snapshot.py diff --kind removed --top 30
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
SNAP_DB = os.path.join(ROOT, "data", "index", "snapshots.db")

KEEP_DEFAULT = 5        # 保留最近幾份快照（每份約與命中數等行，別貪多）
ITEMS_LIMIT = 20000     # diff_items 單次上限，超出只存彙總
CTX = 14                # 上下文前後各取幾字（與 docs/17 條目格式一致）

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  id          INTEGER PRIMARY KEY,
  created_at  TEXT NOT NULL,
  label       TEXT,
  n_sentences INTEGER,
  n_mentions  INTEGER,
  note        TEXT
);

CREATE TABLE IF NOT EXISTS snapshot_mentions (
  snapshot_id INTEGER NOT NULL,
  uid         TEXT    NOT NULL,
  s           INTEGER,
  e           INTEGER,
  surface     TEXT,
  pid         TEXT,
  tier        TEXT,
  chapter_id  TEXT
);
CREATE INDEX IF NOT EXISTS ix_sm_key ON snapshot_mentions(snapshot_id, uid, s, e, surface);
CREATE INDEX IF NOT EXISTS ix_sm_pid ON snapshot_mentions(snapshot_id, pid);

CREATE TABLE IF NOT EXISTS diffs (
  id              INTEGER PRIMARY KEY,
  created_at      TEXT,
  base_id         INTEGER,
  new_id          INTEGER,
  n_added         INTEGER,
  n_removed       INTEGER,
  n_pid_changed   INTEGER,
  n_tier_changed  INTEGER,
  note            TEXT
);

CREATE TABLE IF NOT EXISTS diff_items (
  diff_id   INTEGER,
  kind      TEXT,
  uid       TEXT,
  s         INTEGER,
  e         INTEGER,
  surface   TEXT,
  old_pid   TEXT,
  new_pid   TEXT,
  old_tier  TEXT,
  new_tier  TEXT,
  chapter_id TEXT,
  context   TEXT
);
CREATE INDEX IF NOT EXISTS ix_di_key ON diff_items(diff_id, kind);
"""

KIND_LABEL = {
    "added": "新增",
    "removed": "消失",
    "pid_changed": "改歸",
    "tier_changed": "tier 變化",
}


# ---------------------------------------------------------------- 基礎設施

def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- dump

def dump(label: str = "", keep: int = KEEP_DEFAULT, note: str = "") -> int:
    """把當前 index.db 的命中集存成一份快照，回傳 snapshot_id。"""
    if not os.path.exists(DB_PATH):
        raise RuntimeError("索引庫不存在：{}\n先跑 rebuild.py".format(DB_PATH))

    src = connect(DB_PATH)
    n_sent = src.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    rows = src.execute(
        "SELECT m.sentence_uid, m.s, m.e, m.surface, m.person_id, m.tier, "
        "       s.chapter_id "
        "FROM mentions m LEFT JOIN sentences s ON s.uid = m.sentence_uid").fetchall()
    src.close()

    snap = connect(SNAP_DB)
    ensure_schema(snap)
    cur = snap.cursor()
    cur.execute(
        "INSERT INTO snapshots (created_at, label, n_sentences, n_mentions, note) "
        "VALUES (?,?,?,?,?)", (now(), label, n_sent, len(rows), note))
    sid = cur.lastrowid
    cur.executemany(
        "INSERT INTO snapshot_mentions "
        "(snapshot_id, uid, s, e, surface, pid, tier, chapter_id) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(sid, r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows])

    # 保留最近 keep 次：多出來的連同明細一起刪，否則庫只長不減
    if keep and keep > 0:
        old = [r[0] for r in cur.execute(
            "SELECT id FROM snapshots ORDER BY id DESC LIMIT -1 OFFSET ?",
            (keep,)).fetchall()]
        for oid in old:
            cur.execute("DELETE FROM snapshot_mentions WHERE snapshot_id=?", (oid,))
            cur.execute("DELETE FROM snapshots WHERE id=?", (oid,))
    snap.commit()
    snap.close()

    print("快照 #{} 已存：{:,} 句 / {:,} 命中（label={}）".format(
        sid, n_sent, len(rows), label or "-"))
    return sid


def list_snapshots() -> None:
    if not os.path.exists(SNAP_DB):
        print("（還沒有快照庫，先跑 dump）")
        return
    snap = connect(SNAP_DB)
    ensure_schema(snap)
    rows = snap.execute(
        "SELECT id, created_at, label, n_sentences, n_mentions FROM snapshots "
        "ORDER BY id").fetchall()
    snap.close()
    if not rows:
        print("（快照庫是空的）")
        return
    print("=== 快照（{} 份）===".format(len(rows)))
    for r in rows:
        print("  #{:<3} {}  {:<10} {:,} 句 / {:,} 命中".format(
            r[0], r[1], r[2] or "-", r[3] or 0, r[4] or 0))


# ---------------------------------------------------------------- diff

def _load(snap: sqlite3.Connection, sid: int) -> dict:
    """載入一份快照為 {key: (pid, tier, chapter_id)}。"""
    out = {}
    for r in snap.execute(
            "SELECT uid, s, e, surface, pid, tier, chapter_id "
            "FROM snapshot_mentions WHERE snapshot_id=?", (sid,)):
        out[(r[0], r[1], r[2], r[3])] = (r[4], r[5], r[6])
    return out


def _load_live() -> dict:
    """當前 index.db 的 {key: (pid, tier, chapter_id)}——diff 的「新」側。

    ⚠️ 別拿兩份快照互比：快照都是在重建**前**取的，兩份都是舊狀態，
    那樣永遠比出 0（第一版就這麼錯的）。「新」側必須是重建**後**的庫。
    """
    if not os.path.exists(DB_PATH):
        raise RuntimeError("索引庫不存在：{}\n先跑 rebuild.py".format(DB_PATH))
    src = connect(DB_PATH)
    out = {}
    for r in src.execute(
            "SELECT m.sentence_uid, m.s, m.e, m.surface, m.person_id, m.tier, "
            "       s.chapter_id "
            "FROM mentions m LEFT JOIN sentences s ON s.uid = m.sentence_uid"):
        out[(r[0], r[1], r[2], r[3])] = (r[4], r[5], r[6])
    src.close()
    return out


def _compare(old: dict, new: dict) -> list:
    """兩張 {key: (pid, tier, chapter_id)} 相減，列出四類變化。"""
    items = []
    for key, (pid, tier, cid) in new.items():
        if key not in old:
            items.append(("added", key, None, None, pid, tier, cid))
        else:
            opid, otier, ocid = old[key]
            if pid != opid:
                items.append(("pid_changed", key, opid, otier, pid, tier,
                              cid or ocid))
            elif tier != otier:
                items.append(("tier_changed", key, opid, otier, pid, tier,
                              cid or ocid))
    for key, (pid, tier, cid) in old.items():
        if key not in new:
            items.append(("removed", key, pid, tier, None, None, cid))
    return items


def _save(base_id, new_id, items: list, items_limit: int = ITEMS_LIMIT):
    """把比較結果落表（彙總 + 明細），回傳 (diff_id, counts, rows)。"""
    counts = {k: 0 for k in KIND_LABEL}
    for it in items:
        counts[it[0]] += 1

    truncated = len(items) > items_limit
    snap = connect(SNAP_DB)
    ensure_schema(snap)
    cur = snap.cursor()
    cur.execute(
        "INSERT INTO diffs (created_at, base_id, new_id, n_added, n_removed, "
        "n_pid_changed, n_tier_changed, note) VALUES (?,?,?,?,?,?,?,?)",
        (now(), base_id, new_id, counts["added"], counts["removed"],
         counts["pid_changed"], counts["tier_changed"],
         "明細被截斷（上限 {}）".format(items_limit) if truncated else ""))
    did = cur.lastrowid

    sents = _sentence_index()
    rows = []
    for kind, key, opid, otier, npid, ntier, cid in items[:items_limit]:
        uid, s, e, surface = key
        txt = ""
        if uid in sents:
            txt = make_context(sents[uid][0], s, e)
            cid = cid or sents[uid][1]
        rows.append((did, kind, uid, s, e, surface, opid, npid, otier, ntier,
                     cid, txt))
    cur.executemany(
        "INSERT INTO diff_items (diff_id, kind, uid, s, e, surface, "
        "old_pid, new_pid, old_tier, new_tier, chapter_id, context) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    snap.commit()
    snap.close()
    return did, counts, rows


def _sentence_index() -> dict:
    """當前庫的 {uid: (text, chapter_id)}，用來給 diff 補上下文。"""
    if not os.path.exists(DB_PATH):
        return {}
    src = connect(DB_PATH)
    out = {r[0]: (r[1], r[2]) for r in src.execute(
        "SELECT uid, text, chapter_id FROM sentences")}
    src.close()
    return out


def make_context(text: str, s: int, e: int) -> str:
    """前後各取 CTX 字，命中串用【】標出（與 docs/17 條目格式一致）。"""
    if text is None:
        return ""
    s = s or 0
    e = e or 0
    a = max(0, s - CTX)
    b = min(len(text), e + CTX)
    return "{0}【{1}】{2}".format(text[a:s], text[s:e], text[e:b])


def compute_diff(base_id: int, new_id: int, items_limit: int = ITEMS_LIMIT):
    """兩份快照互比（手工翻歷史用）。日常走 diff_live。"""
    snap = connect(SNAP_DB)
    ensure_schema(snap)
    old = _load(snap, base_id)
    new = _load(snap, new_id)
    snap.close()
    return _save(base_id, new_id, _compare(old, new), items_limit)


def diff_live(base_id: int, top: int = 10, kind: str = "",
              items_limit: int = ITEMS_LIMIT):
    """**當前庫** vs 某份快照——rebuild 末尾走這個。

    「新」側取自重建後的庫，所以報出來的就是這次改動的實際效果。
    """
    snap = connect(SNAP_DB)
    ensure_schema(snap)
    old = _load(snap, base_id)
    snap.close()
    new = _load_live()
    did, counts, rows = _save(base_id, None, _compare(old, new), items_limit)
    print_diff(did, "快照 #{}".format(base_id), "當前庫", counts, rows, top, kind)
    return did


def print_diff(did: int, base_label, new_label, counts: dict, rows: list,
               top: int = 10, kind: str = "") -> None:
    """base_label / new_label 由調用方給完整稱呼（「快照 #5」或「當前庫」）。"""
    print("\n=== diff #{}：{} → {} ===".format(did, base_label, new_label))
    for k in ("added", "removed", "pid_changed", "tier_changed"):
        mark = "  ★最該看" if k == "removed" else ""
        print("  {:<12} {:>7,}{}".format(KIND_LABEL[k], counts[k], mark))

    for k in ("added", "removed", "pid_changed", "tier_changed"):
        if kind and k != kind:
            continue
        sub = [r for r in rows if r[1] == k]
        if not sub:
            continue
        print("\n── {}（前 {} 條 / 共 {:,}）".format(
            KIND_LABEL[k], min(top, len(sub)), counts[k]))
        for i, r in enumerate(sub[:top], 1):
            _, _, uid, s, e, surface, opid, npid, otier, ntier, cid, ctx = r
            who = "{} → {}".format(opid or "—", npid or "—") \
                if k == "pid_changed" else (npid or opid or "—")
            print("  {:>2}. [{}] {} · {}".format(i, surface, cid or "?", uid))
            print("      {}".format(ctx or "（原句已不在庫中）"))
            print("      {} · {}".format(who, ntier or otier or "—"))


def drop(ids) -> None:
    """刪掉指定快照（連帶它的明細與引用它的 diff）。

    什麼時候用：跑測試/自檢留下了髒快照，或者想手動瘦身。
    例行瘦身不用它——`dump --keep` 會自動清最舊的。
    """
    if not os.path.exists(SNAP_DB):
        print("（還沒有快照庫）")
        return
    snap = connect(SNAP_DB)
    ensure_schema(snap)
    cur = snap.cursor()
    for sid in ids:
        cur.execute("DELETE FROM snapshot_mentions WHERE snapshot_id=?", (sid,))
        for (did,) in cur.execute(
                "SELECT id FROM diffs WHERE base_id=? OR new_id=?",
                (sid, sid)).fetchall():
            cur.execute("DELETE FROM diff_items WHERE diff_id=?", (did,))
            cur.execute("DELETE FROM diffs WHERE id=?", (did,))
        cur.execute("DELETE FROM snapshots WHERE id=?", (sid,))
    snap.commit()
    snap.close()
    print("已刪除快照：{}".format(" ".join("#{}".format(i) for i in ids)))


def diff_latest(top: int = 10, kind: str = "") -> None:
    """最新一份快照 vs 當前庫（等價於「從上次快照到現在變了什麼」）。

    ⚠️ 不要用「最近兩份快照互比」：快照都在重建前取，兩相比較恒為 0。
    """
    if not os.path.exists(SNAP_DB):
        return
    snap = connect(SNAP_DB)
    ensure_schema(snap)
    row = snap.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    snap.close()
    if not row:
        print("\n（還沒有快照）")
        return
    diff_live(row[0], top, kind)


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="BOOKINDEX 快照 / diff")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dump", help="存一份快照")
    p.add_argument("--label", default="", help="標記來源，如 rebuild")
    p.add_argument("--keep", type=int, default=KEEP_DEFAULT, help="保留最近幾份")
    p.add_argument("--note", default="")

    sub.add_parser("list", help="列已有快照")

    p = sub.add_parser("drop", help="刪掉指定快照（連帶相關 diff）")
    p.add_argument("--id", nargs="+", type=int, required=True)

    p = sub.add_parser("diff", help="比較（預設兩份快照互比）")
    p.add_argument("--base", type=int, default=0, help="基準快照 id（預設倒數第二份）")
    p.add_argument("--new", type=int, default=0, help="新快照 id（預設最新一份）")
    p.add_argument("--live", action="store_true",
                   help="拿**當前庫**當新側，與最新快照比（看「從那時到現在變了什麼」）")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--kind", default="",
                   choices=["", "added", "removed", "pid_changed", "tier_changed"])

    args = ap.parse_args()

    if args.cmd == "dump":
        dump(args.label, args.keep, args.note)
    elif args.cmd == "list":
        list_snapshots()
    elif args.cmd == "drop":
        drop(args.id)
    elif args.cmd == "diff":
        if args.live:
            diff_latest(args.top, args.kind)
            return 0
        if not os.path.exists(SNAP_DB):
            print("（還沒有快照庫）")
            return 1
        snap = connect(SNAP_DB)
        ensure_schema(snap)
        ids = [r[0] for r in snap.execute("SELECT id FROM snapshots ORDER BY id")]
        snap.close()
        if len(ids) < 2:
            print("（至少要兩份快照才能比；先跑 dump）")
            return 1
        base = args.base or ids[-2]
        new = args.new or ids[-1]
        did, counts, rows = compute_diff(base, new)
        print_diff(did, "快照 #{}".format(base), "快照 #{}".format(new),
                   counts, rows, args.top, args.kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
