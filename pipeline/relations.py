# -*- coding: utf-8 -*-
"""关系数据（P6）：规范词表 + 权威源 workbook/relations.xlsx + 灌入 SQLite。

为什么不是直接写库
------------------
`relations` 表在 `index.db` 里，而 index.db 是**每次重建都整个删掉重建**的派生产物。
关系却是人工/AI 审定的结果，丢了补不回来。所以：

    workbook/relations.xlsx（权威源，人写/AI 落盘）
        ↓ apply（建库之后灌回）
    index.db 的 relations 表（派生，随时可重建）

这跟 overrides 是同一套规矩：**管线只读 xlsx，绝不回写**。

三条定死的规则（来自 docs/25 的设计审查）
----------------------------------------
1. **只存规范边**：`父` 存一条（a→b），不重复存 `子`（b→a）。反向由 `REL_INVERSE`
   在代码里派生。防 `(a,父,b)` 与 `(b,子,a)` 双写——那是最常见的脏数据。
2. **`rel_type` 与 `confidence` 不手填**：都由代码派生（rel → rel_type，source → confidence）。
   手填会出现「标 manual 实为猜」，那就没法断言了。
3. **证据以 uid 指向的现句为准**，`证据原文` 只是录入那一刻的展示缓存。
   两者不一致时报警（stale），不静默。

用法
----
    python pipeline/relations.py init
    python pipeline/relations.py add --a p_liubang --b p_liuying --rel 父 --source manual
    python pipeline/relations.py add --a X --b Y --rel 友 --evidence-uid <uid>
    python pipeline/relations.py list
    python pipeline/relations.py check          # 校验（含证据失效）
    python pipeline/relations.py revoke --rel-id <id>
    python pipeline/relations.py apply          # 灌入 index.db
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from common import stable_uid   # noqa: E402

DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
WORKBOOK = os.path.join(ROOT, "workbook", "relations.xlsx")

# ---------------------------------------------------------------- 规范词表
#
# rel → (rel_type, symmetric)。**定死在这里**，枚举外的一律记 other + note，
# 攒够一批再决定是否扩——边填边扩枚举，表里必然出现同义异名。
REL_TABLE = {
    # kinship：有向（父子）或对称（兄弟）
    "父": ("kinship", 0), "母": ("kinship", 0), "子": ("kinship", 0),
    "女": ("kinship", 0), "兄": ("kinship", 1), "弟": ("kinship", 1),
    "姊": ("kinship", 1), "妹": ("kinship", 1), "夫": ("kinship", 1),
    "妻": ("kinship", 1), "祖父": ("kinship", 0), "祖母": ("kinship", 0),
    "孫": ("kinship", 0), "孫女": ("kinship", 0), "姪": ("kinship", 0),
    "甥": ("kinship", 0), "伯叔": ("kinship", 0), "姑": ("kinship", 0),
    "舅": ("kinship", 0), "姨": ("kinship", 0), "從兄弟": ("kinship", 1),
    "養父": ("kinship", 0), "繼母": ("kinship", 0),
    # political
    "主君": ("political", 0), "部屬": ("political", 0), "同僚": ("political", 1),
    "舉主": ("political", 0), "門生": ("political", 0), "政敵": ("political", 1),
    "盟友": ("political", 1), "繼任": ("political", 0), "前任": ("political", 0),
    "部將": ("political", 0), "幕僚": ("political", 0),
    # social
    "師": ("social", 0), "弟子": ("social", 0), "友": ("social", 1),
    "同鄉": ("social", 1), "賓客": ("social", 0), "門客": ("social", 0),
}

# 反向映射：只覆盖 kinship（政治/社会关系大多本就是对称的，不需要反义表）
REL_INVERSE = {
    "父": "子", "子": "父", "母": "女", "女": "母",
    "祖父": "孫", "孫": "祖父", "祖母": "孫女", "孫女": "祖母",
    "伯叔": "姪", "姑": "姪", "姪": "伯叔",
    "舅": "甥", "姨": "甥", "甥": "舅",
    "養父": "子", "繼母": "子",
}

# 置信度**由 source 派生**，不给人手填
CONF_BY_SOURCE = {"manual": 1.0, "ai": 0.8, "auto-summary": 0.6,
                  "manual-guess": 0.4}

HEADERS = [
    "rel_id", "person_a", "原文用字a", "person_b", "原文用字b",
    "关系(rel)", "rel_type", "对称", "时代(era)", "书(book)",
    "证据uid", "证据原文", "来源(source)", "置信度(confidence)",
    "状态(status)", "备注(note)", "录入时间(createdAt)",
]


def rel_id(a: str, b: str, rel: str, book: str = "", era: str = "") -> str:
    """稳定业务主键：重建时 id 会重排号，靠它才能追溯与去重。"""
    raw = "{}|{}|{}|{}|{}".format(a, b, rel, book or "", era or "")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError:
        raise SystemExit("缺少 openpyxl：`python -m pip install openpyxl`")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 表

def init_workbook() -> None:
    opx = _openpyxl()
    if os.path.exists(WORKBOOK):
        return
    wb = opx.Workbook()
    ws = wb.active
    ws.title = "relations"
    ws.append(HEADERS)
    os.makedirs(os.path.dirname(WORKBOOK), exist_ok=True)
    wb.save(WORKBOOK)
    print("已建空表：{}".format(WORKBOOK))


def _read_rows(active_only: bool = True):
    if not os.path.exists(WORKBOOK):
        return []
    opx = _openpyxl()
    wb = opx.load_workbook(WORKBOOK, read_only=True, data_only=True)
    ws = wb["relations"] if "relations" in wb.sheetnames else wb.active
    out = []
    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not r or not r[0]:
            continue
        d = dict(zip(HEADERS, list(r) + [None] * (len(HEADERS) - len(r))))
        d["_row"] = i
        if active_only and str(d.get("状态(status)") or "active").strip() != "active":
            continue
        out.append(d)
    wb.close()
    return out


def _append_row(row: dict) -> None:
    opx = _openpyxl()
    init_workbook()
    wb = opx.load_workbook(WORKBOOK)
    ws = wb["relations"] if "relations" in wb.sheetnames else wb.active
    ws.append([row.get(h) for h in HEADERS])
    try:
        wb.save(WORKBOOK)
        print("已写入：{}".format(WORKBOOK))
    except PermissionError:
        alt = WORKBOOK.replace(".xlsx", ".new.xlsx")
        wb.save(alt)
        print("⚠️ 原表被占用，已改写：{}".format(alt))


def _set_status(rel_id_: str, status: str) -> None:
    opx = _openpyxl()
    if not os.path.exists(WORKBOOK):
        raise SystemExit("还没有 {}".format(WORKBOOK))
    wb = opx.load_workbook(WORKBOOK)
    ws = wb["relations"] if "relations" in wb.sheetnames else wb.active
    col = HEADERS.index("状态(status)") + 1
    n = 0
    for r in ws.iter_rows(min_row=2):
        if str(r[0].value or "").strip() != rel_id_:
            continue
        ws.cell(row=r[0].row, column=col, value=status)
        n += 1
    if not n:
        print("没有匹配的记录：{}".format(rel_id_))
        return
    try:
        wb.save(WORKBOOK)
        print("已作废 {} 条（{}）".format(n, rel_id_))
    except PermissionError:
        wb.save(WORKBOOK.replace(".xlsx", ".new.xlsx"))
        print("⚠️ 原表被占用，已改写 .new.xlsx")


# ---------------------------------------------------------------- 命令

def _sentence_text(uid: str):
    if not uid or not os.path.exists(DB_PATH):
        return ""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT text FROM sentences WHERE uid=?", (uid,)).fetchone()
    conn.close()
    return row[0] if row else ""


def cmd_add(args) -> None:
    rel = args.rel.strip()
    if rel not in REL_TABLE:
        raise SystemExit("「{}」不在规范词表内。先用 --rel other 记下并写 note，"
                         "攒一批再决定是否扩枚举。".format(rel))
    if args.a == args.b:
        raise SystemExit("自环不允许（a 与 b 相同）")
    if args.source not in CONF_BY_SOURCE:
        raise SystemExit("source 只能是 {}".format(" / ".join(CONF_BY_SOURCE)))
    rel_type, sym_default = REL_TABLE[rel]
    sym = args.symmetric if args.symmetric is not None else sym_default

    # 反向双写检查：只存规范边，反向由代码派生
    inv = REL_INVERSE.get(rel)
    if inv:
        for r in _read_rows():
            if (r.get("person_b") == args.a and r.get("person_a") == args.b
                    and r.get("关系(rel)") == inv):
                raise SystemExit("反向边已存在（{b} -{inv}-> {a}）：只存规范边，"
                                 "这条不用再加".format(b=args.b, inv=inv, a=args.a))
    rid = rel_id(args.a, args.b, rel, args.book or "", args.era or "")
    for r in _read_rows():
        if r.get("rel_id") == rid:
            raise SystemExit("这条关系已存在（rel_id={}），别重复加".format(rid))

    _append_row({
        "rel_id": rid,
        "person_a": args.a, "原文用字a": args.surface_a or "",
        "person_b": args.b, "原文用字b": args.surface_b or "",
        "关系(rel)": rel, "rel_type": rel_type, "对称": sym,
        "时代(era)": args.era or "", "书(book)": args.book or "",
        "证据uid": args.evidence_uid or "",
        "证据原文": _sentence_text(args.evidence_uid) if args.evidence_uid else "",
        "来源(source)": args.source,
        "置信度(confidence)": CONF_BY_SOURCE[args.source],
        "状态(status)": "active",
        "备注(note)": args.note or "",
        "录入时间(createdAt)": now(),
    })


def cmd_list(args) -> None:
    rows = _read_rows(active_only=not args.all)
    if not rows:
        print("（还没有关系记录）")
        return
    print("=== 关系（{} 条）===".format(len(rows)))
    for r in rows:
        print("  {} {} —{}—> {}　[{}] conf={} src={} {}".format(
            r.get("rel_id"), r.get("person_a"), r.get("关系(rel)"),
            r.get("person_b"), r.get("rel_type") or "-",
            r.get("置信度(confidence)") or "-", r.get("来源(source)") or "-",
            "（证据 {}）".format(r.get("证据uid")) if r.get("证据uid") else "（无证据）"))


def cmd_check(args) -> int:
    """校验：两端 pid 存在 / rel 在词表 / 无自环 / 无反向双写 / 证据是否失效。"""
    rows = _read_rows(active_only=False)
    if not rows:
        print("（没有记录可校验）")
        return 0
    conn = sqlite3.connect(DB_PATH)
    pids = {r[0] for r in conn.execute("SELECT id FROM persons")}
    active_sents = {r[0] for r in conn.execute(
        "SELECT uid FROM sentences WHERE status='active'")}
    conn.close()

    bad = []
    seen = {}
    for r in rows:
        tag = r.get("rel_id") or "#{}".format(r["_row"])
        a, b, rel = r.get("person_a"), r.get("person_b"), r.get("关系(rel)")
        if r.get("状态(status)") != "active":
            continue
        if a not in pids or b not in pids:
            bad.append("{} pid 不存在（{} / {}）".format(tag, a, b))
        if a == b:
            bad.append("{} 自环".format(tag))
        if rel not in REL_TABLE:
            bad.append("{} rel 「{}」不在词表".format(tag, rel))
        key = (a, b, rel)
        if key in seen:
            bad.append("{} 与 #{} 重复".format(tag, seen[key]))
        seen[key] = r["_row"]
        inv = REL_INVERSE.get(rel)
        if inv and (b, a, inv) in seen:
            bad.append("{} 与 #{} 反向双写".format(tag, seen[(b, a, inv)]))
        uid = r.get("证据uid")
        if uid and uid not in active_sents:
            bad.append("{} 证据句已失效（{}）——需重新取证".format(tag, uid))

    for m in bad:
        print("  ✗ {}".format(m))
    print("  校验 {} 条，问题 {} 处".format(len(rows), len(bad)))
    return len(bad)


def cmd_apply(args) -> int:
    """把 xlsx 灌进 index.db 的 relations 表（建库之后跑，否则会被重建冲掉）。"""
    rows = [r for r in _read_rows() if r.get("状态(status)") == "active"]
    if not os.path.exists(DB_PATH):
        raise SystemExit("索引库不存在，先跑 rebuild.py")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM relations")     # 表是派生的，每次全量重灌
    n = 0
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO relations "
            "(rel_id, person_a, surface_a, person_b, surface_b, rel_type, rel, "
            " symmetric, era, book, evidence_uid, evidence_text, confidence, "
            " source, status, note, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.get("rel_id"), r.get("person_a"), r.get("原文用字a") or "",
             r.get("person_b"), r.get("原文用字b") or "",
             r.get("rel_type") or REL_TABLE.get(r.get("关系(rel)"), ("other", 0))[0],
             r.get("关系(rel)"), int(r.get("对称") or 0),
             r.get("时代(era)") or "", r.get("书(book)") or "",
             r.get("证据uid") or "", r.get("证据原文") or "",
             float(r.get("置信度(confidence)") or 0.0),
             r.get("来源(source)") or "", "active",
             r.get("备注(note)") or "", r.get("录入时间(createdAt)") or ""))
        n += 1
    conn.commit()
    conn.close()
    print("关系灌入：{} 条（权威源 {}）".format(n, WORKBOOK))
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="BOOKINDEX 关系数据（P6）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="建空表").set_defaults(
        func=lambda a: init_workbook())

    p = sub.add_parser("add", help="加一条关系")
    p.add_argument("--a", required=True, help="person_a 的 pid")
    p.add_argument("--b", required=True, help="person_b 的 pid")
    p.add_argument("--rel", required=True, help="关系（须在规范词表内）")
    p.add_argument("--surface-a", default="", help="原文用字（消歧用）")
    p.add_argument("--surface-b", default="")
    p.add_argument("--symmetric", type=int, default=None,
                   help="1 对称 / 0 有向；省略则按词表默认")
    p.add_argument("--era", default="")
    p.add_argument("--book", default="")
    p.add_argument("--evidence-uid", default="")
    p.add_argument("--source", default="manual", choices=sorted(CONF_BY_SOURCE))
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="列关系")
    p.add_argument("--all", action="store_true", help="含已作废的")
    p.set_defaults(func=cmd_list)

    sub.add_parser("check", help="校验（含证据失效）").set_defaults(func=cmd_check)

    p = sub.add_parser("revoke", help="作废一条（状态改 dead）")
    p.add_argument("--rel-id", required=True)
    p.set_defaults(func=lambda a: _set_status(a.rel_id, "dead"))

    sub.add_parser("apply", help="灌入 index.db").set_defaults(func=cmd_apply)

    args = ap.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
