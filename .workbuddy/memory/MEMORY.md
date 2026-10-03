# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> 施工入口 `app/DEV.md`；路线图 `docs/31`；现状 `docs/30`；审查范例 `docs/32`。
> **别读 docs/01–18（数字打架）**。本文件只留「动手前必须知道的约定与坑」，阶段史见 git log。

## 是什么 / 三条红线
离线 Python 管线 + 本地网页的**古籍实体索引**（不是全文检索）。五书 564 篇。旧静态版 `web/` **已冻结**；
日常 `app/`（FastAPI + 8800）；离线快照 `dist/`。`app/` 与 `pipeline/` **刻意不互相 import**，只在 JSON/DB 交汇。
1. **单向数据流**：`workbook/*.xlsx` 只能人写，pipeline 只读。要写 →「写新版本 + 报差异」。
2. **句子主键是稳定 uid** `md5(chapter|para|seq)[:12]`（**三参数，不含原文**）。拆→前半继承，并→merged，删→dead，**不物理删**。⚠️ **实现共五处**（`common.stable_uid` / `build_index_db.make_uid` / `overrides.uid_of` / `verify_p3._uid_of` 一致；**`build_workbook.make_uid` 是四参数含 text，与线上不一致**）。改一处改五处。
3. **规则进代码，数据进表格**：GENERIC_MANUAL / CONTEXT_RULES / SCOPED_ALIASES / BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS 是代码；PERSONS 数据在 xlsx。

## 已拍板的方向
- **小程序取消**；新能力只长在 `app/web/`。**不再接新史书**。编辑深度**封顶 b 档**（拆/并/弃句），改原文不做。
- **裴注/晋书旧史注是独立账本**（`db.person_notes_payload`，联机离线共用）：**不入库、不进 mentionCount**（注文 `pseq` 是段号）；视觉青灰，分量标【裴N】**不相加**。
- **Excel**：persons/places/chapters/overrides 各一 sheet，**只有 sentences 按书分**；「按书看」用只读布尔列 `in_sj…in_js`，**不要拆 sheet**（人物是跨书实体）。
- 算法三层（build 切分 / annotate 匹配·泛称 / 前端 scope）**不推倒**，改质量 = 改词典与守卫。
- 别名只写**繁体**；裸官职、裸帝号**禁止**进单人 core（走 GENERIC）；跨书同人**只扩 books 并集**，禁止新建 `p_xxx2`。
- 文档不写死统计数字——「以当次输出为准」+ 给取数命令。

## 环境与命令
- ⚠️ **python 必须用系统 3.12.10**（`C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe`）；托管 3.13.12 **没装 opencc**，`check_trad.py` 会假失败。
- 回归 `bash scripts/run_all.sh`（约 280s）。⚠️ **跑重建前必须先停 8800**（Windows SQLite 被占 → 退出码 1）。
- ⚠️ **重标注一律走 `app/tools/rebuild.py`**（~40s）；annotate 四步连跑。全量重建 ~34s。
- ⚠️ `curl` 加 `--noproxy '*'`。**断言前先确认端口空着**。`verify_p3` 单跑 4–5 分钟，**长断言配快速版**（`verify_p3_overrides.py` / `verify_p3_place.py`，15s）。
- 一次性脚本归 `pipeline/_scratch/`，**勿用 `python -c`**（PowerShell 吞引号）。根目录 4 字节 `blat` 用 `pipeline/_clean_root_blat.py --apply` 清。⚠️ **别往 .gitignore 写文件名规则**（会误伤 `_scratch`）。⚠️ `%TEMP%` **间歇性不可用**，症状瞬时，重跑就好。

