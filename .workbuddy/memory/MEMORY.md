# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

> **施工入口是 `app/DEV.md`**（三条红线 / 施工顺序 / 常用命令 / 取数命令）。
> 本文件只放长期约定与历史坑。方案推演 `docs/21`，复盘 `docs/22`，
> 优先级表 `docs/16`，本轮计划 `docs/24`，关系审查 `docs/25`。

## 项目是什么
离线 Python 管线 + 本地网页的**古籍实体索引**（不是全文检索）。
五书：史記 130 / 漢書 109 / 後漢書 130 / 三國志 65 / 晉書 130（含载记 30）= 564 篇。
管线 `python pipeline/run_pipeline.py`；静态分享版 `web/index.html`；日常查询+编辑 `app/`（FastAPI）。

## 三条红线（写任何实现前先背）
1. **单向数据流**：Excel（`workbook/*.xlsx`）只能人写，pipeline 只读。
   凡 pipeline 想写 Excel 的地方一律改「写新版本 + 报差异」。
2. **句子主键是稳定 uid**：`md5(chapter|para|seq)[:12]`，拆半继承/合并标 merged/删除标 dead，
   **不物理删**。算法有四处（common / build / tag_uids / build_index_db），改一处改四处。
3. **规则进代码，数据进表格**：GENERIC_MANUAL / CONTEXT_RULES / SCOPED_ALIASES /
   BOOK_CANDIDATES / PERSON_BOOKS_* / OFFICE_WORDS 是代码；PERSONS 数据在 xlsx。

## 已拍板的方向
- **小程序彻底取消**，不重启。静态网页 `web/` **冻结**（只作分享产物，新能力只长在 `app/web/`）。
- **不再接新史书**。编辑深度**封顶在 b 档**（拆/并/弃句），c 档改原文**不做**，留 dead 逃生口。
- 裴注 / 晋书旧史注是**独立账本**，不进 mentionCount，UI 标【裴N】。
- `app/` 与 `pipeline/` **刻意不互相 import**，只在 JSON 上交汇（后端调脚本子进程）。

## 改动铁律
- 算法三层（build 切分 / annotate 匹配·泛称 / 前端 scope）**不推倒**，改质量 = 改词典与守卫。
- 每修一个坑，`verify.py` 加一条断言，基线**只许升不许降**。
- 别名只写**繁体**；裸官职、裸帝号/王号**禁止**进单人 core（走 GENERIC）；长名优先。
- 跨书同人**只扩 books 并集**，禁止新建 `p_xxx2`。
- **文档不写死统计数字**——「以当次输出为准」+ 给取数命令（历史教训：74/75/79 打架）。
- **前端文案一律繁体**：`check_trad.py` 扫 `app/web/app.js`，简体注释会让 F 闸失败。
- 一次性脚本归 `pipeline/_scratch/`（判据「下一轮还用不用」），移动时改 `parents[1]→parents[2]`。

## 环境与命令
- ⚠️ **python 必须用系统 3.12.10**（`C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe`），
  托管版 3.13.12 **没装 opencc**，跑 `check_trad.py` 会假失败。
- 回归：`bash scripts/run_all.sh`（/`--full` /`--no-ui`）。回归默认端口 **8790**（8770 被 VPN 客户端占）。
- ⚠️ **annotate 必须四步连跑**（annotate → pei → js_note → places）；凡「重标注」一律走 `app/tools/rebuild.py`。
- ⚠️ **跑重建前必须先停本地服务**：Windows 上 SQLite 被占 → 删不掉旧库 → 退出码 1。
- ⚠️ 库表主键别想当然：`books` 主键是 **`code`** 不是 `id`。
- ⚠️ subprocess 参数不能并成一个字符串，必须分开传。
- 取「在书分布」用 **book-data.json 的 `byBook`**，不是 people.json 的 `books`（后者手工条目全空）。

## 「AI 概率判定闭环」= 通用工作法
四件套：**取证 → 判 → 落 → 断言**。取证生成器产 JSON（每条自带可计算信号 + 语料上下文 + 空 `ai` 字段）；
判定写回独立 verdicts 文件（数据重生成后判定不丢）；应用器默认预演、`--apply` 才写；
每轮结论必有断言。已用：表字/泛称（`_gen_ai_batch`→`_apply_ai`）、人名（`_gen_name_batch`→`_apply_names`）、
关系（`_gen_rel_candidates`→`_apply_rel_batch`）。
- **人工清单必须自带证据**（归属分布 + 原文上下文 + 候选朝代 + 当前 default），**一律生成器产出禁止手敲**；
  判不了勾「未知」，不要硬判。

## 各阶段已完成（关键设计）
- **P0**：`persons.xlsx` 是权威源；`build_dict.py` 只留规则，`persons_data.py` 存种子。
  三条纪律：导出只读源数据（防 `build_dict→people.json→xlsx→build_dict` 循环）、**不预排序**、
  验证用 people.json **md5 逐字节比对**。
