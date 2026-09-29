# 新开发入口（本地索引 + 可编辑数据库）

> **这是新开发的唯一入口。** 完整背景与决策推演见 `docs/21`，
> 回顾分析见 `docs/22`–`23`，**下一步施工计划见 `docs/24`**。日常施工只看本文件就够。
>
> **事实源只有四处**：本文件 / `workbook/*.xlsx` / `pipeline/` 里的非 `_` 脚本 /
> `docs/21`–`24`。其余旧文档的数字互相打架，别拿它们当事实。

## 一、定位

`web/` 是**静态版，已冻结**（2026-09-28 拍板）：仍按原流程产出、仍用于分享，
但**不再改视觉与交互**。新能力一律只长在 `app/web/`。
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
| **快照 diff（P3）** | **做到「落 SQLite」**：独立快照库 `data/index/snapshots.db`（为什么独立见 docs/24 §三 P3-2），可翻历史；终端照打印。**网页 diff 页本次不做** |
| **`overrides`（P3）** | **`workbook/overrides.xlsx`**：人（含将来的 UI）写、pipeline **只读**；写冲突走 `.new.xlsx` + 报差异。⚠️ 脚本会填的列（`context`/`old_*`）**只在录入那一刻写，重建绝不刷新** |
| **静态版 `web/`** | **冻结**：只作分享产物，不再改视觉与交互；视觉演进只发生在 `app/web/`。抽共享 CSS 不做 |

## 四、施工顺序（每段结束都能用）

| 阶段 | 交付 | 状态 |
|---|---|---|
| **P0** | PERSONS 抽到 xlsx + `build_dict.py` 只留规则 | ✅ **已完成** |
| **P1** | 稳定 `uid` 落地、SQLite 索引库、**`relations` 表先建后填** | ✅ **已完成** |
| **P2** | FastAPI + 全文检索 + 原文对照界面 | ✅ **已完成** |
| **P3** | 编辑 → 重建 → 快照 diff | ✅ **已完成**（`rebuild.py` / `snapshot.py` / `overrides.py` / `verify_p3.py`） |
| **P4** | 句级拆分/合并/弃用 | ✅ **已完成**（uid 下沉 + 命令行 + 网页 UI） |
| **P5** | `verify.py` 断言接入新链路 | ✅ **已完成**（5 条一致性断言，基线 113 条） |

### 界面上的两处小改动（2026-09-29）

- **跨句对话的续接标记**（原文层）：古籍一句里常有多处「。！？」，按句读断就会把一对
  引号拆到两句——这是原文的本來面目，不是 bug。所以**只在显示层**处理：承接上一句的
  段落加左侧点线缩进（`q-cont`），话没说完的段落与下一句贴紧（`q-open`）。
  数据层（切分结果）一个字都不动（docs/21 §13 选 A 的改良版）。
- **同名异人消歧**：搜索结果给序号徽章，并标出每人**主要见于哪几本书**——
  同名往往各属一书（劉焉 ×3：後漢書 33 / 三國志 9 / 後漢書 8），
  只靠朝代和头衔分不出来。分书命中由 `/api/search` 一并返回（一次查询，不是 N+1）。

### P3 已交付什么

**一条命令走完全流程**（约 30–45 秒）：

```bash
python app/tools/rebuild.py
```

```
（dump 快照）→ build_dict → annotate → annotate_pei → annotate_js_note
            → annotate_places → apply_overrides → build_index_db →（自動 diff）
```

| 文件 | 职责 |
|---|---|
| `app/tools/rebuild.py` | 一键重建：顺序固定、任一步失败即停、末尾对账。选项 `--from N` / `--with-build` / `--no-snapshot` / `--no-overrides` / `--dry-run` / `--keep` / `--diff-top` |
| `app/tools/snapshot.py` | 快照与 diff：`dump` / `list` / `diff` / `drop`。独立库 `data/index/snapshots.db` |
| `app/tools/overrides.py` | 单条纠错：`init` / `show` / `add` / `revoke` / `list` / `apply`。表在 `workbook/overrides.xlsx` |
| `app/tools/verify_p3.py` | 新链路断言（条数以当次输出为准，只许升不许降） |

两个要点（都是踩过才知道的）：

- **快照库必须独立于 `index.db`**。后者是「可删重建」的产物，历史快照放进去会被重建冲掉。
- **diff 的「新」侧是当前库，不是另一份快照**。快照都在重建**前**取，两份快照互比恒为 0
  （第一版就犯了这个错，改完才报得出变化）。

三类变化 + tier 变化，每条自带上下文：

