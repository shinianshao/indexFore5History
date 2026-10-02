# -*- coding: utf-8 -*-
"""導出「離線靜態快照」dist/ —— 雙擊 index.html 就能用，也能整個文件夾發給別人。

為什麼要有它（docs/29 §六-6）
----------------------------
app/web/ 那套前端要靠 FastAPI 才有 /api/*，換台機器就得先裝依賴、再起服務；
而**索引本體是不常變的只讀數據**——為「翻一翻」跑一個服務不划算。
所以把 index.db 導成一份靜態快照：

    dist/index.html   與 app/web/index.html 同一份，只多引一個 data.js
    dist/app.js       **原樣拷貝**，不複製一套前端
    dist/data.js      window.BOOKINDEX_DATA = …（全量數據）

前端只認「有沒有 window.BOOKINDEX_DATA」：有＝離線讀快照，沒有＝聯機打 /api/*。
**業務規則仍然只有服務端一份**（計數口徑、排序、關係圖 BFS、證據狀態、置信度衰減），
離線層做的是「緊湊數組 → 前端要的物件形狀」的**機械還原**，不含任何規則——
這是刻意劃的線：一旦離線層開始自己算，就又多了一個會漂移的真相源。

與聯機版的兩處**刻意**差異（都在文檔裡寫死，不是漏的）
----------------------------------------------------
1. 聯機 `/api/person/{pid}` 的 mentions 上限 200、`/api/chapter/{cid}` 上限 500；
   離線快照**給全部**。UI 上「劉邦 2064 處」這種大人物，聯機要看更多得翻頁（沒做），
   離線一次給全——只多不少，不算不一致。
2. 句子表不導出 `para_seq / seq / pos_key`：順序已經烤進陣列下標裡，前端只按順序顯示。
   三個字段 × 9.6 萬句 ≈ 2MB，省下來是白賺。

用法
----
    python app/tools/export_static.py            導出到 dist/
    python app/tools/export_static.py --out DIR  換個目錄
    python app/tools/export_static.py --check    只比對 dist/ 與庫是否同步（不重寫）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
# ⚠️ app/ 與 pipeline/ 不互相 import（紅線），但 app/server/db.py 是**自家**的倉儲層：
# 導出必須跟聯機查庫走同一套規則，所以直接復用它，而不是把 SQL 再抄一遍。
sys.path.insert(0, os.path.join(HERE, "..", "server"))
import db  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

WEB_DIR = os.path.join(ROOT, "app", "web")
DEFAULT_OUT = os.path.join(ROOT, "dist")

# 書作用域：「」= 全五書 + 五個單書。索引頁的計數是按書算的，沒法從全量推出來
# （地名索引的 items 不帶分書明細），所以老實導六份。
SCOPES = ["", "sj", "hs", "hhs", "sgz", "js"]
# 關係圖的兩個旋鈕：度數 1/2/3 × 只看有證據（min_conf 0.5）。
# 只給**有邊的人**導——沒邊的人聯機返回的也是 {nodes:[{id,degree:0}],edges:[]}，
# 前端自己就能造，不必在快照裡佔 2240 個位置。
REL_DEGREES = (1, 2, 3)
REL_CONFS = (0.0, 0.5)


# ---------------------------------------------------------------- 取數

def _sentences() -> list:
    """全庫句子，按（篇, 段, 句）排好序，存 [uid, 篇號, 正文, 段號]。

    ⚠️ 段號（para_seq）是 2026-10-02 為「原文層跳段」加的第 4 位。
    為什麼要存而不是讓前端推：段界不等於句界（一句可跨段、一段可多句），
    前端拿不到段信息就只能靠猜——而**離線版沒有 db 可查**，猜不出來。
    體積代價：96,336 個小整數，JSON 裡約 0.3MB，可忽略。
    """
    rows = []
    with db.connect() as c:
        for uid, cid, text, para in c.execute(
                "SELECT uid, chapter_id, text, para_seq FROM sentences "
                "ORDER BY chapter_id, para_seq, seq"):
            rows.append([uid, cid, text or "", para])
    return rows


def _chapters(sents: list) -> dict:
    """篇 → [全名, 書號, 起始下標, 結束下標)（sents 裡同一篇是連續區間）。"""
    spans = {}
    for i, (_uid, cid, _t, _para) in enumerate(sents):
        a, b = spans.get(cid, (i, i + 1))
        spans[cid] = (a if a < i else i, b if b > i + 1 else i + 1)
    out = {}
    with db.connect() as c:
        for cid, ft, bid in c.execute(
                "SELECT id, full_title, book_id FROM chapters"):
            a, b = spans.get(cid, (0, 0))
            out[cid] = [ft or "", bid or "", a, b]
    return out


def _persons() -> dict:
    """人 → [繁名, 簡名, 朝代, 頭銜, 簡介, [別名…]]。"""
    als: dict = {}
    out = {}
    with db.connect() as c:
        for pid, al in c.execute("SELECT person_id, alias FROM aliases"):
            als.setdefault(pid, []).append(al)
        sql = ("SELECT id, trad_name, name, dynasty, title, summary "
               "FROM persons WHERE status='active'")
        for r in c.execute(sql):
            out[r["id"]] = [r["trad_name"] or "", r["name"] or "",
                            r["dynasty"] or "", r["title"] or "",
                            r["summary"] or "", als.get(r["id"], [])]
    return out


def _mentions(uid2i: dict) -> dict:
    """人 → [[句下標, 表面詞, s, e, tier], …]（句正文不重複存，按下標查 sents）。"""
    out: dict = {}
    with db.connect() as c:
        sql = ("SELECT m.person_id, s.uid, m.surface, m.s, m.e, m.tier "
               "FROM mentions m JOIN sentences s ON s.uid = m.sentence_uid "
               "ORDER BY m.person_id, s.chapter_id, s.para_seq, s.seq")
        for pid, uid, surf, s, e, tier in c.execute(sql):
            i = uid2i.get(uid)
            if i is None:          # 句被棄用後從 sentences 裡消失，命中就懸空了
                continue
            out.setdefault(pid, []).append(
                [i, surf or "", s or 0, e or 0, tier or ""])
    return out


def _places() -> dict:
    """地 → [繁名, 簡名, 類型, 類型說明, 時代, 簡介]。"""
    out = {}
    with db.connect() as c:
        for r in c.execute(
                "SELECT id, trad_name, name, kind, era, summary FROM places"):
            k = r["kind"] or "外"
            out[r["id"]] = [r["trad_name"] or "", r["name"] or "", k,
                            db.PLACE_KIND_LABEL.get(k, k),
                            r["era"] or "", r["summary"] or ""]
    return out


def _pbook() -> dict:
    """檢索用的分書分佈：人 → [總次數, [[書號, 書名, 次數], …]]（Top 3）。

    同名異人消歧靠的就是「這人主要見於哪幾本書」，聯機版在 search_persons 裡現算，
    離線版必須帶著，不然同名那幾位又分不出來了。
    """
    with db.connect() as c:
        bname = {r[0]: r[1] for r in c.execute("SELECT code, name FROM books")}
        dist: dict = {}
        for pid, bid, n in c.execute(
                "SELECT m.person_id, c.book_id, COUNT(*) FROM mentions m "
                "JOIN sentences s ON s.uid = m.sentence_uid "
                "JOIN chapters c ON c.id = s.chapter_id "
                "GROUP BY m.person_id, c.book_id"):
            dist.setdefault(pid, []).append((bid, n))
        out = {}
        for pid, lst in dist.items():
            top = sorted(lst, key=lambda x: -x[1])[:3]
            out[pid] = [sum(n for _, n in lst),
                        [[b, bname.get(b, b), n] for b, n in top]]
        return out


def _relations() -> dict:
    """有關係的人 → {"度數:min_conf": {nodes, edges}}（圖直接由 db 層算，不重寫 BFS）。"""
    pids = set()
    with db.connect() as c:
        for a, b in c.execute(
                "SELECT person_a, person_b FROM relations WHERE status='active'"):
            pids.add(a)
            pids.add(b)
    out = {}
    for pid in sorted(pids):
        m = {}
        for dg in REL_DEGREES:
            for cf in REL_CONFS:
                g = db.relations_graph(pid, dg, "", "", cf, 200)
                if g.get("edges"):
                    # ⚠️ key 的數字格式要跟前端拼的一字不差：JS 那邊是 "1" + ":" + "0"，
                    # 這裡若用 "{}".format(0.0) 會寫成 "1:0.0"——對不上，關係卡全空，
                    # 而且不報錯（查不到就當沒關係），是最難發現的那種壞法。
                    m["{}:{}".format(dg, "%g" % cf)] = g
        out[pid] = m
    return out


def build() -> dict:
    """取數並組裝。26 秒裡大部分花在關係圖上，所以逐步記時——
    想知道該優化哪一步，看一眼就知道，不用再插打印。"""
    t0 = time.time()
    took: list = []

    def step(name, fn, *a):
        s = time.time()
        r = fn(*a)
        took.append((name, round(time.time() - s, 1)))
        return r

    if not os.path.exists(db.db_path()):
        raise SystemExit(
            "索引庫不存在：{}\n先跑：python app/tools/rebuild.py".format(db.db_path()))

    sents = step("句子", _sentences)
    uid2i = {u: i for i, (u, _c, _t, _para) in enumerate(sents)}
    chaps = step("篇目", _chapters, sents)
    pers = step("人物", _persons)
    pm = step("命中", _mentions, uid2i)
    pla = step("地名", _places)
    pbook = step("分書分佈", _pbook)
    rel = step("關係圖", _relations)
    # ⚠️ 六份索引共用一次按書計數（db.all_counts），再按書收窄——
    # 各查一遍要 23s，共用只要 4s，結果完全一致（db._narrow 的注釋裡有推導）。
    with db.connect() as c:
        counts = step("按書計數", db.all_counts, c)
    idx = step("索引六份", lambda: {b: db.index_payload(b, "c", counts) for b in SCOPES})
    stats = step("規模", db.stats)
    n_rel = step("關係條數", lambda: db.connect().execute(
        "SELECT COUNT(*) FROM relations WHERE status='active'").fetchone()[0])

    with db.connect() as c:
        books = [[r[0], r[1]] for r in c.execute(
            "SELECT code, name FROM books ORDER BY code")]

    data = {
        "v": 1,
        "gen": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "sentences": len(sents), "chapters": len(chaps),
            "persons": len(pers), "places": len(pla),
            "mentions": sum(len(v) for v in pm.values()),
            # ⚠️ 關係條數 ≠ 有關係的人數：rel 是按「有邊的人」建的索引（152 個 key），
            # 邊本身只有 99 條。計數要對得上庫，不然 --check 會天天報過期。
            "relations": n_rel,
            "aliases": sum(len(p[5]) for p in pers.values()),
        },
        "stats": stats,
        "books": books,
        "sents": sents,
        "chaps": chaps,
        "pers": pers,
        "pm": pm,
        "pla": pla,
        "pbook": pbook,
        "idx": idx,
        "rel": rel,
    }
    data["_sec"] = round(time.time() - t0, 1)
    data["_steps"] = took
    return data


# ---------------------------------------------------------------- 落盤

# 这几个键是大块，先写成**字符串**再由 JSON.parse 还原（见 dump_js 里的原因）
BIG = ("sents", "chaps", "pers", "pm", "pla", "pbook", "idx", "rel")


def dump_js(data: dict) -> str:
    """data.js 的內容。

    ⚠️ 大块数据写成 `JSON.parse('…')` 而不是直接写成对象字面量——这不是风格问题：
    15MB 的**字面量**会让 V8 在解析时把整棵 AST 撑起来，实测 jsdom 里直接
    `JavaScript heap out of memory`（4GB 打满）。字符串字面量没有 AST 展开，
    解析完源串即可回收，峰值内存差一个数量级。

    ⚠️ 另外三个 JSON-in-HTML 的老坑：
      1. 正文里出现 `</script>` 会提前关掉标签 → 把 `</` 转义成 `<\\/`（JS 字符串里合法）。
      2. 行分隔符 U+2028/2029 在 JS 字符串里非法（JSON 合法）→ 一并转义。
      3. 嵌在单引号里，要先转义反斜杠再转义单引号（顺序反了会把 JSON 自己的转义弄坏）。
    """
    parts = []
    for k, v in data.items():
        if k.startswith("_"):
            continue
        s = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        if k in BIG:
            s = (s.replace("</", "<\\/")
                  .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
                  .replace("\\", "\\\\").replace("'", "\\'"))
            parts.append("{}:JSON.parse('{}')".format(json.dumps(k), s))
        else:
            parts.append("{}:{}".format(json.dumps(k), s))
    return ("/* 離線快照數據 —— **自動生成，勿手改**（app/tools/export_static.py）\n"
            " * 生成時間：%s\n"
            " * 句子 %s / 篇 %s / 人 %s / 地 %s / 命中 %s / 關係 %s\n"
            " *\n"
            " * 緊湊格式（省體積，由 app/web/app.js 的離線層還原成前端要的形狀）：\n"
            " *   sents[i] = [uid, 篇號, 正文, 段號]  —— 全庫句子只存一份，按下標引用\n"
            " *   chaps[cid] = [全名, 書號, 起始, 結束)\n"
            " *   pers[pid]  = [繁名, 簡名, 朝代, 頭銜, 簡介, [別名…]]\n"
            " *   pm[pid]    = [[句下標, 表面詞, s, e, tier], …]\n"
            " *   pla[pid]   = [繁名, 簡名, 類型, 類型說明, 時代, 簡介]\n"
            " *   pbook[pid] = [總次數, [[書號, 書名, 次數], …]]\n"
            " *   idx[書號]  = /api/index 的原樣響應（書號 \"\" = 全五書）\n"
            " *   rel[pid]   = {\"度數:min_conf\": {nodes, edges}}\n"
            " *\n"
            " * 大塊是 JSON.parse('…') 而不是字面量：見 export_static.py 裡的解釋。\n"
            " */\n"
            "window.BOOKINDEX_DATA={%s};\n") % (
        data["gen"],
        data["counts"]["sentences"], data["counts"]["chapters"],
        data["counts"]["persons"], data["counts"]["places"],
        data["counts"]["mentions"], data["counts"]["relations"],
        ",\n".join(parts))


def write_atomic(path: str, text: str) -> None:
    """原子寫：先寫 .tmp 再 os.replace。

    ⚠️ 這是 8MB+ 的大檔，寫到一半被中斷就留一個半截 JSON——上一輪正是這麼
    把 book-data.json 弄壞的（語料重跑了 40 秒才發現）。原子寫是剛需。
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def write_html(out_dir: str) -> str:
    """把 app/web/index.html 拷到 dist/，並在 app.js **之前**插上 data.js。

    順序不能反：app.js 一上來就要讀 window.BOOKINDEX_DATA。
    """
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    tag = '<script src="app.js"></script>'
    if tag not in html:
        raise SystemExit("app/web/index.html 裡找不到 {!r}——換了寫法這裡要跟著改".format(tag))
    html = html.replace(tag, '<script src="data.js"></script>\n' + tag)
    p = os.path.join(out_dir, "index.html")
    write_atomic(p, html)
    return p


