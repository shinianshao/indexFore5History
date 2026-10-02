"""把占位 pid（`p_xNNNNN`）改成拼音语义 id。

**只改 id，不改任何其他数据。** 规则对齐现有 1,627 个语义化 pid 的命名法：
  `p_<全拼>`                       唯一
  `p_<全拼>_<朝代缩写>`             与已有 pid 撞名时，按朝代消歧
  `p_<全拼><数字>`                  仍撞名时加序号（不新建人，只换 id）

⚠️ 三条红线相关：
  1. 本脚本**只改 id**，不动姓名/别名字面/归属——不是「新建人」。
  2. 改名涉及**权威源** `workbook/persons.xlsx`（id 列）与
     `workbook/relations.xlsx`（person_a / person_b）。persons 是权威源，
     relations 的边会在 rebuild 最后一步重新灌库，但**权威源里的 id 必须同步**。
  3. 默认预演；`--apply` 才写。写前后都要能核。

用法：
    python pipeline/_rename_placeholder_pids.py               # 预演
    python pipeline/_rename_placeholder_pids.py --apply       # 真改 persons.xlsx
    python pipeline/_rename_placeholder_pids.py --plan-out FILE  # 导出改名映射表
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "index" / "index.db"
PERSONS_XLSX = ROOT / "workbook" / "persons.xlsx"
RELATIONS_XLSX = ROOT / "workbook" / "relations.xlsx"

PLACEHOLDER = re.compile(r"^p_x\d+$")

# 朝代 → 缩写（对齐现有 pid 里的用法：sg 三國 / hs 漢 / hhs 後漢 / js 晉 / sj 史記 / zh 先秦）
ERA_ABBR = {
    "西漢": "hs", "東漢": "hhs", "漢": "hhs", "後漢": "hhs",
    "三國": "sg", "蜀": "sg", "魏": "sg", "吳": "sg",
    "西晉": "js", "東晉": "js", "晉": "js",
    "先秦": "zh", "戰國": "zh", "春秋": "zh",
    "十六國": "sgl", "南北朝": "nbs",
}


def to_pinyin(name: str) -> str | None:
    """汉��名 → 全拼小写无调；非汉字或全非汉字返回 None。"""
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError:
        print("需要 pypinyin：pip install pypinyin")
        sys.exit(1)
    parts = lazy_pinyin(name, style=Style.NORMAL, errors="ignore")
    py = "".join(parts).lower()
    py = re.sub(r"[^a-z]", "", py)
    return py or None


def load_placeholder() -> list[dict]:
    if not DB.exists():
        print(f"找不到 {DB}")
        sys.exit(1)
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT id, name, dynasty FROM persons ORDER BY id")]
    con.close()
    return [r for r in rows if PLACEHOLDER.match(r["id"] or "")]


def existing_ids() -> set[str]:
    con = sqlite3.connect(str(DB))
    got = {r[0] for r in con.execute("SELECT id FROM persons")}
    con.close()
    return got


def build_plan(ph: list[dict], taken: set[str]) -> list[dict]:
    """算出 (old_id, new_id, name, dynasty) 映射。撞名按朝代、再按序号消歧。"""
    plan: list[dict] = []
    used = set(taken)
    for row in ph:
        name = (row["name"] or "").strip()
        py = to_pinyin(name) if name else None
        if not py:
            plan.append({**row, "new_id": None, "why": "正名为空或非汉字"})
            continue
        cand = f"p_{py}"
        if cand in used:
            era = (row["dynasty"] or "").strip()
            abbr = ERA_ABBR.get(era)
            if abbr:
                cand2 = f"p_{py}_{abbr}"
                if cand2 not in used:
                    cand = cand2
                else:
                    n = 2
                    while f"p_{py}{n}" in used:
                        n += 1
                    cand = f"p_{py}{n}"
            else:
                n = 2
                while f"p_{py}{n}" in used:
                    n += 1
                cand = f"p_{py}{n}"
        used.add(cand)
        plan.append({**row, "new_id": cand, "why": ""})
    return plan


def _pick_sheet(wb, need_cols):
    """找到带指定列的 sheet。**别写死 sheet 名**——实测 persons.xlsx 的表叫中文
    `人物`（另有 `说明` 表），写死 `persons` 会直接失败（已踩）。判据用列名。"""
    for name in wb.sheetnames:
        cand = wb[name]
        header = [c.value for c in cand[1]]
        if all(c in header for c in need_cols):
            return cand, header
    return None, None


def apply_plan(plan: list[dict]) -> tuple[int, list[str]]:
    """改 persons.xlsx 的 id 列。只改 id，其它列原样。"""
    wb = openpyxl.load_workbook(PERSONS_XLSX)
    ws, header = _pick_sheet(wb, ("id",))
    if ws is None:
        return 0, ["persons.xlsx 里没有带 id 列的 sheet，实有：{}".format(wb.sheetnames)]
    col = header.index("id") + 1
    mapping = {r["id"]: r["new_id"] for r in plan if r["new_id"]}
    if not mapping:
        return 0, []
    changed = 0
    for row in ws.iter_rows(min_row=2):
        cell = row[col - 1]
        old = cell.value
        if old and str(old).strip() in mapping:
            cell.value = mapping[str(old).strip()]
            changed += 1
    wb.save(PERSONS_XLSX)
    return changed, []


def apply_relations(plan: list[dict]) -> tuple[int, list[str]]:
    """同步改 relations.xlsx 的 person_a / person_b。

    ⚠️ 这一步不能省：边以 pid 为外键，persons 改了而 relations 没改，
    重建后那条边的两端会变成查不到人的悬空 id（`apply_relations` 不报错，
    只是静默灌进去，前端关系图上凭空少一条边）。
    """
    if not RELATIONS_XLSX.exists():
        return 0, ["relations.xlsx 不存在"]
    mapping = {r["id"]: r["new_id"] for r in plan if r["new_id"]}
    if not mapping:
        return 0, []
    wb = openpyxl.load_workbook(RELATIONS_XLSX)
    ws, header = _pick_sheet(wb, ("person_a", "person_b"))
    if ws is None:
        return 0, ["relations.xlsx 里没有带 person_a/person_b 的 sheet"]
    cols = {k: header.index(k) + 1 for k in ("person_a", "person_b")}
    changed = 0
    for row in ws.iter_rows(min_row=2):
        for c in cols.values():
            cell = row[c - 1]
            old = cell.value
            if old and str(old).strip() in mapping:
                cell.value = mapping[str(old).strip()]
                changed += 1
    wb.save(RELATIONS_XLSX)
    return changed, []


def main() -> int:
    ap = argparse.ArgumentParser(description="占位 pid → 拼音语义 id")
    ap.add_argument("--apply", action="store_true", help="真改 persons.xlsx")
    ap.add_argument("--plan-out", help="导出改名映射表（csv）")
    ap.add_argument("--limit", type=int, default=0, help="只列前 N 条明细")
    args = ap.parse_args()

    ph = load_placeholder()
    if not ph:
        print("没有占位 pid。")
        return 0
    taken = existing_ids()
    plan = build_plan(ph, taken)

    ok = [r for r in plan if r["new_id"]]
    bad = [r for r in plan if not r["new_id"]]
    collide = [r for r in ok if r["new_id"] != f"p_{to_pinyin(r['name'] or '')}"]

    print(f"占位 pid {len(ph)} 个：可改名 {len(ok)}，需人工 {len(bad)}")
    print(f"其中因撞名加了朝代/序号的：{len(collide)}")

    if bad:
        print("—— 需人工（正名为空或非汉字）——")
        for r in bad[:20]:
            print(f"  {r['id']}  {r['name']!r}")

    if collide:
        print("—— 撞名加了后缀（前 20）——")
        for r in collide[:20]:
            print(f"  {r['id']} → {r['new_id']}   {r['name']}（{r['dynasty']}）")

    if args.plan_out:
        import csv
        p = ROOT / args.plan_out
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as f:
            wtr = csv.writer(f)
            wtr.writerow(["old_id", "new_id", "name", "dynasty"])
            for r in plan:
                wtr.writerow([r["id"], r["new_id"] or "", r["name"], r["dynasty"]])
        print(f"映射表已写 {p.relative_to(ROOT)}")

    if not args.apply:
        print("预演模式。加 --apply 真改 persons.xlsx 与 relations.xlsx。")
        return 0

    changed, errs = apply_plan(plan)
    if errs:
        for e in errs:
            print(f"失败：{e}")
        return 1
    print(f"已改 persons.xlsx 的 id {changed} 行")

    rchanged, rerrs = apply_relations(plan)
    if rerrs:
        for e in rerrs:
            print(f"relations 同步失败：{e}")
        return 1
    print(f"已改 relations.xlsx 的 pid 引用 {rchanged} 处")

    print("下一步：python app/tools/rebuild.py  →  bash scripts/run_all.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
