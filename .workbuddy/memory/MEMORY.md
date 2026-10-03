# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> 施工入口 `app/DEV.md`；路线图 `docs/31`；现状 `docs/30`；审查范例 `docs/32`/`33`/`34`。
> **别读 docs/01–18（数字打架）**。本文件只留「动手前必须知道的约定与坑」，阶段史见 git log。

## 是什么 / 三条红线
离线 Python 管线 + 本地网页的**古籍实体索引**（不是全文检索）。五书 564 篇。旧静态版 `web/` **已冻结**；
日常 `app/`（FastAPI + 8800）；离线快照 `dist/`。`app/` 与 `pipeline/` **刻意不互相 import**，只在 JSON/DB 交汇。
1. **单向数据流**：`workbook/*.xlsx` 只能人写，pipeline 只读。要写 →「写新版本 + 报差异」。
2. **句子主键是稳定 uid** `md5(chapter|para|seq)[:12]`（**三参数，不含原文**）。拆→前半继承，并→merged，删→dead，**不物理删**。⚠️ **实现共五处**（`common.stable_uid`/`build_index_db.make_uid`/`overrides.uid_of`/`verify_p3._uid_of` 一致；**`build_workbook.make_uid` 是四参数含 text，不一致**）。改一处改五处。
3. **规则进代码，数据进表格**：GENERIC_MANUAL / CONTEXT_RULES / SCOPED_ALIASES / BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS 是代码；PERSONS 数据在 xlsx。

## 已拍板的方向
- **小程序取消**；新能力只长在 `app/web/`。**不再接新史书**。编辑深度**封顶 b 档**（拆/并/弃句），改原文不做。
- **裴注/晋书旧史注是独立账本**（`db.person_notes_payload`，联机离线共用）：**不入库、不进 mentionCount**（注文 `pseq` 是**段号**不是 uid，与正文切分体系不同）；视觉青灰，分量标【裴N】**不相加**。
- 算法三层（build 切分 / annotate 匹配·泛称 / 前端 scope）**不推倒**，改质量 = 改词典与守卫。
- 别名只写**繁体**；裸官职、裸帝号**禁止**进单人 core（走 GENERIC）；跨书同人**只扩 books 并集**，禁止新建 `p_xxx2`。
- Excel 布局（persons/places/chapters/overrides 各一 sheet、**只有 sentences 按书分**、「按书看」用只读布尔列
  `in_sj…in_js` 不拆 sheet）见 `app/DEV.md`。

## 环境与命令
- ⚠️ **python 必须用系统 3.12.10**（`…\Python312\python.exe`）；托管 3.13.12 **没装 opencc**，`check_trad.py` 会假失败。Node `…/node/versions/22.22.2-3/node.exe` + `NODE_PATH=…/node/workspace/node_modules`。
- 回归 `bash scripts/run_all.sh`（约 280s）。⚠️ **跑重建前必须先停 8800**（Windows SQLite 被占 → 退出码 1）。重标注走 `app/tools/rebuild.py`（~40s，annotate 四步连跑）。
- ⚠️ `curl` 加 `--noproxy '*'`。**断言前先确认端口空着**。`verify_p3` 单跑 4–5 分钟，**长断言必须配快速版**（`verify_p3_overrides.py`/`_place.py`/`_mark.py`，各 ~15s）。
- 一次性脚本归 `pipeline/_scratch/`，**勿用 `python -c`**（PowerShell 吞引号）。根目录 4 字节 `blat` 用 `pipeline/_clean_root_blat.py --apply` 清。⚠️ **别往 .gitignore 写文件名规则**（会误伤 `_scratch`）。⚠️ `%TEMP%` **间歇性不可用**，症状瞬时，重跑就好。

## ⚠️ 数据形状（同一类坑反复踩，一律自动探测）
- **xlsx sheet/列名自动探测** → `_pick_sheet(wb, need_cols)`：`persons.xlsx` 表叫 **`人物`**；列 **`dynasty`** 不是 `era`；主键 **`id`** 不是 `pid`。
- index.db：`books` 主键 **`code`**；`relations` 两端 **`person_a`/`person_b`**；`mentions` **没有 `book` 列**（按书要四跳）。「在书分布」用 **`byBook`**。
- 不变量：`person_aliases` 的 **`n == Σ byBook`**（[14] 守）；前端 `BOOKS[].era` **必须与库一致**（[15] 守，`sj` 通史 NULL）。
- **`s`/`e` 是 Python 的 Unicode「碼位」下标**（不是字节也不是 UTF-16 碼元），`text[s:e]==surface` 全量 182,128 条成立。
  ⚠️ 前端**不能**用 `indexOf(surface)`（一句內多次出現會標第一處，實測 8319 條標錯），**也不能**裸 `text.slice(s,e)`
  （古籍含非 BMP 字如 `U+24CF9`，JS 碼元下標會偏 → **新造 63 條錯**）。正確做法 = `app.js` 的 `hitSpan` 三級回退。
