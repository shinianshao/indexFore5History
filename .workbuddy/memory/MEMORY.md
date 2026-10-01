# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> **施工入口 `app/DEV.md`**（三条红线/顺序/命令）。本文件只放「动手前必须知道」的约定与坑。
> 推演 `docs/21`、优先级 `docs/16`、计划 `docs/24`、关系审查 `docs/25`/`docs/28`。

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
- **断言自己造的数据要自己收走**：`verify_p3.purge_test_rows()`（只删 dead + 测试标记行）。

## 已知残留 / 排队（取数 `_probe_rel_backlog.py`）
- ⚠️ **简介这条线已近抽干**：含关系词 70 条，已出边 59 / 剩 11。要上量只能从语料正文抽（先试点）。
- `docs/26` 剩 7 条：1 同名（劉保/安帝）+ 6 解析不出（奪子/德兄納/張偃/曲沃桓叔/袁京/名噲，
  都是库里没有的人，要先补人）。
- 重复 pid `p_liuyan_sg` / `p_liuyan_ys` 待合并；613 个 `p_xNNNNN` → 拼音语义 id
  （**须排在依赖 pid 的活之前**）。
- 网页「标错」入口（照 P4-2 同套做法）。
- 文档 01–18 数字打架待治理（已治理 15/16/README）。
