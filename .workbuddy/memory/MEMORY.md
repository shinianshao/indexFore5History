# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> **新开发请优先看 `app/DEV.md`**（2026-09-27 起）。本文件是长期约定与历史坑，
> `app/DEV.md` 是当前施工的单一入口（三条红线 / 施工顺序 / 常用命令 / 取数命令）。
> 完整方案推演在 `docs/21`，复盘在 `docs/22`。

## 项目是什么
离线 Python 管线 + 本地静态网页的**古籍实体索引**（不是全文检索）。
五书：史記 130 / 漢書 109 / 後漢書 130 / 三國志 65 / 晉書 130（含载记 30）= 564 篇。
入口 `web/index.html`；管线 `python pipeline/run_pipeline.py`。

## 用户已拍板的方向性决策
1. **小程序彻底取消**（2026-09-26 终局）。`docs/01` 的 `miniprogram/` 与云托管 `server/`
   从未建立，不再重启。改为「**本地索引 + 可编辑数据库**」，方案见 `docs/21`。
   现有静态网页**保留**作为发布/分享产物，不做替换。
2. **不再接新史书**（2026-09）。下一阶段只做：抽查检索结果 → 修词典/守卫/泛称 → 断言回归。
3. 裴注 / 晋书旧史注是**独立账本**，不进 `mentionCount`；UI 开启时合计并标【裴N】。

## 版本控制约定（2026-09-25 建立）
- 仓库已 git init，本地身份 `bookindex-dev / dev@local`（仓库级，非全局）。
- **判据：凡 `pipeline/*.py` 会覆写的文件一律不入库。**
  已忽略：`data/raw/` `data/corpus/` `data/index/` `data/dict/people.json`
  `data/dict/places.json` `web/*-data.js` `*.bak` `pipeline/_*.json`。
- **不可再生的手工资产必须入库**（丢了补不回来）：
  `data/dict/books.json`、`data/dict/volumes/*.json`（五书篇名表，人工审定工作量最大）、
  `data/dict/alias-rules.json`、`pipeline/build_dict.py`（PERSONS/CHAPTER_OWNERS 唯一来源）、
  `pipeline/build_places.py`（PLACES 唯一来源）、`web/app.js`、`web/index.html`。

## 改动时的铁律
- 算法三层（build 切分 / annotate 匹配·泛称 / 前端 scope）**不推倒**，改质量 = 改词典与守卫。
- 每修一个坑，`verify.py` **加一条断言**，基线只许升不许降（条数以 `--check` 末行为准）。
- 别名只写**繁体**；裸官职、裸帝号/王号**禁止**进单人 core（走 GENERIC 泛称）；长名优先。
- 跨书同人**只扩 `books` 并集**，禁止新建 `p_xxx2`，禁止后表覆盖前表。
- 改词典只跑 `annotate*` 子集；**轮末才全量** `run_pipeline`。
- 复杂清洗脚本写 `pipeline/_*.py`，勿用 `python -c`（PowerShell 会吞引号/正则）。
- **文档不写死统计数字**（人数/断言数/命中数）——一律「以当次输出为准」并给出取数命令。
  历史教训：docs 里 74/75/79 三个数打架，实际 81；「2169 人」实际 2013。
- **一次性脚本归 `pipeline/_scratch/`**，判据「下一轮还会不会用到」。
  移动时必改两处：① `ROOT = Path(__file__).resolve().parents[1]` → **`parents[2]`**（多一层）；
  ② 导入 `common`/`trad` 的要加 `sys.path.insert(0, 父目录)`。详见 `pipeline/_scratch/README.md`。

## 泛称判定的层级（2026-09-25 新增第 ⓪ 级）
`annotate.resolve_generic` 的梯子现在是：
**⓪ ctxRule（上下文硬证据）→ ①owner → ②related → ③sentence → ④paragraph
→ ⑤chapter → ⑥era → ⑦guess**。
- ⓪ 由 `build_dict.GENERIC_CONTEXT_RULES` 提供：年号 / 谥号 / 亲属称谓。
  ⚠️ **必须写在「按书 narrowing」之前**——写反了硬证据会被书作用域挡掉
  （第一版就是写反的，元帝仍落曹奐 46 处；改对后降到 6 处且全是景元/咸熙那几处）。
- `target=None` 的规则表示「这里不是这个人」（如「高祖…曾祖」亲属用法）→ 返回 `none`。
- 修裸短名的优先顺序：**补长名 > 分书收束候选 > ctxRule > 动 default**。
  动 default 会误伤真追述，是最后手段。

