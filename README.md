# BOOKINDEX · 古籍人物 / 地名索引

前四史 + 晋书的**实体索引**（不是全文检索）：离线 Python 管线把原文切成句、用别名词典
标出每个实体，产出一个**本地静态网页**。打开网页就能查，不需要服务端、不需要联网。

核心能力是**别名归一 + 篇目分层**。搜「刘邦」，《史记》里这两个字一次都没出现过，
全书写的是「高祖」（302 处）、「沛公」（242）、「漢王」（353）、「劉季」（15）——
照样一处不落，并分成两类结果：

- **整篇讲述**：这一篇的主人公就是他（如《史记·高祖本纪》）
- **顺带提及**：别的篇里提到他，逐句列出，并高亮**书里真正写的那个称呼**（显示「沛公」，不是「刘邦」）

---

## 快速开始

```bash
# 1) 直接看（产物已在仓库外，见下）—— 起个静态服务
cd web && python -m http.server 8770
# 浏览器打开 http://127.0.0.1:8770/index.html
```

```bash
# 2) 重跑管线（五书全量，约几分钟；会把 data/ 与 web/*-data.js 重新生成一遍）
python pipeline/run_pipeline.py

# 3) 改完东西跑回归（推荐用一键脚本，见下）
bash scripts/run_all.sh
```

**依赖**：Python 3.12（须装 `opencc`，用于繁简/异体归一）；UI 测试另需 Node + `jsdom`。

---

## 当前基线（2026-09-25）

| 项 | 值 |
|---|---|
| 覆盖 | 史記 130 / 漢書 109 / 後漢書 130 / 三國志 65 / 晉書 130（含载记 30）= **564 篇** |
| 语料 | 95,632 句 |
| 词典 | 人物 **2013** / 地名 **1575** / 零命中 0 |
| 验收 | `verify --check` **81/81** · `check_trad` A–G 七道闸 · UI 65 / 46 / 49 |

---

## 回归链（一键）

```bash
bash scripts/run_all.sh            # 常规：断言 → 字面层 → UI 四套（约 1-2 分钟）
bash scripts/run_all.sh --full     # 追加 _ui_sweep.js 全量扫描（慢）
bash scripts/run_all.sh --no-ui    # 只跑 Python 侧（改词典时的快速回路）
```

脚本会自动定位 python（挑**装了 opencc** 的那个）、node 与 jsdom 目录，
并自动起停 8770 端口的静态服务。手工等价步骤：

```bash
python pipeline/verify.py --check      # 数据断言基线，只许升不许降
python pipeline/check_trad.py          # 字面层 A–G 七道闸

cd web && python -m http.server 8770 &  # UI 测试需要它
NODE_PATH=<含 jsdom 的 node_modules> node pipeline/_ui_test.js
NODE_PATH=<...> node pipeline/_ui_test_books.js
NODE_PATH=<...> node pipeline/_ui_test_places.js
NODE_PATH=<...> node pipeline/_ui_csscheck.js
```

---

## 目录结构

```
pipeline/        离线管线（Python）
  fetch_book.py    抓维基文库卷页
  build.py         提取正文、切句        → data/corpus/*.json
  build_dict.py    人物词典与泛称规则    → data/dict/people.json
  annotate.py      别名标注、建索引      → data/index/*.json + web/app-data.js
  annotate_pei.py  裴注独立索引          → data/index/pei-data.json
  annotate_js_note.py  晋书旧史注独立索引
  build_places.py / annotate_places.py   地名层
  check_trad.py    字面层守卫（必须最后跑）
  verify.py        回归断言
  run_pipeline.py  按顺序编排以上各步
  _*.py            一次性探针/修复脚本（可删）

data/
  raw/ corpus/ index/   抓取 / 切分 / 索引产物（**不入库**）
  dict/                 books.json 书注册表、volumes/*.json 五书篇名表（人工审定）
web/
  index.html app.js     源码（**入库**）
  *-data.js             管线生成的数据（**不入库**）
docs/                   18 篇设计 / 台账 / 交接文档
scripts/run_all.sh      一键回归
```

**入库判据**：凡 `pipeline/*.py` 会覆写的文件一律不入库（见 `.gitignore`）。
不可再生、必须入库的人工资产是 `data/dict/books.json`、`data/dict/volumes/*.json`、
`pipeline/build_dict.py`（`PERSONS` 的唯一来源）、`pipeline/build_places.py`、`web/app.js`。

---

## 改动铁律

1. **算法三层不推倒** —— build 切分 / annotate 匹配·泛称 / 前端作用域。改质量 = 改词典与守卫。
2. **每修一个坑，`verify.py` 加一条断言**，基线只许升不许降。
3. 别名只写**繁体**；裸官职、裸帝号/王号**禁止**进单人 core（走 `GENERIC` 泛称）；长名优先。
4. 跨书同人**只扩 `books` 并集**，禁止新建 `p_xxx2`，禁止后表覆盖前表。
5. 改词典只跑 `annotate*` 子集，轮末才跑全量 `run_pipeline`。
6. 复杂清洗脚本写 `pipeline/_*.py`，**勿用 `python -c`**（PowerShell 会吞引号和正则）。

---

## 文档地图

| 文档 | 内容 |
|---|---|
| **`docs/16`** | **新会话交接书**：目标、抽查工作流、回归链、禁区 —— 接手先读这篇 |
| `docs/18` | 人名筛查方法与原则（什么算人名、排除闸） |
| `docs/17` | **待办：人工判断清单**（裸帝号 default + guess 池），等勾选后回填 |
| `docs/15` | 本轮问题与经验总结 |
| `docs/11–12` | 以史记为标杆的问题报告 + R0–R5 修改方案 |
| `docs/13–14` | 晋书接入流程与五轮落地 |
| `docs/01–10` | 早期方案与前三书接入记录（部分已过时，见下） |

> ⚠ `docs/01` 方案中的**微信小程序 / 云托管路线已暂停**（`miniprogram/`、`server/`
> 从未建立），当前交付形态是本地静态网页。文档 01–18 是线性累积的，
> 其中的统计数字（verify 条数、人物数）多为当轮快照，**以实跑结果为准**。

---

## 已知残留（未决）

- `docs/17` 人工判断清单：10 条裸帝号/王号 default + 9 条 guess 池 TOP，需人工勾选
- 泛称 `guess` 池约 1473 处；晋书裸「武帝」仍有汉武帝 85 处追述
- 附传/类传长尾缺人；表字尊称命中 ≤10 的长尾
- `web/app-data.js` 31.9 MB 整包注入（`docs/03` 已决策按书拆分，尚未实施）
- 文档 01–18 数字互相打架，待治理
