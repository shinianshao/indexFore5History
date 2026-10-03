# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> 施工入口 `app/DEV.md`；路线图 `docs/31`；现状快照 `docs/30`。
> **别读 docs/01–18（数字互相打架）**，要看当前状态只认 30/31。
> 本文件只留「动手前必须知道的约定与坑」；阶段史见 git log。

## 是什么 / 三条红线
离线 Python 管线 + 本地网页的**古籍实体索引**（不是全文检索）。五书 564 篇
（史記130/漢書109/後漢書130/三國志65/晉書130）。旧静态版 `web/` **已冻结**；
日常 `app/`（FastAPI + 8800）；离线快照 `dist/`。`app/` 与 `pipeline/`
**刻意不互相 import**，只在 JSON/DB 上交汇。
1. **单向数据流**：`workbook/*.xlsx` 只能人写，pipeline 只读。要写 →「写新版本 + 报差异」。
2. **句子主键是稳定 uid** `md5(chapter|para|seq)[:12]`：拆→前半继承，并→merged，
   删→dead，**不物理删**。算法有四处（common/build/tag_uids/build_index_db），改一处改四处。
3. **规则进代码，数据进表格**：GENERIC_MANUAL / CONTEXT_RULES / SCOPED_ALIASES /
   BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS 是代码；PERSONS 数据在 xlsx。

## 已拍板的方向
- **小程序取消，不重启**；新能力只长在 `app/web/`。**不再接新史书**。
- 编辑深度**封顶 b 档**（拆/并/弃句），c 档改原文**不做**，留 dead 逃生口。
- **裴注/晋书旧史注是独立账本**（`db.person_notes_payload`，联机离线共用）：
  **不入库、不进 mentionCount**（注文 `pseq` 是段号，与正文切分体系不同）；
  视觉青灰区别于正文，分量标【裴N】**不相加**。实有 523 人 / 4,173 處。
- **Excel 组织**：persons/places/chapters/overrides 各一 sheet，**只有 sentences 按书分
  sheet**；「按书看」用只读布尔列 `in_sj…in_js` 筛，**不要拆 sheet**（人物是跨书实体）。
- 算法三层（build 切分 / annotate 匹配·泛称 / 前端 scope）**不推倒**，改质量 = 改词典与守卫。
- 别名只写**繁体**；裸官职、裸帝号/王号**禁止**进单人 core（走 GENERIC）；长名优先。
  跨书同人**只扩 books 并集**，禁止新建 `p_xxx2`。

## 环境与命令
- ⚠️ **python 必须用系统 3.12.10**（`C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe`）；
  托管版 3.13.12 **没装 opencc**，跑 `check_trad.py` 会假失败。
- 回归 `bash scripts/run_all.sh`（`--full` 追加全量扫描 / `--no-ui` 只跑 Python，约 200s）。
  ⚠️ **跑重建前必须先停本地服务**（Windows SQLite 被占 → 退出码 1 / 删不掉旧库）。
- ⚠️ **重标注一律走 `app/tools/rebuild.py`**（~40s，含快照 + 自动 diff）；
  annotate 四步连跑（annotate → pei → js_note → places）。全量重建 ~34s。
- ⚠️ `curl` 加 `--noproxy '*'`。⚠️ **断言前先确认端口空着**（8800 常被日常服务占）。
- ⚠️ `verify_p3` 单跑 4–5 分钟，别用短 timeout。**长断言配快速版**：
  `verify_p3_overrides.py` 只跑 `[16]`、`verify_p3_place.py` 只跑 `[17]`。
- 文档不写死统计数字——「以当次输出为准」+ 给取数命令。
- 一次性脚本归 `pipeline/_scratch/`（判据「下一轮还用不用」），移动时 `parents[1]→[2]`；
  复杂清洗写 `pipeline/_*.py`，**勿用 `python -c`**（PowerShell 吞引号/正则）。
- ⚠️ 根目录会堆 4 字节 `blat` 临时文件，清理 `python pipeline/_clean_root_blat.py --apply`
  （按**内容 + git 跟踪**双判据，默认预演）。⚠️ **别往 .gitignore 写文件名规则**：
  gitignore 看不见内容，7–8 位字符类规则会误伤同是 8 字符的 `pipeline/_scratch`。
- ⚠️ 本机 `%TEMP%` **间歇性不可用**（连带 openpyxl 存不了盘、safe-delete 锁超时），
  症状多半瞬时，重跑一次就好。

## ⚠️ 数据形状（同一类坑反复踩，一律自动探测）
- **xlsx sheet 名/列名自动探测**（踩过 5 次）→ `_pick_sheet(wb, need_cols)`：
  `persons.xlsx` 表叫中文 **`人物`**；列是 **`dynasty`** 不是 `era`；主键 **`id`** 不是 `pid`。
