# 新开发入口（本地索引 + 可编辑数据库）

> **这是新开发的唯一入口。** 完整背景与决策推演见 `docs/21`、
> 本次对话的回顾分析见 `docs/22`。日常施工只看本文件就够。

## 一、定位

`web/` 是**静态版，保留不动**（仍按原流程产出，用于分享）。
`app/` 是**新版**：本地服务 + SQLite + Excel 权威源，用于日常查询与编辑。

一句话架构：**规则进代码，数据进表格；表格归你写，管道只读它。**

```
workbook/*.xlsx   ← 权威源，只有人写
   ↓ sync
SQLite index.db   ← 派生，随时可删重建
   ↓ annotate 重跑（秒级，全量重跑不心疼）
app/web           ← 查询与编辑界面（FastAPI）
```

## 二、三条红线（动手前先背）

1. **单向数据流**：Excel 只能由人写，管道**永不回写**。
   凡 pipeline 想写 Excel 的地方，一律改成「写新版本 + 报差异」。
   否则重建会把你的审定结果冲掉。
2. **句子主键必须是稳定 `uid`**：现有 `sj-001-0002-001` 是位置键，
   一改切分就位移，会连带打垮全部命中外键与你手写的纠错记录。
   拆分→前半继承原 uid；合并→留第一个标 `merged`；删除→标 `dead` 不物理删。
3. **规则与数据分离**：`GENERIC_MANUAL` / `GENERIC_CONTEXT_RULES` /
   `SCOPED_ALIASES` / `BOOK_CANDIDATES` / `PERSON_BOOKS_*` / `OFFICE_WORDS`
   继续是**代码**；人名/别名/地名/篇名/句子搬进**表格**。

## 三、已确认的设计决策

| 议题 | 结论 |
|---|---|
| 编辑深度 | 封顶在「拆/并/删句」；**不改原文**，只留「整句弃用 `dead`」口 |
| Excel 组织 | 人名/地名各一个工作簿 + 拼音列 + **布尔列 `in_sj…in_js` 筛书**（不拆表）；句子按书/卷拆 sheet |
| 网页 | **FastAPI 做日常 + 静态版做分享**，双轨并存 |
| 视觉 | **克制的古典**：宣纸 `#F7F4EC` / 墨 `#2B2A27` / **朱砂 `#9E3D32`**；正文 serif、控件 sans；不做竖排/印章/汉字数字 |
| 命中置信度 | **必须可见**：core 实线朱砂，guess **虚线**+「？」 |
| 关系范围 | 血缘 + 政治 + 社会三类全开（枚举见 docs/21 §12.2.1） |
| 证据句 | 可有可无；无证据的 confidence 压上限，图上用虚线浅色 |
| 朝代 | 可跨朝代，用「度数 / 关系类型 / 朝代 / 书」四个旋钮控密度 |
| 图控件 | **ECharts**；接口固定 `renderGraph(adjacency, options)` |

## 四、施工顺序（每段结束都能用）

| 阶段 | 交付 | 状态 |
|---|---|---|
| **P0** | PERSONS 抽到 xlsx + `build_dict.py` 只留规则 | ✅ **已完成** |
| **P1** | 稳定 `uid` 落地、SQLite 索引库、**`relations` 表先建后填** | ✅ **已完成** |
| **P2** | FastAPI + 全文检索 + 原文对照界面 | ✅ **已完成** |
| P3 | 编辑 → 重建 → 快照 diff（新增/消失/改归三类） | 未开始 |
| P4 | 句级拆分/合并/弃用 UI | 未开始 |
| P5 | `verify.py` 断言接入新链路 | 未开始 |

### P2 已交付什么

**启动**：

```bash
python app/server/main.py          # → http://127.0.0.1:8800/
PORT=8800 BOOKINDEX_DB=... python app/server/main.py
```

| 文件 | 职责 |
|---|---|
| `app/server/db.py` | 仓储层：只查 SQLite，返回 dict/list，**不 import fastapi**（可脱离 Web 单测） |
| `app/server/main.py` | 路由：参数校验 + 响应封装；启动自检（库不存在即快速失败）；统一错误结构 |
| `app/web/index.html` | 视觉：克制的古典（宣纸 `#F7F4EC` / 墨 `#2B2A27` / 朱砂 `#9E3D32`） |
| `app/web/app.js` | 交互：检索 / 详情 / 原文层 / hash 回退 / `renderGraph()` 预留 |

端点：

```
GET /health                      健康检查（含库是否存在）
GET /api/stats                   规模与 tier 分布
GET /api/search?q=劉邦           人名/称谓/别名检索（同名异人都会返回）
GET /api/fts?q=鴻門              全文检索（任意词，不限人名）
GET /api/person/{pid}            人物档案 + 命中（按篇分组）
GET /api/chapter/{cid}           一篇的原文
GET /api/person/{pid}/relations  **关系接口预留**，当前返回空数组
```

已实现的两个设计要点（§12.3）：

- **命中置信度可见**：`core` 朱砂实线，其余 tier 虚线 + 「？篇主 / ？推斷」标注。
  guess 那批推断命中现在一眼能认出来，不会误当成确定命中
  （当前多少处：`python app/tools/query.py --stats` 的 tier 分布里看）。
- **回退**：hash 路由 + 页头返回按钮（原文层开着时先关它）。

没做的（刻意）：JWT / 限流 / 多租户——本地单人工具，加了只增维护成本。
前端由同一服务提供，**同源，故不需要 CORS**。

### P1 已交付什么

