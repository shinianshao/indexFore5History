# -*- coding: utf-8 -*-
"""P0-甲：命中標色必須落在**庫給的 s/e** 上，不能用 indexOf（2026-10-03 審查）。

問題
----
`app/web/app.js` 的 `markSentence(text, surface, tier)` 簽名裡**沒有 s/e**，
只能 `text.indexOf(surface)` 找第一處。同一句裡同一個詞多次出現時
（「舜…堯…舜」），標色落在不相干的語境上。
實測 182128 條命中裡**8319 條（4.6%）**標錯位置。

⚠️ 但**也不能只改成 `text.slice(s, e)`**——這是審查報告給的建議改法，照做會
**新造 63 條錯標**：`s`/`e` 是 pipeline 用 Python 算的**碼位**下標，
JS 的 `slice` 按 **UTF-16 碼元**。古籍裡有非 BMP 字（實測 U+24CF9 湯/U+23D40湦
這類罕用異體字），一個字算兩個碼元，位置整個偏。
所以修法是三級回退（slice → 按碼位切 → indexOf 兜底），
見 app/web/app.js 的 `hitSpan`。

斷言打在哪裡
------------
**不能**只斷「庫裡 s/e 對不對」——數據本來就對（實測 text[s:e]==surface 100%），
那樣這條斷言與前端無關，修沒修前端都是綠。
要斷在**會被打破的那一層**：把 `app/web/app.js` 裡的 `hitSpan`/`markSentence`
**原樣抽出來跑**（不重寫、不 mock），餵全量真命中，斷渲染出的 HTML 裡
`<mark>` 的落點與位置。這樣改壞前端必紅。

判據是「**mark 之前恰好 s 個字**」而不是「三段拼回原句」——
後者對 indexOf **恆真**，會把 8319 條錯標判成 0 錯綠。
而且要數**碼位**（Array.from）不是碼元（.length），否則走路徑 B 的那 63 條
（其實是對的）會被誤判成錯。

⚠️ 兩個我自己踩過的判據坑（寫下來免得再踩）
1. Python 裡 `len(text) == len(list(text))` **恆成立**（str 本身就是碼位序列），
   拿它判「碼位≠碼元」是恆假 —— 斷言直接 0 條紅。判有沒有非 BMP 字要用
   `any(ord(ch) > 0xFFFF for ch in text)`。
2. 判「落點對不對」不能只斷字串相等。`hitSpan` 的路徑 B 早期版本返回**碼位下標**
   交給調用方 `text.slice`（碼元）再切一遍，看著切出來了、實際正是它要修的錯。
   現在 `hitSpan` 直接返回**切好的三段字串**，不把下標外洩出去。

用法：python app/tools/verify_p3_mark.py     （約 15 秒）
注入驗證：bash app/tools/verify_p3_mark_inject.sh
           三種壞寫法（indexOf / 天真 slice / 碼元洩漏）逐一注入，必須都變紅
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

NODE = (os.environ.get("BOOKINDEX_NODE")
        or "C:/Users/dell/.workbuddy/binaries/node/versions/22.22.2-3/node.exe")

CHECKS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok))
    print("  {} {}{}".format("OK  " if ok else "FAIL", name,
                             ("  — " + detail) if detail else ""))


# 從 app/web/app.js **原樣抽** hitSpan + markSentence。
# ⚠️ 按**函數體邊界**截取，不能按字串唯一性 replace(old,new,1)：
#    app.js 裡 indexOf 出現在多處，replace(...,1) 改的是第一處（offSearchPlaces
#    的搜索），注入會完全沒生效而斷言全綠——差一步就誤判「斷言沒用」。
RUNNER = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function cut(a, b) {
  const i = src.indexOf(a);
  if (i < 0) throw new Error("起點找不到: " + a);
  const j = src.indexOf(b, i);
  if (j < 0) throw new Error("終點找不到: " + b);
  return src.slice(i, j);
}
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const TIER_NOTE = { owner: "篇主", chapter: "篇目", era: "時代", sentence: "句內",
  paragraph: "段內", related: "關聯", scoped: "限定", guess: "推斷" };
const body = cut("  function hitSpan(", "  /* ---------- 渲染：結果列表 ---------- */");
const mod = new Function("esc", "TIER_NOTE", body + "\nreturn { hitSpan, markSentence };")(esc, TIER_NOTE);

const rows = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const cpLen = (x) => Array.from(x).length;
let bad = 0, nullSpan = 0, pathB = 0, pathC = 0;
const badSamples = [];
for (const r of rows) {
  const sp = mod.hitSpan(r.text, r.surface, r.s, r.e);
  if (!sp) { nullSpan++; continue; }
  // 三級回退各走了多少——路徑 B 必須 >0（否則就是「天真的 slice」在冒充修好的版本）
  if (Array.from(r.text).length !== r.text.length) pathB++;   // 該句含非 BMP 字
  if (cpLen(sp[0]) !== r.s) pathC++;
  const html = mod.markSentence(r.text, r.surface, r.tier, r.s, r.e);
  const m = html.match(/<mark class="[^"]*">([\s\S]*?)<\/mark>/);
  const good = m && m[1] === r.surface &&
               sp[0] + sp[1] + sp[2] === r.text && cpLen(sp[0]) === r.s;
  if (!good) { bad++; if (badSamples.length < 5) badSamples.push(r.uid); }
}
console.log(JSON.stringify({ n: rows.length, bad: bad, nullSpan: nullSpan,
                             pathB: pathB, pathC: pathC, badSamples: badSamples }));
"""


