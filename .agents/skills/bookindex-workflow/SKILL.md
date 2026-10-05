---
name: bookindex-workflow
description: "古籍索引系统（BOOKINDEX）全栈架构、管线重建、断言验证与日常运维工作流。Use when 接手BOOKINDEX项目、执行rebuild重建索引、运行断言回归、处理Excel权威源与单向数据流、排查Windows平台文件损坏或权限问题、编写总结交接文档或新开对话。"
icon: "📜"
---

# 古籍索引系统（BOOKINDEX）工程规范与运维工作流

## 一、项目本质与架构全景

本项目是前四史（史记、汉书、后汉书、三国志）+ 晋书的**实体索引与篇目分层系统**（非全文检索）。
- **事实源入口**：`app/DEV.md`（施工入口）· `docs/36-踩坑清单.md`（踩坑与铁律）· `.workbuddy/memory/MEMORY.md`。
- **历史文档警示**：`docs/01`~`18` 数字打架、早期小程序方案已废弃，切勿当作当前事实。
- **架构全景**：
  - 权威源：`workbook/*.xlsx`（人与UI写，pipeline只读）
  - 派生存储：`data/index/index.db`（SQLite + FTS5）
  - 联机服务：`app/`（FastAPI 后端 8800 端口 + 原生单页应用）
  - 离线分发：`dist/`（`export_static.py` 生成的免服务端脱机快照）

---

## 二、三条不可逾越的红线

1. **单向数据流**：
   - `workbook/*.xlsx`（`persons.xlsx`, `places.xlsx`, `overrides.xlsx`, `sentence-edits.xlsx`, `relations.xlsx`）为唯一不可再生权威源。
   - Pipeline 管道只能**读取**，绝对禁止回写覆盖。若需调整，必须以「写新版本 + 报差异」的形式交付。
2. **稳定三参数 uid**：
   - 句子主键必须是：`md5(篇|段序|句序)[:12]`（不含文本原文）。
   - 拆句：前半继承原 uid，后半分配新 uid；
   - 并句：留第一句，第二句标记 `merged`；
   - 弃用：标记 `dead`，永远不做物理删除。
3. **规则与数据彻底解耦**：
   - 泛称消歧、匹配规则、停用词在 Python 代码；
   - 实体正名、别名、朝代、关系边等实体数据在 Excel。

---

## 三、常用命令与环境铁律

### 1. 解释器与依赖
- **必须使用系统 Python 3.12.10**：
  `C:/Users/dell/AppData/Local/Programs/Python/Python312/python.exe`
  *注意：PATH 前列的托管 Python 3.13.12 未安装 opencc，会导致繁简七道闸 `check_trad.py` 假失败！*

### 2. 核心操作命令
```bash
# 1. 停止本地 8800 服务后，执行全量索引重建（约 30-45 秒）
python app/tools/rebuild.py

# 2. 导出脱机静态快照（必须不带参数运行才执行真写盘）
python app/tools/export_static.py

# 3. 快速断言回路（单项约 15-30 秒，避免等待 4-5 分钟的全量 verify_p3）
python app/tools/verify_p3_mark.py       # 标色切片落点验证
python app/tools/verify_p3_mfilter.py    # 命中数口径与分书/分时代筛选验证
python app/tools/verify_p3_overrides.py  # 网页纠错入口验证
python app/tools/verify_p3_place.py      # 地名检索与详情验证
python app/tools/verify_p3_paras.py      # 全量段落、注文跳转可达与长篇验证

# 4. 独立审查：故障注入红绿双向闭环（约 5 秒）
python app/tools/verify_p1_fault_injection.py

# 5. 字面层繁简七道闸（A–G 闸）
python pipeline/check_trad.py

# 6. 全量一键回归（断言 + 字面层 + UI 测试，约 4 分钟）
bash scripts/run_all.sh
```

---

## 四、Windows 平台避坑与护栏

1. **openpyxl 原子写入护栏**：
   - Windows 权限及临时目录限制下，Python `openpyxl.save(path)` 会先截断文件，失败时残留 2.3KB 损坏文件。
   - **严禁直接调用 `wb.save(path)`**，必须统一使用 `pipeline.common.safe_save_workbook(wb, path)`（内存 `BytesIO` 封包 + 临时文件原子替换 `os.replace`），杜绝 0 字节截断损坏。
   - UI 写入测试必须配置沙盒环境变量：`BOOKINDEX_OVERRIDES` 指向测试专用路径。
   - 每次跑完带写操作的测试或脚本后，必须执行 `git status workbook/`，确认权威源未被意外修改或损坏。
2. **清理根目录 4 字节 `blat` 文件**：
   - 遇到根目录泄漏的 `blat` 文件，使用隔离脚本或批处理：
     `python pipeline/_clean_root_blat.py --apply`
3. **SQLite 锁占用**：
   - 重建索引前必须确保 8800 服务已关闭，否则 Windows 句柄锁会导致 `build_index_db` 抛错退出（退出码 1）。

---

## 五、断言与质量铁律

1. **拒绝恒真断言**：
   - 断言必须经过「**故意注入故障 → 验证测试变红 → 还原代码 → 验证测试变绿**」的四步闭环。
   - 警惕 7 类假绿：空列表 `all()`、宽泛选择器、断终态而非状态转移、验了引擎未验调用点接线等。
