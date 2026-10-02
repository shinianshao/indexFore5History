# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> 施工入口 `app/DEV.md`；路线图 `docs/31`；现状快照 `docs/30`。
> **别读 docs/01–18（数字互相打架）**，要看当前状态只认 30/31。
> 阶段史见 git log 与各 docs，本文件只留「动手前必须知道的约定与坑」。

## 项目是什么
离线 Python 管线 + 本地网页的**古籍实体索引**（不是全文检索）。
五书 564 篇：史記 130 / 漢書 109 / 後漢書 130 / 三國志 65 / 晉書 130。
旧静态版 `web/`（**已冻结**）；日常 `app/`（FastAPI + 端口 8800）；离线快照 `dist/`。
`app/` 与 `pipeline/` **刻意不互相 import**，只在 JSON 上交汇。

## 三条红线
1. **单向数据流**：`workbook/*.xlsx` 只能人写，pipeline 只读。要写 Excel →「写新版本 + 报差异」。
2. **句子主键是稳定 uid** `md5(chapter|para|seq)[:12]`：拆→前半继承，并→merged，删→dead，**不物理删**。
   uid 算法有四处（common / build / tag_uids / build_index_db），改一处改四处。
3. **规则进代码，数据进表格**：GENERIC_MANUAL / CONTEXT_RULES / SCOPED_ALIASES /
   BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS 是代码；PERSONS 数据在 xlsx。

## 已拍板的方向
- **小程序取消，不重启**；新能力只长在 `app/web/`。**不再接新史书**。
- 编辑深度**封顶 b 档**（拆/并/弃句），c 档改原文**不做**，留 dead 逃生口。
- **裴注 / 晋书旧史注是独立账本**（`db.person_notes_payload` → `person_payload["notes"]`，
  联机与离线共用）：**不入库、不进 mentionCount**（注文 `pseq` 是段号，与正文切分体系不同）。
  视觉青灰区别于正文，分量标【裴N】摆在正文命中旁，**不相加**。实有 523 人 / 4,173 處。
- **Excel 组织**：persons/places/chapters/overrides 各一 sheet，**只有 sentences 按书分 sheet**；
  「按书看」用只读布尔列 `in_sj…in_js` 筛，**不要拆 sheet**（人物是跨书实体）。
- 算法三层（build 切分 / annotate 匹配·泛称 / 前端 scope）**不推倒**，改质量 = 改词典与守卫。

## 环境与命令
- ⚠️ **python 必须用系统 3.12.10**（`C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe`）；
  托管版 3.13.12 **没装 opencc**，跑 `check_trad.py` 会假失败。
- 回归 `bash scripts/run_all.sh`（`--full` 追加全量扫描 / `--no-ui` 只跑 Python，约 200s）。
  日常服务 8800；回归临时端口 8790（8770 被 VPN 占）+ 关系图 API 8811。
- ⚠️ **跑重建前必须先停本地服务**（Windows SQLite 被占 → 退出码 1）；run_all 有前置检查。
- ⚠️ **重标注一律走 `app/tools/rebuild.py`**（~40s，含快照 + 自动 diff）；
  annotate 必须四步连跑（annotate → pei → js_note → places）。全量重建 ~34s。
- ⚠️ `curl` 要加 `--noproxy '*'`（本机配了代理）。
- 基线取/latest：`run_all.sh` 10/10 · `verify.py` 113 · `verify_p3` 79 ·
  `_ui_test_index` 29 · `_ui_test_rel` 11 · `_ui_test_offline` 51。
  ⚠️ `verify_p3` 单跑要 4–5 分钟，别用短 timeout。

## ⚠️ 数据形状（同一类坑反复踩，一律自动探测）
- **xlsx sheet 名 / 列名自动探测**（踩过 5 次）→ `_pick_sheet(wb, need_cols)`：
  `persons.xlsx` 表叫中文 **`人物`**（另有 `说明`）；列是 **`dynasty`** 不是 `era`；
  **主键 `id` 不是 `pid`**。
- index.db：`books` 主键 **`code`**；`relations` 两端 **`person_a`/`person_b`**；
  `mentions` = `{id, sentence_uid, person_id, surface, s, e, tier}`，**没有 `book` 列**
  （按书要 `mentions→sentences→chapters.book_id→books.code` 四跳）。
- book-data.json 的 mark = `{s,e,pid,tier,alias}`；取「在书分布」用它 **`byBook`**，
  不是 people.json 的 `books`。
- **`person_aliases` 表**（2026-10-03）：`{person_id, seq, w, simp, n, kind, variants(JSON), by_book(JSON)}`
  3,926 条，由 annotate 的 `build_alias_list` 算好后原样落表（app/ 不 import pipeline/）。
  不变量 **`n == Σ byBook`**（verify_p3 [14] 守）。每人最多 14 条（曹操）。