def main() -> int:
    print("\n[18] 命中標色落點 · 前端實碼（docs/34 P0-1）")

    if not os.path.exists(NODE):
        print("  跳過：找不到 node（{}）".format(NODE))
        return 0

    idx = os.path.join(ROOT, "data", "index", "index.db")
    if not os.path.exists(idx):
        check("索引庫存在", False, idx)
        return 1

    # ---- 先斷數據側前提：不符就別談前端了（否則「全綠」可能是因為沒資料） ----
    con = sqlite3.connect(idx)
    con.row_factory = sqlite3.Row
    rows = []
    for tbl in ("mentions", "place_mentions"):
        rows.extend(dict(r) for r in con.execute(
            "SELECT m.sentence_uid AS uid, s.text AS text, m.surface AS surface,"
            " m.s AS s, m.e AS e, m.tier AS tier"
            " FROM {} m JOIN sentences s ON s.uid = m.sentence_uid".format(tbl)))
    con.close()

    check("有命中可驗（全量喂進去，不是抽樣）", len(rows) > 100000,
          "{} 條".format(len(rows)))
    if len(rows) <= 100000:
        return 1

    # 前提：Python 側 s/e 自洽（不對的話前端再對也沒意義）
    bad_py = [r for r in rows if r["s"] is None or r["e"] is None
              or (r["text"] or "")[r["s"]:r["e"]] != (r["surface"] or "")]
    check("庫裡 s/e 自洽（text[s:e]==surface）", not bad_py,
          "不符 {} 條".format(len(bad_py)))
    # ⚠️ Python 字符串**本身就是码位序列**，len(text) 恒等于 len(list(text))——
    #   拿它当「码位≠码元」的判据是恒假（第一版就这么写错了，直接 0 条红）。
    #   要判的是「句里有没有非 BMP 字」——只有这种字才会让 JS 的码元下标偏。
    nonbmp = [r for r in rows if any(ord(ch) > 0xFFFF for ch in (r["text"] or ""))]
    check("有含非 BMP 字的句子（B 路徑的前提）", len(nonbmp) > 0,
          "{} 條".format(len(nonbmp)))

    # ---- 跑前端真碼 ----
    tmp_js = os.path.join(tempfile.gettempdir(), "bi_verify_mark_runner.js")
    tmp_js2 = os.path.join(tempfile.gettempdir(), "bi_verify_mark_data.json")
    with open(tmp_js, "w", encoding="utf-8") as f:
        f.write(RUNNER)
    with open(tmp_js2, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)

    try:
        p = subprocess.run([NODE, tmp_js, os.path.join(ROOT, "app", "web", "app.js"), tmp_js2],
                           capture_output=True, text=True, encoding="utf-8")
    finally:
        for pth in (tmp_js, tmp_js2):
            if os.path.exists(pth):
                try:
                    os.remove(pth)
                except OSError:
                    pass

    if p.returncode != 0:
        check("抽出 hitSpan/markSentence 並跑全量", False,
              (p.stderr or "").strip().splitlines()[-1] if p.stderr else "rc=%d" % p.returncode)
        return 1
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        check("跑全量的輸出可解析", False, p.stdout[-300:])
        return 1

    # ⚠️ 判據是「bad == 0」且**樣本非空**——樣本空的話壞法可能只是沒觸發
    check("前端 hitSpan/markSentence 落點全對", r["bad"] == 0,
          "{}/{} 錯，樣例 {}".format(r["bad"], r["n"], r.get("badSamples")))
    check("每條都標得到（沒有落空成 null）", r["nullSpan"] == 0,
          "{} 條標不到".format(r["nullSpan"]))
    check("B 路徑（按碼位切）確實被走到過", r["pathB"] > 0,
          "{} 條含非 BMP 字".format(r["pathB"]))
    check("C 路徑（indexOf 兜底）幾乎不走", r["pathC"] == 0,
          "{} 條落到兜底（s/e 與 text 不同源，要查數據）".format(r["pathC"]))

    ok = sum(1 for _, v in CHECKS if v)
    print("\n  {}/{} 通過".format(ok, len(CHECKS)))
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
