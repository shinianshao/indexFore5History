# -*- coding: utf-8 -*-
"""裴注人物索引：只扫三国志 〈…〉 注文，**不进**主索引统计。

口径（docs/10 已拍板）：
  裴注保留为注、不参与正文人名地名统计；
  本脚本单独产出 pei 索引，供人物页「裴注提及」使用。

产物：
  data/index/pei-data.json
  web/pei-data.js          window.PEI_DATA
  pipeline/_pei_report.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CORPUS, DICT, INDEX, PIPELINE, WEB,  # noqa: E402
                    corpus_paths, load_json, norm, write_json)
from annotate import alias_ok, build_scoped, t2s  # noqa: E402

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
except Exception:
    _T2S = None

# 每人最多保留的样例条数（控产物体积）
MAX_SAMPLES_PER_PERSON = 40
MAX_SAMPLES_PER_CHAPTER = 8
ANGLE_RE = re.compile(r"〈[^〉]*〉")


def pei_text(para: dict) -> str:
    """段内裴注正文（去掉 〈〉 包装，只留注文内容）。"""
    raw = para.get("note") or ""
    if not raw:
        # 兜底：从 text 再剥
        from build import peel_angle_notes
        raw = peel_angle_notes(para.get("text") or "")[1]
    parts = []
    for m in ANGLE_RE.finditer(raw):
        parts.append(m.group(0)[1:-1])
    # 悬空注文
    if "〈" in raw and "〉" not in raw:
        parts.append(raw[raw.find("〈") + 1:])
    elif "〉" in raw and "〈" not in raw:
        parts.append(raw[: raw.find("〉")])
    return "\n".join(parts) if parts else (raw.strip("〈〉") if raw else "")


def build_core_pattern(people: dict, book_code: str):
    """与 annotate 同构：全局 core + 本书专属，不含泛称。"""
    generics = people.get("genericAliases") or []
    generic_forms = set()
    for entry in generics:
        for form in entry.get("forms") or ():
            generic_forms.add(norm(form))

    base_pairs, book_pairs = [], defaultdict(list)
    for person in people["persons"]:
        books = person.get("books") or []
        for alias in person["aliases"]:
            if norm(alias) in generic_forms:
                continue
            if books:
                if book_code in books:
                    book_pairs[person["id"]]  # noop keep structure
                    book_pairs[book_code].append((alias, person["id"]))
            else:
                base_pairs.append((alias, person["id"]))
    # 合并：base + 本书记专属（与 annotate book_pat 相同逻辑）
    extra = [
        (a, pid)
        for a, pid in book_pairs.get(book_code, [])
        if norm(a) not in {norm(x) for x, _ in base_pairs}
    ]
    from common import compile_alias_pattern
    return compile_alias_pattern(base_pairs + extra)


def main():
    people = load_json(os.path.join(DICT, "people.json"),
                       {"persons": [], "chapterOwners": {}})
    persons = {p["id"]: p for p in people["persons"]}
    pat, smap = build_core_pattern(people, "sgz")
    scoped = build_scoped(people)

    # pid -> 累计
    person_n = Counter()
    person_ch = defaultdict(set)
    person_alias = defaultdict(Counter)
    person_by_chapter = defaultdict(Counter)  # pid -> {cid: n}
    # 样例：按人保留，每篇最多几条
    person_samples = defaultdict(list)
    chapter_n = Counter()  # cid -> n
    para_with_pei = 0
    pei_chars = 0
    hit_marks = 0

    sample_per_chapter = defaultdict(int)  # (pid, cid) -> count

    for path in corpus_paths(ready_only=True):
        doc = load_json(path)
        if doc.get("bookId") != "sgz":
            continue
        cid = doc["chapterId"]
        last_text_pseq = 1
        for para in doc.get("paragraphs") or []:
            if para.get("sentences"):
                last_text_pseq = para.get("seq", 1)
            text = pei_text(para)
            if not text:
                continue
            para_with_pei += 1
            pei_chars += len(text)
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
                # 上下文摘录
                a = max(0, s - 18)
                b = min(len(text), e + 22)
                person_samples[pid].append({
                    "cid": cid,
                    "pseq": target_pseq,
                    "alias": surface,
                    "s": s - a,
                    "e": e - a,
                    "text": text[a:b],
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

            # 篇内限定单字（与正文同规则）
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

    # 输出
    out_persons = {}
    for pid, n in person_n.most_common():
        out_persons[pid] = {
            "n": n,
            "chapters": len(person_ch[pid]),
            "aliases": [
                {"w": w, "n": c}
                for w, c in person_alias[pid].most_common(12)
            ],
            "byChapter": dict(person_by_chapter[pid].most_common(30)),
            "items": person_samples[pid][:MAX_SAMPLES_PER_PERSON],
        }

    # 索引：chapter -> [{pid, n}]
    chapter_index = defaultdict(lambda: Counter())
    for pid, items in person_samples.items():
        for it in items:
            chapter_index[it["cid"]][pid] += 1
    # 用全量计数覆盖样例计数
    ch_person = defaultdict(Counter)
    for pid, chs in person_ch.items():
        # 需要每篇命中数——上面 chapter_n 只有总数
        pass

    # 重算每篇每人：二次结构
    # samples 不完整时用 person_ch 不够——在循环里补 chapter_person
    # 为稳妥：重新从 person_samples 不可靠，改为在 add_hit 外再累加
    # 简化产物：只输出 persons + meta，chapters 用 items 聚合（近似，全量 n 仍准确）

    meta = {
        "bookId": "sgz",
        "book": "三國志",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": "裴注〈…〉内人物命中；不参与正文 mentionCount/泛称基线。",
        "paragraphsWithNote": para_with_pei,
        "noteChars": pei_chars,
        "mentionCount": hit_marks,
        "personCount": len(out_persons),
        "chapterCount": len(chapter_n),
    }

    data = {
        "meta": meta,
        "persons": out_persons,
        "chapters": {
            cid: {"n": chapter_n[cid]}
            for cid in sorted(chapter_n)
        },
    }

    write_json(os.path.join(INDEX, "pei-data.json"), data, indent=2)
    js_path = os.path.join(WEB, "pei-data.js")
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write("window.PEI_DATA = ")
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")

    write_json(os.path.join(PIPELINE, "_pei_report.json"), {
        **meta,
        "top": [
            {"pid": pid,
             "name": persons.get(pid, {}).get("tradName", pid),
             "n": out_persons[pid]["n"],
             "chapters": out_persons[pid]["chapters"]}
            for pid, _ in person_n.most_common(20)
        ],
    }, indent=2)

    print(
        "裴注段 {} / 注文 {} 字 / 命中 {} / 人物 {} / 篇 {}".format(
            para_with_pei, pei_chars, hit_marks, len(out_persons), len(chapter_n)
        )
    )
    for pid, _ in person_n.most_common(8):
        print(
            "  {} {} ×{} / {} 篇".format(
                pid,
                persons.get(pid, {}).get("tradName", pid),
                out_persons[pid]["n"],
                out_persons[pid]["chapters"],
            )
        )


if __name__ == "__main__":
    main()
