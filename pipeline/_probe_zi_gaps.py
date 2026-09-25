# -*- coding: utf-8 -*-
"""P2-a 表字/尊称长尾体检：从 summary 抽「字X」，量它在语料里的命中。

目标：命中 ≥10 的表字早已收进别名；**命中 1–10 的长尾**还没收，逐批补。

用法：
    python pipeline/_probe_zi_gaps.py                 # 全量
    python pipeline/_probe_zi_gaps.py --min 3 --max 10
    python pipeline/_probe_zi_gaps.py --missing-only  # 只看还没进别名的
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEOPLE = json.loads(
    (ROOT / "data" / "dict" / "people.json").read_text(encoding="utf-8"))["persons"]
BD = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
BY_ID = {p["id"]: p for p in BD["persons"]}

# 「字X」抽取：字 后 1–2 字，后跟句读或到 summary 结尾
PAT_ZI = re.compile(r"字([\u4e00-\u9fff]{1,2})(?=[，。、；\s）)]|$)")

# 单字表字不加守卫就是灾难（「字伯」满地都是），默认跳过
STOP_1CHAR = True


def load_corpus():
    buf = []
    for f in sorted(glob.glob(str(ROOT / "data" / "corpus" / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        parts = []
        for para in d.get("paragraphs") or []:
            if para.get("text"):
                parts.append(para["text"])
            for s in para.get("sentences") or []:
                if s.get("text"):
                    parts.append(s["text"])
        buf.append("\n".join(parts))
    return "\n".join(buf)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=1)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--missing-only", action="store_true")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", default=None, help="把「可补」清单写成 json")
    ap.add_argument("--samples", type=int, default=0, help="打印前 N 条的原文上下文")
    a = ap.parse_args()

    text = load_corpus()
    rows = []
    seen = set()
    for p in PEOPLE:
        summary = p.get("summary") or ""
        aliases = set(p.get("aliases") or [])
        for zi in PAT_ZI.findall(summary):
            if len(zi) < 2 and STOP_1CHAR:
                continue
            key = (p["id"], zi)
            if key in seen:
                continue
            seen.add(key)
            n = text.count(zi)
            if not (a.min <= n <= a.max):
                continue
            in_dict = zi in aliases
            if a.missing_only and in_dict:
                continue
            rows.append((n, p["id"], p.get("tradName") or p.get("name"), zi, in_dict))

    # ---- 冲突检测：表字不是人名，同名/同字/撞地名都会误挂 ----
    owner_of = Counter()
    for p in PEOPLE:
        for al in p.get("aliases") or []:
            owner_of[al] += 1
        owner_of[p.get("tradName") or p.get("name")] += 1
    place_names = set()
    try:
        pl = json.loads((ROOT / "data" / "dict" / "places.json").read_text(encoding="utf-8"))
        for q in (pl.get("places") if isinstance(pl, dict) else pl):
            place_names.add(q.get("tradName") or q.get("name"))
            for al in q.get("aliases") or []:
                place_names.add(al)
    except Exception:
        pass
    zi_owners = Counter()
    for _, _, _, zi, _ in rows:
        zi_owners[zi] += 1

    def conflicts(zi):
        out = []
        if zi_owners[zi] > 1:
            out.append("同字×{}".format(zi_owners[zi]))
        if owner_of.get(zi):
            out.append("撞人名×{}".format(owner_of[zi]))
        if zi in place_names:
            out.append("撞地名")
        return out

    rows.sort(reverse=True)
    clean = [r for r in rows if not conflicts(r[3])]
    dirty = [r for r in rows if conflicts(r[3])]
    print("表字长尾 {} 条（命中 {}~{}）　可补 {} / 有冲突 {}".format(
        len(rows), a.min, a.max, len(clean), len(dirty)))
    print("{:<5} {:<12} {:<8} {:<8} {}".format("命中", "pid", "人名", "表字", "已入典"))
    for n, pid, name, zi, in_dict in (dirty + clean)[: a.top]:
        cf = conflicts(zi)
        print("{:<5} {:<12} {:<8} {:<8} {} {}".format(
            n, pid, name, zi, "是" if in_dict else "否", "⚠" + "、".join(cf) if cf else ""))
    print("\n可补 {} 条 / 命中 {} 处；有冲突 {} 条 / 命中 {} 处".format(
        len(clean), sum(r[0] for r in clean), len(dirty), sum(r[0] for r in dirty)))
    if a.samples:
        print("\n── 原文样本（每条最多 2 句，用来人工看是不是真表字用法）──")
        for n, pid, name, zi, _ in (clean + dirty)[: a.samples]:
            shown = 0
            for f in sorted(glob.glob(str(ROOT / "data" / "corpus" / "*.json"))):
                if shown >= 2:
                    break
                d = json.loads(Path(f).read_text(encoding="utf-8"))
                for para in d.get("paragraphs") or []:
                    for s in para.get("sentences") or []:
                        t = s.get("text") or ""
                        if zi in t:
                            i = t.find(zi)
                            print("  {:<4} {:<8} {}".format(
                                zi, name, t[max(0, i - 16): i + len(zi) + 16]))
                            shown += 1
                            break
                    if shown >= 2:
                        break
    if a.out:
        Path(a.out).write_text(json.dumps(
            [{"pid": r[1], "name": r[2], "zi": r[3], "n": r[0]} for r in clean],
            ensure_ascii=False, indent=1), encoding="utf-8")
        print("可补清单 -> {}".format(a.out))


if __name__ == "__main__":
    main()
