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
| **P6-0/1** | 关系数据落点 + 契约定型 | ✅ **已完成**（审查出的 P0 六项与 P1 表/代码层全部修掉） |
| **P6-2** | 关系抽取（简介 → 候选 → 落盘） | ✅ **已完成**（62 条入库；帝号类 **40 条已判**，剩 7 条见 `docs/26`） |
| **P6-3** | 关系图（`renderGraph`，**不引 ECharts**）+ 四个密度旋钮 | ✅ **已完成** |
| **P7-1** | pid 语义化（占位归零）/ 原文层跳段與段落篩選 / 裴注独立账本 | ✅ **已完成**（2026-10-02） |
| **P7-2** | 人物页对齐静态版：完整称谓表 / 「前朝」标记 | ✅ **已完成**（2026-10-03） |
| **P3-4** | 网页「标错」入口（UI 代写 `overrides.xlsx`） | ✅ **已完成**（2026-10-03，见下文） |
| **P8-1** | 地名检索 + 地名详情页 + 离线补齐 | ✅ **已完成**（2026-10-03，见下文） |

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
| `app/tools/verify_p3_overrides.py` | 只跑 `[16]`（纠错入口），15 秒版 |
| `app/tools/verify_p3_place.py` | 只跑 `[17]`（地名检索与详情），15 秒版 |

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

### P3-4 已交付什么（网页「标错」入口）

人物页每条命中 hover 出「標錯」，就地展开一行面板：

- **改归**：输人名 → 点候选（走 `/api/search`），不用手敲 pid；
- **不是他**：这处不作数（drop，整条命中从索引里去掉）；
- 已标错的命中带「已標錯 → 項羽」徽章 + 「撤銷」；顶部提示「已記錄 N 條糾錯，重建後生效」。

新增端点：

```
GET  /api/overrides                               生效中的纠错（前端打徽章用）
POST /api/override      {uid, s, e, surface, action, new?, pid?, note?}
POST /api/override/revoke  {uid}                  撤销该句的全部纠错
```

> ⚠️ **nth 由后端算**（`db.mention_nth`），前端**不许传**。前端看到的是
> 「这个人在本句里第几条」，nth 是「本句所有人命中里第几条」——一句常挂着好几个
> 人，两个序号不是一回事。算错就会**改到别人头上，而且不报错**
> （`overrides.apply` 只按 nth 取第几条，取错照样报「改歸 1 條」）。
> 实测样本：某句「漢王」是全句第 3 条命中，在劉邦自己那儿排第 2。

> ⚠️ **回归用的服务要设 `BOOKINDEX_OVERRIDES`**（与 `BOOKINDEX_DB` 同一套约定）：
> UI 测试真的会点一次「标错」，而 revoke 是**改状态不删行**，打真实权威源就等于
> 每次回归给 `workbook/overrides.xlsx` 多两行 dead 行。`run_all.sh` 已指向
> `data/index/overrides.ui-test.xlsx`（已 gitignore），服务启动时会把这件事嚷出来。

### P8-1 已交付什么（地名检索 + 详情页 + 离线）

此前地名侧**能列不能点**：`/api/search` 只查 persons、没有任何 `/api/place/...` 端点、
`export_static.py` 只导 places 主表（`place_mentions` 一点痕迹都没有）。

**根因不是检索逻辑，是建库漏了一列**：`places.name` 与 `trad_name` **逐行相同**
（全表 0 行不同），简体名一直只存在 book-data 的 `aliases` 里而从未灌进库
→ 输「邯郸」零命中，**联机离线都一样**。新建 `place_aliases` 表（2464 条 / 覆盖
全部 1575 个地名，次数与分书从 `place_mentions.surface` **现算**——`aliases` 不带次数）。
修后：邯郸 → 邯鄲 273 处；長安 1346、成都 434、临淄 50、江陵 218。

