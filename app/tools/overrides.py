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
# ⚠️ 只有**沙盒**才設 `BOOKINDEX_OVERRIDES`（與 `BOOKINDEX_DB` 同一套約定）。
# 為什麼要有它：UI 測試要真的點「標錯」走一遍寫入，而 revoke 是**改狀態不刪行**——
# 每跑一次回歸，權威源裡就多兩行 dead 行，永遠髒著（purge 只認帶自檢標記的行，
# UI 點擊可不會帶標記）。回歸時把服務指向 `data/index/overrides.ui-test.xlsx`
# （已 gitignore），權威源一根手指都不碰。
DEFAULT_WORKBOOK = os.path.join(ROOT, "workbook", "overrides.xlsx")
WORKBOOK = os.environ.get("BOOKINDEX_OVERRIDES") or DEFAULT_WORKBOOK

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


def sentence_mentions(conn, uid: str, pid: str = ""):
    """該句的全部命中，按位置排序後附上 nth（1-based）。"""
    row = conn.execute("SELECT text, chapter_id FROM sentences WHERE uid=?",
                       (uid,)).fetchone()
    if not row:
        raise SystemExit("庫裡沒有這個 uid：{}".format(uid))
    table = "place_mentions" if (pid and str(pid).startswith("pl_")) else "mentions"
    id_col = "place_id" if table == "place_mentions" else "person_id"
    rows = conn.execute(
        "SELECT {}, surface, s, e, tier FROM {} "
        "WHERE sentence_uid=? ORDER BY s, e".format(id_col, table), (uid,)).fetchall()
    out = []
    for i, r in enumerate(rows, 1):
        out.append({"nth": i, "pid": r[0], "surface": r[1],
                    "s": r[2], "e": r[3], "tier": r[4]})
    return row[0], row[1], out


def resolve_pid(conn, who: str) -> str:
    """实体名/ID → pid/plid。本來就是 id 就原樣返回；多個候選報錯。"""
    who = str(who or "").strip()
    if who.startswith("p_") or who.startswith("pl_"):
        return who
    # 先查地名
    hit_pl = {r[0] for r in conn.execute(
        "SELECT id FROM places WHERE trad_name=? OR name=?", (who, who))}
    if not hit_pl:
        alias_pl = {r[0] for r in conn.execute(
            "SELECT place_id FROM place_aliases WHERE alias=?", (who,))}
        hit_pl = alias_pl
    if len(hit_pl) == 1:
        return hit_pl.pop()
    if len(hit_pl) > 1:
        raise SystemExit("「{}」對應多個地名，請改寫 id：{}".format(
            who, " / ".join(sorted(hit_pl))))

    # 再查人名
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
    raise SystemExit("查無此人或地名：{}（可先查 python app/tools/query.py {}）".format(who, who))


# ---------------------------------------------------------------- 表操作

def safe_save_workbook(wb, path: str) -> None:
    """安全原子保存 openpyxl 工作簿，防 Windows 下 open('wb') 截斷損壞原表。

    原理：先在內存 io.BytesIO() 完成 Zip 封包，成功後再寫入臨時文件原子替換目標。
    若生成過程報錯或目標被佔用，原文件 100% 保持完好，絕不留 0 字節或 2.3KB 損壞檔。
    """
    import io
    bio = io.BytesIO()
    wb.save(bio)
    buf = bio.getvalue()
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)
    tmp = path + ".tmp." + str(os.getpid())
    try:
        with open(tmp, "wb") as f:
            f.write(buf)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


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
    safe_save_workbook(wb, WORKBOOK)
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


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def active_rows() -> list:
    """生效中的糾錯行（對外接口，網頁「標錯」入口用）。

    為什麼要單獨一層：表裡是**中文列名**（`应归(newPid)` / `上下文`…），
    讓前端去認中文表頭，等於把 xlsx 的列名寫死在第二個地方——
    改一列就要改兩處，而且不會報錯。這裡統一翻成英文鍵再出去。
    """
    out = []
    for r in _read_rows():
        # s / e 強制成整數：Excel 裡手改過的單元格讀回來可能是 17.0，
        # 前端拿它拼 key（uid|s|e|surface）就與庫裡對不上，**徽章會靜默消失**。
        out.append({
            "uid": str(r.get("uid") or "").strip(),
            "s": _int_or_none(r.get("s")), "e": _int_or_none(r.get("e")),
            "surface": r.get("surface"), "nth": r.get("nth"),
            "from": r.get("原pid") or "",
            "to": str(r.get("应归(newPid)") or "").strip(),
            "action": r.get("动作(action)") or "",
            "note": r.get("备注(note)") or "",
            "context": r.get("上下文") or "",
        })
    return out