- **`persons.era_rank` / `books.era_from,era_to`**（2026-10-03）：时代序号 + 书记载区间
  （hs[8,10] hhs[10,11] sgz[11,12] js[12,15]，**sj 通史为 NULL**）。eraRank 覆盖 2071/2240。
  前端 `BOOKS[].era` 是常量，**与库必须一致**（verify_p3 [15] 守）。
- ⚠️ `pipeline/verify.py` 的 `ROOT` 是**字符串**，`ROOT / "x"` 直接 TypeError（build_dict 同）。
- ⚠️ **「按 pid 索引的表」不止 relations.xlsx**：`check_trad.py` 的 `TRADNAME_EXCEPTIONS` 也是。
- ⚠️ **大 JSON 一律走 `common.write_json`**（已改原子写），别手写 `open(p,"w")+json.dump`。

## ⚠️ 断言铁律
- 每修一个坑加一条断言，基线**只许升不许降**。改完必须「**注入错误 → 变红 → 还原 → 变绿**」。
- **红线断言要断在「会被打破的那一层」**：注文不进 mentionCount 若断在库里，查不出「往 payload
  里拼条目」的破法；且 `mentions` 有 limit(200) 让条数比较形同虚设 → 必须逐条查 payload 标记。
- **集合比较要想清方向**（写成 `_zi <= set(_zi)` 是恒真，断言等于废了）。
- **改数据形状必配断言**：给离线 `sents` 加段号时 `export_static.py` 有**三处** `enumerate(sents)`
  要同步，漏改 → 导出中途炸、`dist/` 留旧档（**还能打开**，最难发现）→ 已加 `--verify` 守形状。
- **前端加了块，后端也要加断言**（`_ui_test_index.js` 守页面，`verify_p3` 守 `/api/index` 字段）。
- **断言自己造的数据要自己收走**（`verify_p3.purge_test_rows()`）；撤销必须放 `finally`，
  清理函数**不能只收 dead 行**（崩溃留下的恰恰是 active 行，下次重建会真套用上去）。
- **断言红了 ≠ 数据错了**，先看它断的那批是什么（例：列傳里的类传/四夷传本就没有篇主）。
- ⚠️ **批量改 pid 会被 diff 计两次**（既进 `added` 又进 `pid_changed`）→ 先核对 `added` 桶。
- 已有 GMEMORY 的 SMP 流水线注 uid **从 MAX 起递增**且**同一句子里的引号 uid 必须成组相邻**（相邻才
  能配对）；邻接作用于 trim 后的 emoji 段 Emacs Philip Bradley 分组成 Алекс。

## 离线快照（一套前端、两种数据源）
- `dist/` 的 app.js 就是 `app/web/app.js` 的拷贝，靠「有没有 `window.BOOKINDEX_DATA`」切换。
  **永远不要复制第三份前端。**
- 导出 `app/tools/export_static.py`（`--check` 查过期 / `--verify` 断 `db._narrow` 等价式）。
- ⚠️ **响应体组装必须放在 db 层**（`index_payload` / `person_payload`），放端点里就得让导出抄一遍，
  抄歪了离线版悄悄不一致**且不报错**。
- ⚠️ 关系图快照 key 用 `"%g" % conf`（`1:0` 不是 `1:0.0`）：对不上**不报错**，只是关系卡全空。
- ⚠️ **大 JSON 写 `JSON.parse('…')`**，不要写成对象字面量（15MB 字面量撑爆 V8 AST，jsdom 4GB OOM）。
- ⚠️ **`location.hash` 规范化必须「守卫与解析吃同一份」**（`normHash`）。教训：两处共用同一个
  规范化值时必须都改，只改一处会把另一个坑从遮蔽下放出来。

## ⚠️ 联机/离线一致性（反复出现的结构性决定）
- **凡是「按当前书作用域变化」的数字，一律让前端算**（`aliasScopeN` / `isFormerEra`）。
  离线路由 `offlineGet` 用 `person/([^/?]+)` 匹配，**查询串会被忽略**——后端收窄的话
  离线版拿不到等值结果，两边悄悄分叉且不报错。数据（byBook / eraRank / eraRange）
  由后端给全，前端只做选择，两份前端跑同一段代码。
- **常量漂移是同一类坏**：app.js 的 `ALIAS_KINDS`、`BOOKS[].era` 与库/后端必须一字不差
  （与关系图 `"%g" % conf` 同类）——错了不报错，只分错组 / 标错人。两条都已在 verify_p3
  [14]/[15] 里用「正则抽 JS 常量 vs 库」门住。
- ⚠️ **改了 UI 形状，旧断言会红**——那是断言过期不是 bug（实测：`.alias-tag` 扁平别名
  → 分组表后离线测试红 1 条）。把旧断言升级成新形状的判据，别删。

## UI / 测试
- ⚠️ **UI 测试写错时症状是「等不到」不是报错**：原文层在 `#readerBody` 不在 `#out`；
  人物索引条目是 `.item[data-name]`（`.row[data-pid]` 是搜索结果行）；
  **检索靠点按钮触发**（`qEl` 只绑 keydown，没有 input）；测试环境没有全局 `document`，用取到的 `doc`。