- **P1**：`data/index/index.db`（**可删重建的产物**）。FTS5 中文分词坑：unicode61 把整句当一个 token
  → **按字切分入库 + 短语查询** `MATCH '"項 羽"'`；**不要用 trigram**（要求 ≥3 字）。
  uid 优先级：**语料 uid > 旧库按位置复用 > 现算**。mentions/aliases 追加写会翻倍
  →「偷旧 uid → 删库 → 重建 → 复用」。
- **P2**：裸短名错挂（长名 > 分书收束 > ctxRule > 动 default）、类传补人（**自动抽必人工看原文**）。
- **P3**：一键 rebuild（~40s）、快照 diff 落**独立库** `snapshots.db`（不能进 index.db，会被冲掉）、
  overrides 落 `workbook/overrides.xlsx`。坑：**两份快照互比恒为 0**（新侧必须是重建后的当前库）、
  drop 的验证要**数条数**。
- **P4**：uid 下沉语料；句级编辑（split/merge/dead）**从 `data/corpus-orig/` 重放**实现撤销与幂等；
  网页端 hover 出三动作，拆分=**点字选断点**；后端 rebuild 走后台线程 + 前端轮询。
- **P5**：`verify.py` 的 `_newchain_cases()` 断言句数/命中/人物与 index.db 一致 + uid 四处一致 +
  命中逐条对齐（差集必须空）。基线 **113**（以当次输出为准）。`verify_p3.py` **52 条**（P6-4 后，
  含 [7] 关系规则 / [8] 证据状态 / [9] 展示读法 / [10] 证据一对多）。
- **P6 关系**：权威源 `workbook/relations.xlsx`；`relations` 表在 index.db，
  **建库后由 `apply_relations` 灌回**（先灌必丢）。只存规范边（`REL_TABLE` + `REL_INVERSE`，
  拒绝反向双写与自环）；`rel_id=md5(a|b|rel|era|book)`；`confidence` 由 `derive_confidence(source, has_evidence)`
  **派生**（无证据压 0.4）；边起点 `source` 与关系来源撞键 → 来源叫 **`origin`**。
  端点返回 `{nodes, edges}` + degree/rel_type/book/min_conf。
  抽取只收**显式关系词**（之子/之弟/之妻…），**禁止共现出边**；**裸帝号一律不自动落**（跨朝代多义，
  实测「文帝」被解析成曹丕）→ 进人工清单。去重判据用 **(a,b,rel)** 不能用 rel_id。
- **P6-4（第二次独立审查 docs/28 的修复批次）**——三条规则层收获，写同类代码直接抄：
  1. **有向量的展示要站在中心那一端换算，且有性别变体**（`父 → (子, 女)`，靠 `rel_view`）。
     ⚠️「称呼反向」`CALL_INVERSE` 与「反向边」`REL_INVERSE` 是**两张表**：前者连对称边都需要
     （兄边在中心看来是「弟」），后者只用来禁双写。取证时拿错表 → 硬句式 0 命中。
  2. **天然为空的列不能当过滤器**：`book` 61/62 条是空的（关系跨书，同人物），
     `AND (book=? OR book='')` 会让 `book=zzz` 也放行。正解是看**证据句落在哪本书**，
     书号不在五书内直接 400。
  3. **证据是一对多的**：12/62 条边有 ≥2 条候选句 → `relation_evidence` 子表 + xlsx 证据页
     （`verdict=reject` 只留档不算证据；主证据失效但另有一句活着 → 仍算有据）。
- **独立审查的规矩（docs/24 §八）**：关系数据要审**两次**（设计层 docs/25 / 产品层 docs/28）；
  第二次必须换一个**不参与开发的会话**，且**只准它写那一份报告**，否则会被实现带着走。
  它的判据是「故意注入错误，断言必须变红」——查不出内容对错的断言等于没写。
- **断言自己造的数据要自己收走**：`revoke` 只改状态不删行，跑了十几轮积了 44 行 dead 行，
  权威源永远脏着 → `verify_p3.purge_test_rows()`（只删 dead + 命中测试标记的行）。
- **审查教训（可推广）**：**凡是「不可再生的审定数据」，先问「它落在哪个会被删重建的产物里」**。

## 已知残留 / 待办
- **`docs/26` 帝号关系人工判定（38 条，判定栏全空）** → 回填 verdicts 再落盘。
  这是 P6-4 之后**下一个可做**的量（P1 已全修，审查放行扩量）。
- 重复 pid `p_liuyan_sg` / `p_liuyan_ys` 待合并；`p_xNNNNN` → 拼音语义 id（**须排在依赖 pid 的活之前**）。
- guess 池下一个：周公、趙王、關內侯、文王、梁王、常山王。
- 网页「标错」入口（照 P4-2 同套做法）。
- 文档 01–18 数字互相打架待治理（已治理 15/16/README）。
