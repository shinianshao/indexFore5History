# -*- coding: utf-8 -*-
"""P3-1 一鍵重建：把「改完表要敲五條命令」消掉。

為什麼要有這個腳本
------------------
改一次 `workbook/persons.xlsx` 之後，要依序跑六步才會在網頁上看到變化。
少跑任何一步都會出事，而且**出事的方式很安靜**：

- 漏 `annotate_pei.py` → 裴注帳本被沖掉（句子 96,468 → 48,461，踩過一次）；
- 漏 `annotate_js_note.py` → 晉書舊史注帳本消失；
- 漏 `build_index_db.py` → 網頁查的還是舊庫，你會以為改了沒生效。

所以這個腳本的全部價值就是：**順序不會錯、失敗會停、跑完有對賬**。

流程
----
    （dump 快照）→ build_dict → annotate → annotate_pei → annotate_js_note
                → annotate_places → build_index_db →（自動 diff）

開頭存快照、結尾報 diff，是 P3-2 接上來的：改一次表就能看見「變在哪」。
快照在**第一步之前**取（舊狀態），這樣 diff 才含當次改動的效果。
關掉用 `--no-snapshot`。

`build.py`（從 raw HTML 切分語料）**不在預設流程裡**——改詞典不需要重切語料，
切一次要幾分鐘。語料真變了才加 `--with-build`。

用法
----
    python app/tools/rebuild.py               # 全量重建（含快照 + diff）
    python app/tools/rebuild.py --from 3      # 從第 3 步開始（前兩步剛跑過）
    python app/tools/rebuild.py --with-build  # 連語料切分一起重來
    python app/tools/rebuild.py --no-snapshot # 不存快照、不報 diff
    python app/tools/rebuild.py --dry-run     # 只列命令，不執行

退出碼：0 全通；非 0 = 第幾步失敗（進程退出碼即步驟序號）。
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snapshot    # noqa: E402  快照與 diff（P3-2）
import overrides   # noqa: E402  單條糾錯（P3-3）

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # app/tools → app → 根
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")

# （步驟名, 相對於 ROOT 的腳本路徑, 一句話說明）
STEPS = [
    ("build_dict", "pipeline/build_dict.py",
     "讀 workbook/*.xlsx → people.json / places.json（⚠️ 只讀，不回寫）"),
    ("annotate", "pipeline/annotate.py",
     "主帳本標註（別名匹配 + 泛稱歸屬判定）"),
    ("annotate_pei", "pipeline/annotate_pei.py",
     "裴注帳本（獨立記，不進 mentionCount）"),
    ("annotate_js_note", "pipeline/annotate_js_note.py",
     "晉書舊史注帳本"),
    ("annotate_places", "pipeline/annotate_places.py",
     "地名標註"),
    ("build_index_db", "app/tools/build_index_db.py",
     "→ SQLite（含 FTS5 全文索引）"),
]

# P3-3：這一步不是獨立腳本，而是直接改 book-data.json 的一層 post 修正，
# 必須夾在 annotate 四步之後、build_index_db 之前——見 overrides.py 的說明。
OVERRIDE_STEP = "apply_overrides"

# 語料變了才需要跑這一步：raw HTML → corpus 切分
BUILD_STEP = ("build", "pipeline/build.py", "raw HTML → corpus 切分（慢，預設不跑）")


def run_step(name: str, rel: str, desc: str, dry: bool) -> float:
    """跑一步，失敗即拋。回傳耗時（秒）。"""
    script = os.path.join(ROOT, rel)
    cmd = [sys.executable, script]
    print("\n── [{}] {}   {}".format(name, desc, "" if not dry else "(dry-run)"))
    print("   $ {}".format(" ".join(cmd)))
    if dry:
        return 0.0
    if not os.path.exists(script):
        raise RuntimeError("腳本不存在：{}".format(script))

    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # 不捕獲輸出：讓子進程直接打印，出了錯你能看見完整堆疊
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    dt = time.time() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            "步驟 [{}] 失敗（退出碼 {}），已停止——不要拿半截產物當成功".format(
                name, proc.returncode))
    print("   ✓ 用時 {:.1f}s".format(dt))
    return dt


def print_stats() -> None:
    """跑完對個賬：規模與上一版差多少，一眼能看到。"""
    if not os.path.exists(DB_PATH):
        print("\n（索引庫不存在，跳過對賬）")
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        counts = {}
        for t in ("sentences", "mentions", "persons", "aliases", "places"):
            counts[t] = conn.execute("SELECT COUNT(*) FROM {}".format(t)).fetchone()[0]
    finally:
        conn.close()
    print("\n── 重建後規模")
    for k, v in counts.items():
        print("   {:<10} {:>8,}".format(k, v))


def main() -> int:
    ap = argparse.ArgumentParser(description="BOOKINDEX 一鍵重建")
    ap.add_argument("--from", dest="start", default=1, type=int,
                    help="從第幾步開始（1-based，預設 1）")
    ap.add_argument("--with-build", action="store_true",
                    help="在最前面加跑 build.py（語料切分，慢）")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="不存快照、不報 diff")
    ap.add_argument("--no-overrides", action="store_true",
                    help="不套用 workbook/overrides.xlsx 的單條糾錯")
    ap.add_argument("--keep", type=int, default=snapshot.KEEP_DEFAULT,
                    help="快照保留最近幾份（預設 {}）".format(snapshot.KEEP_DEFAULT))
    ap.add_argument("--diff-top", type=int, default=10,
                    help="diff 每類打印幾條（預設 10）")
    ap.add_argument("--dry-run", action="store_true", help="只列命令不執行")
    args = ap.parse_args()

    steps = list(STEPS)
    if args.with_build:
        steps = [BUILD_STEP] + steps

    if args.start < 1 or args.start > len(steps):
        print("步驟序號超出範圍：1–{}".format(len(steps)))
        return 2

    todo = steps[args.start - 1:]
    print("BOOKINDEX 一鍵重建 · 根目錄 {}".format(ROOT))
    print("共 {} 步，本次執行 {} 步".format(len(steps), len(todo)))

    # 快照必須在第一步之前取：這時庫裡還是「改動前」的狀態
    pre_sid = None
    if not args.no_snapshot and not args.dry_run:
        try:
            pre_sid = snapshot.dump(label="pre-rebuild", keep=args.keep)
        except RuntimeError as e:
            print("（跳過快照：{}）".format(e))

    t0 = time.time()
    for i, (name, rel, desc) in enumerate(todo, start=args.start):
        try:
            # 糾錯必須在建庫之前套用：改的是 book-data.json，庫是由它生成的
            if name == "build_index_db" and not args.no_overrides \
                    and not args.dry_run:
                overrides.cmd_apply(argparse.Namespace(dry_run=False))
            run_step(name, rel, desc, args.dry_run)
        except RuntimeError as e:
            print("\n✗ {}".format(e))
            return i
    total = time.time() - t0

    if not args.dry_run:
        print_stats()
        if pre_sid:
            # 新側是重建後的庫，不是另一份快照——兩份快照都是舊狀態，比不出東西
            snapshot.diff_live(pre_sid, top=args.diff_top)
    print("\n✓ 全部完成，總用時 {:.1f}s".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