## ⚠️ 数据形状（同一类坑反复踩，一律自动探测）
- **xlsx sheet/列名自动探测** → `_pick_sheet(wb, need_cols)`：`persons.xlsx` 表叫 **`人物`**；列 **`dynasty`** 不是 `era`；主键 **`id`** 不是 `pid`。
- index.db：`books` 主键 **`code`**；`relations` 两端 **`person_a`/`person_b`**；`mentions` **没有 `book` 列**（按书要四跳）。book-data 的 mark = `{s,e,pid,tier,alias}`；「在书分布」用 **`byBook`**。
- 不变量：`person_aliases` 的 **`n == Σ byBook`**（[14] 守）；前端 `BOOKS[].era` 常量**必须与库一致**（[15] 守，`sj` 通史为 NULL）。
- **`place_aliases`**（2026-10-03，2525 条）：`{place_id,seq,w,n,by_book}` + **`PRIMARY KEY (place_id,w)`**。必须有——`places.name` 与 `trad_name` **逐行相同**，简体名只在 book-data 的 `aliases` 里。
  ⚠️ **写法集合必须「登的 ∪ 语料实测的」**：只取 `places[].aliases` 会漏 61 种语料里真用的写法（`河閒` 96/`雒` 89/`關内` 41…）→「按原文写法搜不到」+ `Σn ≠ COUNT(place_mentions)`。**「登了哪些」与「用了哪些」是两个集合。**
- ⚠️ `pipeline/verify.py` 的 `ROOT` 是**字符串**（`ROOT / "x"` TypeError）。⚠️ **大 JSON 一律走 `common.write_json`**（原子写）。

## ⚠️ 断言铁律
- 每修一个坑加一条断言，基线**只许升不许降**。改完必须「**注入错误 → 变红 → 还原 → 变绿**」。
- **红线断言要断在「会被打破的那一层」**；**端点层必须真打一次 HTTP**（出过「db 全绿、端点 500」）。
- ⚠️ **恒真断言是这一类坏里最贵的**：`all()` 对空列表返 True、宽松选择器（`.item` 混进人物条目）数字照样 >0、`ms[i]` 不求值。**每条集合类断言都要问「样本为空时它是什么结果」。**
- **前端加了块，后端也要加断言**。**断言自己造的数据要自己收走**（放 `finally`；清理函数**不能只收 dead 行**——崩溃留下的恰恰是 active 行）。
- **断言红了 ≠ 数据错了**，先看它断的那批是什么。
- ⚠️ **「是否已生效」这类状态不在数据里，只能算**（`overrides.xlsx` 的行永远 active）。不算 → **界面骗人且不报错**。→ 凡是「行留着但状态会变」的表都问一句「这状态是存出来的还是算出来的」。
- ⚠️ **前端拿到 xlsx 读回的值必须先归一**（`17.0` vs `17`）→ 拼 key 对不上、**徽章静默消失**。`db._as_int` 与 `overrides._int_or_none` 两处都要。
- ⚠️ **改数据形状必配断言**（给 `sents` 加字段时有三处 `enumerate(sents)` 要同步，漏改 → `dist/` 留旧档**还能打开**，最难发现）。
- ⚠️ **批量改 pid 会被 diff 计两次**（既进 `added` 又进 `pid_changed`）→ 先核对 `added` 桶。

