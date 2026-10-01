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
from typing import Dict, List

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from common import stable_uid   # noqa: E402

# DB 路径认环境变量：断言要在**临时库副本**上做注入测试（docs/28 P0-5），
# 否则「故意注入一个错误看断言变不变红」根本没法隔离验证。
DB_PATH = (os.environ.get("BOOKINDEX_DB")
           or os.path.join(ROOT, "data", "index", "index.db"))
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

# ⚠️ 与 REL_INVERSE **不是一回事**，别互相替代：
#   REL_INVERSE 是「反向边」表——只覆盖有向边，用来禁止 (a,父,b)/(b,子,a) 双写；
#   CALL_INVERSE 是「称呼反向」表——句里/页面上写的是「a 之 X」，X 是**对方对 a 的称呼**。
#   对称边也需要它：边 (a,兄,b) 在页面与语料里都写作「a 之弟」，而 兄→弟 不在 REL_INVERSE 里。
#
# 值是**候选元组**（性别变体在前一个：男/女）：父→(子, 女)。
# 展示时按对方性别选一个；取证时两个都算命中（「蔡邕之女也」也是 (蔡邕,父,蔡文姬) 的证据，
# 只认「子」会漏掉这类硬句式——docs/28 P1-2）。
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

# 性别判据：只在**选称呼用词**时用（子/女、弟/妹），判错也只是称谓之差，
# 比现在「父亲/女儿」颠倒的后果小得多。命中即视为女。
FEMALE_HINT = ("太后", "皇后", "公主", "王后", "夫人", "太后", "姬", "妃",
               "后", "女", "母", "婦", "妻", "娣", "娥")


def looks_female(*texts) -> bool:
    s = "".join(str(t or "") for t in texts)
    return any(w in s for w in FEMALE_HINT)


def rel_view(rel: str, other_female: bool) -> str:
    """站在 a 的视角，该把对方称作什么。展示与取证共用同一套词表。"""
    cands = CALL_INVERSE.get(rel)
    if not cands:
        return rel
    if len(cands) > 1:
        return cands[1] if other_female else cands[0]
    return cands[0]


# 置信度**由 source 派生**，不给人手填
CONF_BY_SOURCE = {"manual": 1.0, "ai": 0.8, "auto-summary": 0.6,
                  "manual-guess": 0.4}
# 没有证据句的一律压到推断档：出处都没有的关系，不敢当事实用（docs/24 §12.4.1）
NO_EVIDENCE_CAP = 0.4


def derive_confidence(source: str, has_evidence: bool) -> float:
    base = CONF_BY_SOURCE.get(source, 0.4)
    return base if has_evidence else min(base, NO_EVIDENCE_CAP)

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
    ev = wb.create_sheet(EV_SHEET)     # 证据一对多（docs/28 P1-6）
    ev.append(EV_HEADERS)
    os.makedirs(os.path.dirname(WORKBOOK), exist_ok=True)
    wb.save(WORKBOOK)
    print("已建空表：{}（含 {} 页）".format(WORKBOOK, EV_SHEET))


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


EV_SHEET = "relation_evidence"
EV_HEADERS = ["rel_id", "证据uid", "判定(verdict)", "备注(note)",
              "录入时间(createdAt)"]
# accept = 采用；reject = 候选被否（留着，免得下一轮取证又把它抽出来）
EV_VERDICTS = ("", "accept", "reject")


def _read_ev_rows():
    """读证据子表。一条关系可以有多条出处（docs/28 P1-6）。

    表里没有这个 sheet 时返回空——不是错误：老表是「一 edge 一 uid」时代建的，
    由 `cmd_apply` 从主表的 `证据uid` 回填（见 `_evidence_pairs`）。
    """
    if not os.path.exists(WORKBOOK):
        return []
    opx = _openpyxl()
    wb = opx.load_workbook(WORKBOOK, read_only=True, data_only=True)
    if EV_SHEET not in wb.sheetnames:
        wb.close()
        return []
    ws = wb[EV_SHEET]
    out = []
    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not r or not r[0] or not r[1]:
            continue
        d = dict(zip(EV_HEADERS, list(r) + [None] * (len(EV_HEADERS) - len(r))))
        d["_row"] = i
        out.append(d)
    wb.close()
    return out


