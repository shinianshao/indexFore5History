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

⚠️ 但**只斷函式本身還不夠**（2026-10-04 獨立審查 P1-1）。抽出來的函式是
**本檔案自己帶著 s/e 呼叫**的，產品碼裡那兩個呼叫點（人物 `:632` / 地名 `:719`）
有沒有真的把 `s/e` 餵進去，**這一層原本完全沒有人看**。
實測：把兩處改回 `markSentence(m.text, m.surface, m.tier)`，
本檔案 **7/7 全綠**、離線 UI **74/0 全綠**，而 8319 條錯標 100% 復活且不報錯——
因為 `hitSpan` 收到 `undefined` 會**靜默落到路徑 C（indexOf）**，正好是修復前的行為。
等於驗了引擎沒驗接線。所以下面加了一條靜態檢查守呼叫點。

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

import io
import json
import os
import re
import sqlite3
import subprocess
import sys

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
// ⚠️ 引數位置：本檔以 `node -e RUNNER <app.js>` 執行，所以 argv[1] 是 app.js；
//    資料（18 萬條）走 stdin，不落盤。
const src = fs.readFileSync(process.argv[1], "utf8");
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

const rows = JSON.parse(fs.readFileSync(0, "utf8"));
const cpLen = (x) => Array.from(x).length;
let bad = 0, nullSpan = 0, pathA = 0, pathB = 0, pathC = 0;
const badSamples = [];
for (const r of rows) {
  // 路徑分佈：這裡**獨立複刻** hitSpan 三級的判據，不是複用它——
  // 目的是讓 A/B/C 的分佈成為一個可對賬的數字（獨立複算：A=182065/B=63/C=0），
  // 而不是「看起來有在走」。真偽由下面 bad==0 那條守，這段只負責分佈。
  // ⚠️ 若 hitSpan 的判據改了，這段要同步——不同步的症狀是 pathA+pathB+pathC != n。
  const cp = Array.from(r.text);
  const a = Number(r.s), b = Number(r.e);
  if (b <= r.text.length && r.text.slice(a, b) === r.surface) pathA++;
  else if (b <= cp.length && cp.slice(a, b).join("") === r.surface) pathB++;
  else pathC++;

  const sp = mod.hitSpan(r.text, r.surface, r.s, r.e);
  if (!sp) { nullSpan++; continue; }
  const html = mod.markSentence(r.text, r.surface, r.tier, r.s, r.e);
  const m = html.match(/<mark class="[^"]*">([\s\S]*?)<\/mark>/);
  const good = m && m[1] === r.surface &&
               sp[0] + sp[1] + sp[2] === r.text && cpLen(sp[0]) === r.s;
  if (!good) { bad++; if (badSamples.length < 5) badSamples.push(r.uid); }
}
console.log(JSON.stringify({ n: rows.length, bad: bad, nullSpan: nullSpan,
                             pathA: pathA, pathB: pathB, pathC: pathC,
                             badSamples: badSamples }));
"""


APP_JS = os.path.join(ROOT, "app", "web", "app.js")

# 產品碼裡 markSentence 的呼叫點：人物命中句與地名命中句各一處。
# ⚠️ 為什麼要單獨斷它：下面的全量測試是**本檔案自己帶著 s/e 呼叫**抽出的函式，
#    呼叫點漏傳時它照綠（實測 7/7 綠而 8319 條錯標復活）。這是「驗了引擎沒驗接線」。
N_CALL_SITES = 2


def check_call_sites() -> None:
    """靜態掃 app.js：每個 markSentence 呼叫點都必須傳滿 5 個實參（含 s/e）。"""
    src = io.open(APP_JS, encoding="utf-8").read()
    calls = []
    for m in re.finditer(r"markSentence\(([^()]*)\)", src):
        # 函式定義行（`function markSentence(text, surface, tier, s, e)`）不是呼叫點
        if src[:m.start()].rstrip().endswith("function"):
            continue
        calls.append(m.group(1))
    bad = [c for c in calls if len([x for x in c.split(",") if x.strip()]) < 5]
    # ⚠️ 判據必須先斷「找得到呼叫點」——re 找不到時 calls 是空列表，
    #    `not bad` 對空列表恆真，那就又是「壞法不發聲」的假綠。
    check("每個 markSentence 呼叫點都傳了 s/e（不是只驗函式本身）",
          len(calls) >= N_CALL_SITES and not bad,
          "共 {} 處呼叫（應 ≥{}），漏傳 {}".format(len(calls), N_CALL_SITES, len(bad)))


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

    # ---- 接線層：產品碼的呼叫點有沒有真的傳 s/e（P1-1） ----
    check_call_sites()

    # ---- 跑前端真碼 ----
    # ⚠️ **不落盤**：runner 走 `node -e`（當作命令列參數，約 2–3KB，遠低於
    #    Windows 命令列 32767 上限），18 萬條資料走 stdin。
    #    原本寫到 tempfile.gettempdir()，那樣有兩個毛病：
    #      (1) 某些機器上 tempfile 直接拋 `No usable temporary directory`
    #          ——**極容易被誤讀成「斷言發現問題」**，其實是環境；
    #      (2) 白白把 15MB JSON 寫一遍磁碟。
    #    不落盤之後這兩個都消失，也不需要任何清理。
    if len(RUNNER) > 30000:
        check("runner 沒超出命令列長度上限", False, "{} 字元".format(len(RUNNER)))
        return 1
    try:
        p = subprocess.run([NODE, "-e", RUNNER, APP_JS],
                           input=json.dumps(rows, ensure_ascii=False),
                           capture_output=True, text=True, encoding="utf-8")
    except OSError as ex:
        check("跑得動 node", False, "{}".format(ex))
        return 1

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
    # 路徑分佈（可對賬：獨立複算 A=182065 / B=63 / C=0）
    check("B 路徑（按碼位切）確實被走到過", r["pathB"] > 0,
          "A={} B={} C={}".format(r["pathA"], r["pathB"], r["pathC"]))
    check("C 路徑（indexOf 兜底）幾乎不走", r["pathC"] == 0,
          "{} 條落到兜底（s/e 與 text 不同源，要查數據）".format(r["pathC"]))
    # ⚠️ 三路徑互斥且覆蓋全部：這條守的是「上面那段路徑判據與 hitSpan 沒走偏」
    #    ——判據與实现不同步時，它會紅，而不是讓分佈數字悄悄騙人。
    check("A/B/C 三路徑互斥且覆蓋全部",
          r["pathA"] + r["pathB"] + r["pathC"] == r["n"],
          "{}+{}+{} vs {}".format(r["pathA"], r["pathB"], r["pathC"], r["n"]))

    ok = sum(1 for _, v in CHECKS if v)
    print("\n  {}/{} 通過".format(ok, len(CHECKS)))
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