## 补人的规矩（类传/附传，2026-09-25 建立）
- 捞人句式：`X字Y`（准）；`X，Y人也`（噪声大，生成器 `--zi-only` 默认关掉）。
- 链路：`_gen_class_fill.py --all --zi-only` → **`_class_fill_prep.py` 清洗**
  （剔噪声 + 避 pid 冲突）→ `_apply_persons_fill.py <计划路径>`。
- **自动抽必出误抽，人工一定要看原文**后再入库。已剔除的四类：
  官名+名（京兆尹防）、动宾（甄豐校文字部）、复姓被截尾（觟陽鸿→陽鴻）、
  亲属限定语+名（安孫遂，安孫=田安之孫）。
- **`books` 只给检测到的那本书**，不扩。体检 `pipeline/_probe_class_leak.py`：
  书外漏召里绝大多数是**同名异人**（張溫 hhs/sgz、張玄 hhs/js、魏桓 sj）
  和**短语陷阱**（史漢的「何曾」是副词），靠扩 books 消必然引入误挂。
  现有例外只有一条：`build_dict.py` 里「sgz-only 一律扩含 js」（三国人物在晋书大量追述）。
- 异体字（鐘/卹/沖/鑒/説/勛）会触发 C 闸 → 登记进 `check_trad.py` 的
  `TRADNAME_EXCEPTIONS` **第 ③ 类**（以语料写法为正名），**不要反过来改语料**。

## 回归链（优先用一键脚本）
```bash
bash scripts/run_all.sh            # 断言 → 字面层 → UI 四套（约 50 秒）
bash scripts/run_all.sh --full     # 追加 _ui_sweep.js 全量扫描（慢）
bash scripts/run_all.sh --no-ui    # 只跑 Python 侧，改词典时的快速回路
```
⚠ **python 必须挑装了 opencc 的那个**：本机是**系统 Python 3.12.10**
（`C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe`）。
PATH 上第一位的托管版 3.13.12 **没装 opencc**，拿它跑 `check_trad.py` 会假失败。

手工等价步骤（脚本失效时才用）：
```
python pipeline/verify.py --check        # 断言基线
python pipeline/check_trad.py            # A–G 七道字面闸
# UI 需先起 http.server 8770，且设 NODE_PATH=C:\Users\dell\.workbuddy\binaries\node\workspace\node_modules
pipeline/_ui_test.js / _ui_test_books.js / _ui_test_places.js / _ui_csscheck.js
```

## 人工判断清单的规矩（2026-09-25 用户拍板，以后都这么办）
- **条目必须自带四项证据**：归属分布+tier 构成、原文上下文（前后各 14 字）、候选人的朝代、当前 default。
  只有统计数字的清单用户判不了——旧 docs/17 因此作废重写。
- **一律生成器产出，禁止手敲**：
  ```bash
  python pipeline/_gen_review_items.py --list                    # 挑：按 guess 处数降序
  python pipeline/_gen_review_items.py --alias 武帝 --book js --per 6 \
      --out "docs/17-条目-<批次>.md"
  ```
- 模板在 `docs/17-待办-人工判断清单.md` §二（生成器格式必须与之对齐）；
  批次文件 `docs/17-条目-*.md` 是作业纸，判定回填后结论进 §五台账、文件可删。
- 判不了就勾**未知**（`none`/`guess`），不要为填完而硬归。
- 生成器要点：只扫规范形（防简繁重复计数）；「被更长别名接管」≠漏标
  （漢高祖 由长名命中是正确行为）；上下文按 pid 轮转取样。

## 已知残留（未决）
- 待判批次：`docs/17-条目-晋书帝号.md`（高祖/武帝/元帝/惠帝/明帝 @js）。
  用户 2026-09-25 说「先不急」，P1 收尾后再回来。
- guess 池规模以 `--list` 当次输出为准；晋书裸「武帝」仍有汉武帝追述（属合理追述）。
- guess 池下一个该看：周公、趙王、關內侯、文王、梁王、常山王。
- 类传补人的**书外漏召**（逐条人工判，少数如 石苞@sgz、杜預@sgz 是真漏）。
- 表字尊称命中≤10 的长尾（`_probe_alias_gaps.py`）。
- 前端 `app-data.js` 31.9MB 整包注入（`docs/03` 决策的按书拆分从未实施）。
- 文档 01–18 数字互相打架，待治理；已治理的有 15 / 16 / README（改为「以实跑为准」）。