> ⚠️ **2525 条**（不是初版的 2464）：独立审查查出**语料里实际用过的 61 种写法
> 从没进过 `places[].aliases`**（`河閒` 96 处 / `雒` 89 处 / `關内` 41 处…），
> 于是「用户按原文写法搜不到」+ 60 个地名 `Σ n ≠ COUNT(place_mentions)`。
> 修法是灌库时把**语料实测 surface 并进 forms**（正名 → aliases 原序 → 实测按次数降序）。
> 这类缺口的通用教训：**「登了哪些写法」与「语料用了哪些写法」是两个集合，
> 别拿前者当后者**。

新增/变更：

```
GET /api/search?q=&kind=all|person|place     → {query, items, places}
GET /api/place/{pid}?limit=                  → {profile, mentions, books, aliases}
```

- **索引条目直接进详情页**（`data-place`），不再绕人物搜索——地名实测无重名，
  绕一圈只会撞上「人物搜索里没有这个地名」→ 空。
- **`renderPlace` 与 `renderPerson` 刻意同构**（payload 同形）。写第二套渲染不是省事，
  是多一处会悄悄分叉的地方。
- 离线补 `pmen` / `plalias` / `plbook` 三块（data.js 16.5 → 19.1MB）。买的是两边不分歧。
- `readerState.pid` 改名 **`scope`**：它**只当布爾用**（「有没有筛选上下文」），
  人物页与地名页都往里塞 id。不改的话地名页的「只看相關段落」按钮直接消失。

> ⚠️ **地名侧最贵的坑是「不报错」**：搜不到、点不动，界面都不提示。
> 所以断言必须断在「会被打破的那一层」——`search_places` 不查 `place_aliases`
> （db 层）、端点忘返 `places`（只有端点层能抓）、离线漏导 `plalias`（只有离线测试能抓）。
> 端点层要**真打一次 HTTP**，db 层全绿不代表端点没漏字段。

### P8-2 已交付什么（P0-甲 标色落点 + P0-乙 注文入口接线）

两条都是 docs/34 报的前端 P0，**都不报错、只是显示错**，所以断言必须断在
「会被打破的那一层」。

#### 甲：标色落点（`markSentence` → `hitSpan`）

`markSentence(text, surface, tier)` 签名里**没有 s/e**，只能 `indexOf` 找第一处。
一句里同一词多次出现（「舜…堯…舜」）就标到不相干的语境上——
**实测 182,128 条命中里 8,319 条（4.6%）标错**。

⚠️ **但不能只改成 `text.slice(s, e)`**——审查报告的这条建议**照做会新造 63 条错标**：
`s`/`e` 是 pipeline 用 Python 算的 **Unicode 碼位**下标，JS 的 `slice` 按 **UTF-16 碼元**；
古籍里有非 BMP 字（实测 `U+24CF9`、`U+23D40` 这类罕用異體字），一个字算两个碼元，位置整个偏。

所以是**三級回退**，每級都以「切出來的字串 `=== surface`」为判据：

| 级 | 做法 | 覆盖 |
|---|---|---|
| A | `text.slice(s, e)` | 182,065 / 182,128（99.97%） |
| B | `Array.from(text)` 按碼位切 | 修那 63 条 |
| C | `indexOf` 兜底 | 0 条（真走到说明 s/e 与 text 不同源，是数据问题） |

`hitSpan` 返回**切好的三段字符串**而不是下标——下标外泄会让调用方再用碼元 `slice` 切一遍，
正是它自己要修的错（我第一版就这么写的，注入验证当场抓出来）。

> ⚠️ **Python 里 `len(t) == len(list(t))` 恒成立**（str 本身就是碼位序列），
> 拿它判「碼位≠碼元」是恒假。判有没有非 BMP 字只能用 `any(ord(c) > 0xFFFF for c in t)`。
> 断落点要数**碼位**（JS `Array.from(x).length`）不是碼元（`x.length`）。

#### 乙：注文的两个入口接上点击