- index.db：`books` 主键 **`code`**；`relations` 两端 **`person_a`/`person_b`**；
  `mentions` = `{id, sentence_uid, person_id, surface, s, e, tier}`，**没有 `book` 列**
  （按书要 `mentions→sentences→chapters.book_id→books.code` 四跳）。
- book-data.json 的 mark = `{s,e,pid,tier,alias}`；「在书分布」用 **`byBook`**，不是 `books`。
- **`person_aliases` 表**：`{person_id,seq,w,simp,n,kind,variants(JSON),by_book(JSON)}`，
  由 annotate 的 `build_alias_list` 算好后原样落表（app/ 不 import pipeline/）。
  不变量 **`n == Σ byBook`**（verify_p3 [14] 守）。
- **`persons.era_rank` / `books.era_from,era_to`**：hs[8,10] hhs[10,11] sgz[11,12]
  js[12,15]，**sj 通史为 NULL**。前端 `BOOKS[].era` 是常量，**与库必须一致**（[15] 守）。
- **`place_aliases` 表**（2026-10-03）：`{place_id,seq,w,n,by_book}`。**必须有**——
  `places.name` 与 `trad_name` **逐行相同**（全表 0 行不同），简体名一直只在 book-data
  的 `aliases` 里而从未灌进库 → 只 `LIKE trad_name/name` 等于简体输入整个地名库失明。
- ⚠️ `pipeline/verify.py` 的 `ROOT` 是**字符串**，`ROOT / "x"` 直接 TypeError（build_dict 同）。
- ⚠️ **「按 pid 索引的表」不止 relations.xlsx**：`check_trad.py` 的 `TRADNAME_EXCEPTIONS` 也是。
- ⚠️ **大 JSON 一律走 `common.write_json`**（原子写），别手写 `open(p,"w")+json.dump`。

## ⚠️ 断言铁律
- 每修一个坑加一条断言，基线**只许升不许降**。改完必须「**注入错误 → 变红 → 还原 → 变绿**」。
- **红线断言要断在「会被打破的那一层」**：断在库里查不出「往 payload 里拼条目」的破法；
  `mentions` 有 limit(200) 让条数比较形同虚设 → 必须逐条查 payload 标记。
- **集合比较要想清方向**（写成 `_zi <= set(_zi)` 是恒真，断言等于废了）。
- **端点层必须真打一次 HTTP**，只测 db 层不够（出过一次「db 全绿、端点 500」）。
- **前端加了块，后端也要加断言**（`_ui_test_index.js` 守页面，`verify_p3` 守 API 字段）。
- **断言自己造的数据要自己收走**（`verify_p3.purge_test_rows()`，放 `finally`）；
  清理函数**不能只收 dead 行**（崩溃留下的恰恰是 active 行，下次重建会真套用上去）。
- **断言红了 ≠ 数据错了**，先看它断的那批是什么（例：列傳里的类传本就没有篇主）。
- **改数据形状必配断言**：给离线 `sents` 加段号时有**三处** `enumerate(sents)` 要同步，
  漏改 → 导出中途炸、`dist/` 留旧档（**还能打开**，最难发现）→ 已加 `--verify` 守形状。
- ⚠️ **「是否已生效」这类状态不在数据里，只能算**：`overrides.xlsx` 的行永远 active
  （revoke 只改状态为了留痕），`db.override_states` 拿行去问库才算得出。
  不算的后果是**界面骗人且不报错**：顶栏 N 永不归零、改归生效后别人页面也挂徽章。
  → 凡是「行留着但状态会变」的表，都要问一句「这状态是存出来的还是算出来的」。
- ⚠️ **前端拿到 xlsx 读回的值必须先归一**（`17.0` vs `17`）：拼 key 对不上 →
  **徽章静默消失**，不报错。`db._as_int` 与 `overrides._int_or_none` 两处都要。
- ⚠️ **批量改 pid 会被 diff 计两次**（既进 `added` 又进 `pid_changed`）→ 先核对 `added` 桶。

## UI / 测试
- ⚠️ **UI 测试写错时症状是「等不到」不是报错**：原文层在 `#readerBody` 不在 `#out`；
  人物索引条目 `.item[data-name]`、地名条目 `.item[data-place]`（`.row[data-*]` 是搜索结果行）；
  **检索靠点按钮触发**（`qEl` 只绑 keydown，没有 input）；测试环境没有全局 `document`，用 `doc`。