## 「AI 概率判定闭环」已成为通用工作法（2026-09-26 建立）
任何「这堆东西对不对」的问题都照这个四件套：**取证 → 判 → 落 → 断言**。
- 取证生成器产出 JSON，每条必须自带**可计算代理信号 + 语料上下文**，空 `ai` 字段。
- 判定写回独立 verdicts 文件，**数据重生成后判定不丢**。
- 应用器改 `build_dict.py`（唯一来源），默认预演、`--apply` 才写。
- 每轮结论必有 `verify.py` 断言。
已成链路：`_gen_ai_batch.py` → `_ai_show.py` / `_ai_judge.py` → `_ai_autorule.py` → `_apply_ai.py`
（表字/泛称）；`_gen_name_batch.py` → `_apply_names.py` + `_name_plan.txt`（人名纠正）。

## 人名纠正的判据（2026-09-26）
- **判「是不是人名」必须给上下文**，光靠后缀正则必炸：N1 会把周文王/齊桓公也打成问题；
  默认issing庐手工收的名字都是真人（張耳/李斯/韓遂），**虚词尾闸只对自动补齐条目开**。
- 自动补人有两类错，治法相反：
  - **切词噪声**（刪条目）：赵分/单于既/王如故/公子+虚词、非人实体（荊門/倉部/盧水胡）、
    官职粘连（相國何 → 实体是蕭何）
  - **名字被切短**（补长，不删）：原文写的是公孫戎奴/公子開方/公子曼滿，
    补长后**旧短串仍留作别名**（别处真短写法仍能收）
- PERSONS 元组被其他结构引用时的判据：`PERSON_BOOKS_*` 是随行书域表，删人可以连坐清掉；
  其余语义结构（SCOPED_ALIASES / GENERIC_MANUAL / BOOK_CANDIDATES）有引用就**不许删**。
- 「身份外壳」不等于错：旗舰 agreed 含得下一个真本名才剥（越王勾踐→勾踐）；
  章德竇皇后/魯元公主/鉤弋夫人 这种**没有别的本名**的，壳就是正名，不动。
- ⚠️ **一次性脚本别忘了写 `if __name__ == "__main__": main()`**。已经踩过一次：
  跑起来安安静静退出 0、什么都没改，最难查。

## 新方向：本地索引 + Excel 权威源（2026-09-26 拍板，docs/21）
用户诉求：索引要详细到「方便查找确认」，且**能编辑、编辑后能更新索引**。
四项选择：①Excel 做权威源，源码只留规则 ②Excel 看图 + 本地网页查明细
③编辑深度到「词典 + 单条命中 + 句子切分与篇名」④旧静态网页保留。

一句话：**规则进代码，数据进表格；表格归人写，pipeline 只读它。**

实测基础（决定了方案，别再猜）：句子 96,468 / 命中明细 **66,782**（不是二三十万）
/ 人物 2,276 / **全量重跑 annotate 只要 12 秒**。
→ **不做增量更新**，改一行表格就 12 秒全量重建。这条省掉大半工作量。

三条红线（写进任何实现前先背一遍）：
1. **单向数据流**：Excel 只能人写，pipeline 只读。凡 pipeline 想写 Excel 的地方
   一律改成「写新版本 + 报差异」，否则重建会冲掉用户的审定。
2. **句子主键必须是稳定 uid**：现在是位置键 `sj-001-0002-001`，一旦可编辑切分
   就会位移，连带打垮 66,782 条命中外键 + 手写 override + 快照 diff。
   拆→前半继承原 uid / 后半新 uid；合并→留第一个标 merged；删→标 dead 不物理删。
   这事必须 P0/P1 做对，事后补＝全量迁移。
3. **规则与数据分离**：GENERIC_MANUAL / GENERIC_CONTEXT_RULES / SCOPED_ALIASES /
   BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS 继续是代码（适合 git diff，
   现有 `_apply_ai.py` 继续改它）；PERSONS 数据搬 xlsx。

编辑深度三档：a 篇名元数据（P1）/ b 拆分合并删句（P4）/ c 自由改原文（**建议封顶在 b**，
真要改应回去改数据源；给 c 留「整句弃用 dead」的逃生口即可）。

回归升级：verify.py 断言保留（只许升不许降），**新增快照 diff**——每次重建自动报
新增/消失/改归三类变化，比断言数字直观，正对「方便查找确认」的诉求。

预估：~4,050 行，AI 侧 120–175 万 token（±50%）；P0/P1/P5 属确定性搬运、
脚本自己跑 AI 只校对的话可压到 70–110 万。

⚠ **annotate 必须四步连跑**：annotate.py → annotate_pei.py → annotate_js_note.py
→ annotate_places.py。只跑第一步会把裴注账本冲掉（句子 96,468 → 48,461），
2026-09-26 已踩过一次并补回。

