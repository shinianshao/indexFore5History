# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> **施工入口 `app/DEV.md`**（三条红线/顺序/命令）。本文件只放「动手前必须知道」的约定与坑。
> **当前状态快照 `docs/30`**（接在 29 之后）。推演 `docs/21`、优先级 `docs/16`、
> 计划 `docs/24`、关系审查 `docs/25`/`docs/28`、盘点 `docs/29`。

## 项目是什么
离线 Python 管线 + 本地网页的**古籍实体索引**（不是全文检索）。
五书：史記 130 / 漢書 109 / 後漢書 130 / 三國志 65 / 晉書 130 = 564 篇。
静态分享版 `web/index.html`（**已冻结**）；日常查询+编辑 `app/`（FastAPI）。
`app/` 与 `pipeline/` **刻意不互相 import**，只在 JSON 上交汇。

## 三条红线
1. **单向数据流**：`workbook/*.xlsx` 只能人写，pipeline 只读。想写 Excel → 改「写新版本 + 报差异」。
2. **句子主键是稳定 uid** `md5(chapter|para|seq)[:12]`：拆→前半继承，并→标 merged，删→标 dead，**不物理删**。
   算法有四处（common / build / tag_uids / build_index_db），改一处改四处。
3. **规则进代码，数据进表格**：GENERIC_MANUAL / CONTEXT_RULES / SCOPED_ALIASES /
   BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS 是代码；PERSONS 数据在 xlsx。

## 已拍板的方向
- **小程序取消，不重启**。新能力只长在 `app/web/`。
- **不再接新史书**。编辑深度**封顶 b 档**（拆/并/弃句），c 档改原文**不做**，留 dead 逃生口。
- 裴注 / 晋书旧史注是**独立账本**，不进 mentionCount。
- **Excel 组织**：persons/places/chapters/overrides 各一 sheet，**只有 sentences 按书分 sheet**。
  「按书看」用只读布尔列 `in_sj…in_js` 筛，**不要拆 sheet**（人物是跨书实体）。

## 改动铁律
- 算法三层（build 切分 / annotate 匹配·泛称 / 前端 scope）**不推倒**，改质量 = 改词典与守卫。
- 每修一个坑就加一条断言，基线**只许升不许降**。
- 别名只写**繁体**；裸官职、裸帝号/王号**禁止**进单人 core（走 GENERIC）；长名优先。
- 跨书同人**只扩 books 并集**，禁止新建 `p_xxx2`。
- **文档不写死统计数字**——「以当次输出为准」+ 给取数命令。
- **前端文案一律繁体**（`check_trad.py` 扫 `app/web/app.js`，简体注释会让 F 闸失败）。
- 一次性脚本归 `pipeline/_scratch/`（判据「下一轮还用不用」），移动时 `parents[1]→[2]`。
- 复杂清洗写 `pipeline/_*.py`，**勿用 `python -c`**（PowerShell 吞引号/正则）。

## 离线快照（docs/29 §六-6，P7-3，**已完成 2026-10-02**）
- 原则：**一套前端、两种数据源**。`dist/` 的 app.js 就是 app/web/app.js 的拷贝，
  靠「有没有 `window.BOOKINDEX_DATA`」切换。**永远不要复制第三份前端。**
- 导出：`python app/tools/export_static.py`（17s / 14.7MB）＋ `--check`（查过期）
  ＋ `--verify`（断 `db._narrow` 等价式，23s，只进 `--full`）。产物 `dist/` 已 gitignore。
  已进 `run_all.sh`；离线测试 `_ui_test_offline.js` 27/27（纯 `file://`，不注入 fetch）。
- ⚠️ **响应体组装必须放在 db 层**（`index_payload` / `person_payload`），联机端点与
  导出共用；放端点里就得让导出抄一遍，抄歪了离线版悄悄跟联机版不一致且不报错。
