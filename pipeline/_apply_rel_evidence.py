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

⚠️ 只写四列：`证据uid` / `证据原文` / `置信度(confidence)` / `备注(note)`。
其余列（尤其人写的 source / era / book / status）**一个字都不动**——
那是权威源里归人的部分，脚本碰了就重建时冲掉审定（红线 1）。

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
WRITABLE = ("证据uid", "证据原文", "置信度(confidence)", "备注(note)")


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
        if row.get("证据uid"):
            skipped.append((rid, "已有证据，跳过"))
            continue
        v = verdicts.get(rid) or {}
        if v.get("accept") is False:
            skipped.append((rid, "人工判定为否"))
            continue
        if v.get("uid"):                       # 人工指定了别的句子
            cand = next((c for c in it["cands"] if c["uid"] == v["uid"]), None)
            if not cand:
                cand = {"uid": v["uid"], "text": _sentence_text(v["uid"]),
                        "score": 0, "signals": ["人工指定"]}
            src = "人工判定"
        elif it["cands"] and it["cands"][0]["score"] >= AUTO_MIN and (
                len(it["cands"]) == 1 or it["cands"][1]["score"] < AUTO_MIN):
            cand = it["cands"][0]
            src = "自动取证（硬句式）"
        else:
            skipped.append((rid, "没有够硬的证据，留给人工判"))
            continue
        text = _sentence_text(cand["uid"])
        if not text:
            skipped.append((rid, "证据句已失效或不活跃：{}".format(cand["uid"])))
            continue
        src_src = row.get("来源(source)") or "manual"
        conf = R.derive_confidence(src_src, True)
        note = "{}：{}".format(src, "；".join(cand.get("signals") or []))[:120]
        old_note = row.get("备注(note)") or ""
        out.append({
            "rel_id": rid, "a": it["name_a"], "rel": it["rel"], "b": it["name_b"],
            "uid": cand["uid"], "text": text,
            "conf": conf, "old_conf": row.get("置信度(confidence)"),
            "note": (old_note + " " + note).strip()[:200],
            "src": src,
        })
    return out, skipped


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
                    ws.cell(row=r[0].row, column=head[h],
                            value=p[{"证据uid": "uid", "证据原文": "text",
                                     "置信度(confidence)": "conf",
                                     "备注(note)": "note"}[h]])
            n += 1
    try:
        wb.save(R.WORKBOOK)
        print("已写入 {} 行：{}".format(n, R.WORKBOOK))
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
        print("      证据 {uid}：「{t}」".format(uid=p["uid"], t=p["text"][:40]))
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