- **`place_aliases` 写法集合必须「登的 ∪ 语料实测的」**：只取 `places[].aliases` 会漏 61 种语料里真用的写法
  （`河閒`/`雒`/`關内`…）→ `Σn ≠ COUNT(place_mentions)`。**「登了哪些」与「用了哪些」是两个集合。**
- ⚠️ `pipeline/verify.py` 的 `ROOT` 是**字符串**。⚠️ **大 JSON 一律走 `common.write_json`**（原子写）。
- ⚠️ **`dist/` 不在 git 里**（gitignore），且 `dist/app.js` 是 CRLF、`app/web/app.js` 是 LF → 比对要 `tr -d '\r'`。**同步只能靠重跑 `export_static.py`，别手工 cp。**

## ⚠️ 断言铁律
- 每修一个坑加一条断言，基线**只许升不许降**。改完必须「**注入错误 → 变红 → 还原 → 变绿**」。
- **红线断言要断在「会被打破的那一层」**；**端点层必须真打一次 HTTP**（出过「db 全绿、端点 500」）。
- ⚠️ **恒真断言是这一类坏里最贵的**，已踩的六种形态：
  ① `all()` 对空列表返 True；② 宽松选择器（`.item` 混进别类）数字照样 >0；③ `ms[i]` 不求值；
  ④ **断「终态」而不是「状态转移」**——前一步已把原文层打开，`contains("on")` 恒真，删掉分派照样绿（乙的注入验证抓出来的）。修法：**先 `ensureClosed()` 再断它变 on**；
  ⑤ **断「拼回原句」**（`indexOf` 必然满足）→ 断位置要断「mark 之前**恰好 s 個字**」，且**数碼位**（JS `Array.from(x).length`）不是碼元；
  ⑥ Python 里 `len(t)==len(list(t))` **恒成立**（str 是碼位序列）→ 判非 BMP 字只能用 `ord(c)>0xFFFF`。
  **每条集合/状态类断言都要问「样本为空、或前置状态已就位时，它是什么结果」。**
- ⚠️ **审查报告给的「建议改法」本身可能是错的**（P0-甲：报告建议直接 `slice(s,e)`，照做会新造 63 条错标）。**每条建议都要自己实测再动手。**
- **前端加了块，后端也要加断言**。**断言自己造的数据要自己收走**（放 `finally`；清理函数**不能只收 dead 行**——崩溃留下的恰恰是 active 行）。
- **断言红了 ≠ 数据错了**，先看它断的那批是什么。
- ⚠️ **注入脚本自身三个坑**（都亲自踩过）：① **备份只能在开头做一次**——`restore()` 里重备份会让连续注入「越还原越坏」，
  实测把一个分派**永久删掉**了而 trap 还报「成功」，还原后必须比对**字节** + grep 锚点，不能只看测试绿；
  ② **注入点要先 assert 锚点存在**——找不到时 Python 抛 ValueError 退出但脚本照报「✔ 变红」，等于把「注入没生效」
  和「断言抓到了」混为一谈；③ **注入后要跑导出**再跑离线测试，且要设 **`BI_UI_TIMEOUT`**（环境变量，优先于传入参数，
  见 `_ui_test_offline.js`），否则 `waitFor` 吃满 60s，一轮注入十几分钟。
- ⚠️ **「是否已生效」这类状态不在数据里，只能算**（`overrides.xlsx` 的行永远 active）。不算 → **界面骗人且不报错**。
- ⚠️ **前端拿到 xlsx 读回的值必须先归一**（`17.0` vs `17`）→ 拼 key 对不上、**徽章静默消失**。`db._as_int` 与 `overrides._int_or_none` 两处都要。
- ⚠️ **改数据形状必配断言**（给 `sents` 加字段时有三处 `enumerate(sents)` 要同步，漏改 → `dist/` 留旧档**还能打开**，最难发现）。⚠️ **批量改 pid 会被 diff 计两次**（既进 `added` 又进 `pid_changed`）→ 先核对 `added` 桶。

