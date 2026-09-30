# -*- coding: utf-8 -*-
"""关系证据落盘（P6-3）：把判定通过的证据句写回 `workbook/relations.xlsx`。

闭环节奏（沿用「取证 → 判 → 落 → 断言」）
----------------------------------------
    _gen_rel_evidence.py       取证（语料共现，方向敏感 + 第三人/长句降权）
        ↓ 自动：硬句式(score 5) 且唯一；其余进 docs/27 人工判
    _rel_evidence_verdicts.json   人工/AI 判定（可覆盖 uid、也可 accept:false 否掉）
        ↓
    本脚本（默认预演，--apply 才写）
        ↓
    python pipeline/relations.py apply    灌进 index.db

⚠️ 主表只写三列：`证据uid` / `证据原文` / `备注(note)`（置信度是派生的，不写）。
其余列（尤其人写的 source / era / book / status）**一个字都不动**——
那是权威源里归人的部分，脚本碰了就重建时冲掉审定（红线 1）。

**多条出处写进证据页 `relation_evidence`**（docs/28 P1-6）：一条关系常有不止一句
支撑（12/62 条边有 ≥2 条候选），只留一句等于丢证据。主表那一条是**主证据**，
其余在证据页，两者由 `relations.py apply` 汇总灌库。

用法
----
    python pipeline/_apply_rel_evidence.py            # 预演，列出要改什么
    python pipeline/_apply_rel_evidence.py --apply    # 真的写
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import relations as R                        # noqa: E402

EVI_JSON = os.path.join(HERE, "_rel_evidence.json")
VERDICTS = os.path.join(HERE, "_rel_evidence_verdicts.json")
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
AUTO_MIN = 5
# 置信度是**派生的**（source + 有无证据），写进表也没人读（docs/28 P2-1），
# 写了还会在 `relations.py check` 里报「派生列分歧」，所以这里不碰它。
WRITABLE = ("证据uid", "证据原文", "备注(note)")


def _sentence_text(uid: str) -> str:
    if not uid:
        return ""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT text FROM sentences WHERE uid=? AND status='active'",
        (uid,)).fetchone()
    conn.close()
    return row[0] if row else ""


def plan():
    """算出「要改哪些行的哪些列」。预演与落盘共用同一份计划，避免两处逻辑漂移。"""
    if not os.path.exists(EVI_JSON):
        raise SystemExit("先跑：`python pipeline/_gen_rel_evidence.py`")
    with open(EVI_JSON, encoding="utf-8") as f:
        data = json.load(f)
    verdicts = {}
    if os.path.exists(VERDICTS):
        with open(VERDICTS, encoding="utf-8") as f:
            verdicts = json.load(f)

    rows = {r["rel_id"]: r for r in R._read_rows(active_only=False)}
    out, skipped = [], []
    for it in data["items"]:
        rid = it["rel_id"]
        row = rows.get(rid)
        if not row:
            skipped.append((rid, "权威源里没这条（可能已作废）"))
            continue
        v = verdicts.get(rid) or {}
        # ⚠️「撤证据」必须排在「已有证据就跳过」**之前**——
        # 要撤的恰恰是那些已经有证据的边，顺序反了这条分支永远走不到。
        if v.get("accept") is False and v.get("clear"):
            # 判定「这句支撑不了这条边」：边保留，但把证据撤掉、置信度掉回推断档。
            # 例：蘇秦—兄→蘇厲 的证据句实际在说「代」的弟弟（docs/28 P1-1）。
            out.append({
                "rel_id": rid, "a": it["name_a"], "rel": it["rel"],
                "b": it["name_b"], "uid": "", "text": "", "evs": [],
                "conf": R.derive_confidence(row.get("来源(source)") or "manual", False),
                "old_conf": row.get("置信度(confidence)"),
                # 幂等：重跑一次不该把「证据已撤」追加第二遍（note 会越跑越长）
                "note": ((row.get("备注(note)") or "")
                         + ("" if "证据已撤" in (row.get("备注(note)") or "")
                            else " 证据已撤："
                            + str(v.get("note") or "人工判定不成立"))
                         ).strip()[:200],
                "src": "撤证据",
            })
            continue
        if v.get("accept") is False:
            skipped.append((rid, "人工判定为否"))
            continue
        # 证据句可以有多条（docs/28 P1-6）：优先人工指定的 `uids`，
        # 其次 `uid`，最后才是自动取的硬句式。第一条是**主证据**（写主表），
        # 其余进证据页——一条关系常有不止一句支撑，只留一句等于丢证据。
        picks = []
        if v.get("uids"):
            for u in v["uids"]:
                c = next((x for x in it["cands"] if x["uid"] == u), None)
                picks.append(c or {"uid": u, "text": _sentence_text(u),
                                   "score": 0, "signals": ["人工指定"]})
            src = "人工判定（{} 条）".format(len(picks))
        elif v.get("uid"):
            c = next((c for c in it["cands"] if c["uid"] == v["uid"]), None)
            picks.append(c or {"uid": v["uid"], "text": _sentence_text(v["uid"]),
                               "score": 0, "signals": ["人工指定"]})
            src = "人工判定"
        elif it["cands"] and it["cands"][0]["score"] >= AUTO_MIN and (
                len(it["cands"]) == 1 or it["cands"][1]["score"] < AUTO_MIN):
            picks.append(it["cands"][0])
            src = "自动取证（硬句式）"
        else:
            skipped.append((rid, "没有够硬的证据，留给人工判"))
            continue

        evs = []
        for c in picks:
            t = _sentence_text(c["uid"])
            if not t:
                skipped.append((rid, "证据句已失效或不活跃：{}".format(c["uid"])))
                continue
            evs.append({"uid": c["uid"], "text": t,
                        "signals": c.get("signals") or []})
        if not evs:
            continue
        cand = evs[0]
        src_src = row.get("来源(source)") or "manual"
        conf = R.derive_confidence(src_src, True)
        note = "{}：{}".format(src, "；".join(cand["signals"]))[:120]
        old_note = row.get("备注(note)") or ""
        out.append({
            "rel_id": rid, "a": it["name_a"], "rel": it["rel"], "b": it["name_b"],
            "uid": cand["uid"], "text": cand["text"], "evs": evs,
            "conf": conf, "old_conf": row.get("置信度(confidence)"),
            "note": (old_note + " " + note).strip()[:200],
            "src": src,
        })
    return out, skipped


MAIN_MAP = {"证据uid": "uid", "证据原文": "text", "备注(note)": "note"}


def apply(plans) -> None:
    opx = R._openpyxl()
    wb = opx.load_workbook(R.WORKBOOK)
    ws = wb["relations"] if "relations" in wb.sheetnames else wb.active
    head = {c.value: c.column for c in ws[1]}
    col_id = head.get("rel_id")
    if not col_id:
        raise SystemExit("表头缺 rel_id（表被改过？）")
    n = 0
    for p in plans:
        for r in ws.iter_rows(min_row=2):
            if str(r[col_id - 1].value or "").strip() != p["rel_id"]:
                continue
            for h in WRITABLE:
                if h in head:
                    ws.cell(row=r[0].row, column=head[h], value=p[MAIN_MAP[h]])
            n += 1

    # 证据页：先删掉这几条关系的旧证据行，再整体重写。
    # 不这么做就会出现「撤了证据但旧行还在」，而灌库时旧行照样被灌进去。
    if R.EV_SHEET not in wb.sheetnames:
        ev = wb.create_sheet(R.EV_SHEET)
        ev.append(R.EV_HEADERS)
    ev = wb[R.EV_SHEET]
    touched = {p["rel_id"] for p in plans}
    doomed = [row[0].row for row in ev.iter_rows(min_row=2)
              if str(row[0].value or "").strip() in touched]
    for i in sorted(doomed, reverse=True):
        ev.delete_rows(i)
    n_ev = 0
    for p in plans:
        for i, e in enumerate(p["evs"]):
            ev.append([p["rel_id"], e["uid"], "accept",
                       "；".join(e["signals"])[:120] if i else "主证据",
                       R.now()])
            n_ev += 1
    try:
        wb.save(R.WORKBOOK)
        print("已写入 {} 行（证据页 {} 条）：{}".format(n, n_ev, R.WORKBOOK))
    except PermissionError:
        alt = R.WORKBOOK.replace(".xlsx", ".new.xlsx")
        wb.save(alt)
        print("⚠️ 原表被占用（Excel 开着？），已改写：{}".format(alt))


def main() -> int:
    ap = argparse.ArgumentParser(description="关系证据落盘（P6-3）")
    ap.add_argument("--apply", action="store_true", help="真的写（默认只预演）")
    args = ap.parse_args()
    plans, skipped = plan()
    print("=== 关系证据落盘{} ===".format("（写入）" if args.apply else "（预演）"))
    for p in plans:
        print("  [{rid}] {a} —{rel}→ {b}".format(
            rid=p["rel_id"], a=p["a"], rel=p["rel"], b=p["b"]))
        for i, e in enumerate(p["evs"]):
            print("      {}证据 {uid}：「{t}」".format(
                "主" if i == 0 else "附", uid=e["uid"], t=e["text"][:40]))
        print("      置信度 {} → {}　（{}）".format(
            p["old_conf"], p["conf"], p["src"]))
    if skipped:
        print("  跳过 {} 条：".format(len(skipped)))
        for rid, why in skipped[:8]:
            print("      {} {}".format(rid, why))
        if len(skipped) > 8:
            print("      … 其余 {} 条".format(len(skipped) - 8))
    if not args.apply:
        print("\n预演结束。要写入：python pipeline/_apply_rel_evidence.py --apply")
        return 0
    if not plans:
        print("没有可写入的条目")
        return 0
    apply(plans)
    print("下一步：python pipeline/relations.py apply（灌进 index.db，不必整库重建）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
