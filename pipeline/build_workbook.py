# -*- coding: utf-8 -*-
"""从现有产物导出 **Excel 样书**（P0 第一步：只导出，不改任何管线行为）。

目的是把 § 方案变成能摸到的东西：列设计、拼音排序、按书筛选的手感，
先让用户过目，确认后再动 build_dict.py。

**这些 xlsx 此刻只是「视图」**，权威源仍是 build_dict.py。
等 P0 第 3 步做完（pipeline 改成读 xlsx）它们才升级成权威源——
在那之前随便删，重跑本脚本就能再生成。

设计要点
--------
- **一行一个实体**，别名用 `|` 分隔放在同一格——编辑时不用上下翻。
- `pinyin` 与 `in_<书>` 是**只读辅助列**：只用来排序和筛选，pipeline 不读它们。
- `uid`（句子）是**稳定主键**，首次生成后必须固化在表里，之后不再重算。
  ⚠️ 现在这版是「初版 uid」：`md5(篇|段序|句序|原文)` 前 12 位。
  一旦 P1 落地，它就以 Excel 里写的为准，脚本不再重算——否则一改切分就全变。
- 只读列用浅灰底纹标出来，避免误改。

用法
----
    python pipeline/build_workbook.py                # 样书：人名+地名全量，句子只出史記
    python pipeline/build_workbook.py --books hhs    # 句子换别的书
    python pipeline/build_workbook.py --all-books    # 句子全量（慢，文件大）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

try:
    from pypinyin import lazy_pinyin
except Exception:                                     # pragma: no cover
    def lazy_pinyin(s):
        return [s]

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "workbook"
PEOPLE = ROOT / "data" / "dict" / "people.json"
PLACES = ROOT / "data" / "dict" / "places.json"
BOOK = ROOT / "data" / "index" / "book-data.json"

BOOKS = ("sj", "hs", "hhs", "sgz", "js")
BOOK_NAME = {"sj": "史記", "hs": "漢書", "hhs": "後漢書", "sgz": "三國志", "js": "晉書"}

HDR_FILL = PatternFill("solid", fgColor="D9D9D9")     # 表头
RO_FILL = PatternFill("solid", fgColor="F2F2F2")      # 只读列
HDR_FONT = Font(bold=True)


def pinyin_of(name):
    return "".join(lazy_pinyin(name or ""))


def style_sheet(ws, headers, widths, readonly_cols):
    ws.append(headers)
    for i, (h, w) in enumerate(zip(headers, widths), start=1):
        c = ws.cell(row=1, column=i)
        c.fill, c.font = HDR_FILL, HDR_FONT
        c.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    # 只读列整列上底色
    for name in readonly_cols:
        if name not in headers:
            continue
        col = get_column_letter(headers.index(name) + 1)
        for cell in ws[col][1:]:
            cell.fill = RO_FILL
    ws.auto_filter.ref = ws.dimensions


def sheet_persons(wb, people, counts, bookmap):
    ws = wb.create_sheet("人物")
    headers = ["id", "正名(tradName)", "简体名(name)", "朝代", "头衔", "简介",
               "别名(竖线分隔)", "状态", "备注(你写)",
               "in_sj", "in_hs", "in_hhs", "in_sgz", "in_js",
               "pinyin", "命中数"]
    widths = [14, 14, 14, 8, 16, 40, 34, 8, 20, 7, 7, 7, 8, 7, 14, 8]
    ro = ["id", "简体名(name)", "in_sj", "in_hs", "in_hhs", "in_sgz", "in_js",
          "pinyin", "命中数"]
    style_sheet(ws, headers, widths, ro)

    # ⚠️ **不**在这里按拼音排序。导出的行序就是源码的编排顺序
    # （五帝在前、按时代/重要性手工排过），build_dict 读回时会原样采用；
    # 一旦导出时排了序，读回来 people.json 的条目顺序就变了（实测 md5 因此不同）。
    # 拼音只是给你**自己排序看**的辅助列——想按拼音看，在 Excel 里点 pinyin 列升序即可。
    for p in people:
        # 在书分布要用**实际命中**（book-data 的 byBook），不能用 people.json 的 books
        # 字段——手工条目压根没写那一列，會導致劉邦这种跨书人物五列全空。
        books = set(bookmap.get(p["id"]) or p.get("books") or [])
        ws.append([
            p["id"],
            p.get("tradName") or "",
            p.get("name") or "",
            p.get("dynasty") or "",
            p.get("title") or "",
            p.get("summary") or "",
            "|".join(p.get("aliases") or []),
            "active",
            "",
            *(("TRUE" if b in books else "") for b in BOOKS),
            pinyin_of(p.get("tradName")),
            counts.get(p["id"], 0),
        ])
    return ws


def sheet_places(wb, places):
    ws = wb.create_sheet("地名")
    headers = ["id", "正名(tradName)", "简体名(name)", "类别", "时代", "简介",
               "别名(竖线分隔)", "状态", "备注(你写)", "pinyin"]
    widths = [16, 14, 14, 8, 10, 36, 26, 8, 20, 14]
    ro = ["id", "简体名(name)", "pinyin"]
    style_sheet(ws, headers, widths, ro)
    for p in places:          # 同 sheet_persons：保持源顺序，不预排序
        ws.append([
            p["id"], p.get("tradName") or "", p.get("name") or "",
            p.get("kind") or "", p.get("era") or "", p.get("summary") or "",
            "|".join(p.get("aliases") or []), "active", "",
            pinyin_of(p.get("tradName")),
        ])
    return ws


def make_uid(chapter_id, para, seq, text):
    """初版稳定主键。生成一次后应固化在表里，不再重算。"""
    raw = "{}|{}|{}|{}".format(chapter_id, para, seq, text)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def sheet_sentences(wb, sentences, chapters, books):
    ws = wb.create_sheet("句子")
    headers = ["uid", "位置键", "书", "篇(chapterId)", "篇名", "段序", "句序",
               "原文", "状态", "备注(你写)"]
    widths = [14, 16, 8, 12, 26, 7, 7, 70, 8, 20]
    ro = ["uid", "位置键", "书", "篇(chapterId)", "篇名", "段序", "句序"]
    style_sheet(ws, headers, widths, ro)
    n = 0
    for s in sentences:
        cid = s.get("chapterId") or ""
        bk = cid.split("-")[0]
        if bk not in books:
            continue
        ch = chapters.get(cid, {})
        ws.append([
            make_uid(cid, s.get("paraSeq"), s.get("seq"), s.get("text") or ""),
            s.get("id") or "",
            BOOK_NAME.get(bk, bk),
            cid,
            ch.get("fullTitle") or ch.get("title") or "",
            s.get("paraSeq"), s.get("seq"),
            s.get("text") or "",
            "active", "",
        ])
        n += 1
    return ws, n


def sheet_readme(wb, what):
    ws = wb.create_sheet("说明", 0)
    lines = [
        ("BOOKINDEX 工作簿 · {}".format(what), True),
        ("", False),
        ("本文件此刻只是「视图」，权威源仍是 pipeline/persons_data.py。", False),
        ("等 P0 第 3 步做完（pipeline 改成读 xlsx），它才升级成权威源。", False),
        ("在那之前随便删，重跑 build_workbook.py 就能再生。", False),
        ("", False),
        ("列底色说明", True),
        ("  浅灰底 = 只读辅助列（pipeline 不读，你改它也没用，纯为排序/筛选）", False),
        ("  白底   = 可编辑列（改了会被 pipeline 采用）", False),
        ("", False),
        ("怎么用「只看某一本书」", True),
        ("  在人物/地名表筛 in_sj / in_hs / in_hhs / in_sgz / in_js 列的 TRUE。", False),
        ("  不用按书拆 sheet——人物是跨书实体（劉邦五本书都有），拆表会写重。", False),
        ("", False),
        ("怎么按拼音找人", True),
        ("  对 pinyin 列升序排序。该列由 pypinyin 生成，多音字个别不准，", False),
        ("  你直接改这一列不影响任何功能。", False),
        ("", False),
        ("关于 uid", True),
        ("  句子表的 uid 是稳定主键（md5 前 12 位）。首次生成后必须固化在表里，", False),
        ("  之后即使改动句子顺序/边界也不许重算——否则全部外键会失效。", False),
    ]
    for i, (txt, bold) in enumerate(lines, start=1):
        c = ws.cell(row=i, column=1, value=txt)
        if bold:
            c.font = HDR_FONT
    ws.column_dimensions["A"].width = 78


def load_source_persons():
    """人名取**源数据** persons_data.PERSONS，不取 people.json。

    people.json 是 build_dict 的**产物**（别名已展开简繁两版、字段已加工），
    拿它当导出源就形成了 build_dict → people.json → xlsx → build_dict 的循环。
    源数据才是单向链的起点。

    元组格式：(id, 简体名, 繁体名, 朝代, 头衔, 简介, [别名...])
    """
    from persons_data import PERSONS
    return [{"id": t[0], "name": t[1], "tradName": t[2], "dynasty": t[3],
             "title": t[4], "summary": t[5], "aliases": list(t[6] or [])}
            for t in PERSONS]


PERSON_HUMAN_FIELDS = ["正名(tradName)", "朝代", "头衔", "简介",
                       "别名(竖线分隔)", "状态", "备注(你写)"]
PLACE_HUMAN_FIELDS = ["正名(tradName)", "类别", "时代", "简介",
                      "别名(竖线分隔)", "状态", "备注(你写)"]


def _norm(v):
    """比眼前的裁定要用同一个口径，否则闸门会自己吵醒自己。

    Excel 里没写过的单元格读回来是 `None`，Python 源数据里是 `""`——
    直接 `!=` 会让**每一条**都判成「你改过」（实测 1570 条全红），
    闸门一旦过敏就等于没有。
    """
    return "" if v is None else str(v).strip()


def _human_row(rec, kind):
    """把一条源数据折成「人会写的那些列」的值元组（顺序见上面的常量）。"""
    if kind == "person":
        row = (rec.get("tradName"), rec.get("dynasty"), rec.get("title"),
               rec.get("summary"), "|".join(rec.get("aliases") or []), "active", "")
    else:
        row = (rec.get("tradName"), rec.get("kind"), rec.get("era"),
               rec.get("summary"), "|".join(rec.get("aliases") or []), "active", "")
    return tuple(_norm(x) for x in row)


def read_existing_rows(path, sheet, fields):
    """读已有工作簿里「人会写的列」→ {id: tuple}；读不出来就返回 None。

    ⚠️ **只读辅助列不参与比较**：`pinyin` / `in_<书>` / `命中数` 每次重跑都可能变
    （命中数一变就是满表更新），拿它们比对会永远判成「人改过」，闸门就废了。
    """
    if not path.exists():
        return None
    try:
        wb = load_workbook(path)
    except Exception as e:                      # 表被别的方式弄坏了，别拦着重建
        print("  ⚠ {} 读不出来（{}），本次可直接覆盖".format(path.name, e))
        return None
    if sheet not in wb.sheetnames:
        return None
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return None
    hdr = list(rows[0])
    try:
        iid = hdr.index("id")
        idx = [hdr.index(f) for f in fields]
    except ValueError:                          # 列名被改动过 → 当作「有人工痕迹」
        return None
    out = {}
    for r in rows[1:]:
        if iid >= len(r) or not r[iid]:
            continue
        out[r[iid]] = tuple(_norm(r[j] if j < len(r) else None) for j in idx)
    return out


def resolve_target(path, sheet, fields, records, kind, force):
    """**红线 1 的具体落实**：pipeline 想写 Excel 的地方，一律「写新版本 + 报差异」。

    否则你在表格里改的别名、标的状态、写的备注，会被一次重跑悄悄冲掉——
    而 `persons.xlsx` 已经是权威源，冲掉它就等于回到种子数据。

    返回 (真正要写的路径, 是否有检测到你的改动)
    - 文件不存在 / 加了 --force          → 直接写目标文件
    - 「人会写的列」与源数据完全一致      → 幂等重建，覆盖无风险，直接写
    - 检测到不一致                        → 改写 `<名>.new.xlsx`，原表一根手指都不碰
    """
    if force or not path.exists():
        return path, False
    old = read_existing_rows(path, sheet, fields)
    if old is None:
        return path, False
    new = {r["id"]: _human_row(r, kind) for r in records}

    diffs = []
    for pid in list(new.keys()):
        if pid not in old:
            diffs.append(("新增", pid, "", "; ".join(str(x) for x in new[pid])))
        elif old[pid] != new[pid]:
            diffs.append(("改", pid, str(old[pid]), str(new[pid])))
    for pid in list(old.keys()):
        if pid not in new:
            diffs.append(("你的表里有、源数据没有", pid, str(old[pid]), ""))

    if not diffs:
        return path, False                       # 幂等重建：覆盖等于没改

    new_path = path.with_name(path.stem + ".new" + path.suffix)
    print()
    print("  ⚠ {} 检测到 {} 处你看上去的手改，本次**不覆盖**它：".format(
        path.name, len(diffs)))
    for kind_, pid, o, n in diffs[:5]:
        print("      · [{}] {}\n          表里：{}\n          源数据：{}".format(
            kind_, pid, o[:90], n[:90]))
    if len(diffs) > 5:
        print("      · …… 另有 {} 处".format(len(diffs) - 5))
    print("      新版本已写成 {}，比对后再决定要不要替。".format(new_path.name))
    print("      确认要以源数据为准重来：加 --force（会先把原表备份成 .bak）")
    return new_path, True


def _backup(path, force):
    """`--force` 覆盖前先留一条退路——覆盖不可撤销，备份才让「强行」这个词成立。"""
    if not (force and path.exists()):
        return
    bak = path.with_name("{}.bak-{}.xlsx".format(
        path.stem, time.strftime("%Y%m%d-%H%M%S")))
    shutil.copyfile(path, bak)
    print("  已备份 → {}".format(bak.name))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", default="sj", help="导出哪几本书的句子，逗号分隔")
    ap.add_argument("--all-books", action="store_true", help="句子导出全部五书")
    ap.add_argument("--force", action="store_true",
                    help="即使检测到表格里有人工改动也强行重建（先自动备份）")
    a = ap.parse_args()

    people = load_source_persons()
    places = json.loads(PLACES.read_text(encoding="utf-8"))["places"]
    # in_<书> 与命中数是**只读辅助列**（只给你排序/筛选用，pipeline 不读），
    # 来自标注产物；首次导出时它们还不存在，缺失就留空，不让导出卡住。
    bd = (json.loads(BOOK.read_text(encoding="utf-8")) if BOOK.exists()
          else {"persons": [], "chapters": [], "sentences": []})
    counts = {p["id"]: p.get("mentionCount", 0) for p in bd["persons"]}
    bookmap = {p["id"]: sorted((p.get("byBook") or {}).keys()) for p in bd["persons"]}
    chapters = {c["id"]: c for c in bd["chapters"]}
    books = set(BOOKS) if a.all_books else {b.strip() for b in a.books.split(",")}

    # 三个工作簿：人物 / 地名 / 句子（见 docs/21 §5.5）。
    # 人物与地名各一个 sheet（跨书实体，不按书切）；句子按书/卷拆。
    OUT.mkdir(exist_ok=True)
    outs = []

    # 人物 / 地名：先过「人工改动」闸门，再决定写到哪里（红线 1）
    wb = Workbook(); wb.remove(wb.active)
    sheet_readme(wb, "人物")
    sheet_persons(wb, people, counts, bookmap)
    t1 = OUT / "persons.xlsx"
    w1, _ = resolve_target(t1, "人物", PERSON_HUMAN_FIELDS, people, "person", a.force)
    _backup(t1, a.force)
    wb.save(w1); outs.append((w1, len(people)))

    wb = Workbook(); wb.remove(wb.active)
    sheet_readme(wb, "地名")
    sheet_places(wb, places)
    t2 = OUT / "places.xlsx"
    w2, _ = resolve_target(t2, "地名", PLACE_HUMAN_FIELDS, places, "place", a.force)
    _backup(t2, a.force)
    wb.save(w2); outs.append((w2, len(places)))

    # 句子是纯派生视图（人不改它），可以无条件覆盖
    wb = Workbook(); wb.remove(wb.active)
    sheet_readme(wb, "句子")
    _, n = sheet_sentences(wb, bd["sentences"], chapters, books)
    tag = "all" if a.all_books else "-".join(sorted(books))
    p3 = OUT / "sentences-{}.xlsx".format(tag); wb.save(p3); outs.append((p3, n))

    for path, rows in outs:
        print("-> {}   {} 行".format(path, rows))
    print("   只读辅助列：pinyin、in_<书>、命中数、id、位置键、篇名")


if __name__ == "__main__":
    main()
