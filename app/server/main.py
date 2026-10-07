# -*- coding: utf-8 -*-
"""BOOKINDEX 本地查询服务（docs/21 P2）。

定位：**本地单人工具**，不是生产 Web 服务。所以刻意不做 JWT / 限流 / 多租户——
那套东西在这个场景里只会增加维护成本。留下的是真正有用的：
启动自检、输入校验、统一错误结构、健康检查。

启动
----
    python app/server/main.py
    # 或
    PORT=8800 BOOKINDEX_DB=.../index.db python app/server/main.py

然后打开 http://127.0.0.1:8800/

端点
----
    GET /health                      健康检查（含库是否存在）
    GET /api/stats                   规模与 tier 分布
    GET /api/search?q=劉邦           人名/称谓/别名检索（同名异人都会返回）
    GET /api/fts?q=鴻門              全文检索（任意词，不限人名）
    GET /api/person/{pid}            人物档案 + 命中（按篇分组）
    GET /api/chapter/{cid}           一篇的原文
    GET /api/person/{pid}/relations  **关系接口预留**，当前返回空数组

    POST /api/sentence/edit        {uid, action, at?}  记一条句级编辑（split/merge/dead）
    POST /api/sentence/revoke      {uid}               撤销该句的全部编辑
    GET  /api/overrides                                生效中的单条纠错（网页「标错」用）
    POST /api/override             {uid, s, e, surface, action, new?, pid?, note?}
    POST /api/override/revoke      {uid}               撤销该句的全部纠错
    POST /api/rebuild                                  后台重建（约 40 秒）
    GET  /api/rebuild/status                           查重建状态与日志尾部
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)          # 让 `import db` 在直接运行时可用
import db                          # noqa: E402

APP_ROOT = os.path.dirname(HERE)
WEB_DIR = os.path.join(APP_ROOT, "web")
PROJECT_ROOT = os.path.dirname(APP_ROOT)
# 单条纠错（overrides）是**人这一侧**的工具，与 db 同属 app/，
# 可以 import——它不碰 pipeline，也不破坏「两边只在 JSON 上交汇」。
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app", "tools"))
import overrides                   # noqa: E402

# 配置集中在这里，全部来自环境变量（本地工具没有密钥，故不引入 .env 机制）
PORT = int(os.environ.get("PORT", "8800"))
HOST = os.environ.get("HOST", "127.0.0.1")
MAX_Q = 64        # 查询串长度上限
MAX_LIMIT = 500   # 单次返回条数上限


def _check(q: str, limit: int) -> int:
    """入口校验：不信任任何客户端输入。"""
    if not q or not q.strip():
        raise HTTPException(400, "查询词不能为空")
    if len(q) > MAX_Q:
        raise HTTPException(400, "查询词过长（最多 {} 字）".format(MAX_Q))
    return max(1, min(int(limit), MAX_LIMIT))


def _book_param(book: str) -> str | None:
    """书号校验：空＝不筛，支持单书号或逗号分隔多书号（如 hs,hhs）。

    ⚠️ 不校验的话 `?book=zzz` 会返回 200 + 空列表——界面上就是「这人 0 處」，
    而实际上只是参数打错了（docs/34 P1 反复出现的同一类坏：静默 200）。
    """
    book = (book or "").strip()
    if not book:
        return None
    raw_codes = [b.strip() for b in book.split(",") if b.strip()]
    if not raw_codes:
        return None
    valid_codes = db.book_codes()
    unknown = [b for b in raw_codes if b not in valid_codes]
    if unknown:
        raise HTTPException(400, "未知書號：{}（可選 {}）".format(
            ", ".join(unknown), " / ".join(valid_codes)))
    ordered = [b for b in valid_codes if b in raw_codes]
    if len(ordered) == len(valid_codes):
        return None
    return ",".join(ordered)


def _era_param(era: str) -> int | None:
    """时代序校验：空＝不筛，否则必须是 0..len(ERA_NAMES)-1。"""
    era = (era or "").strip()
    if not era:
        return None
    try:
        i = int(era)
    except ValueError:
        raise HTTPException(400, "時代序必須是整數：{}".format(era))
    if not (0 <= i < len(db.ERA_NAMES)):
        raise HTTPException(400, "時代序超出範圍：{}（0..{}）".format(
            i, len(db.ERA_NAMES) - 1))
    return i


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动即校验，快速失败——别等用户点搜索才发现库没建。

    用 lifespan 而不是已废弃的 `@app.on_event("startup")`：
    后者在新版 FastAPI/Starlette 上会抛 DeprecationWarning，迟早被移除。
    """
    p = db.db_path()
    if not os.path.exists(p):
        raise RuntimeError(
            "索引库不存在：{}\n先跑：python app/tools/build_index_db.py".format(p))
    if overrides.WORKBOOK != overrides.DEFAULT_WORKBOOK:
        # 只有回归的沙盒服务才设它；设了又忘了，纠錯就写不到权威源里去了，
        # 而界面上**看不出任何异常**——所以要嚷出来。
        print("⚠️ BOOKINDEX_OVERRIDES 生效：纠错写入的是 {}".format(
            overrides.WORKBOOK))
    else:
        # ⚠️ 這一側更要喊。**不設**才是危險的那一侧：UI 測試點一次「寫入」就髒權威源，
        #   而界面上**不報任何異常**。我自己踩過（手起 8811 跑 UI 測試忘了設沙盒變量，
        #   overrides.xlsx 多出一行 dead 自檢行，還是逐行比對才發現的）。
        #   日常服務走這條沒問題；**跑 UI 測試請另設 BOOKINDEX_OVERRIDES**。
        print("· BOOKINDEX_OVERRIDES 未設：糾錯寫入權威源 {}".format(
            overrides.WORKBOOK))
        print("  （跑 UI 測試請另設沙盒，否則測試會髒權威源）")
    yield


