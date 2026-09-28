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
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)          # 让 `import db` 在直接运行时可用
import db                          # noqa: E402

APP_ROOT = os.path.dirname(HERE)
WEB_DIR = os.path.join(APP_ROOT, "web")

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


app = FastAPI(title="BOOKINDEX", version="0.1.0",
              description="古籍人物/地名索引 · 本地查询服务")


@app.on_event("startup")
def startup() -> None:
    """启动即校验，快速失败——别等用户点搜索才发现库没建。"""
    p = db.db_path()
    if not os.path.exists(p):
        raise RuntimeError(
            "索引库不存在：{}\n先跑：python app/tools/build_index_db.py".format(p))


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
        "relations": db.person_relations(pid),
    }


@app.get("/api/chapter/{cid}")
def api_chapter(cid: str, limit: int = Query(500)):
    limit = max(1, min(int(limit), MAX_LIMIT))
    data = db.chapter_sentences(cid, limit)
    if not data["chapter"]:
        raise HTTPException(404, "查无此篇：{}".format(cid))
    return data


@app.get("/api/person/{pid}/relations")
def api_relations(pid: str):
    """关系图 / family tree 的接口。

    现在数据为空，但**字段已定型**，将来灌数据不必改前后端契约。
    `evidence_uid` 为空的边，前端应画成虚线（docs/21 §12.4.1）。
    """
    return {"person": pid, "items": db.person_relations(pid)}


# 前端由同一个服务提供，故**同源、不需要 CORS**
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    print("BOOKINDEX 服务 → http://{}:{}/".format(HOST, PORT))
    print("索引库：{}".format(db.db_path()))
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