- ⚠️ **提速引入的等价式要配断言**：`all_counts` 一次算完 + `_narrow` 收窄（23s→11.5s），
  等价式是手推的，`_book_counts` 口径一改就破，而破了对导出**不报错**。
- ⚠️ 关系图快照 key 用 `"%g" % conf`（`1:0` 不是 `1:0.0`）——与 JS 拼的字符串
  必须一字不差，对不上时**不报错**，只是关系卡全空，最难查的一类坏。
- ⚠️ **大 JSON 写 `JSON.parse('…')`，不要写成对象字面量**：15MB 字面量会把 V8 的
  AST 撑爆（jsdom 里 4GB OOM）。
- ⚠️ **`location.hash` 规范化必须「守卫与解析吃同一份」**（`app/web/app.js` 的 `normHash`）：
  -坑一：`location.hash` 把中文百分号编码，`h === lastWritten` 守卫**从来没生效过**，
  每次中文检索都二次渲染，把用户刚点开的标签页顶回去。
  - 坑二（被坑一遮住，所以一直没人发现）：路由正则 `([^?]+)` 贪婪，把 `/person` 一起
  吞进查询词 → `#/q/舜操/person` → 下一轮变成 `舜操/person/person` → 每点一次长一段 →
  `/api/search?q=…` 超 64 字变 422。已收紧成 `[^?#/]+`。
  - **教训：两个地方共用一个「规范化后的值」时，必须都改；只改一处会把另一个坑从遮蔽下放出来。**

## 环境与命令
- ⚠️ **python 必须用系统 3.12.10**
  （`C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe`）；
  托管版 3.13.12 **没装 opencc**，跑 `check_trad.py` 会假失败。
- 回归 `bash scripts/run_all.sh`（`--full` 追加全量扫描 / `--no-ui` 只跑 Python）。
  端口 **8790**（8770 被 VPN 占）+ 关系图 API **8811**；日常服务 **8800**。
- ⚠️ **跑重建前必须先停本地服务**（Windows SQLite 被占 → 删不掉旧库 → 退出码 1）。
  `run_all.sh` 有前置检查，8800 在跑会直接退出 2。
- ⚠️ **annotate 必须四步连跑**（annotate → pei → js_note → places）；
  凡「重标注」一律走 `app/tools/rebuild.py`（~40s，含快照 + 自动 diff）。
- ⚠️ `curl` 要加 `--noproxy '*'`（本机配了代理）。
- ⚠️ 库表主键别想当然：`persons` 主键是 **`id`** 不是 `pid`；`books` 主键是 **`code`** 不是 `id`；
  `relations` 端点是 **`person_a`/`person_b`** 不是 `a`/`b`。
- 取「在书分布」用 **book-data.json 的 `byBook`**，不是 people.json 的 `books`。
- ⚠️ **大 JSON 一律走 `common.write_json`（已改原子写：`.tmp` + fsync + `os.replace`）**。
  别再手写 `open(p,"w")`+`json.dump`——8MB 的 book-data.json 写到一半被 SIGTERM
  会留半截档，下次报 `Expecting ',' delimiter: column N`，看不出是上一轮被中断。
  半截/损坏的产物（book-data.json / pei-data.json）都是可再生的，重跑 `rebuild.py` 即可。
- ⚠️ **前端加了块，后端也要加断言**：`_ui_test_index.js` 守页面，
  `verify_p3` [10]「索引四块 · 后端契约」守 `/api/index` 的字段
  （篇主/地名/字數/按书收窄/快捷词换书）。只守前端 = 改 SCHEMA 删一列也没人知道。
- ⚠️ 本机**临时目录会间歇性不可用**（python 报 `No usable temporary directory`），
  连带 safe-delete 守卫「state lock timeout」、openpyxl 存不了盘、
  还会把 1200 个 4 字节 `blat` 临时文件吐在仓库根目录。症状多半是**瞬时**的，
  重跑一次就好；守卫的锁卡死时清
  `%TEMP%\codebuddy-safe-delete-bulk\*\.lock` 空目录即可恢复。