app = FastAPI(title="BOOKINDEX", version="0.1.0",
              description="古籍人物/地名索引 · 本地查询服务",
              lifespan=lifespan)


@app.exception_handler(Exception)
async def on_error(request, exc):  # noqa: ANN001
    """统一错误结构。客户端只看到 message，**绝不回传堆栈**。"""
    if isinstance(exc, HTTPException):
        return JSONResponse({"message": exc.detail}, status_code=exc.status_code)
    return JSONResponse({"message": "服务器内部错误"}, status_code=500)


@app.get("/health")
def health():
    p = db.db_path()
    return {"status": "ok" if os.path.exists(p) else "no-db", "db": p}


@app.get("/api/stats")
def api_stats():
    return db.stats()


@app.get("/api/index")
def api_index(book: str = Query("", description="书号 sj/hs/hhs/sgz/js 或逗号分隔多书号，空=全部"),
              sort: str = Query("c", description="c=篇数（默认） 或 n=次数")):
    """一次性取回索引页三块（人物 / 地名 / 篇目）+ 快捷词。

    为什么要合成一个端点：四块都要按书作用域重算，分开请求会把同一份
    JOIN 聚合跑四遍（实测单跑一遍 0.6~1.2s）。合成一次前端只等一轮。

    ⚠️ 响应体在 db.index_payload 里拼（与离线导出共用），这里只做参数校验。
    """
    valid_book = _book_param(book) or ""
    return db.index_payload(valid_book, sort)


@app.get("/api/quick")
def api_quick(book: str = Query("", description="书号或多书号，空=全部"),
              np: int = Query(20, ge=1, le=50), nl: int = Query(10, ge=1, le=30)):
    """只取快捷词（换书时用，比 /api/index 轻）。"""
    valid_book = _book_param(book) or ""
    return db.quick_words(book=valid_book, np=np, nl=nl)


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1, max_length=MAX_Q),
               limit: int = Query(30),
               kind: str = Query("all", description="all=人物+地名 person=只要人 place=只要地")):
    """检索。**人物与地名一次返回**（`items` / `places` 两个数组）。

    为什么合成一个端点而不是加 `/api/search/place`
    ------------------------------------------------
    用户的动作只有一个：**输入一个词**。「長安」既是地名也可能是人名（人名里
    确实有「長安」），拆成两个端点就得让用户先选类别，而他已经用打字表达了
    意图。分开返回、前端分两段显示，比让他先选省事。

    ⚠️ 老的 `items`（人物）语义不变——离线版 `offSearch` 走的是自己那份实现，
    两边都返回 `{query, items, places}`，前端渲染代码完全一致。
    """
    limit = _check(q, limit)
    want_place = kind in ("all", "place")
    want_person = kind in ("all", "person")
    return {"query": q,
            "items": db.search_persons(q, limit) if want_person else [],
            "places": db.search_places(q, limit) if want_place else []}