## UI / 测试
- ⚠️ **UI 测试写错时症状是「等不到」不是报错**：原文层在 `#readerBody`；人物索引条目 `.item[data-name]`、**地名条目 `.item[data-place]`**（`.row[data-*]` 是搜索结果行）；**检索靠点按钮**（`qEl` 只绑 keydown）；测试环境用取到的 `doc`。
- ⚠️ **等待条件必须是「这一屏独有的东西」**——四处同源踩坑：① 等 `.person-head .name`，**检索页也有**；② 上一块留下同类元素（离线搜「鴻門」留下地名行——它本就是關隘）→ 量到**残留**，断言恒真；③ 同一段代码在文件里**出现多次**（`offPerson`/`offPlace` 都有 `CHAPT[s[1]]`）→ 注入按顺序 `replace(...,1)` 改的是第一处，**注入没生效却以为断言没用**；④ 把「当前数据的偶然」写进条件。修法：等该页独有标记 + **先 `out.innerHTML=""` 清屏** + 判据写死内容 + 注入点用**上下文边界**（`index("function offPlace(")`）定位。
- ⚠️ **测试块之间要收尾上一块的现场**；**注入要能优雅变红**（traceback 会让整段全灭）。⚠️ **改 UI 会打进注释里的简体字/乱码**（`U+FFFD`）→ `check_trad.py` F 闸红，写完 `grep -c $'\ufffd'` 扫一遍。
- ⚠️ `waitFor` **返回布尔不是元素**（等完要重新取一次元素）。`location.hash` 设成同值**不触发** hashchange（先跳别的路由）。每步做空值保护（`if (el) click(el)`）。
- ⚠️ **UI 测试真点「写入」就脏权威源** → 沙盒变量 **`BOOKINDEX_OVERRIDES`**。
- ⚠️ **后台服务用 `&` 起会被回收**，必须 `run_in_background: true`（不带 `&`）。症状是 UI 测试**大面积 0 条**——**先怀疑服务死了，别急着改断言**。
- ⚠️ **两条相似路径要分别测**（`.item[data-place]` 索引页 vs `.row[data-place]` 检索页；离线 `offlineGet` vs 联机 `fetch`）。
- ⚠️ **openpyxl 重存会改 xlsx 字节**（内容逐行相同，`git diff` 看着像脏了）：**先逐行比对再决定还原**（`git show HEAD:f` + `iter_rows(values_only=True)`）。路径用 `C:/Users/dell/AppData/Local/Temp/`，`/tmp` 在 Git Bash 与 Win32 Python 不通。

## 离线快照 / 联机离线一致性
- `dist/app.js` 是 `app/web/app.js` 的拷贝，靠「有没有 `window.BOOKINDEX_DATA`」切换。**永远不要复制第三份前端。** 导出 `app/tools/export_static.py`（`--check` 查过期 / `--verify` 断形状）。
- ⚠️ **响应体组装必须放 db 层**（`index_payload`/`person_payload`/`place_payload`），端点与离线导出共用；放端点里就得让导出抄一遍，抄歪了**悄悄不一致且不报错**。
- ⚠️ **`counts` 要给每块数据各记一份**（`place_mentions`/`place_aliases`/`place_books`）：三块能**各自独立坏掉而总数不变**，只比一个键则 `--check` 判成「同步」。
- ⚠️ **大 JSON 写 `JSON.parse('…')`**（15MB 字面量撑爆 V8 AST，jsdom 4GB OOM）；**别只读文件头**（`sents` 9.4MB 排在前面）。
- ⚠️ 关系图快照 key 用 `"%g" % conf`（对不上**不报错**，只是关系卡全空）；⚠️ **`location.hash` 规范化必须「守卫与解析吃同一份」**（`normHash`）。
- **凡是「按当前书作用域变化」的数字，一律让前端算**（`aliasScopeN`/`isFormerEra`）：离线路由会**忽略查询串**，后端收窄的话两边悄悄分叉。数据后端给全。
- **常量漂移是同一类坏**：app.js 的 `ALIAS_KINDS`/`BOOKS[].era` 与库必须一字不差（[14]/[15] 门住）。
- ⚠️ 联机 `limit=200` 而离线给全量是**刻意差异·只多不少**（`export_static.py` 注释写明）→ **不是实现偏离**，但**UI 层自相矛盾**（搜索卡 2064、详情页 200，无分页无提示）= P0-丙。

