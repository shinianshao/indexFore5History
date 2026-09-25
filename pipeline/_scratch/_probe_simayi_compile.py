# -*- coding: utf-8 -*-
"""复现 annotate 的别名编译与匹配，定位 司馬懿/仲達 漏召。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))  # 已移入 _scratch/，补回 pipeline/ 以便导入 common / trad
from common import compile_alias_pattern, norm  # noqa: E402

ppl = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
persons = ppl["persons"]

# 按 annotate 同逻辑编译 sgz 模式
generic_forms = set()
for entry in ppl.get("genericAliases") or []:
    for form in entry["forms"]:
        generic_forms.add(norm(form))

base_pairs = []
book_pairs = {}
for person in persons:
    books = person.get("books") or []
    for alias in person["aliases"]:
        if norm(alias) in generic_forms:
            continue
        if books:
            for code in books:
                book_pairs.setdefault(code, []).append((alias, person["id"]))
        else:
            base_pairs.append((alias, person["id"]))

base_alias = {norm(a) for a, _ in base_pairs}
extra = [(a, pid) for a, pid in book_pairs.get("sgz", []) if norm(a) not in base_alias]
pat, mapping = compile_alias_pattern(base_pairs + extra)

print("mapping keys containing 司馬/仲達/宣帝:")
for k, v in sorted(mapping.items()):
    if any(x in k for x in ("司馬", "仲達", "宣帝", "司马", "仲达")):
        print(repr(k), "->", v)

print("\nbook_pairs sgz 里的司馬懿/仲達:")
for a, pid in book_pairs.get("sgz", []):
    if "司馬" in a or "仲達" in a or "仲达" in a or a in ("宣帝", "晋宣帝", "晉宣帝"):
        print(repr(a), pid, "norm=", repr(norm(a)))

samples = [
    "督軍御史中丞司馬懿、侍御史鄭渾",
    "尚書僕射西鄉侯司馬懿爲撫軍大將軍",
    "司馬懿臨危制變",
    "司馬仲達所能頡頏",
    "死諸葛走生仲達",
    "仲達歐血乎",
    "晉宣帝率二十萬眾拒亮",
    "宣帝常謂亮持重",
    "司馬懿所向無前",
]
print("\n=== 样例匹配 ===")
for s in samples:
    ns = norm(s)
    hits = [(m.group(0), mapping.get(m.group(0)), m.start(), m.end()) for m in pat.finditer(ns)]
    print(s, "->", hits)

# 从 sgz-02 实际句再试
doc = json.loads((ROOT / "data/corpus/sgz-02.json").read_text(encoding="utf-8"))
for para in doc["paragraphs"]:
    for sent in para["sentences"]:
        if "司馬懿" in sent["text"]:
            ns = norm(sent["text"])
            hits = [(m.group(0), mapping.get(m.group(0))) for m in pat.finditer(ns)]
            print("\nREAL:", sent["text"][:80])
            print(" norm:", ns[:80])
            print(" hits:", hits)
            print(" 司馬懿 in ns?", "司馬懿" in ns, "司馬懿" in ns)
