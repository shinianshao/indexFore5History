# -*- coding: utf-8 -*-
"""比對 `workbook/*.xlsx` 與 HEAD 的**內容**是否真的變了（一次性）。

為什麼要比對內容而不是看 git：`openpyxl` 重存會改 xlsx 位元組（壓縮串流不同），
`git diff` 顯示 `Bin 5040 -> 5042` 看著像髒了，其實可能一字未改。
反過來也一樣：位元組一樣不代表內容一樣——所以只能逐行比。

用法
----
    bash -c 'git show HEAD:workbook/overrides.xlsx > C:/Users/dell/AppData/Local/Temp/ov.xlsx'
    python pipeline/_scratch/_cmp_workbook.py
"""
import os
import sys

from openpyxl import load_workbook

TMP = "C:/Users/dell/AppData/Local/Temp"
PAIRS = [
    ("workbook/overrides.xlsx", TMP + "/ov_head.xlsx"),
    ("workbook/sentence-edits.xlsx", TMP + "/se_head.xlsx"),
]


def rows(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return out


def main():
    for cur, head in PAIRS:
        if not os.path.exists(head):
            print("[跳過] 缺 %s（先 git show HEAD:%s > 它）" % (head, cur))
            continue
        a, b = rows(cur), rows(head)
        if set(a) != set(b):
            print("✗ %s：頁籤不同 %s vs %s" % (cur, sorted(a), sorted(b)))
            continue
        diff = []
        for sh in a:
            if a[sh] == b[sh]:
                continue
            ra, rb = a[sh], b[sh]
            if len(ra) != len(rb):
                diff.append("%s：行數 %d → %d" % (sh, len(rb), len(ra)))
            for i, (x, y) in enumerate(zip(ra, rb)):
                if x != y:
                    diff.append("%s 第 %d 行：%s → %s" % (sh, i + 1, y, x))
        print(("✗ %s 內容變了：\n    " % cur) + "\n    ".join(diff[:12])
              if diff else "✔ %s 內容與 HEAD 一致（只是位元組不同）" % cur)


if __name__ == "__main__":
    sys.exit(main())
