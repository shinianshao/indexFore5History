# 历史纯静态前端归档说明（Phase 2 Legacy）

> **⚠️ 状态：已冻结（FROZEN / READ-ONLY）**  
> 归档日期：2026-10-04  
> 责任说明：本目录是项目第二阶段（2026-09）的纯静态单页网页实现，依赖加载 30MB+ 的 `*-data.js` 单体大包。

---

## 目录现状与开发指南

1. **生产日常开发请勿修改本目录**：
   - 联机主力前端位于 **`app/web/`**（FastAPI 后端驱动，支持动态按需查询、SQLite FTS5 全文搜索、多证据关系图谱与网页标错入口）；
   - 离线单页分发位于 **`dist/`**（通过 `app/tools/export_static.py` 生成的优化轻量快照，与联机版共用同一套 `app.js` 逻辑）。

2. **保留本目录的原因**：
   - 自动化回归测试（如 `pipeline/_ui_csscheck.js` 及 `--full` 模式下的静态版 UI 对齐脚本）依赖本目录启动参照服务；
   - 作为新版重构的基准参照物，不完全物理删除以避免破坏基线回归。

3. **若需开发新功能**：
   - 修改前端代码：请编辑 [`app/web/app.js`](../app/web/app.js) 或 [`app/web/index.html`](../app/web/index.html)；
   - 修改后同步离线快照：执行 `python app/tools/export_static.py`（会自动同步复制 `app.js` 到 `dist/` 并更新快照数据）。