## UI / 测试
- ⚠️ **UI 测试写错时症状是「等不到」不是报错**：原文层在 `#readerBody`；人物索引条目 `.item[data-name]`、**地名条目 `.item[data-place]`**（`.row[data-*]` 是搜索结果行）；**检索靠点按钮**（`qEl` 只绑 keydown）；测试环境用取到的 `doc`。
- ⚠️ **等待条件必须是「这一屏独有的东西」**——四处同源踩坑：① 等 `.person-head .name`，**检索页也有** → 断言读到错误的屏；② 上一块留下同类元素（离线搜「鴻門」留下地名行——它本就是關隘）→ 量到**残留**，断言恒真；③ 同一段代码在文件里**出现多次**（`offPerson`/`offPlace` 都有 `CHAPT[s[1]]`）→ 注入按顺序 `replace(...,1)` 改的是第一处，**注入没生效却以为断言没用**；④ 「等不到」的假失败常来自把「当前数据的偶然」写进条件。修法：等该页独有标记（`.sent[data-place]`）+ **先 `out.innerHTML=""` 清屏** + 判据写死内容 + 注入点用**上下文边界**（`index("function offPlace(")`）定位。
- ⚠️ **测试块之间要收尾上一块的现场**（原文层没关 → 「点句→原文层」**假通过）。**注入要能优雅变红**（traceback 会让整段 20 条全灭 → 要能提前收工并记一条红）。
- ⚠️ `waitFor` **返回布尔不是元素**。`location.hash` 设成同值**不触发** hashchange（先跳别的路由）。
- ⚠️ **UI 测试真点「写入」就脏权威源** → 沙盒变量 **`BOOKINDEX_OVERRIDES`**（run_all 指向 `data/index/overrides.ui-test.xlsx`）。每步做空值保护（`if (el) click(el)`）。
- ⚠️ **后台服务用 `&` 起会被回收**，必须 `run_in_background: true`（不带 `&`）。症状是 UI 测试**大面积 0 条**——**先怀疑服务死了**。
- ⚠️ **openpyxl 重存会改 xlsx 字节**（内容逐行相同）：**先逐行比对再决定还原**（`git show HEAD:f` + `iter_rows(values_only=True)`；路径用 `C:/Users/dell/AppData/Local/Temp/`，`/tmp` 在 Git Bash 与 Win32 Python 不通）。
- **前端文案一律繁体**。⚠️ **改了 UI 形状旧断言会红**——那是断言过期，**升级成新形状的判据别删**。

## 离线快照 / 联机离线一致性
- `dist/app.js` 是 `app/web/app.js` 的拷贝，靠「有没有 `window.BOOKINDEX_DATA`」切换。**永远不要复制第三份前端。** 导出 `app/tools/export_static.py`（`--check` 查过期 / `--verify` 断形状）。
- ⚠️ **响应体组装必须放 db 层**（`index_payload`/`person_payload`/`place_payload`），端点与离线导出共用；放端点里就得让导出抄一遍，抄歪了**悄悄不一致且不报错**。
- ⚠️ **`counts` 要给每块数据各记一份**（`place_mentions`/`place_aliases`/`place_books`）：三块能**各自独立坏掉而总数不变**（plalias 空 → 简体检索失明），只比一个键则 `--check` 判成「同步」。
- ⚠️ **大 JSON 写 `JSON.parse('…')`**（字面量撑爆 V8 AST）。⚠️ **别只读文件头**（`sents` 9.4MB 排在前面，摳前几 MB 会把「明明导了」判成「缺」）→ 读整份匹配真形貌。
- ⚠️ 关系图快照 key 用 `"%g" % conf`；⚠️ **`location.hash` 规范化必须「守卫与解析吃同一份」**（`normHash`）。
- **凡是「按当前书作用域变化」的数字，一律让前端算**（`aliasScopeN`/`isFormerEra`）：离线路由会**忽略查询串**，后端收窄的话两边悄悄分叉。数据后端给全。
- **常量漂移是同一类坏**：app.js 的 `ALIAS_KINDS`/`BOOKS[].era` 与库必须一字不差（[14]/[15] 门住）。

## 地名侧（2026-10-03 起转向此，人名暂停）
**数据不缺，缺的是入口。** 1575 地 · `place_mentions` **115,615** · 9 类 · `era`+`summary` 100% · **无重名** · 单字国名抽查标注基本都对（没有人物侧「裸官职/帝号」那种歧义）。`place_mentions` 与 `mentions` **完全对称**，db 层照抄改名即可。
✅ **已做**：检索 + 详情页 + 离线一次做完（`search_places`/`place_payload`/`/api/place/{id}`；索引条目**直接进详情页**，不再绕人物搜索；`renderPlace` 与 `renderPerson` **刻意同构**；路由 `#/place/{id}`；离线补 `pmen`/`plalias`/`plbook`）。⚠️ `readerState.pid` 改名 **`scope`**（它只当布爾用，人物页与地名页都塞 id）。
❌ **还剩「标错」入口**：地名命中句**没有**标错按钮是**遗漏不是设计**（`renderPlace` 没渲染 `data-s/e/surface`），但要先设计误标判据（一个 surface 可能正当指向多个地名）→ 用户说了先不做。

