"""取證：613 个占位 pid 是谁、分布在哪些书、名字能否自动生成。

只讀，不寫。輸出：
  1. 占位 pid 總數 / 有多少在關係邊裡被引用 / 有多少在別名裡
  2. 名字來源：正名（persons.xlsx 的 name 列）是否已是可用的漢語名
  3. 重名情況：同一個正名對應幾個 pid（決定要不要先合併）
  4. 拼音可得性：正名的漢語拼音能否算出來（本機是否裝 pypinyin）

用法：
    python pipeline/_probe_placeholder_pid.py
    python pipeline/_probe_placeholder_pid.py --out docs/31-占位pid取证.md
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "index" / "index.db"
PLACEHOLDER = re.compile(r"^p_x\d+$")


def load() -> tuple[list[dict], dict]:
    if not DB.exists():
        print(f"找不到 {DB}，先跑 python app/tools/build_index_db.py")
        sys.exit(1)
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    persons = [dict(r) for r in con.execute(
        "SELECT id, name, dynasty FROM persons ORDER BY id")]
    # 关系边里的引用计数
    edge_ref = Counter()
    for r in con.execute(
            "SELECT person_a, person_b FROM relations WHERE status='active'"):
        for pid in (r["person_a"], r["person_b"]):
            if pid:
                edge_ref[pid] += 1
    # 别名引用
    alias_ref = Counter()
    for (pid,) in con.execute("SELECT person_id FROM aliases"):
        if pid:
            alias_ref[pid] += 1
    con.close()
    return persons, {"edge": edge_ref, "alias": alias_ref}


def pinyin_available() -> bool:
    try:
        import pypinyin  # noqa: F401
        return True
    except ImportError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="占位 pid 取证（只读）")
    ap.add_argument("--out", help="写成 markdown 文件")
    ap.add_argument("--sample", type=int, default=20, help="抽样列出的条数")
    args = ap.parse_args()

    persons, refs = load()
    ph = [p for p in persons if PLACEHOLDER.match(p["id"] or "")]
    normal = [p for p in persons if not PLACEHOLDER.match(p["id"] or "")]

    out: list[str] = []
    w = out.append

    w("# 31 · 占位 pid 取证（只读，未改任何数据）\n")
    w("> 取数命令：`python pipeline/_probe_placeholder_pid.py`")
    w("> 生成时间：本次运行\n")

    w("## 一、总量\n")
    w(f"| 项 | 数 |")
    w("|---|---|")
    w(f"| 人物总数 | {len(persons)} |")
    w(f"| 占位 pid（`p_xNNNNN`） | **{len(ph)}** |")
    w(f"| 已语义化 pid | {len(normal)} |")
    w(f"| 占位比例 | {len(ph) / len(persons) * 100:.1f}% |")
    w("")

    # 引用面
    in_edge = sum(1 for p in ph if refs["edge"].get(p["id"]))
    in_alias = sum(1 for p in ph if refs["alias"].get(p["id"]))
    w("## 二、改 pid 会牵动多少地方\n")
    w(f"| 引用位置 | 占位 pid 中被引用的个数 |")
    w("|---|---|")
    w(f"| `relations` 边（person_a / person_b） | {in_edge} |")
    w(f"| `aliases`（person_id） | {in_alias} |")
    w("")
    w("> 这两项都落在**权威源或派生产物**里：边在 `workbook/relations.xlsx`，"
      "别名在 `workbook/persons.xlsx`。改 id 前后都要同步。")
    w("")

    # 重名
    by_name: dict[str, list[str]] = defaultdict(list)
    for p in persons:
        if p["name"]:
            by_name[p["name"]].append(p["id"])
    dup = {k: v for k, v in by_name.items() if len(v) > 1}
    ph_dup = {k: v for k, v in dup.items() if any(PLACEHOLDER.match(i) for i in v)}
    w("## 三、重名情况（决定能否自动生成 id）\n")
    w(f"| 项 | 数 |")
    w("|---|---|")
    w(f"| 全部重名组（同名多 pid） | {len(dup)} |")
    w(f"| 其中含占位 pid 的组 | {len(ph_dup)} |")
    w(f"| 占位 pid 涉及的人名数 | {len({p['name'] for p in ph if p['name']})} |")
    w("")
    if ph_dup:
        w("含占位 pid 的重名组（**这些不能自动改名**，会撞车）：\n")
        for name, ids in sorted(ph_dup.items())[: args.sample]:
            mark = " ← 有占位" if any(PLACEHOLDER.match(i) for i in ids) else ""
            w(f"- **{name}**：{', '.join(ids)}{mark}")
        if len(ph_dup) > args.sample:
            w(f"- …另有 {len(ph_dup) - args.sample} 组")
        w("")

    # 抽样
    w("## 四、占位 pid 抽样（看正名是否可用）\n")
    w("| pid | 正名 | 朝代 | 边引用 | 别名数 |")
    w("|---|---|---|---|---|")
    for p in ph[: args.sample]:
        w(f"| `{p['id']}` | {p['name'] or '（空）'} | {p['dynasty'] or '—'} "
          f"| {refs['edge'].get(p['id'], 0)} | {refs['alias'].get(p['id'], 0)} |")
    if len(ph) > args.sample:
        w(f"\n…另有 {len(ph) - args.sample} 个")
    w("")

    # 拼音
    has_pinyin = pinyin_available()
    w("## 五、拼音来源\n")
    w(f"- `pypinyin` 可用：{'是' if has_pinyin else '**否**'}")
    if not has_pinyin:
        w("- 装它：`pip install pypinyin`（纯 Python，无编译依赖）")
    w("- persons 表里已有 `era`；拼音**不需要**从 era 推，只需要正名。")
    w("")

    # 结论
    w("## 六、结论（供判断，不是承诺）\n")
    auto_ok = len(ph) - len({p["name"] for p in ph if p["name"]} & set(dup))
    w(f"1. **可自动改名**：正名唯一且非空的占位 pid，约 **{auto_ok}** 个。")
    w(f"2. **需人工拍板**：重名组 {len(ph_dup)} 组（同名异人，正是项目规矩里"
      "「必须看原文」的那类）。")
    w(f"3. **改名成本**：要同步 `persons.xlsx` / `relations.xlsx` 两张权威源，"
      "改完全量重建 34s + 回归 241s 可验。")
    w("4. 顺序上应当**先做同名合并、再做语义化**——反过来的话，合并时要同时改两套 id。")
    w("")

    text = "\n".join(out)
    if args.out:
        p = ROOT / args.out
        p.write_text(text, encoding="utf-8")
        print(f"已写 {p.relative_to(ROOT)}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