def _ensure_ev_sheet() -> None:
    """补建证据 sheet（已存在的表不会自动多出这一页）。"""
    opx = _openpyxl()
    wb = opx.load_workbook(WORKBOOK)
    if EV_SHEET in wb.sheetnames:
        return
    ws = wb.create_sheet(EV_SHEET)
    ws.append(EV_HEADERS)
    try:
        wb.save(WORKBOOK)
        print("已补建证据页 {}：{}".format(EV_SHEET, WORKBOOK))
    except PermissionError:
        wb.save(WORKBOOK.replace(".xlsx", ".new.xlsx"))
        print("⚠️ 原表被占用，已改写 .new.xlsx")


def _evidence_pairs(rows):
    """汇总「rel_id → [(uid, verdict, note)]」，供灌库使用。

    两个来源合并：① 证据子表（一对多的正路）；② 主表 `证据uid`
    （老数据/手写行，一律当作 accept）。子表里有就不再从主表重复补。
    """
    pairs: Dict[str, list] = {}
    for d in _read_ev_rows():
        rid = str(d.get("rel_id") or "").strip()
        uid = str(d.get("证据uid") or "").strip()
        if not rid or not uid:
            continue
        pairs.setdefault(rid, []).append(
            (uid, str(d.get("判定(verdict)") or "").strip(),
             str(d.get("备注(note)") or "").strip()))
    for r in rows:
        rid = str(r.get("rel_id") or "").strip()
        uid = str(r.get("证据uid") or "").strip()
        if not rid or not uid:
            continue
        if any(u == uid for u, _, _ in pairs.get(rid, [])):
            continue
        pairs.setdefault(rid, []).append((uid, "accept", ""))
    return pairs


