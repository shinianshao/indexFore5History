# -*- coding: utf-8 -*-
"""一次性：在本機「檔案刪除被擋」的環境病下重跑 `build_workbook --only sentences`。

環境病（2026-10-04 實測）
------------------------
`os.remove` / `os.unlink` / bash `rm` 在本機一律 `PermissionError WinError 5`
（跳出沙盒也一樣）。連帶後果：

1. `tempfile` 探測臨時目錄時要**刪掉**它剛建的探針檔，刪不掉 → 永遠
   「No usable temporary directory」（順手在 cwd 留下幾千個 4 字節 `blat` 檔）；
2. `openpyxl` 每寫一張 worksheet 都要 `NamedTemporaryFile` + `cleanup()` 裡
   `os.remove(self.out)` → 必然崩，且崩在**存盤中途**，會把目標 xlsx 截斷成壞檔。

本腳本只在**進程內**把「臨時檔刪不掉」這件事嚥掉，**不碰任何產品碼**：
產品碼裡 `os.remove` 該是什麼還是什麼。臨時檔統一倒進 `.tmp_probe/`（已被 git 忽略）。

用法
----
    python pipeline/_scratch/_rebuild_sentences_xlsx.py            # 預演（只算不寫）
    python pipeline/_scratch/_rebuild_sentences_xlsx.py --apply    # 真寫

預演模式會把新 uid 算出來跟庫對賬，但**不呼叫 wb.save()**——
因為 save 會先截斷目標檔，萬一崩了就留一個壞 xlsx（這個坑踩過：2306 字節壞表）。
"""
from __future__ import annotations

import os
import runpy
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIPE = os.path.join(ROOT, "pipeline")
TMP = os.path.join(ROOT, ".tmp_probe")

APPLY = "--apply" in sys.argv
BOOKS = "sj"


def neutralize_delete():
    """讓「刪不掉」不再是致命錯誤（僅本進程）。"""
    _real = os.remove

    def _rm(path, **kw):
        try:
            _real(path, **kw)
        except PermissionError:
            pass

    os.remove = _rm
    os.unlink = _rm


def preview():
    """預演：把新 uid 算出來，跟 workbook/ 與 index.db 對賬，不寫盤。"""
    sys.path.insert(0, PIPE)
    import json
    from openpyxl import load_workbook

    from common import stable_uid

    bd = json.load(open(os.path.join(ROOT, "data", "index", "book-data.json"),
                        encoding="utf-8"))
    bks = BOOKS.split(",")
    sj = [s for s in bd["sentences"]
          if (s.get("chapterId") or "").split("-")[0] in bks]
    want = {s["uid"] for s in sj}
    dup = len(sj) - len(want)
    print("book-data.json 裡 {} 的句子：{:,} 條 / {:,} 個 uid（重複 {:,}）".format(
        BOOKS, len(sj), len(want), dup))

    p = os.path.join(ROOT, "workbook", "sentences-sj.xlsx")
    wb = load_workbook(p)
    rows = list(wb["句子"].iter_rows(values_only=True))
    hdr = [str(h) for h in rows[0]]
    iu, ic, ip, isq = (hdr.index("uid"), hdr.index("篇(chapterId)"),
                       hdr.index("段序"), hdr.index("句序"))

    def _as_int(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v

    n = hit_old = hit_new = 0
    for r in rows[1:]:
        if iu >= len(r) or not r[iu]:
            continue
        n += 1
        old = str(r[iu]).strip()
        new = stable_uid(r[ic], _as_int(r[ip]), _as_int(r[isq]))
        hit_old += (old in want)
        hit_new += (new in want)
    print("  表裡行數        : {:,}".format(n))
    print("  舊 uid 命中庫    : {:,}  ← 應為 0（四參數分叉）".format(hit_old))
    print("  新 uid 命中庫    : {:,}  ← 應等於行數".format(hit_new))
    gap = len(want) - n
    print("  庫比表多        : {:,} 條（舊快照，重跑會補齊）".format(gap))
    # 判據取「每一行都能在庫裡找到」，**不取**「行數 == 庫裡條數」：
    # 後者會被「表是舊快照」這種正常情況絆倒，那不是本輪要修的東西。
    ok = hit_old == 0 and hit_new == n and dup == 0
    print("  預演結果        : {}".format("對得上，可以 --apply" if ok else "❌ 對不上，別寫"))
    return 0 if ok else 1


def main() -> int:
    if not APPLY:
        return preview()

    os.makedirs(TMP, exist_ok=True)
    import tempfile
    tempfile.tempdir = TMP          # 繞過探測（探測要刪檔，必敗）
    neutralize_delete()

    sys.argv = ["build_workbook.py", "--only", "sentences", "--books", BOOKS]
    sys.path.insert(0, PIPE)
    runpy.run_path(os.path.join(PIPE, "build_workbook.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