## 「AI 概率判定闭环」= 通用工作法
**取证 → 判 → 落 → 断言**。取证生成器产 JSON（每条自带可计算信号 + 语料上下文 + 空 `ai` 字段）；
判定写回独立 verdicts 文件（数据重生成后判定不丢）；应用器默认预演、`--apply` 才写。
已用：表字/泛称、人名、关系。
- **人工清单必须自带证据**（归属分布 + 原文上下文 + 候选朝代 + 当前解析），**一律生成器产出禁止手敲**。
- ⚠️ **生成器必须跳过已判定的条目**（key 一致）。踩过两次：`_gen_rel_evidence.py` 和
  `_gen_rel_review.py` 都曾无视 verdicts，判完 40 条重跑还是 40 条 → 下一轮从头再判。
- 判不了勾「未知」，不要硬判。

## 关系数据（当前主战场）
- 权威源 `workbook/relations.xlsx`；`relations` 表在 index.db，**建库后由 `apply_relations` 灌回**（先灌必丢）。
- 规范 `(a,rel,b)` = **「a 是 b 的 rel」**，长辈/夫/兄那一侧在 `a`。只存规范边，
  `REL_INVERSE` 拒绝反向双写。**去重判据用 (a,b,rel)，不能用 rel_id**（rel_id 会撞车，见下）。
- `rel_id=md5(a|b|rel|era|book)`；`confidence` 由 `derive_confidence` **派生**（无证据压 0.4）。
- ⚠️ 边起点叫 `source`，关系来源改叫 **`origin`**（同名键后者会无声覆盖前者）。
- 抽取只收**显式关系词**（之子/之弟/之妻…），**禁止共现出边**；
  **裸帝号一律不自动落**（跨朝代多义，「文帝」被解析成曹丕）→ 进 `docs/26` 人工判。
- **展现层三张表别混**：`REL_TABLE`（rel→类型/对称）/ `REL_INVERSE`（**反向边**，禁双写）/
  `CALL_INVERSE`（**反向称呼**，带性别变体 `父→(子,女)`，连对称边都需要）。
  页面靠 `rel_view` 换算：刘邦页「妻 吕太后」、吕后页「夫 汉高祖」、曹操页「女 曹節」。
- **证据判据只有一条：句子里明说了才算，共现一律不算**。证据**一对多**（`relation_evidence` 子表）。
- ⚠️ `relations.py revoke --rel-id` 会**一次误伤多行**（xlsx 里同一 rel_id 有 dead+active 两行，
  docs/28 P1-8）。要精确作废就按「行号 + (a,b,rel)」改状态列。
- ⚠️ `relations.py check` 的退出码：只有 `check` 子命令的返回值该变成退出码，
  其它子命令返回的是「灌入条数」不能当退出码（apply 返回 99 会被当成失败）。

## 盘点与方案（docs/29）
- **改得起是本钱**：全量重建 ~34s、一键回归 ~241s（11 项）。改完立刻能验，所以
  「多做一轮」便宜、「猜着做」贵。
- 规模（2026-10-02）：句 96,336 / 人 2,240 / 别名 6,040 / 地 1,575 / 篇 564 / 边 99。
- **两套前端是持续税**（`web/` 48MB 已冻结 + `app/web/` 0.3MB 日常）：每加功能理论上改两处，
  且回归里还跑着 4 个只守静态版的 UI 测试。
- ⚠️ **pid 语义化（676 个 `p_xNNNNN`）+ 同名合并（17 组）是唯一「越拖越贵」的活**：
  改 pid 要同步 relations.xlsx / overrides / sentence-edits / people.json，
  每多落一批数据就多一笔。**应插队到前端细节之前。**（同名人无法自动化，必须人工看原文判。）
- ❌ **不做：从正文大规模抽关系**。简介那条线已近抽干（70 条含关系词 / 已出边 59），
  要上量只能扫 96,336 句：无标注数据、误判会画成实线误导、规模无上限。要就只做小试点。