## 关系数据
- 权威源 `workbook/relations.xlsx`；`relations` 表**建库后由 `apply_relations` 灌回**（先灌必丢）。规范 `(a,rel,b)` = **「a 是 b 的 rel」**；只存规范边，`REL_INVERSE` 拒绝反向双写。**去重判据用 (a,b,rel)，不能用 rel_id**（会撞车）。
- `rel_id=md5(a|b|rel|era|book)`；`confidence` 由 `derive_confidence` **派生**。⚠️ 边起点叫 `source`，关系来源叫 **`origin`**（同名键后者无声覆盖前者）。
- **证据判据只有一条：句子里明说了才算，共现一律不算**（子表 `relation_evidence`）。展现层三表别混：`REL_TABLE`/`REL_INVERSE`/`CALL_INVERSE`（反向称呼带性别变体）。
- 抽取只收**显式关系词**，**禁止共现出边**；**裸帝号不自动落** → 进人工清单。
- ⚠️ `relations.py revoke --rel-id` 会**一次误伤多行**（同 rel_id 有 dead+active），要精确作废按「行号+(a,b,rel)」。⚠️ 只有 `check` 的返回值该当退出码（apply 返回条数会当失败）。
- ❌ **不做**：从 96,453 句正文大规模抽关系。

## 审查规矩
审两次，第二次换**不参与开发的会话**且**只准它写那一份报告**；判据是「故意注入错误，断言必须变红」。**不可再生的审定数据，先问它落在哪个会被删重建的产物里。** 范例见 `docs/32`（3 个 P0 全是断言缺口，P1-1 是真功能缺陷）。

## 当前待办（docs/31 §四）
0. ⚠️ **全项目独立审查（docs/33 数据层 / docs/34 服务端与前端）已完成，4 条 P0 待决**：
   - **P0-甲 标色标错字**（`app.js` 的 `markSentence` 用 `indexOf` 找第一处，库里给的是第 `s` 处；
     实测 182,128 条命中里 **8,319 条标错**，一句内多次出现时指错语境）→ 改用 `m.s`/`m.e` 定位
   - **P0-乙 注文「讀全篇 ›」与明细行是死按钮**（渲染了 `data-chapter` 但点击分派里没分支）
   - **P0-丙 联机/离线命中数口径相反且无提示**（搜索卡 2064 / 详情页 200，无分页无提示）→ 需用户定交互
   - **P0-丁 `sentences-sj.xlsx` 的 uid 是旧四参数**（全量 22104 行逐行不符，`overrides.xlsx` 目前 0 行还没人踩）→ 要不要重算属**不可再生数据**决策
1. **同名合并 17 组 / 35 人**（⚠️ 只能用户本人看原文拍板）+ `p_liuyan_sg`/`_ys` 重复 pid
2. 关系边 `book` 列补全（⚠️ **填 book 会改 rel_id** → 要迁移 39 行证据。99 边仅 31 有据：**取舍要用户定**。
   ⚠️ **审查发现 era 也恒空、且 era/book 都进 rel_id → 两件事必须合并成一次做**，否则要迁移两次证据）
3. 人工清单剩 7 条（要先补 6 个库里没有的人）
4. ~~文档 01–18 数字治理~~ ✅ 只做了便宜的一半（横幅挡住误读，逐份核对未做）
5. ✅ 网页「标错」（P3-4）——⚠️ **nth 只能后端算**（前端序号 ≠ 全句序号）
6. ✅ 地名检索 + 详情页 + 离线 · ✅ 独立审查整改（`docs/32`）
7. ❌ 地名「标错」入口（需先设计误标判据）