@app.get("/api/place/{pid}")
def api_place(pid: str, limit: int = Query(200), book: str = Query(""),
              era: str = Query("")):
    """地名详情。响应体在 db 层拼（`db.place_payload`），与离线导出共用一份。

    以前**根本没有这个端点**：点地名条会落到 `search(name)` → 人物搜索 → 空
    （实测「長安」0 条，而 places 里长安有 1346 处）。地名索引那一千多条
    只能看不能进。
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    data = db.place_payload(pid, limit,
                            book=_book_param(book), era=_era_param(era))
    if not data:
        raise HTTPException(404, "查無此地：{}".format(pid))
    return data


@app.get("/api/fts")
def api_fts(q: str = Query(..., min_length=1, max_length=MAX_Q),
            limit: int = Query(50)):
    limit = _check(q, limit)
    return {"query": q, "items": db.full_text_search(q, limit)}


@app.get("/api/person/{pid}")
def api_person(pid: str, limit: int = Query(200), book: str = Query(""),
               era: str = Query("")):
    """人物档案 + 命中（按篇分组）。

    `book` / `era` 是**命中筛选**（docs/34 P0-3 的解法之一）：
    联机的 `mentions` 有 200 条上限，不筛就只能看到前 200 条，
    而界面上的「共 N 處」又是全量——两个数挨在一起自相矛盾。
    筛选让用户能钻进某一本书 / 某一个时代，把这 200 条花在他要看的地方。

    ⚠️ 筛选必须发生在**服务端**：客户端只拿到 200 条，本地再筛只是
    「从这 200 条里挑」，用户会以为「漢書只有 12 處」——那比不筛更骗人。
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    # 响应体同样在 db 层拼（db.person_payload），与离线导出共用一份
    data = db.person_payload(pid, limit,
                             book=_book_param(book), era=_era_param(era))
    if not data:
        raise HTTPException(404, "查无此人：{}".format(pid))
    return data


MAX_CHAPTER_LIMIT = 5000  # 全篇原文单次上限（最长篇 sj-014 有 3454 句）


@app.get("/api/chapter/{cid}")
def api_chapter(cid: str, limit: int = Query(5000)):
    limit = max(1, min(int(limit), MAX_CHAPTER_LIMIT))
    data = db.chapter_sentences(cid, limit)
    if not data["chapter"]:
        raise HTTPException(404, "查无此篇：{}".format(cid))
    return data


@app.get("/api/person/{pid}/relations")
def api_relations(pid: str,
                  degree: int = Query(1, ge=1, le=3, description="邻居度数"),
                  rel_type: str = Query("", description="kinship/political/social"),
                  book: str = Query("", description="按书过滤，如 hhs"),
                  min_conf: float = Query(0.0, ge=0.0, le=1.0,
                                          description="置信度下限"),
                  limit: int = Query(200)):
    """关系图 / family tree 的接口：返回 `{nodes, edges}`，前端直接喂给 renderGraph。

    四个密度旋钮（docs/21 §12.4.1）都在这里：度数 / 关系大类 / 按书 / 置信度下限。
    `evidence_uid` 为空或 `confidence` 低的边，前端画成虚线（docs/25 §四）。

    书号不在五书之内 → 400（docs/28 P1-3：以前 `book=zzz` 也被静默放行，
    返回的是「全都没过滤」的结果，看着像生效其实没有）。
    """
    try:
        g = db.relations_graph(pid, degree, rel_type, book, min_conf,
                               min(int(limit), MAX_LIMIT))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"person": pid, **g}


# ---------------------------------------------------------------- 句级编辑
#
# 为什么走子进程而不是 import pipeline：app/ 与 pipeline/ 刻意**不互相 import**
# （docs/23 §7.1，这是当初做对的一个决定）。两边只在 JSON 上交汇，
# 这里也就继续用「调脚本」的方式，代价只是一次进程启动。
EDITS = os.path.join(PROJECT_ROOT, "pipeline", "apply_sentence_edits.py")
OV_TOOL = os.path.join(APP_ROOT, "tools", "overrides.py")
ACTIONS = ("split", "merge", "dead")


