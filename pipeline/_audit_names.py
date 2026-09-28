# -*- coding: utf-8 -*-
"""人名索引**正名**体检：把「不像人名」和「明显错了」的条目挑出来。

用户反馈（2026-09-26）：「完整查看人名索引名称，可以发现有些还带了身份名，
还有不少是错误的」。

本脚本只做**检测**，不改数据。检测分八道：

  N1 正名带谥号/爵位后缀（…王、…公、…侯、…君、…帝、…太后、…夫人）
  N2 正名带官职（太守、將軍、相國、司馬、大夫…）
  N3 正名是**简体形**（铁律：只写繁体）
  N4 name（简体）与 tradName（繁体）**对不上**（OpenCC 互转不等）
  N5 朝代与所属书**明显冲突**（如人只出现在晋书，却标「上古/西漢/春秋」）
  N6 aliases 里混进了**正名本身**（冗余，会把 topAliases 撑成两行）
  N7 aliases 里混进**简体形**（同 N3，只是发生在别名里）
  N8 正名含非姓名标记（「各书提及人物」「某某之子」等批量补人的模板残渣）

用法
----
    python pipeline/_audit_names.py                # 全量体检，报八道计数 + 样本
    python pipeline/_audit_names.py --n1 40        # 某道多打些
    python pipeline/_audit_names.py --out pipeline/_name_issues.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PEOPLE = ROOT / "data" / "dict" / "people.json"

try:
    from opencc import OpenCC
    _t2s = OpenCC("t2s").convert
    _s2t = OpenCC("s2t").convert
except Exception:                                     # pragma: no cover
    def _t2s(s):
        return s
    def _s2t(s):
        return s

# N1：谥号/爵位后缀。真正的**人名**不会以这些结尾（姬昌、嬴政才是人名）。
TITLE_SUFFIX = ("太后", "太子", "王后", "皇后", "夫人", "相国", "相國", "将军", "將軍",
                "皇帝", "太傅", "太师", "太師", "太保", "太守", "太后", "王", "公",
                "侯", "君", "帝", "后", "妃", "姬", "主")
# N2：官职/身份词，出现在正名**任何位置**都可疑（「京兆尹防」这类是误抽）
OFFICE_WORDS = ("太守", "將軍", "将军", "相國", "相国", "司馬", "司马", "司徒", "司空",
                "太尉", "太傅", "太師", "太师", "太保", "大夫", "尚書", "尚书",
                "刺史", "校尉", "中郎", "京兆", "御史", "丞相", "侍中", "令史",
                "王公", "公子", "太后", "皇后")
# N8：批量补人时带进来的模板残渣
TEMPLATE_MARK = ("各书提及人物", "之子", "之弟", "之兄", "之姊", "之妹", "之女",
                 "之妻", "之母", "之父", "部将", "部將", "（《", "人物，")

# N5：书 → 该人可能所属朝代（用于判断朝代是否明显冲突）
BOOK_DYNASTIES = {
    "sj": {"上古", "夏", "商", "西周", "春秋", "戰國", "秦", "西漢"},
    "hs": {"西周", "春秋", "戰國", "秦", "西漢", "新"},
    "hhs": {"西周", "春秋", "戰國", "秦", "西漢", "新", "東漢", "三國"},
    "sgz": {"東漢", "三國", "西漢", "戰國", "秦"},
    "js": {"三國", "西晉", "東晉", "十六國", "東漢", "西漢", "春秋", "戰國", "上古", "西周", "秦", "夏", "商"},
}
# 泛代（用典、追述）不算冲突——这些人被追述到哪本书都可能
VAGUE_DYNASTY = {"上古", "西周", "春秋", "戰國", "夏", "商", "秦"}


def is_trad(s):
    """s 是否已是繁体（OpenCC s2t 不改就是繁体）。"""
    return _s2t(s) == s


def load():
    return json.loads(PEOPLE.read_text(encoding="utf-8"))["persons"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15, help="每道打印几条")
    ap.add_argument("--n1", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    persons = load()
    hits = {k: [] for k in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8")}

    for p in persons:
        pid = p["id"]
        nm = p.get("name") or ""
        tn = p.get("tradName") or ""
        dyn = p.get("dynasty") or ""
        books = list((p.get("byBook") or {}).keys()) or (p.get("books") or [])
        aliases = p.get("aliases") or []
        summ = p.get("summary") or ""
        title = p.get("title") or ""

        def rec(kind, why):
            hits[kind].append({"pid": pid, "name": nm, "tradName": tn,
                               "dynasty": dyn, "books": books,
                               "title": title, "why": why,
                               "summary": summ[:36]})

        # N1 谥号/爵位后缀
        for suf in TITLE_SUFFIX:
            if tn.endswith(suf) and len(tn) > len(suf):
                # 「周公旦」「王莽」这种不是称号：末字前是人名用字不做强判，
                # 这里只挑「姓/国 + 谥 + 爵」三段式（长度≥3 且含谥号字）
                rec("N1", "正名以「{}」结尾".format(suf))
                break
        # N2 官职
        for w in OFFICE_WORDS:
            if w in tn:
                rec("N2", "正名含官职/身份词「{}」".format(w))
                break
        # N3 正名是简体形
        if tn and not is_trad(tn):
            rec("N3", "正名「{}」是简体形（规范繁体：{}）".format(tn, _s2t(tn)))
        # N4 name 与 tradName 对不上
        if tn and nm and _t2s(tn) != nm:
            rec("N4", "简体名「{}」≠ t2s(繁体名「{}」)=「{}」".format(nm, tn, _t2s(tn)))
        # N5 朝代与书冲突
        if dyn and dyn not in VAGUE_DYNASTY and books:
            allowed = set()
            for b in books:
                allowed |= BOOK_DYNASTIES.get(b, set())
            if allowed and dyn not in allowed:
                rec("N5", "朝代「{}」与所属书 {} 不匹配（该书常见：{}）".format(
                    dyn, "/".join(sorted(books)), "/".join(sorted(allowed)[:6])))
        # N6 别名里混进正名
        dup = [x for x in aliases if x == tn or x == nm]
        if dup:
            rec("N6", "别名里含正名本身：{}".format("/".join(dup[:3])))
        # N7 别名里的简体形
        simp = [x for x in aliases if x and not is_trad(x)]
        if simp:
            rec("N7", "别名含简体形：{}".format("/".join(simp[:4])))
        # N8 模板残渣
        for m in TEMPLATE_MARK:
            if m in summ or m in title:
                rec("N8", "「{}」疑似批量补人模板残渣".format(m))
                break

    print("人物 {} 人。八道体检：\n".format(len(persons)))
    print("| 闸 | 含义 | 命中 |")
    print("|---|---|---:|")
    names = {"N1": "正名带谥号/爵位后缀", "N2": "正名带官职/身份词",
             "N3": "正名是简体形", "N4": "简繁正名对不上",
             "N5": "朝代与所属书冲突", "N6": "别名含正名本身",
             "N7": "别名含简体形", "N8": "批量补人模板残渣"}
    for k in sorted(hits):
        print("| {} | {} | {} |".format(k, names[k], len(hits[k])))

    for k in sorted(hits):
        n = a.n1 if (a.n1 and k == "N1") else a.n
        rows = hits[k]
        if not rows:
            continue
        print("\n### {} {}（{} 条，打印 {} 条）".format(k, names[k], len(rows), min(n, len(rows))))
        for r in rows[:n]:
            print("  · {} {} / {} 【{}】书={} — {}".format(
                r["pid"], r["tradName"], r["name"], r["dynasty"],
                "/".join(r["books"]) or "-", r["why"]))

    if a.out:
        Path(a.out).write_text(json.dumps(hits, ensure_ascii=False, indent=1),
                               encoding="utf-8")
        print("\n-> {}".format(a.out))


if __name__ == "__main__":
    main()