def _append_row(row: dict) -> None:
    """追加一行。寫不進去（Excel 開著）就寫 `.new.xlsx`，絕不強行覆蓋。"""
    opx = _openpyxl()
    init_workbook()
    wb = opx.load_workbook(WORKBOOK)
    ws = wb["overrides"] if "overrides" in wb.sheetnames else wb.active
    ws.append([row.get(h) for h in HEADERS])
    try:
        safe_save_workbook(wb, WORKBOOK)
        print("已寫入：{}".format(WORKBOOK))
    except (PermissionError, OSError):
        alt = WORKBOOK.replace(".xlsx", ".new.xlsx")
        try:
            safe_save_workbook(wb, alt)
            print("⚠️ 原表被佔用（Excel 開著？），已改寫：{}\n   關掉 Excel 後手動合併這一行。".format(alt))
        except Exception as e:
            print("⚠️ 寫入備用表失敗：{}".format(e))



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
    pid_hint = getattr(args, "pid", "") or ""
    text, cid, ms = sentence_mentions(conn, args.uid, pid_hint)
    pick = [m for m in ms if m["nth"] == args.nth]
    if not pick:
        conn.close()
        raise SystemExit("這句沒有第 {} 條命中（共 {} 條）".format(args.nth, len(ms)))
    m = pick[0]

    new_pid = ""
    if args.action == "reassign":
        if not args.new:
            conn.close()
            raise SystemExit("reassign 必須給 --new（人名、地名或 id）")
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
        safe_save_workbook(wb, WORKBOOK)
        print("已作廢 {} 條（{}）".format(n, args.uid))
    except (PermissionError, OSError):
        alt = WORKBOOK.replace(".xlsx", ".new.xlsx")
        try:
            safe_save_workbook(wb, alt)
            print("⚠️ 原表被佔用，已改寫：{}".format(alt))
        except Exception as e:
            print("⚠️ 寫入備用表失敗：{}".format(e))



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
        orig_pid = str(r.get("原pid") or "").strip()
        new_pid = str(r.get("应归(newPid)") or "").strip()
        is_place_hint = orig_pid.startswith("pl_") or (not orig_pid and new_pid.startswith("pl_"))

        def find_cand(target_list):
            cand = [m for m in target_list
                    if m.get("s") == r["s"] and m.get("e") == r["e"]
                    and m.get("alias") == r["surface"]]
            if not cand:
                same = [m for m in target_list if m.get("alias") == r["surface"]]
                nth = int(r["nth"] or 0)
                if 1 <= nth <= len(same):
                    cand = [sorted(same, key=lambda m: (m.get("s") or 0,
                                                        m.get("e") or 0))[nth - 1]]
            return cand

        for s in sents:
            marks = s.get("marks") or []
            pmarks = s.get("pmarks") or []

            cand = []
            cand_source = None
            if is_place_hint:
                cand = find_cand(pmarks)
                if cand:
                    cand_source = "pmarks"
                else:
                    cand = find_cand(marks)
                    if cand:
                        cand_source = "marks"
            else:
                cand = find_cand(marks)
                if cand:
                    cand_source = "marks"
                else:
                    cand = find_cand(pmarks)
                    if cand:
                        cand_source = "pmarks"

            if not cand:
                miss.append("{}#{}".format(uid, r["nth"]))
                continue

            target_list = pmarks if cand_source == "pmarks" else marks
            for m in cand:
                if action == "drop":
                    target_list.remove(m)
                    n_drop += 1
                elif action == "reassign" and new_pid:
                    m["pid"] = new_pid
                    m["override"] = 1          # 保留原 tier，只加標記
                    # 跨實體類型遷移
                    if cand_source == "pmarks" and not new_pid.startswith("pl_"):
                        target_list.remove(m)
                        marks.append(m)
                    elif cand_source == "marks" and new_pid.startswith("pl_"):
                        target_list.remove(m)
                        pmarks.append(m)
                    n_re += 1
                elif action == "keep":
                    pass

            s["marks"] = marks
            if pmarks:
                s["pmarks"] = pmarks
            elif "pmarks" in s:
                s["pmarks"] = []

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
    p.add_argument("--pid", default="", help="原命中 pid 提示（區分人名 vs 地名）")
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