- **前端文案一律繁体**（`check_trad.py` 扫 `app/web/app.js`，简体注释会让 F 闸失败）。

## 「AI 概率判定闭环」= 通用工作法
**取证 → 判 → 落 → 断言**。取证生成器产 JSON（自带可计算信号 + 语料上下文 + 空 `ai` 字段）；
判定写回**独立 verdicts 文件**（数据重生成后判定不丢）；应用器默认预演、`--apply` 才写。
- **人工清单必须自带证据**，**一律生成器产出禁止手敲**。
- ⚠️ **生成器必须跳过已判定的条目**（key 一致），判完重跑还是原样 = 下一轮从头再判。
- 判不了勾「未知」，不要硬判。

## 关系数据
- 权威源 `workbook/relations.xlsx`；`relations` 表**建库后由 `apply_relations` 灌回**（先灌必丢）。
- 规范 `(a,rel,b)` = **「a 是 b 的 rel」**，长辈/夫/兄那一侧在 `a`；只存规范边，`REL_INVERSE` 拒绝反向双写。
  **去重判据用 (a,b,rel)，不能用 rel_id**（rel_id 会撞车）。
- `rel_id=md5(a|b|rel|era|book)`；`confidence` 由 `derive_confidence` **派生**（无证据压 0.4）。
- ⚠️ 边起点叫 `source`，关系来源改叫 **`origin`**（同名键后者无声覆盖前者）。
- **证据判据只有一条：句子里明说了才算，共现一律不算**（子表 `relation_evidence`，一对多）。
- 展现层三张表别混：`REL_TABLE`（类型/对称）/ `REL_INVERSE`（反向边）/ `CALL_INVERSE`（反向称呼，
  带性别变体 `父→(子,女)`）。页面靠 `rel_view` 换算。
- 抽取只收**显式关系词**，**禁止共现出边**；**裸帝号一律不自动落** → 进人工清单判。
- ⚠️ `relations.py revoke --rel-id` 会**一次误伤多行**（xlsx 同 rel_id 有 dead+active 两行），
  要精确作废按「行号 + (a,b,rel)」改状态列。
- ⚠️ `relations.py check` 的退出码：只有 `check` 子命令的返回值该变成退出码，
  apply 返回「灌入条数」不能当退出码（返回 99 会被当成失败）。
- ❌ **不做：从 96,336 句正文大规模抽关系**（无标注数据、误判画成实线误导、无上限）。
  简介那条线已近抽干（70 条含关系词 / 已出边 59）。

## 其他
- 别名只写**繁体**；裸官职、裸帝号/王号**禁止**进单人 core（走 GENERIC）；长名优先。
  跨书同人**只扩 books 并集**，禁止新建 `p_xxx2`。
- **文档不写死统计数字**——「以当次输出为准」+ 给取数命令。
- 一次性脚本归 `pipeline/_scratch/`（判据「下一轮还用不用」），移动时 `parents[1]→[2]`；
  复杂清洗写 `pipeline/_*.py`，**勿用 `python -c`**（PowerShell 吞引号/正则）。
- ⚠️ 根目录会堆 4 字节 `blat` 临时文件（`%TEMP%` 间歇不可用时 Python 吐的），清理
  `$PY pipeline/_clean_root_blat.py --apply`（按**内容 + git 跟踪**双判据，默认预演）。
  ⚠️ **别往 .gitignore 写文件名规则**：gitignore 看不见内容，任何 7–8 位字符类规则都会误伤
  同是 8 字符的 `pipeline/_scratch`，而 `!` 反豁免对已排除目录的内容**无效**。
- ⚠️ 本机 `%TEMP%` 会**间歇性不可用**（连带 openpyxl 存不了盘、safe-delete 锁超时），
  症状多半瞬时，重跑一次就好；锁卡死时清 `%TEMP%\codebuddy-safe-delete-bulk\*\.lock`。
- 审查规矩：关系数据审两次，第二次换**不参与开发的会话**且**只准它写那一份报告**；
  判据是「故意注入错误，断言必须变红」。**不可再生的审定数据，先问它落在哪个会被删重建的产物里。**

## 当前待办（docs/31 §四，2026-10-03 凌晨更新）
1. **同名合并 17 组 / 35 人**（⚠️ **只能用户本人看原文拍板**，AI 只出取证清单）+ `p_liuyan_sg`/`_ys` 重复 pid
2. 关系边 `book` 列补全（⚠️ **卡点：`rel_id=md5(a|b|rel|book|era)`，填 book 会改变 rel_id**
   → 重算就要迁移 39 行证据。实测 99 边仅 31 有据：29 条单书可机械补（sj22/hs7/hhs2/js2），
   2 条跨书，68 条无据。**取舍要用户定**）
3. 人工清单剩 7 条（要先补 6 个库里没有的人）
4. 文档 01–18 数字治理；`app/DEV.md` 待办清单清理
| — | 网页「标错」入口（照 P4-2 同套做法，UI 代写 `overrides.xlsx`） | 新功能 |