def _set_status(rel_id_: str, status: str) -> None:
    """按 rel_id 改状态。⚠️ **只改 active 行**——表里留着历史 dead 行，
    而 rel_id 是内容哈希，同一条关系被撤销后又重加会出现同 id 的行
    （docs/28 P1-8：这样的两行确实存在）。按 id 无差别匹配会一次误伤两行。"""
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
        if str(r[col - 1].value or "active").strip() != "active":
            continue                      # 已作废的历史行不碰
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
        "置信度(confidence)": derive_confidence(args.source,
                                                bool(args.evidence_uid)),
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
    warn = []              # 派生列与规则不一致：只报，不拦（落库以代码为准）
    seen = {}
    rid_seen = {}          # active 行之间 rel_id 必须唯一（历史 dead 行不算）
    for r in rows:
        tag = r.get("rel_id") or "#{}".format(r["_row"])
        a, b, rel = r.get("person_a"), r.get("person_b"), r.get("关系(rel)")
        if r.get("状态(status)") != "active":
            continue
        rid = r.get("rel_id")
        if rid in rid_seen:
            bad.append("{} rel_id 与 #{} 重复（同一条关系被加了两次）".format(
                tag, rid_seen[rid]))
        rid_seen[rid] = r["_row"]
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
        # 派生列（rel_type / 对称 / 置信度）**只由代码规则产出**，表里的同名列
        # 一律不读（P2-1）：读了就会出现「表里写 1、落库算 0.4」的静默分歧。
        # 这里不改数据，只把分歧喊出来，免得有人照着表去排查。
        rt, sym = REL_TABLE.get(rel, ("other", 0))
        for col, got, want in (
                ("rel_type", r.get("rel_type"), rt),
                ("对称", r.get("对称"), sym),
                ("置信度(confidence)", r.get("置信度(confidence)"),
                 derive_confidence(r.get("来源(source)") or "manual",
                                   bool(r.get("证据uid"))))):
            if got not in (None, "") and got != want:
                warn.append("{} 表里 {} = {}，但按规则应是 {}"
                            "（以代码为准，表列仅供参考）".format(tag, col, got, want))
        inv = REL_INVERSE.get(rel)
        if inv and (b, a, inv) in seen:
            bad.append("{} 与 #{} 反向双写".format(tag, seen[(b, a, inv)]))
        uid = r.get("证据uid")
        if uid and uid not in active_sents:
            bad.append("{} 证据句已失效（{}）——需重新取证".format(tag, uid))

    # 证据子表（docs/28 P1-6）：一条关系多条出处。
    rid2row = {str(r.get("rel_id") or "").strip(): r["_row"]
               for r in rows if str(r.get("状态(status)")) == "active"}
    ev_seen = {}
    for d in _read_ev_rows():
        rid = str(d.get("rel_id") or "").strip()
        uid = str(d.get("证据uid") or "").strip()
        tag = "证据 {}@{}".format(uid[:8], rid[:8])
        v = str(d.get("判定(verdict)") or "").strip()
        if v not in EV_VERDICTS:
            bad.append("{} 判定「{}」不在词表（accept / reject / 空）".format(tag, v))
        if rid not in rid2row:
            bad.append("{} 挂在不存在或非 active 的关系上".format(tag))
        if uid not in active_sents:
            bad.append("{} 证据句已失效——需重新取证".format(tag))
        if (rid, uid) in ev_seen:
            bad.append("{} 与 #{} 重复".format(tag, ev_seen[(rid, uid)]))
        ev_seen[(rid, uid)] = d["_row"]
    # 主表有证据、子表却没有：不影响落库（会回填），但提醒一次，免得两边漂移
    for r in rows:
        if str(r.get("状态(status)")) != "active":
            continue
        rid, uid = str(r.get("rel_id") or "").strip(), str(r.get("证据uid") or "").strip()
        if uid and (rid, uid) not in ev_seen:
            warn.append("{} 主表有证据但证据页没有该行（灌库时会自动回填）"
                        .format(rid[:8]))

    for m in warn:
        print("  ⚠ {}".format(m))
    for m in bad:
        print("  ✗ {}".format(m))
    print("  校验 {} 条，问题 {} 处，派生列分歧 {} 处".format(
        len(rows), len(bad), len(warn)))
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
        # rel_type / 对称 **一律由 REL_TABLE 派生**，不读表里的同名列（P2-1）。
        # 表是给人看的（排序/筛选方便），规则只有一份，在代码里。
        rt, sym = REL_TABLE.get(r.get("关系(rel)"), ("other", 0))
        conn.execute(
            "INSERT OR REPLACE INTO relations "
            "(rel_id, person_a, surface_a, person_b, surface_b, rel_type, rel, "
            " symmetric, era, book, evidence_uid, evidence_text, confidence, "
            " source, status, note, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.get("rel_id"), r.get("person_a"), r.get("原文用字a") or "",
             r.get("person_b"), r.get("原文用字b") or "",
             rt, r.get("关系(rel)"), int(sym),
             r.get("时代(era)") or "", r.get("书(book)") or "",
             r.get("证据uid") or "", r.get("证据原文") or "",
             derive_confidence(r.get("来源(source)") or "manual",
                               bool(r.get("证据uid"))),
            r.get("来源(source)") or "", "active",
            r.get("备注(note)") or "", r.get("录入时间(createdAt)") or ""))
        n += 1

    # 证据子表：全量重灌（同 relations，是派生的）。
    # 主证据回填到 relations.evidence_uid：只用到一条的场合不用改代码。
    pairs = _evidence_pairs(rows)
    conn.execute("DELETE FROM relation_evidence")
    n_ev = 0
    for rid, lst in pairs.items():
        primary = next((u for u, v, _ in lst if v != "reject"), "")
        if primary:
            conn.execute("UPDATE relations SET evidence_uid=? WHERE rel_id=?",
                         (primary, rid))
        for uid, v, note in lst:
            conn.execute(
                "INSERT OR REPLACE INTO relation_evidence "
                "(rel_id, evidence_uid, verdict, note, created_at) "
                "VALUES (?,?,?,?,?)", (rid, uid, v or "accept", note, now()))
            n_ev += 1
    conn.commit()
    conn.close()
    print("关系灌入：{} 条，证据 {} 条（权威源 {}）".format(n, n_ev, WORKBOOK))
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
    rc = args.func(args)
    # ⚠️ 只有 check 的返回值是「问题条数」，必须变成退出码，否则一键回归恒绿。
    # 其它子命令返回的是「灌入条数」之类的计数，不能当退出码用（apply 返回 62 会被当成失败）。
    if getattr(args, "cmd", "") == "check" and rc:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
