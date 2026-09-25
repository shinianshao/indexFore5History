# 项目长期约定 · BOOKINDEX（古籍人物/地名索引）

## 项目是什么
离线 Python 管线 + 本地静态网页的**古籍实体索引**（不是全文检索）。
五书：史記 130 / 漢書 109 / 後漢書 130 / 三國志 65 / 晉書 130（含载记 30）= 564 篇。
入口 `web/index.html`；管线 `python pipeline/run_pipeline.py`。

## 用户已拍板的方向性决策
1. **微信小程序路线暂停**（2026-09-25）。`docs/01` 里的 `miniprogram/` 与云托管 `server/`
   从未建立，不再作为待办；当前交付形态是本地静态网页。以后重启再说。
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
- 每修一个坑，`verify.py` **加一条断言**，基线只许升不许降（当前 81/81）。
- 别名只写**繁体**；裸官职、裸帝号/王号**禁止**进单人 core（走 GENERIC 泛称）；长名优先。
- 跨书同人**只扩 `books` 并集**，禁止新建 `p_xxx2`，禁止后表覆盖前表。
- 改词典只跑 `annotate*` 子集；**轮末才全量** `run_pipeline`。
- 复杂清洗脚本写 `pipeline/_*.py`，勿用 `python -c`（PowerShell 会吞引号/正则）。
- **文档不写死统计数字**（人数/断言数/命中数）——一律「以当次输出为准」并给出取数命令。
  历史教训：docs 里 74/75/79 三个数打架，实际 81；「2169 人」实际 2013。
- **一次性脚本归 `pipeline/_scratch/`**，判据「下一轮还会不会用到」。
  移动时必改两处：① `ROOT = Path(__file__).resolve().parents[1]` → **`parents[2]`**（多一层）；
  ② 导入 `common`/`trad` 的要加 `sys.path.insert(0, 父目录)`。详见 `pipeline/_scratch/README.md`。

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
- guess 池规模以 `--list` 当次输出为准（曾约 1473 处）；晋书裸「武帝」仍有汉武帝追述。
- guess 池下一个该看：周公、趙王、關內侯、文王、梁王、常山王。
- 附传/类传长尾缺人、表字尊称命中≤10 的长尾。
- 前端 `app-data.js` 31.9MB 整包注入（`docs/03` 决策的按书拆分从未实施）。
- 文档 01–18 数字互相打架（74/75/79 vs 实际 81；2169 vs 实际 2013 人），待治理。