def _run_edits(*args: str) -> str:
    """跑 apply_sentence_edits.py 的某个子命令，失败就把输出抛成 500。"""
    cmd = [sys.executable, EDITS] + list(args)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise HTTPException(500, "写入失败：{}".format(
            (p.stderr or p.stdout or "无输出").strip()[:200]))
    return (p.stdout or "").strip()


@app.post("/api/sentence/edit")
def api_sentence_edit(body: dict = Body(...)):
    """记一条句级编辑（split / merge / dead）。

    写的是 `workbook/sentence-edits.xlsx`——**那是人写的权威源**，
    这里只是「UI 代你写」。pipeline 侧依然只读它（红线 1）。
    """
    uid = str(body.get("uid") or "").strip()
    action = str(body.get("action") or "").strip()
    if not uid:
        raise HTTPException(400, "缺 uid")
    if action not in ACTIONS:
        raise HTTPException(400, "动作只能是 {} 之一".format(" / ".join(ACTIONS)))
    args = ["add", "--uid", uid, "--action", action]
    if action == "split":
        at = int(body.get("at") or 0)
        if at <= 0:
            raise HTTPException(400, "split 需要 at（在第几个字之后断开，1-based）")
        args += ["--at", str(at)]
    if body.get("note"):
        args += ["--note", str(body["note"])[:120]]
    _run_edits(*args)
    return {"ok": True, "uid": uid, "action": action,
            "message": "已记录，重建后生效"}


@app.post("/api/sentence/revoke")
def api_sentence_revoke(body: dict = Body(...)):
    """撤销某句的全部编辑（状态改 dead，不删行）。"""
    uid = str(body.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "缺 uid")
    _run_edits("revoke", "--uid", uid)
    return {"ok": True, "uid": uid, "message": "已撤销，重建后还原"}


# ---------------------------------------------------------------- 单条纠错（网页「标错」）
#
# 与句级编辑同套做法：**UI 代你写** `workbook/overrides.xlsx`，pipeline 侧依然只读
# （红线 1）。写不进去（Excel 开着）时 `overrides.py` 自己会改落 `.new.xlsx`，
# 不会把你的表冲掉。
OV_ACTIONS = ("reassign", "drop", "keep")


def _run_overrides(*args: str) -> str:
    cmd = [sys.executable, OV_TOOL] + list(args)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise HTTPException(500, "写入失败：{}".format(
            (p.stderr or p.stdout or "无输出").strip()[:200]))
    return (p.stdout or "").strip()


@app.get("/api/overrides")
def api_overrides(uid: str = Query("", description="只看某句的纠错")):
    """生效中的纠错列表——前端靠它给已标错的命中打「已標錯」徽章。

    给的是英文键（`overrides.active_rows()` 翻好的），不要把中文列名漏到前端：
    表头一改就要改两处，而且不报错。
    """
    items = overrides.active_rows()
    if uid:
        uid = uid.strip()
        items = [r for r in items if r["uid"] == uid]
    # pid/plid 翻成正名：界面上「已標錯 → 項羽」比「→ p_xiangyu」有用得多
    p_names = db.person_names([r["to"] for r in items] + [r["from"] for r in items])
    pl_names = db.place_names([r["to"] for r in items] + [r["from"] for r in items])
    # ⚠️ 一定要带上「是否已生效」：表里的行永远 active，重建完也不会消失。
    #    不算的话顶栏的 N 永不归零，会一直骗你「重建后生效」。
    for r, applied in zip(items, db.override_states(items)):
        r["toName"] = pl_names.get(r["to"]) or p_names.get(r["to"], "")
        r["fromName"] = pl_names.get(r["from"]) or p_names.get(r["from"], "")
        r["applied"] = applied
    pending = sum(1 for r in items if not r["applied"])
    return {"items": items, "count": len(items), "pending": pending}