- **`data/index/index.db`**（产物，可删重建）：八张表 + FTS5 全文索引。
  `sentences` / `mentions` / `persons` / `aliases` / `places` / `chapters` / `books`
  / **`relations`（预留，先空着）**。
- **命中明细独立成表**：原本埋在 `sentence.marks` 的嵌套数组里没法查，
  现在能直接筛「所有 `tier=guess` 的命中」——这正是「方便查找确认」的入口。
- **稳定 `uid` 落地**：`sentences.uid`，且**优先复用库里已有的**（重跑不漂移）。
  ⚠️ 已知限制见 `build_index_db.py` 的 `make_uid()` 注释：目前按 (篇, 段序, 句序)
  匹配，等 P4 真正支持编辑句子时，这里要改成按文本内容匹配。
- **查询工具 `app/tools/query.py`**：不用再写一次性 `_probe_*` 脚本了。

> 数据流是**单向**的，不是双向：`xlsx（权威）→ build_dict → book-data.json → index.db`。
> 没有任何环节回写 xlsx——这是红线 1，别搞反。

### P0 已交付什么

- `pipeline/persons_data.py`：从 `build_dict.py` 抽出的 **PERSONS 种子数据**
  （表格不存在时的回退源；人名数不写死，看 `people.json` 的 `persons` 长度）。
  `build_dict.py` 只留规则；拆分后 `people.json` 的 md5 **逐字节不变**。
- `pipeline/build_workbook.py` 改成**只读源数据**（`persons_data.PERSONS`），
  不再从 `people.json` 倒推——否则会形成 `build_dict → people.json → xlsx → build_dict` 的循环。
- **`workbook/persons.xlsx` 已是权威源**：`build_dict.py` 优先读它，缺文件才回退种子数据
  （且回退时会打印警告，不静默）。端到端已验证：改别名→生效、状态标 `dead`→条目消失、
  改回→md5 回到基准。
- 三个工作簿：`persons.xlsx` / `places.xlsx` / `sentences-<书>.xlsx`。

> ⚠️ 一个设计决定：`build_workbook.py` **导出时不预排序**。
> 行序就是源码的编排顺序（五帝在前），读回时原样采用。
> 若导出时按拼音排了序，读回来 `people.json` 的条目顺序就变了（实测 md5 因此不同）。
> 拼音只是给你**自己在 Excel 里排序看**的辅助列。

## 五、常用命令

```bash
# Excel 工作簿（persons / places / sentences-<书>）
# ⚠ 生成器只有 pipeline/build_workbook.py 这一份，别跑 app/tools/ 下那个同名副本
python pipeline/build_workbook.py                 # 句子默认只出史記
python pipeline/build_workbook.py --all-books     # 句子全五书（文件大、慢）

# SQLite 索引库（全量重建；加 --fresh 表示不复用旧 uid）
python app/tools/build_index_db.py

# 查询：查人 / 全文检索 / 按 tier 抽待确认项
python app/tools/query.py --stats
python app/tools/query.py 梁王            # 自动识别同名异人
python app/tools/query.py --fts 鴻門
python app/tools/query.py --tier guess -n 30

# 回归：断言 + 字面层七闸（数字每次会涨，以末行输出为准，不写死）
python pipeline/verify.py --check
python pipeline/check_trad.py

# ⚠️ 标注必须四步连跑，只跑第一步会丢裴注账本
python pipeline/build.py && python pipeline/annotate.py \
  && python pipeline/annotate_pei.py && python pipeline/annotate_js_note.py \
  && python pipeline/annotate_places.py

# 一键回归（断言 + 字面层 + UI 四套，约 60 秒）
bash scripts/run_all.sh                 # 默认端口 8790
PORT=8770 bash scripts/run_all.sh       # 想换端口
```
> 默认端口是 **8790** 不是 8770——8770 被本机 VPN 客户端占着。

**Python 解释器**：一律用系统 Python 3.12.10
（`C:/Users/dell/AppData/Local/Programs/Python/Python312/python.exe`），
PATH 上第一位的托管版 3.13.12 **没装 opencc**，`check_trad.py` 会假失败。

## 六、取数命令（数字会变，命令不变）

```bash
python -c "
import json
d=json.load(open('data/index/book-data.json',encoding='utf-8'))
S=d['sentences']
print('sentences', len(S))
print('marks', sum(len(s.get('marks') or []) for s in S))
print('persons', len(d['persons']), 'places', len(d['places']), 'chapters', len(d['chapters']))
"
```

## 七、待办（按优先级）

1. **P0–P2 的成果还没进 git**（最后一次提交停在 docs/19）——其中 `workbook/persons.xlsx`
   是人工审定资产，丢了补不回来，建议先提交一次
2. `app/tools/build_workbook.py` 是过期副本（读 `people.json`、按拼音排序、输出
   `bookindex-sj.xlsx`），与 `pipeline/build_workbook.py` 重复 93 行差异，待裁决删哪份
3. `.gitignore` 底部「人工资产」注释已过时：PERSONS 的权威源现在是
   `pipeline/persons_data.py` + `workbook/persons.xlsx`；`workbook/sentences-*.xlsx`
   属可再生，应显式忽略
4. 断句第二类（跨句对话引号）已定方案：**不动数据层，只在显示层做续接标记**
5. `p_xNNNNN` 随机 id 批量改拼音语义 id
6. 18 组同名异人（劉焉 ×3 等）的 UI 消歧
7. `app/server/main.py` 用了已废弃的 `@app.on_event("startup")`，有 DeprecationWarning