def report(data: dict, out_dir: str) -> None:
    print("離線快照 → {}".format(out_dir))
    print("  生成 {}（取數 {}s：{}）".format(
        data["gen"], data.pop("_sec", "?"),
        " ".join("{}{}s".format(k, v) for k, v in data.pop("_steps", []))))
    for k in ("sentences", "chapters", "persons", "places", "mentions", "relations"):
        print("  {:<10} {:>7,}".format(k, data["counts"][k]))
    print("  ── 體積 ──")
    # ⚠️ 按**字節**算，不是字符數：中文一個字 1 字符但 3 字節，
    # 用 len(str) 會把體積低估到三分之一，看著像「還能再塞點」。
    for k in ("sents", "idx", "pm", "pers", "pla", "rel", "chaps", "pbook", "stats"):
        n = len(json.dumps(data.get(k), ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8"))
        print("  {:<8} {:>6.1f} MB".format(k, n / 1048576.0))
    total = os.path.getsize(os.path.join(out_dir, "data.js"))
    print("  data.js  {:.1f} MB".format(total / 1048576.0))


# ---------------------------------------------------------------- 比對

def verify() -> int:
    """「按書收窄」與「按書各查一遍」是否等價。

    這是導出提速（23s → 4s）換來的**新風險**：`db._narrow` 是手上推導出來的等價式，
    哪天 `list_persons / list_places` 的聚合口徑變了（比如開始按 tier 過濾），
    收窄就會悄悄不等價，而導出不會報錯——只會產出一份跟聯機版對不上的快照。
    所以要有一條斷言專門盯著它。慢（約 23s），只在 --full 裡跑。
    """
    bad = 0
    for b in SCOPES:
        slow = db.index_payload(b, "c")
        with db.connect() as c:
            fast = db.index_payload(b, "c", db.all_counts(c))
        for block in ("persons", "places"):
            a = {(x["id"], x["n"], x["c"]) for x in slow[block]["items"]}
            bx = {(x["id"], x["n"], x["c"]) for x in fast[block]["items"]}
            if a != bx:
                print("× {} 的 {} 不等價：慢 {} 條 / 快 {} 條（差 {}）".format(
                    b or "全五書", block, len(a), len(bx), len(a ^ bx)))
                bad += 1
    if bad:
        print("× 收窄不等價：db._narrow 的假設破了，導出不能再走快路徑")
        return 1
    print("✓ 六個書作用域 × 人物/地名：收窄與重查完全等價")

    # ---- sents 的數據形狀契約 ----
    # 2026-10-02 加段號（[uid, 篇號, 正文, para_seq]）時踩過：改了形狀，
    # export 裡有**三處** enumerate(sents) 要跟著改，漏了兩處 →
    # ValueError 在導出中途炸，dist/ 留著上一次的舊檔（還能打開，更難發現）。
    # 這條斷言專盯「形狀」：只要有人再往 sents 裡加/減位，前端就會拿到
    # undefined 的段號，跳段功能**靜默失效**（不報錯，只是跳不動）。
    sents = _sentences()
    widths = {len(r) for r in sents}
    if widths != {4}:
        print("× sents 的形狀不對：應為 4 位 [uid, 篇號, 正文, 段號]，"
              "實得寬度 {}".format(sorted(widths)))
        return 1
    with db.connect() as c:
        db_max = c.execute(
            "SELECT MAX(para_seq), COUNT(*) FROM sentences").fetchone()
    n_para = sum(1 for r in sents if r[3] is not None)
    if db_max[0] and n_para != db_max[1]:
        print("× 有句缺段號：{} / {}（前端跳段會對不上位置）".format(
            n_para, db_max[1]))
        return 1
    # 段號必須**在每篇內單調遞增**（前端按 sents 順序渲染，靠它算段界）
    last: dict = {}
    for _u, cid, _t, para in sents:
        if para is None:
            continue
        if cid in last and para < last[cid]:
            print("× 段號在篇 {} 內倒退：{} < {}".format(cid, para, last[cid]))
            return 1
        last[cid] = para
    print("✓ sents 形狀 4 位、段號齊全、篇內單調遞增（{} 句）".format(len(sents)))
    return 0


def check(out_dir: str) -> int:
    """dist/ 與當前庫是否同步：比 counts（不含生成時間）。

    ⚠️ 只比 counts 不比全文——全文比對要重新導一遍（十幾秒），而「快照過期」
    這種事用規模就能抓到 99%。
    """
    p = os.path.join(out_dir, "data.js")
    if not os.path.exists(p):
        print("× 還沒有 {}".format(p))
        return 1
    with open(p, encoding="utf-8") as fh:
        txt = fh.read()
    # ⚠️ 只摳 counts 這一小段，不要 json.loads 整份：大塊是 JSON.parse('…')，
    # 整份根本不是合法 JSON。而且整份讀進來解析一遍要好幾秒，沒必要。
    m = re.search(r'"counts":\{([^}]*)\}', txt)
    if not m:
        print("× {} 裡找不到 counts".format(p))
        return 1
    old = {k: int(v) for k, v in re.findall(r'"(\w+)":(\d+)', m.group(1))}
    with db.connect() as c:
        new = {
            "sentences": c.execute("SELECT COUNT(*) FROM sentences").fetchone()[0],
            "chapters": c.execute("SELECT COUNT(*) FROM chapters").fetchone()[0],
            "persons": c.execute(
                "SELECT COUNT(*) FROM persons WHERE status='active'").fetchone()[0],
            "places": c.execute("SELECT COUNT(*) FROM places").fetchone()[0],
            "mentions": c.execute("SELECT COUNT(*) FROM mentions").fetchone()[0],
            "relations": c.execute(
                "SELECT COUNT(*) FROM relations WHERE status='active'").fetchone()[0],
            "aliases": c.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
        }
    # 命中數口徑：導出時會丟掉「句已被棄用」的懸空命中，所以只可能 ≤ 庫裡的數
    bad = [k for k in new if k not in ("mentions", "relations") and old.get(k) != new[k]]
    if old.get("mentions", 0) > new["mentions"]:
        bad.append("mentions")
    if old.get("relations", 0) > new["relations"]:
        bad.append("relations")
    if bad:
        print("× 快照過期：{}".format(
            ", ".join("{} {}→{}".format(k, old.get(k), new[k]) for k in bad)))
        print("  重導：python app/tools/export_static.py")
        return 1
    print("✓ 快照與庫同步（{} 句 / {} 命中）".format(
        new["sentences"], old.get("mentions")))
    return 0


# ---------------------------------------------------------------- 入口

def main() -> int:
    ap = argparse.ArgumentParser(description="導出離線靜態快照 dist/")
    ap.add_argument("--out", default=DEFAULT_OUT, help="輸出目錄（默認 dist/）")
    ap.add_argument("--check", action="store_true", help="只比對 dist/ 是否過期")
    ap.add_argument("--verify", action="store_true", help="斷言收窄等價（慢，約 23s）")
    ap.add_argument("--no-html", action="store_true", help="只產 data.js")
    a = ap.parse_args()

    if a.check:
        return check(a.out)
    if a.verify:
        return verify()

    data = build()
    os.makedirs(a.out, exist_ok=True)
    write_atomic(os.path.join(a.out, "data.js"), dump_js(data))
    if not a.no_html:
        write_html(a.out)
        with open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8") as fh:
            write_atomic(os.path.join(a.out, "app.js"), fh.read())
    report(data, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