注明的「讀全篇 ›」（`.open-full`）与明细行（`.pei-line`）**一直渲染了 `data-chapter`**，
但 `out` 的点击分派里**没有对应分支** → 元素在、点了没反应。
「讀全篇」与明细行的差别在**要不要跳段**：后者的 `data-pseq` 是**段号**
（⚠️ 注文与正文的切分体系不同，**不能**拿它当 uid 去查 `p[data-uid]`），
所以 `openChapter` 加了第四个参数 `pseq`，走既有的 `jumpToPara`。

> ⚠️ 旧断言写著「讀全篇**可點**」「明細行**可點**」，實際只斷 `length > 0`——
> **寫著可點卻沒點過一次**。現在真點開並斷原文層真的起來，而且聯機/離線各測一遍
> （離線走 `offlineGet`、聯機走 `fetch`，是兩條路徑）。

新增断言：

```
app/tools/verify_p3_mark.py        [18] 全量 182,128 條餵前端真碼，斷 <mark> 落點（~15s）
app/tools/verify_p3_mark_inject.sh      甲的三種壞寫法逐一注入，必須都變紅
app/tools/verify_p3_note_inject.sh      乙的三種壞寫法逐一注入，必須都變紅
```

`verify_p3.py` 主流程已接 `[18]`（快速版可單獨跑，15 秒，不必等 4–5 分鐘的全量）。

> ⚠️ **注入驗證本身也踩了兩個坑，都寫在 MEMORY 裡了**：
> ① 備份只能在開頭做一次——`restore()` 裡重備份會讓連續注入「越還原越壞」，
> 實測把 `plEl` 分派**永久刪掉**了而 trap 還報「成功」；
> ② **斷「終態」而不是「狀態轉移」是恆真的**——前一步已把原文層打開，
> `contains("on")` 在點擊前就已是 true，刪掉分派照樣綠。
> 修法是 `ensureClosed()` 再斷它變 on。

### P6-2 已交付什么（关系抽取）

走的是项目一贯的「取证 → 判 → 落 → 断言」闭环：

```bash
python pipeline/_gen_rel_candidates.py        # 取证：从人物简介抽显式关系词
python pipeline/_apply_rel_batch.py --dry-run # 看会落多少
python pipeline/_apply_rel_batch.py           # 落盘 workbook/relations.xlsx
python pipeline/relations.py check            # 校验（含重复 / 反向双写 / 证据失效）
python app/tools/rebuild.py                   # 灌库 + 自动 diff
python pipeline/_gen_rel_review.py            # 不敢落的 → docs/26 人工判定清单
```

**只收显式关系词**（「司馬昭之子」「劉邦之妻」），**绝不从共现推断**——
同句出现两个人什么都说明不了。

第一批结果：候选 106 条 → 落盘 **62 条**（唯一匹配且非裸帝号），
**38 条裸帝号**（文帝/明帝/武帝/宣帝…）留人工判定（`docs/26`）。

> 裸帝号为什么不自动落：同一个称号跨朝代指不同的人——
> 实测「文帝之子」被解析成**曹丕**（应为汉文帝刘恒）、「宣帝之子」被解析成**司马懿**。
> 生成器按别名解析只能碰运气，这类必须带朝代判。

落下来的这 62 条 **都没有证据句**（简介不是语料句，没有 uid），
所以按规则统一压到 `confidence=0.4`（推断档），图上画虚线——
**没出处的关系，不当事实用**。

### P6-0 / P6-1 已交付什么（设计审查后的问题全修）

审查（`docs/25`）出的六条 P0 与 P1 的表/代码层全部修掉了：