## 地名侧（2026-10-03 起转向此，人名暂停）
**数据不缺，缺的是入口。** `place_mentions` 115,615 · 9 类 · **无重名** · 单字国名抽查标注基本都对
（没有人物侧「裸官职/帝号」那种歧义）。`place_mentions` 与 `mentions` **完全对称**，db 层照抄改名即可。
✅ 检索 + 详情页 + 离线已做完（`renderPlace` 与 `renderPerson` **刻意同构**）。⚠️ `readerState.pid` 改名 **`scope`**。
❌ **还缺「标错」入口**：是**遗漏不是设计**，但要先设计误标判据（一个 surface 可能正当指向多个地名）。

## 关系数据
- 权威源 `workbook/relations.xlsx`；`relations` 表**建库后由 `apply_relations` 灌回**（先灌必丢）。规范 `(a,rel,b)` = **「a 是 b 的 rel」**；只存规范边。**去重判据用 (a,b,rel)，不能用 rel_id**（会撞车）。
- `rel_id=md5(a|b|rel|era|book)`（⚠️ **book 与 era 都进去 → 补这两列必须一次做完**，否则迁移两次证据）；`confidence` **派生**。⚠️ 边起点叫 `source`，关系来源叫 **`origin`**（同名键后者无声覆盖前者）。
- **证据判据只有一条：句子里明说了才算，共现一律不算**。展现层三表别混：`REL_TABLE`/`REL_INVERSE`/`CALL_INVERSE`。
- 抽取只收**显式关系词**，**禁止共现出边**；**裸帝号不自动落**。⚠️ `revoke --rel-id` 会**一次误伤多行**（同 rel_id 有 dead+active），要精确作废按「行号+(a,b,rel)」。⚠️ 只有 `check` 的返回值该当退出码。
- ❌ **不做**：从 96,453 句正文大规模抽关系。

## 审查规矩
审两次，第二次换**不参与开发的会话**且**只准它写那一份报告**；判据是「故意注入错误，断言必须变红」。
**不可再生的审定数据，先问它落在哪个会被删重建的产物里。**
⚠️ **审查期间 `workbook/*.xlsx` 会因测试 purge 的 openpyxl 重存而显示 modified**——逐行比对确认相同再 `git checkout --`。

## 当前待办（docs/31 §四）
0. **全项目独立审查（docs/33 数据层 / docs/34 服务端与前端）4 条 P0**：
   - ✅ **P0-甲 标色标错字**（2026-10-03 修完）→ `hitSpan` 三级回退 + `verify_p3_mark.py`（7/7，注入三种坏写法全红）
   - ✅ **P0-乙 注文「讀全篇 ›」与明细行是死按钮**（2026-10-03 修完）→ 接入 `openChapter`（新增 `pseq` 跳段）+ 联机/离线各 4 条断言
   - ⏸ **P0-丙 联机/离线命中数口径相反且无提示**（**约定内部矛盾，矛盾在 UI 层**）→ 需用户定交互方案
   - ⏸ **P0-丁 `sentences-sj.xlsx` 的 uid 是旧四参数**（全量 22,104 行逐行不符）。⚠️ **审查报告说「不可再生、要用户拍板」是误判**：
     `build_workbook.py:376` 注释「純派生視圖，可無條件覆蓋」+ `.gitignore:71` 排除该表 + git log 无记录 → **可重生成，重跑 `python pipeline/build_workbook.py --books sj`**
1. **同名合并 17 组 / 35 人**（⚠️ 只能用户本人看原文拍板）+ `p_liuyan_sg`/`_ys` 重复 pid
2. 关系边 `book`+`era` 补全（⚠️ **两者都进 rel_id → 必须合并成一次做**，否则迁移两次证据。99 边仅 31 有据：**取舍要用户定**）
3. 人工清单剩 7 条（要先补 6 个库里没有的人）
4. ✅ 网页「标错」（P3-4，⚠️ **nth 只能后端算**）· ✅ 地名检索/详情/离线 · ✅ `docs/32` 整改
5. ❌ 地名「标错」入口（需先设计误标判据）