```bash
python app/tools/snapshot.py diff --live            # 上次快照 → 现在
python app/tools/snapshot.py diff --live --kind removed --top 30
```

单条纠错的闭环（P3-4 没做 UI，走命令行）：

```bash
python app/tools/query.py --tier guess -n 20        # 挑可疑命中（带 uid）
python app/tools/overrides.py show --uid <uid>      # 看这句有哪些命中
python app/tools/overrides.py add --uid <uid> --nth 1 --new 刘邦
python app/tools/rebuild.py                          # 套用 + 报出变化
python app/tools/overrides.py revoke --uid <uid>    # 反悔（状态改 dead，不删行）
```

> ⚠️ **pipeline 对 `overrides.xlsx` 只有读权限**。会由脚本填的列（`上下文`/`原pid`/`原tier`）
> **只在录入那一刻写，重建绝不刷新**——否则就是 P0「导出脚本冲掉权威源」那次事故的重演。
> 写由 `add` / `revoke`（以及将来的 UI）承担，两者是「人」这一侧的动作。

### P5 已交付什么

`verify.py --check` 现在同时断**旧链路**（消歧、别名、表字那 108 条）和
**新链路一致性**（`book-data.json` ↔ `index.db`，5 条）：

| 断言 | 抓住什么 |
|---|---|
| 句数 / 命中数 / 人物数 与库一致 | 漏跑建库、或某一步只跑了一半 |
| **uid 算法四处一致** | `common` / `build` / `tag_uids` / `build_index_db` 改了没同步 |
| **命中逐条对齐**（逐条比 uid+pid+串+偏移+tier） | 编辑与重建之间任何一处错位 |

> 这套断言一上就抓到一个真 bug：**48,097 句「只有地名命中」的句子没有 uid**
> （它们由 `annotate_places.py` 建记录，而 uid 只在 `annotate.py` 那边加过）。
> 这正是 P5 的意义——以前这种事只能靠肉眼发现。

⚠️ 跑重建前**先停掉本地服务**：Windows 上 SQLite 文件被占着，`build_index_db`
删不掉旧库会直接失败（退出码 1，已踩过）。

### P4 已交付什么

**网页端也能编辑了**（P4-2）：打开任意一篇的原文层，句子右侧 hover 出三个动作——
「拆分 / 併下句 / 棄用」。

- **拆分不弹窗填数字**：点「拆分」后**点字选断点**——想在哪断就点那个字
  （比输入偏移直觉得多，也不容易填错）。
- 每记一条，原文层顶部就显示「已記錄 N 條編輯，重建後生效」，
  点「重建」在后台跑（约 40 秒），跑完自动重开原文层。

新增端点：

```
POST /api/sentence/edit      {uid, action, at?}   记一条编辑（split/merge/dead）
POST /api/sentence/revoke    {uid}                撤销该句的全部编辑
POST /api/rebuild                                 后台重建（约 40 秒）
GET  /api/rebuild/status                          查状态与日志尾部
```

> 后端是**调 `apply_sentence_edits.py` 子进程**，不是 import pipeline——
> `app/` 与 `pipeline/` 刻意不互相 import（docs/23 §7.1），两边只在 JSON 上交汇。
> 写的是 `workbook/sentence-edits.xlsx`：**UI 是代你写，pipeline 侧依然只读**（红线 1）。

**P4-0 uid 下沉到语料层**（原本在建库时按位置现算，一改切分就漂移）：

```
corpus（tag_uids.py 打标 / build.py 新切）→ book-data.json（annotate 透传）→ index.db（直接采用）
```

优先级是**语料层 uid > 旧库按位置复用 > 现算**。语料层的才是权威——句子可编辑后位置会位移，
再按位置去旧库捡，会把上一句的 uid 错配到这一句身上。

**P4-1 句级编辑**（`pipeline/apply_sentence_edits.py` + `workbook/sentence-edits.xlsx`）：

```bash
python pipeline/apply_sentence_edits.py show --uid <uid>       # 看原文与字数
python pipeline/apply_sentence_edits.py add --uid <uid> --action split --at 7
python pipeline/apply_sentence_edits.py add --uid <uid> --action merge
python pipeline/apply_sentence_edits.py add --uid <uid> --action dead
python app/tools/rebuild.py                                     # 第 1 步自动套用
python pipeline/apply_sentence_edits.py revoke --uid <uid>      # 反悔
```

uid 三条继承规则：**拆**→前半继承原 uid、后半生成新 uid；**并**→留第一句、第二句标 `merged`；
**弃用**→标 `dead`。后两种**不物理删**，句子仍留在语料里，只是 annotate 跳过。

