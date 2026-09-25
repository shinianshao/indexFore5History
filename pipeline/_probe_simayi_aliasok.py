# -*- coding: utf-8 -*-
"""alias_ok / 句层过滤 诊断。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from common import compile_alias_pattern, norm  # noqa: E402
from annotate import alias_ok  # noqa: E402

ppl = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
persons = ppl["persons"]
generic_forms = set()
for entry in ppl.get("genericAliases") or []:
    for form in entry["forms"]:
        generic_forms.add(norm(form))

base_pairs, book_pairs = [], {}
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

total = matched = okn = 0
fail = []
for fp in sorted((ROOT / "data/corpus").glob("sgz-*.json")):
    doc = json.loads(fp.read_text(encoding="utf-8"))
    for pi, para in enumerate(doc.get("paragraphs") or []):
        for sent in para.get("sentences") or []:
            text = sent.get("text") or ""
            if "司馬懿" not in text and "仲達" not in text and "司馬仲達" not in text:
                continue
            total += 1
            ns = norm(text)
            for m in pat.finditer(ns):
                g = m.group(0)
                if "司馬懿" in g or "仲達" in g or g in ("晉宣帝", "晋宣帝"):
                    matched += 1
                    surface = text[m.start():m.end()]
                    ok = alias_ok(text, m.start(), m.end(), surface)
                    if ok:
                        okn += 1
                    else:
                        fail.append((doc["chapterId"], surface, text[max(0,m.start()-3):m.end()+3]))

print(f"含目标串的句 {total}，正则命中 {matched}，alias_ok 通过 {okn}，拦下 {len(fail)}")
for row in fail[:20]:
    print(" FAIL", row)

# 宣帝 resolve 模拟
print("\n=== 宣帝 candidates 书过滤后 ===")
for g in ppl.get("genericAliases") or []:
    if g.get("alias") != "宣帝":
        continue
    cands = g["candidates"]
    person_books = {p["id"]: p.get("books") or [] for p in persons if p.get("books")}
    filtered = [c for c in cands if not person_books.get(c) or "sgz" in (person_books.get(c) or [])]
    print("raw", cands, "default", g["default"])
    print("filtered for sgz", filtered)
    print("default in filtered?", g["default"] in filtered)
