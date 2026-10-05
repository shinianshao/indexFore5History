# -*- coding: utf-8 -*-
"""晋书旧史注人物索引（独立，不进正文 mentionCount）。

口径（docs/13 已拍板）：注文独立索引；UI 合计标【注N】。
产物：
  data/index/js-note-data.json
  web/js-note-data.js   window.JS_NOTE_DATA
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DICT, INDEX, PIPELINE, WEB, corpus_paths,  # noqa: E402
                    load_json, norm, write_json)
from annotate import alias_ok, build_scoped  # noqa: E402
from annotate_pei import MAX_SAMPLES_PER_CHAPTER, MAX_SAMPLES_PER_PERSON, build_core_pattern, pei_text  # noqa: E402

BOOK = "js"
BOOK_NAME = "晉書"


def main() -> None:
    people = load_json(os.path.join(DICT, "people.json"),
                       {"persons": [], "chapterOwners": {}})
    persons = {p["id"]: p for p in people["persons"]}
    pat, smap = build_core_pattern(people, BOOK)
    scoped = build_scoped(people)

    person_n = Counter()
    person_ch = defaultdict(set)
    person_alias = defaultdict(Counter)
    person_by_chapter = defaultdict(Counter)
    person_samples = defaultdict(list)
    chapter_n = Counter()
    para_with_note = 0
    note_chars = 0
    hit_marks = 0
    sample_per_chapter = defaultdict(int)

    for path in corpus_paths(ready_only=True):
        doc = load_json(path)
        if doc.get("bookId") != BOOK:
            continue
        cid = doc["chapterId"]
        last_text_pseq = 1
        for para in doc.get("paragraphs") or []:
            if para.get("sentences"):
                last_text_pseq = para.get("seq", 1)
            text = pei_text(para)
            if not text:
                continue
            para_with_note += 1
            note_chars += len(text)
            normalized = norm(text)
            occupied = [False] * len(text)
            target_pseq = para.get("seq", 1) if para.get("sentences") else last_text_pseq

            def add_hit(pid, s, e, surface):
                nonlocal hit_marks
                hit_marks += 1
                person_n[pid] += 1
                person_ch[pid].add(cid)
                person_by_chapter[pid][cid] += 1
                person_alias[pid][surface] += 1
                chapter_n[cid] += 1
                key = (pid, cid)
                if sample_per_chapter[key] >= MAX_SAMPLES_PER_CHAPTER:
                    return
                if len(person_samples[pid]) >= MAX_SAMPLES_PER_PERSON:
                    return
                sample_per_chapter[key] += 1
                a = max(0, s - 18)
                b = min(len(text), e + 22)
                person_samples[pid].append({
                    "cid": cid, "pseq": target_pseq, "alias": surface,
                    "s": s - a, "e": e - a, "text": text[a:b],
                })

            if pat:
                for m in pat.finditer(normalized):
                    pid = smap.get(m.group(0))
                    if not pid:
                        continue
                    if any(occupied[i] for i in range(m.start(), m.end())):
                        continue
                    surface = text[m.start():m.end()]
                    if not alias_ok(text, m.start(), m.end(), surface):
                        continue
                    for i in range(m.start(), m.end()):
                        occupied[i] = True
                    add_hit(pid, m.start(), m.end(), surface)

            extra = scoped.get(cid)
            if extra:
                for sp, sm in extra:
                    for m in sp.finditer(normalized):
                        if any(occupied[i] for i in range(m.start(), m.end())):
                            continue
                        pid = sm.get(m.group(0))
                        if not pid:
                            continue
                        surface = text[m.start():m.end()]
                        if not alias_ok(text, m.start(), m.end(), surface):
                            continue
                        for i in range(m.start(), m.end()):
                            occupied[i] = True
                        add_hit(pid, m.start(), m.end(), surface)

    out_persons = {}
    for pid, n in person_n.most_common():
        out_persons[pid] = {
            "n": n,
            "chapters": len(person_ch[pid]),
            "aliases": [{"w": w, "n": c} for w, c in person_alias[pid].most_common(12)],
            "byChapter": dict(person_by_chapter[pid].most_common(30)),
            "items": person_samples[pid][:MAX_SAMPLES_PER_PERSON],
        }

    meta = {
        "bookId": BOOK,
        "book": BOOK_NAME,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": "晉書舊史注〈…〉内人物命中；不参与正文 mentionCount/泛称基线。",
        "paragraphsWithNote": para_with_note,
        "noteChars": note_chars,
        "mentionCount": hit_marks,
        "personCount": len(out_persons),
        "chapterCount": len(chapter_n),
    }
    data = {
        "meta": meta,
        "persons": out_persons,
        "chapters": {cid: {"n": chapter_n[cid]} for cid in sorted(chapter_n)},
    }
    write_json(os.path.join(INDEX, "js-note-data.json"), data, indent=2)
    with open(os.path.join(WEB, "js-note-data.js"), "w", encoding="utf-8") as fh:
        fh.write("window.JS_NOTE_DATA = ")
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    write_json(os.path.join(PIPELINE, "_js_note_report.json"), {
        **meta,
        "top": [
            {"pid": pid, "name": persons.get(pid, {}).get("tradName", pid),
             "n": out_persons[pid]["n"], "chapters": out_persons[pid]["chapters"]}
            for pid, _ in person_n.most_common(20)
        ],
    }, indent=2)
    print("晉書舊史注段 {} / 注文 {} 字 / 命中 {} / 人物 {} / 篇 {}".format(
        para_with_note, note_chars, hit_marks, len(out_persons), len(chapter_n)))
    for pid, _ in person_n.most_common(8):
        print("  {} ×{}".format(persons.get(pid, {}).get("tradName", pid),
                               out_persons[pid]["n"]))


if __name__ == "__main__":
    main()