> **撤销为什么能生效**：不是就地改语料，而是**每次都从原始副本 `data/corpus-orig/` 重放**
> 全部生效编辑。撤销一条后重跑，那篇自然回到原样——不需要额外的回滚代码。
> 顺带解决了幂等：重跑不会二次拆分。

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

> ⚠️ **不会把你的审定冲掉的机制**（2026-09-28 补）：导出前先比一遍「人会写的列」
> （正名/朝代/头衔/简介/别名/状态/备注）。
> - **完全一致** → 幂等重建，直接覆盖，一句话都不多说；
> - **检测到你改过** → 原表一根手指不碰，改写 `persons.new.xlsx` 并把差异打印出来；
> - 真要以源数据为准重来 → 加 `--force`（会先把原表備份成 `.bak-<时间戳>.xlsx`）。
>
> 只读辅助列（`pinyin` / `in_<书>` / `命中数`）**不参与比对**——它们每次重跑都可能变，
> 拿它们比会永远判成「你改过」。

## 五、常用命令

```bash
# Excel 工作簿（persons / places / sentences-<书>）
python pipeline/build_workbook.py                 # 句子默认只出史記
python pipeline/build_workbook.py --all-books     # 句子全五书（文件大、慢）
python pipeline/build_workbook.py --force         # 强行重建（见下方⚠，会备份）

# SQLite 索引库（全量重建；加 --fresh 表示不复用旧 uid）
python app/tools/build_index_db.py

# 一键重建（含 dump 快照 + 自动 diff）
python app/tools/rebuild.py
python app/tools/rebuild.py --from 3         # 从第 3 步（annotate）开始
python app/tools/rebuild.py --dry-run        # 只列命令
python pipeline/tag_uids.py                  # 语料补打 uid（幂等，新切分已自动带）

# 快照与 diff
python app/tools/snapshot.py list
python app/tools/snapshot.py diff --live                    # 上次快照 → 现在
python app/tools/snapshot.py diff --live --kind removed --top 30
python app/tools/snapshot.py drop --id 3 4                  # 删脏快照

# 单条纠错（overrides）
python app/tools/overrides.py show --uid <uid>
python app/tools/overrides.py add --uid <uid> --nth 1 --new 刘邦
python app/tools/overrides.py revoke --uid <uid>
python app/tools/overrides.py list

# 句级编辑（P4）
python pipeline/apply_sentence_edits.py show --uid <uid>
python pipeline/apply_sentence_edits.py add --uid <uid> --action split --at 7
python pipeline/apply_sentence_edits.py revoke --uid <uid>
python pipeline/apply_sentence_edits.py list

# 新链路断言（P3 + P4，条数以当次输出为准）
python app/tools/verify_p3.py

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

1. **断句第二类（跨句对话引号）**：已定方案——**不动数据层，只在显示层做续接标记**
2. `p_xNNNNN` 随机 id 批量改拼音语义 id
3. 18 组同名异人（劉焉 ×3 等）的 UI 消歧
4. `app/server/main.py` 用了已废弃的 `@app.on_event("startup")` → DeprecationWarning
**P0–P5 主线全部完成**（2026-09-29）。剩下的都是可选项，按性价比排：

1. **关系数据（P6）**：`relations` 表已空表预留、端点已通，缺的是抽取与校验。
   工作量最大，也**最该单独做一次独立审查**（主观判断 + AI 抽取，最容易造出假证据）。
2. **P3-4 网页标错入口**：照 P4-2 同一套做（UI 代写 `overrides.xlsx`），半天。
3. **合并重复 pid**（如 `p_liuyan_sg` / `p_liuyan_ys` 其实是同一人）。
4. `p_xNNNNN` → 拼音语义 id：牵动全部外键，改之前先想清迁移与回滚。

> 三个已拍板的决策（详见 `docs/24` §二）：快照 diff **落 SQLite、可翻历史**（不做网页页）；
> `overrides` 落 **`workbook/overrides.xlsx`**（人写、管道只读）；**静态版 `web/` 冻结**。
>
> **夹带小活已清完**（2026-09-29）：`@app.on_event` → lifespan ✅、**17 个一次性脚本归档
> `_scratch/`** ✅、删 3 份废弃 `.bak`（约 34MB）✅、断句第二类**显示层续接标记** ✅、
> **同名异人 UI 消歧**（序号 + 「见于」哪本书）✅。
> 剩 `p_xNNNNN` 改拼音语义 id 未做（牵动全部外键，见下）与 `.mimocode/`（56MB，
> 来源不明，等你确认）。
