# -*- coding: utf-8 -*-
"""P3-3 人工糾錯（`overrides`）：把「這條標錯了」寫成可追溯的一行。

為什麼要有它
------------
泛稱判定（「梁王」到底是誰）總有判不準的時候。與其反覆改 `GENERIC_*` 規則
賭它下次判對，不如承認：**這一處就是判錯了，我指定它歸誰**。
這種「單條糾錯」進 `overrides.xlsx`，規則表繼續管大局，兩者互不干擾。

三條硬規矩（別破）
------------------
1. **pipeline 對 `overrides.xlsx` 只有讀權限**。
   會由腳本填的列（`上下文` / `原pid` / `原tier` …）**只在錄入那一刻寫**，
   重建時**絕不刷新**——否則就是 P0「導出腳本沖掉權威源」那次事故的重演。
   寫入由 `add` 命令或將來的 UI 承擔。
2. **不物理刪除**：糾錯記錄只把 `状态` 改成 `dead`，行留著可追溯。
3. **不進 annotate 引擎**：`apply` 在標註四步**之後**、建庫**之前**改
   `book-data.json`，只動 marks，不動匹配與判定邏輯。

定位一條命中
------------
`uid + s + e + surface` 為主鍵；`nth`（該句內第幾個同名命中）是**冗餘錨**——
`s/e` 是字符偏移，P4 開放改句子邊界後會失效，屆時靠 `nth` 兜。

用法
----
    python app/tools/overrides.py init                      建空表（已存在則不動）
    python app/tools/overrides.py show --uid <uid>          列該句有哪些命中
    python app/tools/overrides.py add  --uid <uid> --nth 2 --new 劉邦
    python app/tools/overrides.py add  --uid <uid> --nth 3 --action drop
    python app/tools/overrides.py list                      列已有糾錯
    python app/tools/overrides.py apply                     套用到 book-data.json
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
BOOK = os.path.join(ROOT, "data", "index", "book-data.json")
WORKBOOK = os.path.join(ROOT, "workbook", "overrides.xlsx")

# 與 persons.xlsx 的風格一致：中文列名（簡體）+ 英文鍵
HEADERS = [
    "uid", "s", "e", "surface", "nth",
    "篇(chapterId)", "上下文",
    "原pid", "原tier",
    "应归(newPid)", "动作(action)", "状态(status)", "备注(note)", "录入时间(createdAt)",
]
ACTIONS = ("reassign", "drop", "keep")

CTX = 14


# ---------------------------------------------------------------- 基礎設施

def _openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError:
        raise SystemExit("缺少 openpyxl：`python -m pip install openpyxl`")


def connect_db():
    if not os.path.exists(DB_PATH):
        raise SystemExit("索引庫不存在：{}\n先跑 rebuild.py".format(DB_PATH))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_context(text: str, s: int, e: int) -> str:
    s = s or 0
    e = e or 0
    return "{0}【{1}】{2}".format(text[max(0, s - CTX):s], text[s:e], text[e:e + CTX]) \
        if text else ""


def sentence_mentions(conn, uid: str):
    """該句的全部命中，按位置排序後附上 nth（1-based）。"""
    row = conn.execute("SELECT text, chapter_id FROM sentences WHERE uid=?",
                       (uid,)).fetchone()
    if not row:
        raise SystemExit("庫裡沒有這個 uid：{}".format(uid))
    rows = conn.execute(
        "SELECT person_id, surface, s, e, tier FROM mentions "
        "WHERE sentence_uid=? ORDER BY s, e", (uid,)).fetchall()
    out = []
    for i, r in enumerate(rows, 1):
        out.append({"nth": i, "pid": r[0], "surface": r[1],
                    "s": r[2], "e": r[3], "tier": r[4]})
    return row[0], row[1], out


def resolve_pid(conn, who: str) -> str:
    """人名 → pid。本來就是 pid 就原樣返回；多個候選就報錯要你寫 pid。"""
    if who.startswith("p_"):
        return who
    hit = {r[0] for r in conn.execute(
        "SELECT id FROM persons WHERE trad_name=? OR name=?", (who, who))}
    if not hit:
        alias = {r[0] for r in conn.execute(
            "SELECT person_id FROM aliases WHERE alias=?", (who,))}
        hit = alias
    if len(hit) == 1:
        return hit.pop()
    if len(hit) > 1:
        raise SystemExit("「{}」對應多個人，請改寫 pid：{}".format(
            who, " / ".join(sorted(hit))))
    raise SystemExit("查無此人：{}（可先查 python app/tools/query.py {}）".format(who, who))


# ---------------------------------------------------------------- 表操作

def init_workbook() -> str:
    opx = _openpyxl()
    if os.path.exists(WORKBOOK):
        print("已存在，一根手指都沒碰：{}".format(WORKBOOK))
        return WORKBOOK
    wb = opx.Workbook()
    ws = wb.active
    ws.title = "overrides"
    ws.append(HEADERS)
    os.makedirs(os.path.dirname(WORKBOOK), exist_ok=True)
    wb.save(WORKBOOK)
    print("已建空表：{}".format(WORKBOOK))
    return WORKBOOK


def _read_rows():
    """讀回 active 的糾錯行（只讀，不改）。"""
    if not os.path.exists(WORKBOOK):
        return []
    opx = _openpyxl()
    wb = opx.load_workbook(WORKBOOK, read_only=True, data_only=True)
    ws = wb["overrides"] if "overrides" in wb.sheetnames else wb.active
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not r[0]:
            continue
        d = dict(zip(HEADERS, list(r) + [None] * (len(HEADERS) - len(r))))
        if str(d.get("状态(status)") or "active").strip().lower() != "active":
            continue
        out.append(d)
    wb.close()
    return out


def _append_row(row: dict) -> None:
    """追加一行。寫不進去（Excel 開著）就寫 `.new.xlsx`，絕不強行覆蓋。"""
    opx = _openpyxl()
    init_workbook()
    wb = opx.load_workbook(WORKBOOK)
    ws = wb["overrides"] if "overrides" in wb.sheetnames else wb.active
    ws.append([row.get(h) for h in HEADERS])
    try:
        wb.save(WORKBOOK)
        print("已寫入：{}".format(WORKBOOK))
    except PermissionError:
        alt = WORKBOOK.replace(".xlsx", ".new.xlsx")
        wb.save(alt)
        print("⚠️ 原表被佔用（Excel 開著？），已改寫：{}\n   關掉 Excel 後手動合併這一行。".format(alt))


# ---------------------------------------------------------------- 子命令

def cmd_show(args) -> None:
    conn = connect_db()
    text, cid, ms = sentence_mentions(conn, args.uid)
    conn.close()
    print("{} · {}\n  {}".format(cid, args.uid, text))
    print("\n該句共 {} 條命中：".format(len(ms)))
    for m in ms:
        print("  #{} [{:>4}:{:>4}] {:<8} {:<10} {}".format(
            m["nth"], m["s"], m["e"], m["surface"], m["tier"], m["pid"]))
    print("\n改歸示例：--nth 2 --new 劉邦　│　整串出索引：--nth 2 --action drop")


def cmd_add(args) -> None:
    conn = connect_db()
    text, cid, ms = sentence_mentions(conn, args.uid)
    pick = [m for m in ms if m["nth"] == args.nth]
    if not pick:
        conn.close()
        raise SystemExit("這句沒有第 {} 條命中（共 {} 條）".format(args.nth, len(ms)))
    m = pick[0]

    new_pid = ""
    if args.action == "reassign":
        if not args.new:
            conn.close()
            raise SystemExit("reassign 必須給 --new（人名或 pid）")
        new_pid = resolve_pid(conn, args.new)
    conn.close()

    row = {
        "uid": args.uid, "s": m["s"], "e": m["e"], "surface": m["surface"],
        "nth": args.nth,
        "篇(chapterId)": cid,
        "上下文": make_context(text, m["s"], m["e"]),
        "原pid": m["pid"], "原tier": m["tier"],
        "应归(newPid)": new_pid,
        "动作(action)": args.action,
        "状态(status)": "active",
        "备注(note)": args.note or "",
        "录入时间(createdAt)": now(),
    }
    _append_row(row)
    print("  {} → {}（{}）　{}".format(m["pid"], new_pid or "—", args.action,
                                       make_context(text, m["s"], m["e"])))


def cmd_list(args) -> None:
    rows = _read_rows()
    if not rows:
        print("（還沒有糾錯記錄）")
        return
    print("=== overrides（{} 條生效中）===".format(len(rows)))
    for r in rows:
        print("  {} #{} {} → {} [{}]　{}".format(
            r["uid"], r["nth"], r["原pid"], r["应归(newPid)"] or "—",
            r["动作(action)"], r["上下文"]))


def cmd_revoke(args) -> None:
    """作廢一條糾錯（把 `状态` 改成 dead，**不刪行**——留著可追溯）。

    這是「人」的動作，和 `add` 同級；pipeline 那側（`apply`）永遠只讀。
    """
    opx = _openpyxl()
    if not os.path.exists(WORKBOOK):
        raise SystemExit("還沒有 {}".format(WORKBOOK))
    wb = opx.load_workbook(WORKBOOK)
    ws = wb["overrides"] if "overrides" in wb.sheetnames else wb.active
    col = {h: i + 1 for i, h in enumerate(HEADERS)}
    n = 0
    for r in ws.iter_rows(min_row=2):
        if str(r[col["uid"] - 1].value or "").strip() != args.uid:
            continue
        if args.nth and int(r[col["nth"] - 1].value or 0) != args.nth:
            continue
        if str(r[col["状态(status)"] - 1].value or "").strip() == "dead":
            continue
        ws.cell(row=r[0].row, column=col["状态(status)"], value="dead")
        n += 1
    if not n:
        print("沒有匹配的生效糾錯：{}".format(args.uid))
        return
    try:
        wb.save(WORKBOOK)
        print("已作廢 {} 條（{}）".format(n, args.uid))
    except PermissionError:
        alt = WORKBOOK.replace(".xlsx", ".new.xlsx")
        wb.save(alt)
        print("⚠️ 原表被佔用，已改寫：{}".format(alt))


def cmd_apply(args) -> int:
    """套用到 book-data.json。rebuild 會在建庫前自動調這個。"""
    rows = _read_rows()
    if not rows:
        return 0

    # uid → 句子：與 build_index_db 同源（md5(chapterId|paraSeq|seq)[:12]）
    import hashlib
    def uid_of(s):
        raw = "{}|{}|{}".format(s["chapterId"], s.get("paraSeq"), s.get("seq"))
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    with open(BOOK, encoding="utf-8") as f:
        d = json.load(f)

    by_uid = {}
    for s in d["sentences"]:
        by_uid.setdefault(uid_of(s), []).append(s)

    n_re, n_drop, miss = 0, 0, []
    for r in rows:
        uid = str(r["uid"]).strip()
        action = str(r["动作(action)"] or "").strip()
        sents = by_uid.get(uid)
        if not sents:
            miss.append(uid)
            continue
        for s in sents:
            marks = s.get("marks") or []
            # 優先精確匹配 (s, e, surface)，再用 nth 兜底
            cand = [m for m in marks
                    if m.get("s") == r["s"] and m.get("e") == r["e"]
                    and m.get("alias") == r["surface"]]
            if not cand:
                same = [m for m in marks if m.get("alias") == r["surface"]]
                nth = int(r["nth"] or 0)
                if 1 <= nth <= len(same):
                    cand = [sorted(same, key=lambda m: (m.get("s") or 0,
                                                        m.get("e") or 0))[nth - 1]]
            if not cand:
                miss.append("{}#{}".format(uid, r["nth"]))
                continue
            for m in cand:
                if action == "drop":
                    marks.remove(m)
                    n_drop += 1
                elif action == "reassign" and r["应归(newPid)"]:
                    m["pid"] = str(r["应归(newPid)"]).strip()
                    m["override"] = 1          # 保留原 tier，只加標記
                    n_re += 1
                elif action == "keep":
                    pass
            s["marks"] = marks

    if not args.dry_run:
        with open(BOOK, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    print("overrides 套用：改歸 {} 條 / 棄用 {} 條{}".format(
        n_re, n_drop, "　（未匹配 {} 條）".format(len(miss)) if miss else ""))
    if miss:
        print("  ⚠️ 沒匹配上：{}".format(" ".join(miss[:10])))
    return n_re + n_drop


def main() -> int:
    ap = argparse.ArgumentParser(description="BOOKINDEX 單條糾錯（overrides）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="建空表（已存在則不動）").set_defaults(
        func=lambda a: init_workbook())

    p = sub.add_parser("show", help="列某句有哪些命中")
    p.add_argument("--uid", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("add", help="寫一條糾錯")
    p.add_argument("--uid", required=True)
    p.add_argument("--nth", required=True, type=int, help="該句內第幾個同名命中（1-based）")
    p.add_argument("--new", default="", help="應歸給誰（人名或 pid）")
    p.add_argument("--action", default="reassign", choices=ACTIONS)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="列已有糾錯")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("revoke", help="作廢一條糾錯（狀態改 dead，不刪行）")
    p.add_argument("--uid", required=True)
    p.add_argument("--nth", type=int, default=0, help="只作廢該句第 n 條（可省略）")
    p.set_defaults(func=cmd_revoke)

    p = sub.add_parser("apply", help="套用到 book-data.json")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
