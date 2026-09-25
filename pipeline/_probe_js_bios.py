# -*- coding: utf-8 -*-
"""列传卷首探传主（只读）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
v = json.loads((ROOT / "data/dict/volumes/js.json").read_text(encoding="utf-8"))

# 姓+名 2-3 字，后接 字/諱/，/。/， 人也
NAME = re.compile(r"([一-鿿]{2,3})(?:，|字|諱|，|。)")

for n in range(31, 101):
    s = "{:03d}".format(n)
    d = json.loads((ROOT / f"data/corpus/js-{s}.json").read_text(encoding="utf-8"))
    t = "".join((p.get("text") or "") for p in (d.get("paragraphs") or [])[:2])
    t = t.replace("\n", "")
    # 常见开篇：「某某，字…」「某某字…」「某某，…人也」
    names = []
    for m in re.finditer(r"([一-鿿]{2,3})(?:，字|字[一-鿿]{1,2}，|，[一-鿿]{0,6}人也)", t[:200]):
        names.append(m.group(1))
    # 合传：再扫前 400 字内「某某，字」
    if not names:
        for m in re.finditer(r"([一-鿿]{2,3})，字", t[:400]):
            names.append(m.group(1))
    print(f"{s} {v[s][:22]:22} | {','.join(dict.fromkeys(names))[:40]:40} | {t[:50]}")