2. **古籍编码三级回退**：
   - 古籍中含有非 BMP 字符，前端标色严禁纯 `indexOf` 或裸 `slice`，必须使用 `hitSpan`（A 快路径 / B 按码位切 / C 兜底）。
3. **数据层段落完整性与注文闭环**：
   - 严禁为了缩减体积过滤纯文本句子，必须全量入库 223,164 句，确保段落连贯无开洞。
   - 纯注文段落必须通过 `last_text_pseq` 锚定至其依附的正文段落，前端 `jumpToPara` 增加向前回溯安全兜底，确保注文明细 100% 可达。
4. **地名纠错与跨实体标注（P8-b）**：
   - 地名纠错复用 `workbook/overrides.xlsx`，通过 `pid.startswith("pl_")` 精准匹配并修改 `s["pmarks"]`；
   - 跨实体纠错（地名转人名 / 人名转地名）需在 `marks` 与 `pmarks` 之间执行安全移动；
   - 网页标错端点闭环通过 `python app/tools/verify_p3_overrides.py`（28/28 项）进行红绿回归。
5. **关系边元数据与去重契约**：
   - 关系去重必须以 `(person_a, person_b, rel)` 业务三元组与反向边映射为准；
   - 关系边 `book` 列必须存单值书号（如 `sj`、`hs`），天然跨多书的关系规范保留为空串 `""`，切忌填入逗号多值；
   - 关系库健康度检验运行 `python pipeline/relations.py check`，全量灌库运行 `python pipeline/relations.py apply`。
6. **关系主键 rel_id 契约重构（纯业务三元组）**：
   - `rel_id` 算法严格定义为纯语义三元组哈希：`md5(f"{a}|{b}|{rel}")[:12]`，严禁将 `book`、`era` 属性揉入主键计算，避免填补元数据时主键漂移打碎证据子表外键；
   - 任何涉及关系的改动必须运行 `python app/tools/verify_p2_review.py`（22/22 断言，支持 `--inject` 故障注入红绿闭环）。
7. **离线快照与前端脚本同步守卫（P3）**：
   - `export_static.py --check` 不仅核验数据计数，且严格守卫 `dist/app.js` 与 `app/web/app.js` 源码一致性；
   - 历史前端 `web/` 目录已全面冻结，仅作为无头 UI 参照物保留，日常开发与修改统一在 `app/web/`；
   - P3 阶段工程治理与收口断言运行 `python app/tools/verify_p3_review.py`（16/16 项断言，支持 `--inject` 故障注入）。
8. **全系统端到端深度独立审查（Full-System Review）**：
   - 运行 `python app/tools/verify_system_comprehensive_review.py`（35/35 项断言全覆盖权威源、管线、库、API、前端、快照、治理 7 大层级，支持 `--inject` 故障注入红绿闭环）。
9. **地名扩充落地与权威源打通（docs/44–45）**：
   - **权威源单向流已打通**：`pipeline/build_places.py` 优先读取 `workbook/places.xlsx`（Sheet `地名`），`pipeline/build_dict.py` 联动触发 `build_places`，人写 Excel → pipeline 构建真正落地；
   - **行政建制对齐**：`db.py`、`annotate_places.py`、`app.js` 三方对齐 `"州"`（州部）分类；
   - **核心地名扩充达标**：地名实体由 1,575 处扩充至 1,621 处，正文标注达 119,148 处；汉魏十三州部、武昌/夏口、赤壁/官渡/街亭/五丈原/樊城、潼关/剑阁/虎牢关等 0 检索失明彻底解决；
   - **地名独立审查断言**：运行 `python app/tools/verify_places_enrichment.py`（10/10 项断言，支持 `--inject` 故障注入红绿双向闭环）。
10. **无传核心名将谋臣扩充落地（docs/46–47）**：
   - **突破主传传主视野**：收录李傕/諸葛誕/王戎/文欽/文鴦/冉閔/董承/隨何/戚夫人/審配/苻融/石崇/朱序/田豐/陸抗/顏良/郭圖等 40 位核心名将谋臣，实体增至 2,278 人，正文标注增至 67,373 处；
   - **同音同名消歧与原典异体补齐**：消解 `p_lukang_sg`（陸抗）vs `p_lukang`（陸康）、`p_furong_qq`（苻融）vs `p_furong`（符融）同音撞车，补齐 `麋竺`、`麋芳` 鹿字旁正典写法；
   - **人物独立审查断言**：运行 `python app/tools/verify_persons_enrichment.py`（10/10 项断言，支持 `--inject` 故障注入红绿双向闭环）。

---

## 六、跨会话交接与技能维护协议（Mandatory Protocol）

**用户明确规则**：
每次完成总结、架构审查或重大功能迭代后，**必须在项目中留下说明文档，并针对技能进行必要同步更新**：
1. **递增留下交接文档**：在 `docs/` 下生成最新的说明文档（如 `docs/39-...md` ~ `docs/64-...md`），记录当轮结论、规模数据与最新缺陷台账。
2. **更新项目核心记忆**：同步更新 `docs/36-踩坑清单.md` 和 `.workbuddy/memory/MEMORY.md`，保持最新待办清晰。
3. **维护并更新技能**：保持 `.agents/skills/` 与 `.mimocode/skills/` 的各技能内容与工程事实同步，确保后续新对话载入时能立即准确对齐工作流。