- 「跟原来网页版一样」**不该 100% 照搬**：静态版的「一次性加载 32.8MB」、
  「快捷词不换书」是当年绕开无数据库的妥协。新版按需查库更好，别改回去。

## 各阶段已完成（压缩）
- **P0**：`persons.xlsx` 是权威源，`persons_data.py` 存种子。三条纪律：导出只读源数据
  （防 `build_dict→people.json→xlsx→build_dict` 循环）、**不预排序**、验证用 people.json **md5 比对**。
  ⚠️ `build_dict.py` 的 `ROOT` 是**字符串**，别写 `ROOT / "x"`。
- **P1**：`index.db`（**可删重建的产物**）。FTS5 坑：unicode61 把整句当一个 token →
  **按字切分入库 + 短语查询** `MATCH '"項 羽"'`；**别用 trigram**（要求 ≥3 字）。
  mentions/aliases 追加写会翻倍 →「偷旧 uid → 删库 → 重建 → 复用」。
- **P2**：裸短名错挂（修法顺序：长名 > 分书收束 > ctxRule > 动 default）；类传补人**必人工看原文**。
- **P3**：快照 diff 落**独立库** `snapshots.db`（不能进 index.db，会被冲掉）；
  overrides 落 `workbook/overrides.xlsx`。坑：两份快照互比恒为 0（新侧必须是当前库）。
- **P4**：uid 下沉语料；句级编辑**从 `data/corpus-orig/` 重放**实现撤销与幂等。
- **P5**：`verify.py`（基线 113）与 `verify_p3.py`（基线 58）是**两套，都要跑**，都已进 `run_all.sh`。
- **P6-5a 证据补录**：有据边 2 → 31。24 条边语料里没共现，补不回来。
- **P6-5b 帝号批次**：40 条全判（36 accept / 2 reject），已落盘灌库。剩 1 同名 + 6 解析不出。

## 审查规矩
- 关系数据审**两次**（设计层 docs/25 / 产品层 docs/28）；第二次换**不参与开发的会话**，
  **只准它写那一份报告**。判据：**故意注入错误，断言必须变红**。
- **凡是「不可再生的审定数据」，先问它落在哪个会被删重建的产物里**。
- **断言自己造的数据要自己收走**：`verify_p3.purge_test_rows()`。
- ⚠️ **凡是「先写脏数据、验完再撤」的断言，撤销必须放 `finally`**；清理函数**不能只收 dead 行**
  ——崩溃留下的恰恰是 **active** 行，下一次重建会真的把它套用上去（实测：「沛公」被改归项羽）。
  `purge_test_rows` 现在见到活着的自检行会先标 dead 再删。
- ⚠️ **断言红了 ≠ 数据错了**，先看清它断的那批是什么。例：「本紀/世家/列傳都有篇主」红 31 篇，
  查了才知道列傳里混着**类传与四夷传**（西南夷/龜策/貨殖/匈奴/西域/宣元六王），本就没有篇主；
  改断「本紀/世家」（以人命名）→ 缺 0。

## 已知残留 / 排队（取数 `_probe_rel_backlog.py`）
- ⚠️ **简介这条线已近抽干**：含关系词 70 条，已出边 59 / 剩 11。要上量只能从语料正文抽（先试点）。
- `docs/26` 剩 7 条：1 同名（劉保/安帝）+ 6 解析不出（奪子/德兄納/張偃/曲沃桓叔/袁京/名噲，
  都是库里没有的人，要先补人）。
- 重复 pid `p_liuyan_sg` / `p_liuyan_ys` 待合并；613 个 `p_xNNNNN` → 拼音语义 id
  （**须排在依赖 pid 的活之前**）。
- 网页「标错」入口（照 P4-2 同套做法）。
- 文档 01–18 数字打架待治理（已治理 15/16/README）。