Excel 组织（2026-09-26 定）：persons / places / chapters / overrides 各 1 个 sheet，
**只有 sentences 按书分 sheet**。理由：人物地名是**跨书实体**（劉邦五书都有），
按书切会双写漂移；句子天然属一篇，且 96k 行必须拆。拼音列只读。

网页双轨：**FastAPI 做日常查询+编辑，静态版做分享产物**。命中涨到 15–20 万后
静态全量注入（现 32MB）必死，所以日常工具不能建在静态方案上。

**编辑深度封顶在 b 档**（拆/并/删句），c 档改原文**不做**，留「整句弃用 dead」逃生口。

**「按书看」≠「按书存」**：想要单看某本书，用只读布尔列 `in_sj…in_js` 筛选，
**不要拆 sheet**——人物是跨书实体，拆表会写重漂移。

## 前端与关系图（2026-09-26 提出，**待确认后实施**）
用户要「古典、一致、人性化」，并为**人物关系图 / family tree** 留接口。
详见 `docs/21` §12。**当前状态：只规划未动手。**

- **留接口主要是数据模型的活**：`persons` 表现在无任何关系字段，
  P1 必须把 `relations` 表建出来（可先空），否则将来做族谱要重扫全语料＝返工。
  字段：person_a/person_b/rel_type/rel/direction/**evidence_uid**/evidence_text/
  confidence/source/note。**`evidence_uid` 是硬要求**（关系属主观判断，没出处不敢信）。
- 种子线索：现有 summary 简介里前 400 条就有 23 条含「之子/之弟/之父/妻」，
  可自动抽候选 → 走 AI 判定闭环确认。
- 前端现状：`web/index.html` 已有 CSS 变量体系（--bg/--panel/--accent/--muted/--serif），
  基调已是暖灰褐（#b8b3a8 / #a2977f），书名走 --serif。
  **结论：沿用这套变量，静态版与 FastAPI 版共用，不搞两套视觉。**
- 待确认 5 问：关系范围 / 必须带证据句 / 图规模（建议单人局部，全局会成毛线团）/
  古典程度（竖排印章要不要，倾向克制）/ 族谱是否按朝代切。

Excel 侧依赖 `openpyxl` + `pypinyin`，已装进系统 Python 3.12.10（与 opencc 同环境）。
⚠️ 取「在书分布」要用 **book-data.json 的 `byBook`**，不是 people.json 的 `books`
——后者手工条目没写，会全空。

## P0 已完成（2026-09-28）：Excel 是权威源了
- `pipeline/persons_data.py` = PERSONS 种子数据（2347 行，从 build_dict.py 抽出）。
  `build_dict.py` 5332 → 2987 行**只留规则**（GENERIC_MANUAL / CONTEXT_RULES /
  SCOPED_ALIASES / BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS）。
- `build_dict.py` 的 `_load_persons()` **优先读 `workbook/persons.xlsx`**，
  缺文件才回退种子数据（回退会打印警告，不静默）。
- **权威源切换的三条纪律**（踩过坑才立起来）：
  1. `build_workbook.py` 必须只读**源数据** `persons_data.PERSONS`，
     不能从 `people.json` 倒推——否则形成 `build_dict → people.json → xlsx → build_dict` 循环。
  2. **导出时不预排序**。行序=源码编排顺序，读回原样采用；
     预排序会让 people.json 条目顺序改变、md5 不同。拼音只是给用户自己排序看的。
  3. 验证手段是 **people.json 的 md5 逐字节比对**——重构必须"行为完全不变"。
- 端到端已验证：改别名→生效 / 状态标 `dead`→条目消失 / 改回→md5 回基准。
- ⚠️ `build_dict.py` 的 `ROOT` 是**字符串**，别写 `ROOT / "path"`，用 `os.path.join`。
- ⚠️ 回归**默认端口 8790**（8770 被本机 VPN 客户端 iKuuuVPNCore 占着）。
- ⚠️ 写中文注释也要用**繁体**——check_trad 扫描 app.js 全文，简体注释会让 F 界面闸失败。

## P1 已完成（2026-09-28）：SQLite 索引库
`app/tools/build_index_db.py` → `data/index/index.db`（产物，可删重建）。
配套查询 `app/tools/query.py`（替代一次性 `_probe_*` 脚本）。
- 数据流**单向**：`xlsx（权威）→ build_dict → book-data.json → index.db`，
  **没有任何环节回写 xlsx**（红线 1）。