@app.post("/api/override")
def api_override(body: dict = Body(...)):
    """标一条错：`reassign`（改归给别人）或 `drop`（这处不算他）。

    ⚠️ nth **由后端算**（`db.mention_nth`）：前端给的 (s, e, surface) 定位一处命中，
    nth 是「本句第几个命中」。前端自己算必然算错——它只看到这一个人的序号。
    """
    uid = str(body.get("uid") or "").strip()
    surface = str(body.get("surface") or "").strip()
    action = str(body.get("action") or "").strip()
    if not uid or not surface:
        raise HTTPException(400, "缺 uid 或 surface")
    if action not in OV_ACTIONS:
        raise HTTPException(400, "动作只能是 {} 之一".format(" / ".join(OV_ACTIONS)))
    try:
        s = int(body.get("s"))
        e = int(body.get("e"))
    except (TypeError, ValueError):
        raise HTTPException(400, "s / e 必须是整数偏移")
    pid = str(body.get("pid") or "").strip()
    nth = db.mention_nth(uid, s, e, surface, pid)
    if not nth:
        raise HTTPException(404, "这句里已经没有「{}」这条命中了（可能已被编辑过）"
                                 .format(surface))
    new_pid = str(body.get("new") or "").strip()
    if action == "reassign" and not new_pid:
        raise HTTPException(400, "reassign 要给 new（人名或 pid）")
    args = ["add", "--uid", uid, "--nth", str(nth), "--action", action]
    if pid:
        args += ["--pid", pid]
    if action == "reassign":
        args += ["--new", new_pid]
    if body.get("note"):
        args += ["--note", str(body["note"])[:120]]
    out = _run_overrides(*args)
    # ⚠️ `overrides.py` 在 Excel 占着表时会改写 `.new.xlsx` 并**照样返回 0**。
    #    不把这句警告透出去，界面就回「已记录」——其实那行还没进你的权威源。
    warn = ""
    if "⚠️" in out:
        warn = out.split("⚠️", 1)[1].strip().splitlines()[0][:160]
    return {"ok": True, "uid": uid, "nth": nth, "action": action,
            "warning": warn,
            "message": "已记录（本句第 {} 条命中），重建后生效".format(nth)}


@app.post("/api/override/revoke")
def api_override_revoke(body: dict = Body(...)):
    """撤销某句的全部纠错（状态改 dead，不删行）。"""
    uid = str(body.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "缺 uid")
    _run_overrides("revoke", "--uid", uid)
    return {"ok": True, "uid": uid, "message": "已撤销，重建后还原"}


# ---------------------------------------------------------------- 重建
#
# 重建要 40 秒左右，不能挂在请求里等（会把交互卡死）。丢到后台线程跑，
# 前端轮询状态。本地单人工具，一个全局状态就够，不需要任务队列。
_rebuild = {"running": False, "ok": None, "log": []}


def _rebuild_worker() -> None:
    _rebuild["log"] = []
    _rebuild["ok"] = None
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.Popen(
            [sys.executable, os.path.join(PROJECT_ROOT, "app", "tools",
                                          "rebuild.py")],
            cwd=PROJECT_ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        for line in p.stdout:
            _rebuild["log"].append(line.rstrip())
            if len(_rebuild["log"]) > 400:
                _rebuild["log"] = _rebuild["log"][-200:]
        p.wait()
        _rebuild["ok"] = (p.returncode == 0)
    except Exception as e:                       # noqa: BLE001
        _rebuild["log"].append("重建异常：{}".format(e))
        _rebuild["ok"] = False
    finally:
        _rebuild["running"] = False


@app.post("/api/rebuild")
def api_rebuild():
    if _rebuild["running"]:
        return {"started": False, "message": "上一次重建还在跑"}
    _rebuild["running"] = True
    threading.Thread(target=_rebuild_worker, daemon=True).start()
    return {"started": True, "message": "已开始重建（约 40 秒）"}


@app.get("/api/rebuild/status")
def api_rebuild_status():
    tail = _rebuild["log"][-12:]
    return {"running": _rebuild["running"], "ok": _rebuild["ok"], "log": tail}


# 前端由同一个服务提供，故**同源、不需要 CORS**
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    print("BOOKINDEX 服务 → http://{}:{}/".format(HOST, PORT))
    print("索引库：{}".format(db.db_path()))
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
