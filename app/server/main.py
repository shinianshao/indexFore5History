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


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1, max_length=MAX_Q),
               limit: int = Query(30)):
    limit = _check(q, limit)
    return {"query": q, "items": db.search_persons(q, limit)}


@app.get("/api/fts")
def api_fts(q: str = Query(..., min_length=1, max_length=MAX_Q),
            limit: int = Query(50)):
    limit = _check(q, limit)
    return {"query": q, "items": db.full_text_search(q, limit)}


@app.get("/api/person/{pid}")
def api_person(pid: str, limit: int = Query(200)):
    profile = db.person_profile(pid)
    if not profile:
        raise HTTPException(404, "查无此人：{}".format(pid))
    limit = max(1, min(int(limit), MAX_LIMIT))
    return {
        "profile": profile,
        "mentions": db.person_mentions(pid, None, limit),
        # 直接给图（{nodes, edges}），与前端 renderGraph 的契约一致
        "relations": db.relations_graph(pid, 1, limit=MAX_LIMIT),
    }


@app.get("/api/chapter/{cid}")
def api_chapter(cid: str, limit: int = Query(500)):
    limit = max(1, min(int(limit), MAX_LIMIT))
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