- **FTS5 中文分词是最大的坑**：unicode61 把连续汉字当一个 token，整句即一个 token，
  搜「項羽」只命中 2 句（实际 922 处）。解法：**按字切分入库** +
  查询按字切分 + **短语查询** `MATCH '"項 羽"'`。改后 413 句。
  **不要用 `tokenize='trigram'`**：要求查询词≥3 字，中文人名多为 2 字。
- `sentences.uid` 稳定主键，**优先复用库里已有的**（重跑全复用）。
  已知限制：按 (篇,段序,句序) 匹配，P4 支持编辑句子后要改成按文本内容匹配。
- mentions/aliases 是追加写入，**重跑会翻倍** → 改成「偷旧 uid → 删库 → 重建 → 复用」。
- `relations` 表已建（先空着），字段见 docs/21 §12.2。

命中容量基线：主账本 1.37 命中/句，别名补到 1.5–2 万时命中约 10–15 万（用户估
15–20 万是上限）。**命中不进 Excel**（它是派生数据），只在 SQLite/网页看。

## P1 进度（docs/16 §三）
- ✅ P1-a 裸短名错挂（长名 + 分书收束 + ctxRule）— 提交 a0e5a07
- ✅ P1-b 类传/附传长尾缺人（补 322 人）— 同轮完成
- 下一档是 P2：表字长尾 / guess 池 / 类传书外漏召

## P3 三决策（2026-09-28 用户拍板，计划见 docs/24）
1. **快照 diff 做到「落 SQLite」**：独立库 `data/index/snapshots.db`
   （**不能进 index.db**——它是可删重建的产物，快照放进去会被冲掉）。
   表 `snapshots` / `snapshot_mentions` / `diffs` / `diff_items`；跨库比较用 `ATTACH`。
   比较键 `uid+s+e+surface`；变化**四类**：added / removed / pid_changed / **tier_changed**。
   快照在**重建第一步、build_dict 之前**取（这样 diff 才含 override 效果）。
   **网页 diff 页本轮不做**；终端照打印。
2. **`overrides` 落 `workbook/overrides.xlsx`**（人/UI 写、pipeline 只读）。
   列分"录入时写"（uid/s/e/surface/nth/chapter/context/old_pid/old_tier）与
   "人写"（new_pid/action=reassign|drop|keep/status/note）。
   ⚠️ 脚本会填的列**只在录入那一刻写，重建绝不刷新**——否则重演 P0 冲掉权威源的事故。
   应用器 `apply_overrides.py` 在 annotate 四步**之后**、build_index_db **之前**跑，
   **不动 annotate 引擎**。
3. **静态版 `web/` 冻结**：只作分享产物，不再改视觉与交互；新能力只长在 `app/web/`。
   后续静态版 bug 的修复判据：**影响"能打开、能查"才修，否则留着**。

P3 动工顺序：1 一键重建 → 2 快照库+diff → 3 overrides+应用器 → 5 断言；
**P3-4（UI 写入口/diff 页）本轮不做**。

### P3 已交付（2026-09-28 夜）
`app/tools/rebuild.py`（一键重建，约 30–45s）/ `snapshot.py`（快照+diff）/
`overrides.py`（单条纠错）/ `verify_p3.py`（新链路断言 14 条）。
旧断言基线不变（108/108），people.json md5 回到基准。

**三个坑（都会"静悄悄出错"）**：
1. **两份快照互比恒为 0**——快照都在重建**前**取。diff 的「新」侧必须是
   **重建后的当前库**（`_load_live()`）。`diffs.new_id` 因此为 NULL，
   历史 diff 不能重算，只能翻 `diff_items` 明细。
2. **复原只跑 `annotate.py` 会丢 `places`**——地名是 `annotate_places.py` 加的。
   少了它 book-data.json 缺键，旧断言 `verify.py` 直接 `KeyError: 'places'`。
   **凡"重标注"一律走 `rebuild.py`（四步连跑）**，新链路同样守这条。
3. **subprocess 参数不能并成一个字符串**：`run("overrides.py apply")` 被当成
   含空格的文件路径 → 退出码非 0，却像"脚本失败"。参数必须分开传。

**两处实现偏差**（计划 vs 实际）：
- `reassign` 不改 tier，保留原 tier + 加 `override:1` 字段（不引入前端不认识的 tier 值）。
- 快照默认 **keep=5**（不是 20）：每份与命中数等行，20 份约 200MB。

**断言写法**：drop 的验证要**数条数**（一句常有同名多命中），
不能查"找不找得到"——移掉一条后仍找得到，会误判 drop 没生效。
