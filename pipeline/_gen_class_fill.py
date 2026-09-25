# -*- coding: utf-8 -*-
"""类传/附传缺人 → 批量入典计划（P1-b）。

思路
----
类传（儒林/文苑/黨錮/循吏/酷吏/宦者/孝友/忠義/隱逸/藝術/列女…）与合传里的
从属人物没有独立传记，编目时最容易整批漏掉。他们出现的标志是**传主句式**：

    李充字大逊，陈留人也。        巴肅字恭祖，勃海高城人也
    張儉字符節，山陽高平人       楊政字子行，京兆人也。

凡是「X字Y」「X，Y人也」且**该处没有任何标注**、且 X 不在现有词典里
——就是没入典的人。频数门槛在这里没用（传主往往只出现一两次），
靠的是句式证据而不是出现次数。

用法
----
    python pipeline/_gen_class_fill.py                  # 扫类传篇目，打印预览 + 写计划
    python pipeline/_gen_class_fill.py --all            # 扫全书所有篇目（含附传）
    python pipeline/_gen_class_fill.py --book hhs
    python pipeline/_gen_class_fill.py --out FILE       # 默认 pipeline/_class_fill_plan.json

产出格式与 `_gen_persons_fill.py` 一致（{"new": [...], "alias": []}），
可直接交给 `_apply_persons_fill.py` 写入 build_dict.py。

清洗规则（宁缺勿滥）
--------------------
- 3 字且前两字是已知地名 → 砍掉首字（「濟陰曹曾」→「曹曾」）
- 含 王/侯/公/君/太后/皇帝/太子/將軍 → 弃（「懷侯嘉」这类是谥号不是人名）
- 繁体不动点校验失败 → 弃（否则 check_trad A/C 闸报警）
- 已入典（繁体或简体任一形命中现有别名）→ 弃
- 过 `_gen_persons_fill.is_person_name` 形态闸（姓表 + 官职/虚词噪声）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
import common  # noqa: E402
import _gen_persons_fill as gpf  # noqa: E402  （复用同一套人名形态闸）

CLASS_KEYS = (
    "儒林", "文苑", "循吏", "良吏", "酷吏", "忠義", "孝友", "隱逸", "逸民",
    "藝術", "方術", "列女", "獨行", "黨錮", "宦者", "貨殖", "游俠", "佞幸",
    "刺客", "滑稽", "日者", "龜策", "外戚", "宗室", "四夷", "夷", "蠻",
    "戎", "狄", "匈奴", "鮮卑", "烏桓", "西域", "東夷", "南蠻", "西羌",
)
TITLE_WORDS = set("王侯公君太后皇帝太子將軍相國")
DYN_BY_BOOK = {"sj": "西汉", "hs": "西汉", "hhs": "东汉", "sgz": "三国", "js": "晋"}

PAT_ZI = re.compile(r"([一-鿿]{2,3})[，、]?字([一-鿿]{1,2})")
PAT_REN = re.compile(r"([一-鿿]{2,3})(?:者)?[，、]([一-鿿]{2,6}?)人也")


def make_converter():
    """s2t / t2s；opencc 缺失时退化成恒等（但那样不动点校验会全过，需人工留意）。"""
    try:
        from opencc import OpenCC
        return OpenCC("s2t").convert, OpenCC("t2s").convert
    except Exception as exc:                       # pragma: no cover
        print("（opencc 不可用，简繁转换退化：{}）".format(exc))
        return (lambda x: x), (lambda x: x)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=None)
    ap.add_argument("--all", action="store_true", help="扫全部篇目而非仅类传")
    ap.add_argument("--zi-only", action="store_true",
                    help="只收「X字Y」句式（「X，Y人也」噪声大：任親愛/能弘道/成大業）")
    ap.add_argument("--out", default=str(ROOT / "pipeline" / "_class_fill_plan.json"))
    ap.add_argument("--top", type=int, default=30, help="预览行数")
    a = ap.parse_args()

    s2t, t2s = make_converter()
    bd = common.load_json(str(ROOT / "data" / "index" / "book-data.json"))
    chapters = {c["id"]: c for c in bd["chapters"]}
    persons = {p["id"]: p for p in bd["persons"]}
    dynasty_of = {p["id"]: p.get("dynasty", "") for p in bd["persons"]}

    known = set()
    for p in bd["persons"]:
        for x in [p.get("name"), p.get("tradName")] + list(p.get("aliases") or []):
            if x:
                known.add(x)
                known.add(t2s(x))
                known.add(s2t(x))
    place_aliases = set()
    for pl in bd.get("places") or []:
        for x in [pl.get("name")] + list(pl.get("aliases") or []):
            if x and len(x) >= 2:
                place_aliases.add(x)
                place_aliases.add(t2s(x))

    targets = {}
    for cid, ch in chapters.items():
        if a.book and ch["bookId"] != a.book:
            continue
        if not a.all and not any(k in ch["title"] for k in CLASS_KEYS):
            continue
        targets[cid] = ch

    sents_by_ch = defaultdict(list)
    for s in bd["sentences"]:
        if s.get("chapterId") in targets:
            sents_by_ch[s["chapterId"]].append(s)

    # 篇内主流朝代：新人物没有朝代，就用本篇已标注人物的主流朝代
    dom_dyn = {}
    for cid, ss in sents_by_ch.items():
        c = Counter()
        for s in ss:
            for m in s.get("marks") or []:
                d = dynasty_of.get(m.get("pid"))
                if d:
                    c[d] += 1
        dom_dyn[cid] = c.most_common(1)[0][0] if c else ""

    found = {}          # name_trad -> {"zi","chapters","books","ctx"}
    for cid in sorted(sents_by_ch):
        ch = targets[cid]
        for s in sents_by_ch[cid]:
            text = s.get("text") or ""
            occ = set()
            for m in s.get("marks") or []:
                for i in range(m.get("s", 0), m.get("e", 0)):
                    occ.add(i)
            for pat in ((PAT_ZI,) if a.zi_only else (PAT_ZI, PAT_REN)):
                for mt in pat.finditer(text):
                    i, j = mt.span(1)
                    if any(k in occ for k in range(i, j)):
                        continue
                    name = mt.group(1)
                    if len(name) == 3:
                        # 地名前缀砍首字：「濟陰曹曾」→「曹曾」、「山陽張匡」→「張匡」。
                        # 两种偏移都要试——正则可能从郡名的末字起抓（抓到「陰曹曾」）。
                        if text[max(0, i - 2):i] in place_aliases or \
                                text[max(0, i - 1):i + 1] in place_aliases or \
                                name[0] in "陰陽郡平陵":  # 「吳郡蔡洪」「東平劉楨」
                            name = name[1:]
                    if len(name) < 2 or len(name) > 3:
                        continue
                    if any(c in TITLE_WORDS for c in name):
                        continue
                    # 亲属称谓开头（「曾孫勳」「祖父峻」）——那不是人名
                    if name.startswith(("曾孫", "玄孫", "祖父", "從祖", "外祖", "叔祖",
                                        "叔父", "從父", "從兄", "外兄")) \
                            or name[0] in "族叔兄弟子隱":   # 「叔父泰」「隱兄瑚」
                        continue
                    trad = s2t(name)
                    if s2t(trad) != trad:             # 不动点
                        continue
                    if name in known or trad in known or t2s(trad) in known:
                        continue
                    if not gpf.is_person_name(trad):
                        continue
                    rec = found.setdefault(trad, {
                        "zi": mt.group(2), "chapters": set(), "books": set(),
                        "ctx": (ch["fullTitle"], text[max(0, i - 6):j + 10]),
                    })
                    rec["chapters"].add(cid)
                    rec["books"].add(ch["bookId"])

    # 生成计划
    used_pids = set(persons)
    plan_new = []
    for trad in sorted(found):
        rec = found[trad]
        # pid：与既有 p_x 习惯一致；碰撞就顺延
        base = "p_x" + format(abs(hash(trad)) % 100000, "05d")
        pid, n = base, 2
        while pid in used_pids:
            pid = "{}_{}".format(base, n)
            n += 1
        used_pids.add(pid)
        cid = sorted(rec["chapters"])[0]
        books = sorted(rec["books"])
        dyn = dom_dyn.get(cid) or DYN_BY_BOOK.get(books[0], "未知")
        cls = next((k for k in CLASS_KEYS if k in targets[cid]["title"]), "列傳")
        plan_new.append({
            "pid": pid,
            "name_trad": trad,
            "dynasty": dyn,
            "title": cls,
            "summary": "《{}》人物，字{}。".format(targets[cid]["fullTitle"], rec["zi"]),
            "aliases_trad": [trad, t2s(trad)],
            "books": books,
            "chapter": targets[cid]["fullTitle"],
            "sample": rec["ctx"][1],
        })

    Path(a.out).write_text(
        json.dumps({"new": plan_new, "alias": []}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("候选 {} 人 → {}".format(len(plan_new), a.out))
    print("\n| pid | 名 | 朝代 | 类 | 篇目 | 原文 |")
    print("|---|---|---|---|---|---|")
    for r in plan_new[:a.top]:
        print("| {} | {} | {} | {} | {} | {} |".format(
            r["pid"], r["name_trad"], r["dynasty"], r["title"],
            r["chapter"], r["sample"].replace("|", "｜")))
    by_book = Counter(b for r in plan_new for b in r["books"])
    print("\n按书：{}".format(dict(by_book)))


if __name__ == "__main__":
    main()