- ⚠️ **等待条件必须是「这一屏独有的东西」**——两处同源踩坑：
  ① 等 `.person-head .name`，而**检索页也有这个类** → 条件立刻成立，断言读到错误的屏；
  ② 上一块留下同类元素（离线搜「鴻門」留下地名行——「鴻門」本就是關隘）
  → 下一块量到的是**残留**，断言恒真，注入故障照样绿。
  修法：等该页独有的标记（`.sent[data-place]`）+ **先清屏** + 判据写死内容。
- ⚠️ **别把「当前数据的偶然」写进等待条件**（「鴻門」落成地名卡后，等「查不到」永远等不到）。
  判据该是「渲染已落定」。
- ⚠️ **测试块之间要收尾上一块的现场**（原文层没关 → 下一块「点句→原文层」**假通过**）。
- ⚠️ **注入测试要能优雅变红**：注入引发 traceback 会让整段 20 条断言全灭，
  看不出「哪条该红」。断言块要能**提前收工并记一条红**。
- ⚠️ **`waitFor` 返回的是布尔，不是元素**：等完**重新取一次元素**再读 `textContent`。
- ⚠️ **`location.hash` 设成与当前相同的值不触发 hashchange**：想「再进一次人物页」
  必须先跳到别的路由（`#/q/邦`）再跳回来。
- ⚠️ **UI 测试真点一次「写入」就脏权威源** → 沙盒环境变量 `BOOKINDEX_OVERRIDES`，
  run_all 指向 `data/index/overrides.ui-test.xlsx`；服务启动要嚷出来，
  断言要断「默认落点没被改」。
- ⚠️ **UI 测试每步做空值保护**（`if (el) click(el)`）：崩在 `dispatchEvent` 上会把
  「控制台无异常」也一起吞掉。
- ⚠️ **后台服务用 `&` 起会被回收**（命令返回后进程就没了）。必须用 `run_in_background: true`
  （**不带 `&`**）。症状是 UI 测试**大面积 0 条**——**先怀疑服务死了，别急着改断言**。
- ⚠️ **openpyxl 重存会改 xlsx 字节**（内容逐行相同）。`Bin 5040 -> 5041` 看着像脏了：
  **先逐行比对再决定还原**（`git show HEAD:f` + `iter_rows(values_only=True)`）。
  比对时 `/tmp/x` 在 Git Bash 与 Win32 Python 里路径不通，用 `C:/Users/dell/AppData/Local/Temp/`。
- **前端文案一律繁体**（`check_trad.py` 扫 `app/web/app.js`，简体注释会让 F 闸失败）。
- ⚠️ **改了 UI 形状，旧断言会红**——那是断言过期不是 bug。把旧断言**升级成新形状的判据，
  别删**（改成 `.item` 这类更宽松的选择器，数字照样 >0，断言就废了）。

## 离线快照 / 联机离线一致性
- `dist/app.js` 就是 `app/web/app.js` 的拷贝，靠「有没有 `window.BOOKINDEX_DATA`」切换。
  **永远不要复制第三份前端。** 导出 `app/tools/export_static.py`
  （`--check` 查过期 / `--verify` 断 `db._narrow` 等价式与 `sents` 形状）。
- ⚠️ **响应体组装必须放 db 层**（`index_payload` / `person_payload` / `place_payload`），
  端点与离线导出共用同一份；放端点里就得让导出抄一遍，抄歪了离线版悄悄不一致**且不报错**。
- ⚠️ **大 JSON 写 `JSON.parse('…')`**，不要写对象字面量（15MB 字面量撑爆 V8 AST，jsdom 4GB OOM）。
- ⚠️ **别只读大 JSON 的文件头**：`sents` 一块 9.4MB，小键排在它后面，
  摳前几 MB 会把「明明导了」判成「缺」。读整份并匹配真形貌（`"pla":JSON.parse(`）。
- ⚠️ 关系图快照 key 用 `"%g" % conf`（`1:0` 不是 `1:0.0`）：对不上**不报错**，只是关系卡全空。
- ⚠️ **`location.hash` 规范化必须「守卫与解析吃同一份」**（`normHash`）。教训：两处共用同一个
  规范化值时必须都改，只改一处会把另一个坑从遮蔽下放出来。
- **凡是「按当前书作用域变化」的数字，一律让前端算**（`aliasScopeN` / `isFormerEra`）。
  离线路由 `offlineGet` 用 `person/([^/?]+)` 匹配，**查询串会被忽略**——后端收窄的话
  离线版拿不到等值结果，两边悄悄分叉且不报错。数据（byBook/eraRank/eraRange）后端给全。
- **常量漂移是同一类坏**：app.js 的 `ALIAS_KINDS`、`BOOKS[].era` 与库/后端必须一字不差
  ——错了不报错，只分错组/标错人。[14]/[15] 已用「正则抽 JS 常量 vs 库」门住。