| 审查项 | 修法 |
|---|---|
| **P0-1 落点**（关系在会被删库重建的 index.db） | 权威源 `workbook/relations.xlsx`；`rebuild` 最后一步 `apply_relations` **建库后灌回** |
| **P0-2 稳定主键 + status** | `rel_id`（md5，PRIMARY KEY）+ `status`(active/dead) |
| **P0-3 证据** | 唯一约束 `(rel_id)` 防重复；`relations.py check` 会报**证据句失效**（句子被拆/弃用后） |
| **P0-4 快照 vs uid** | 明写：**以 uid 指向的现句为准**，`evidence_text` 只是录入那一刻的展示缓存 |
| **P0-5 direction** | 换成 `symmetric` 布尔 + 代码 `REL_INVERSE` 派生反向；**只存规范边**，反向双写会被拒绝 |
| **P0-6 契约对不上** | 端点返回 `{nodes, edges}`（就是 `renderGraph` 的输入）+ 四个密度旋钮；前端那张占位卡片改成真读数据 |
| P1-7/8/9/10 | 加 `surface_a/b`（同名异人锚点）、`era`、`book`；`rel_type`/`confidence` 由代码派生不手填；`rel` 规范词表定死在 `pipeline/relations.py` |

```bash
python pipeline/relations.py init
python pipeline/relations.py add --a p_liubang --b p_hanhuidi --rel 父 --book sj --source manual
python pipeline/relations.py check          # 含「证据句已失效」
python pipeline/relations.py apply          # 灌入（rebuild 会自动跑）
```

> ⚠️ 边上有两个 `source` 会撞车：**边的起点叫 `source`，关系来源改叫 `origin`**。
> 同名键写进同一个 dict 后者会无声覆盖前者（已经踩过一次，边上突然变成 "manual"）。

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
GET /api/overrides               生效中的单条纠错（网页「标错」打徽章用）
POST /api/override               {uid, s, e, surface, action, new?, pid?, note?}
POST /api/override/revoke        {uid}
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

> **2026-10-03 重写**：下面这份旧的清单（P6 时代的）已全部做完，留着只会误导
> 下一个会话。**当前唯一的待办清单是 `docs/31` §四**——那份按实测数据排过序，
> 本文件只写「已做完什么」和「开工前必读」。

### 已清完（别再排进待办）

| 项 | 什么时候 | 落在哪 |
|---|---|---|
| 断句第二类（跨句对话引号） | 2026-09-29 | **显示层**续接标记，数据层一个字没动 |
| `@app.on_event` → lifespan | 2026-09-29 | `app/server/main.py` |
| 17 个一次性脚本归档 `_scratch/` | 2026-09-29 | `pipeline/_scratch/` |
| 同名异人 UI 消歧（序号 + 见于哪本书） | 2026-09-29 | 检索结果行 |
| **P6-3 关系图** | 2026-10-01 | `renderGraph()`，**刻意不引 ECharts**（离线工具不该有 CDN 依赖） |
| **pid 语义化**（`p_xNNNNN` → 613 个全改完，占位 pid 归零） | 2026-10-02 | `c4464f3` |
| 原文层跳段 + 只看相关段落 | 2026-10-02 | `fded7b1` |
| 裴注 / 晉書舊史注（独立账本） | 2026-10-02 | `74018f9` |
| 人物详情完整称谓表 | 2026-10-03 | `28bda38` |
| 「前朝」小标记 | 2026-10-03 | `4cda891` |
| **P3-4 网页「标错」入口** | 2026-10-03 | `841c32a`，见上文 P3-4 一节 |
| **P8-1 地名检索 + 详情页 + 离线** | 2026-10-03 | `cc62e9e`，见上文 P8-1 一节 |

关系抽取那批：裸帝号 **40 条已判**（36 accept / 2 reject），`docs/26` 只剩 7 条
（1 条同名待你拍板 + 6 条库里没有这个人，要先补人）。

> 三个已拍板的决策（详见 `docs/24` §二）：快照 diff **落 SQLite、可翻历史**（不做网页页）；
> `overrides` 落 **`workbook/overrides.xlsx`**（人写、管道只读）；**静态版 `web/` 冻结**。
>
> 还剩一个未决的目录：`.mimocode/`（56MB，来源不明，等你确认要不要删）。
