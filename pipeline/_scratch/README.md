# _scratch/ · 一次性脚本存档

这里放的是**绑定某一轮、跑完就不再需要**的脚本：诊断探针、定点修复、某本书某一轮的
批量写入。它们曾经解决过真问题，但**不是工作流的一部分**，日常回归不依赖它们。

判断标准很简单：**「下一轮（比如接一本新书、再修一批别名）还会不会用到它？」**
会用到的留在 `pipeline/`，不会的进这里。

## 留在 pipeline/ 的（仍在工作流里，勿动）

| 类别 | 文件 |
|---|---|
| 回归测试 | `_ui_test.js` `_ui_test_books.js` `_ui_test_places.js` `_ui_csscheck.js` `_ui_sweep.js` |
| 零回归对账闸门 | `_snapshot_counts.py` |
| 截图取证 | `_shot.js` `_shot_books.js` 及各书 `_shot_*.js` |
| 抽查探针（docs/16 §二、docs/18 §四 列为工具） | `_probe_title_mis.py` `_probe_alias_gaps.py` `_probe_book_alias_density.py` `_probe_report_quality.py` `_probe_report_quality2.py` `_probe_js_zaiki.py` |
| 批量入典工具（docs/18 §四 列为工具） | `_gen_alias_fill_plan.py` `_apply_alias_fill.py` `_gen_persons_fill.py` `_apply_persons_fill.py` `_fix_false_persons.py` `_fix_false_persons2.py` |

## 这里是存档（按来源分组）

**三国志轮**（`#C` 官名/帝号、`#D` 别名）
`_probe_sgz_title_mis.py` `_probe_sgz_round2.py` `_probe_sgz_round4.py`
`_fix_office_aliases.py` `_fix_sgz_round5.py` `_fill_sgz_owners.py`
`_apply_owner_fill.py` `_probe_empty_owners.py` `_probe_extract_owners.py` `_probe_fill_plan.py`

**司马懿专项**（R1 正确性事故）
`_probe_simayi_match.py` `_probe_simayi_compile.py` `_probe_simayi_aliasok.py`

**曹操专项**（`#D` 触发）
`_probe_caocao_surface.py` `_probe_caocao_titles.py`

**R2 / R3 / R3c 批量轮**
`_r2_fill_zi.py` `_r3_scan_office.py` `_r3_strip_office.py` `_r3c_fill_bios.py` `_check_office_fix.py`

**散见人物入典后的清尾**
`_fix_persons_fill_dup.py` `_fix_persons_fill_trad.py` `_fix_persons_noise.py`
`_fix_xuer2.py` `_fix_zhouxuan.py`

**晋书轮**
`_probe_js_html.py` `_probe_js_bios.py` `_probe_js_places.py`

**其他**
`_probe_owner_generic.py` `_check_corpus_notes.py`

## ⚠ 移植到别处 / 重新使用时必读

这些脚本里有 39 个原本写的是：

```python
ROOT = Path(__file__).resolve().parents[1]      # 位于 pipeline/ 时，parents[1] = 项目根
```

移进 `_scratch/` 后多了一层，已统一改为 `parents[2]`。若把它们挪回 `pipeline/` 或
再挪到别处，**这个数字必须跟着改**，否则所有数据路径会整体错位一层（症状是「找不到
data/index/book-data.json」）。

另有 3 个脚本要导入兄弟模块 `common` / `trad`（`_fix_persons_fill_trad.py`、
`_probe_simayi_aliasok.py`、`_probe_simayi_compile.py`），已在文件顶部插入：

```python
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
```

把 `pipeline/` 补回搜索路径。再挪动时同理需要保留这段。

## 它们还跑得动吗

实测（2026-09-25，系统 Python 3.12.10）抽查了 6 个，均退出码 0、输出正常：
`_probe_owner_generic.py` `_r3_scan_office.py` `_check_corpus_notes.py`
`_probe_simayi_aliasok.py` `_probe_simayi_compile.py` `_fix_persons_fill_trad.py`

注意：`_fix_*` 系列是**会改 `build_dict.py` 的写入脚本**，重跑可能覆盖现有词典——
除非明确要复现那一次的修复，否则只跑 `_probe_*`（只读）。