## 地名侧（2026-10-03 起转向此，人名暂停）
**数据不缺，缺的是入口。** `places` 1575 · `place_mentions` **115,615** · 9 类
（县1370/郡66/国39/山27/外27/域21/川11/关8/湖6）· `era`+`summary` 100% 填满 ·
**无重名** · 地基比人物侧干净（单字国名抽查 10 条全对，没有「裸官职/帝号」那种歧义）。
`place_mentions` 与 `mentions` 结构**完全对称**，db 层照抄改名即可。

✅ **已做：检索 + 详情页 + 离线，一次做完**（检索与详情是同一件事的两半，拆开会制造不一致）
- db 层 `search_places` / `place_alias_list` / `place_profile` / `place_mentions` /
  `place_books` / `place_payload`；端点 `/api/search` 扩为 `{query,items,places}` + `kind`
  参数、`GET /api/place/{pid}`。前端地名段独立成卡、索引条目**直接进详情页**（不再绕人物
  搜索——那才是「点不動」的根因）、路由 `#/place/{id}`、`renderPlace` 与 `renderPerson`
  **刻意同构**。离线补 `pmen`/`plalias`/`plbook`（+3.2MB）。
- ⚠️ `readerState.pid` 改名 **`scope`**：它**只当布爾用**（「有没有筛选上下文」），
  人物页与地名页都往里塞 id。叫 `pid` 却存地名 id 是撒谎。

**地名侧还剩**：地名**没有「标错」入口**（P3-4 只做在人物页）。单字国名误标（秦 5420 /
楚 5030）目前只能人肉发现；要先想清「误标怎么判」，可能要人工清单 → 用户说了先不做。

## 关系数据
- 权威源 `workbook/relations.xlsx`；`relations` 表**建库后由 `apply_relations` 灌回**
  （先灌必丢）。规范 `(a,rel,b)` = **「a 是 b 的 rel」**，长辈/夫/兄那一侧在 `a`；
  只存规范边，`REL_INVERSE` 拒绝反向双写。**去重判据用 (a,b,rel)，不能用 rel_id**（会撞车）。
- `rel_id=md5(a|b|rel|era|book)`；`confidence` 由 `derive_confidence` **派生**（无证据压 0.4）。
  ⚠️ 边起点叫 `source`，关系来源改叫 **`origin`**（同名键后者无声覆盖前者）。
- **证据判据只有一条：句子里明说了才算，共现一律不算**（子表 `relation_evidence`，一对多）。
  展现层三张表别混：`REL_TABLE`（类型/对称）/ `REL_INVERSE`（反向边）/ `CALL_INVERSE`
  （反向称呼，带性别变体 `父→(子,女)`）。页面靠 `rel_view` 换算。
- 抽取只收**显式关系词**，**禁止共现出边**；**裸帝号一律不自动落** → 进人工清单判。
- ⚠️ `relations.py revoke --rel-id` 会**一次误伤多行**（xlsx 同 rel_id 有 dead+active
  两行），要精确作废按「行号 + (a,b,rel)」改状态列。
- ⚠️ `relations.py check` 的退出码：只有 `check` 子命令的返回值该变成退出码，
  apply 返回「灌入条数」不能当退出码（返回 99 会被当成失败）。
- ❌ **不做**：从 96,336 句正文大规模抽关系（无标注数据、误判画成实线误导、无上限）。

## 审查规矩
关系数据审两次，第二次换**不参与开发的会话**且**只准它写那一份报告**；判据是
「故意注入错误，断言必须变红」。**不可再生的审定数据，先问它落在哪个会被删重建的产物里。**

## 当前待办（docs/31 §四）
1. **同名合并 17 组 / 35 人**（⚠️ 只能用户本人看原文拍板，AI 只出取证清单）
   + `p_liuyan_sg`/`_ys` 重复 pid
2. 关系边 `book` 列补全（⚠️ **卡点：`rel_id=md5(a|b|rel|book|era)`，填 book 会改变 rel_id**
   → 重算就要迁移 39 行证据。实测 99 边仅 31 有据：29 条单书可机械补，2 条跨书，68 条无据。
   **取舍要用户定**）
3. 人工清单剩 7 条（要先补 6 个库里没有的人）
4. ~~文档 01–18 数字治理~~ ✅ 只做了便宜的一半（横幅已挡住误读，逐份核对没做）
5. ✅ 网页「标错」入口（P3-4）——⚠️ **nth 只能后端算**（前端序号 ≠ 全句序号，
   实测 nth=3 / 前端 2，算错改到别人头上且不报错）
6. ✅ 地名检索 + 详情页 + 离线（2026-10-03 晚）
7. ❌ 地名「标错」入口（需先设计误标判据）
