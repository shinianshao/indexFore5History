# -*- coding: utf-8 -*-
"""以史记为标杆，对照 hhs/sgz：缺人、称谓、官名占用、篇主、书作用域、裴注。只读。"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
ppl = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
pei = json.loads((ROOT / "data/index/pei-data.json").read_text(encoding="utf-8"))

BOOKS = ("sj", "hs", "hhs", "sgz")
OFFICE = re.compile(
    r"(丞相|太尉|司徒|司空|太傅|太保|侍中|尚書|尚书|大將軍|大将军|將軍|将军|太守|刺史|州牧|牧$|驃騎|車騎|前將軍|後將軍|左將軍|右將軍)"
)
ZI = re.compile(r"字([一-鿿]{1,3})")


def person_by_id():
    return {p["id"]: p for p in bd["persons"]}


def dict_by_id():
    return {p["id"]: p for p in ppl["persons"]}


def sec(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


# ---------- 1. 体量对照 ----------
sec("1. 分书体量与人物密度（史记为标杆）")
for b in BOOKS:
    chs = [c for c in bd["chapters"] if c.get("bookId") == b]
    persons = [
        p
        for p in bd["persons"]
        if ((p.get("byBook") or {}).get(b) or {}).get("mentionCount", 0) > 0
    ]
    mentions = sum(
        ((p.get("byBook") or {}).get(b) or {}).get("mentionCount", 0)
        for p in bd["persons"]
    )
    owners = sum(1 for c in chs if c.get("mainPersons"))
    sents = [s for s in bd["sentences"] if s.get("chapterId", "").startswith(b + "-")]
    withp = sum(1 for s in sents if s.get("persons"))
    marks = sum(len(s.get("persons") or []) for s in sents)
    chars = sum(c.get("charCount") or 0 for c in chs)
    print(
        f"{b}: 篇 {len(chs):3} 字 {chars:8} 句 {len(sents):6} "
        f"有人句 {withp/len(sents) if sents else 0:5.1%} 人标 {marks:6} "
        f"命中人物 {len(persons):4} 提及 {mentions:6} 篇主 {owners:3}/{len(chs)}"
    )

# ---------- 2. 称谓完备度 ----------
sec("2. 称谓完备度（命中≥5）：字缺口 / 薄别名 / 尊称缺口")
for b in BOOKS:
    persons = [
        p
        for p in bd["persons"]
        if ((p.get("byBook") or {}).get(b) or {}).get("mentionCount", 0) >= 5
    ]
    if not persons:
        continue
    thin = sum(1 for p in persons if len(p.get("aliases") or []) <= 2)
    zi_gap = zi_tot = 0
    zi_samples = []
    for p in persons:
        aliases = set(p.get("aliases") or [])
        aliases.add(p["name"])
        aliases.add(p["tradName"])
        m = ZI.search(p.get("summary") or "")
        if not m:
            continue
        zi_tot += 1
        z = m.group(1)
        if len(z) >= 2 and z not in aliases and z not in "".join(aliases):
            zi_gap += 1
            n = ((p.get("byBook") or {}).get(b) or {}).get("mentionCount", 0)
            if len(zi_samples) < 8:
                zi_samples.append(f"{p['tradName']}字{z}×{n}")
    al_lens = [len(p.get("aliases") or []) for p in persons]
    print(
        f"{b}: ≥5人 {len(persons):4} 别名均 {sum(al_lens)/len(al_lens):.2f} "
        f"薄≤2 {thin:3}({thin/len(persons):.0%}) 双字字缺 {zi_gap}/{zi_tot}"
    )
    if zi_samples:
        print("   字缺例:", ", ".join(zi_samples))

# ---------- 3. 官名/帝号占用 ----------
sec("3. 裸官名/帝号是否仍被单人 core 占用")
# multi-pid aliases
alias_to_pids = defaultdict(set)
for p in ppl["persons"]:
    for a in (p.get("aliases") or []) + [p.get("name"), p.get("tradName")]:
        if a:
            alias_to_pids[a].add(p["id"])
multi = [(a, pids) for a, pids in alias_to_pids.items() if len(pids) > 1]
office_multi = [
    (a, pids)
    for a, pids in multi
    if OFFICE.search(a) or a in ("文帝", "武帝", "景帝", "宣帝", "太祖", "世祖", "高祖", "先主", "大帝")
]
print(f"多人共用别名总数: {len(multi)}  其中官名/帝号型: {len(office_multi)}")
for a, pids in sorted(office_multi, key=lambda x: -len(x[0]))[:20]:
    names = [
        next(
            (p.get("tradName") or p.get("name") for p in ppl["persons"] if p["id"] == pid),
            pid,
        )
        for pid in sorted(pids)[:6]
    ]
    print(f"  {a!r} → {names}")

# single-person bare office in aliases (should be 0 after #C)
bare_office = []
for p in ppl["persons"]:
    for a in p.get("aliases") or []:
        if a in (
            "丞相",
            "太尉",
            "司徒",
            "司空",
            "太傅",
            "太保",
            "侍中",
            "大將軍",
            "大将军",
            "將軍",
            "尚书",
            "尚書",
        ):
            bare_office.append((p["tradName"], a))
print(f"裸官名仍在单人 aliases: {len(bare_office)}", bare_office[:10])

# title=官名但不进 aliases（设计行为，报规模）
title_gap = Counter()
for b in BOOKS:
    for p in bd["persons"]:
        if ((p.get("byBook") or {}).get(b) or {}).get("mentionCount", 0) < 5:
            continue
        title = (p.get("title") or "").strip()
        aliases = set(p.get("aliases") or []) | {p.get("name"), p.get("tradName")}
        if title and title not in aliases and OFFICE.search(title):
            title_gap[b] += 1
print("title=官名且不在 aliases（设计不匹配）:", dict(title_gap))

# ---------- 4. 篇主空缺 ----------
sec("4. 篇主空缺（整篇讲述无主人公）")
for b in BOOKS:
    empty = [c for c in bd["chapters"] if c.get("bookId") == b and not c.get("mainPersons")]
    print(f"{b}: 空篇主 {len(empty)}")
    for c in empty[:12]:
        print(f"   {c['id']} {c.get('fullTitle')} / {c.get('category')}")
    if len(empty) > 12:
        print(f"   … 另 {len(empty)-12} 篇")

# ---------- 5. 书作用域 vs byBook ----------
sec("5. 书作用域把命中挡在外面 / byBook 越界")
byid = person_by_id()
scope_cut = []
for p in bd["persons"]:
    books = p.get("books")
    if not books:
        continue
    for code, r in (p.get("byBook") or {}).items():
        if r and r.get("mentionCount", 0) > 0 and code not in books:
            scope_cut.append((p["tradName"], books, code, r["mentionCount"]))
print(f"byBook 有账但 books 不含该书（本不应出现，annotate 按 books 过滤）: {len(scope_cut)}")
for row in scope_cut[:15]:
    print(" ", row)

# PERSON_BOOKS 造成的漏召：词典 books 限死，但语料表面有
# 用 dict books 与 bd byBook 对比
cut_people = []
for p in ppl["persons"]:
    books = p.get("books")
    if not books or set(books) >= set(BOOKS):
        continue
    hit = bd_ch = None
    for x in bd["persons"]:
        if x["id"] == p["id"]:
            hit = x
            break
    if not hit:
        continue
    for code, r in (hit.get("byBook") or {}).items():
        if r and r.get("mentionCount", 0) > 0 and code not in books:
            cut_people.append((p.get("tradName"), books, code, r["mentionCount"]))
print(f"仍被 books 限死、他书有命中者: {len(cut_people)}")
for row in sorted(cut_people, key=lambda x: -x[3])[:20]:
    print(" ", row)

# books scope distribution
bc = Counter(tuple(p.get("books") or ()) for p in ppl["persons"])
print("books 分布 top:", bc.most_common(8))

# ---------- 6. 薄别名高命中（缺称谓） ----------
sec("6. 命中高但称谓薄（≤2 别名）——缺字/尊称")
for b in BOOKS:
    rows = []
    for p in bd["persons"]:
        n = ((p.get("byBook") or {}).get(b) or {}).get("mentionCount", 0)
        if n >= 20 and len(p.get("aliases") or []) <= 2:
            rows.append((n, p["tradName"], p.get("aliases"), p.get("title")))
    rows.sort(reverse=True)
    print(f"{b}: {len(rows)} 人")
    for n, name, al, title in rows[:10]:
        print(f"   {name}×{n} aliases={al} title={title!r}")

# ---------- 7. 标杆人物对照 ----------
sec("7. 标杆人物：史记主角 vs 后汉/三国主角")
for name in [
    "劉邦",
    "項羽",
    "劉徹",
    "劉秀",
    "曹操",
    "劉備",
    "孫權",
    "諸葛亮",
    "袁紹",
    "董卓",
    "呂布",
    "周瑜",
    "關羽",
    "司馬懿",
    "馬超",
    "張飛",
    "龐德",
    "姜維",
    "荀彧",
    "郭嘉",
    "劉璋",
    "袁術",
]:
    p = next(
        (x for x in bd["persons"] if x.get("tradName") == name or x.get("name") == name),
        None,
    )
    if not p:
        print(f"{name}: NOT IN INDEX")
        continue
    bb = {
        k: v.get("mentionCount")
        for k, v in (p.get("byBook") or {}).items()
        if v and v.get("mentionCount")
    }
    print(
        f"{name}: al={len(p.get('aliases') or [])} title={p.get('title')!r} "
        f"books={p.get('books')} byBook={bb} aliases={p.get('aliases')}"
    )

# ---------- 8. 裴注 ----------
sec("8. 裴注索引 vs 正文（toggle 不影响正文统计是设计；看覆盖）")
pp = pei.get("persons") or {}
body_sgz = {
    p["id"]: ((p.get("byBook") or {}).get("sgz") or {}).get("mentionCount", 0)
    for p in bd["persons"]
}
both = sum(1 for pid, n in body_sgz.items() if n > 0 and (pp.get(pid) or {}).get("n"))
only_body = sum(1 for pid, n in body_sgz.items() if n > 0 and not (pp.get(pid) or {}).get("n"))
only_pei = sum(1 for pid, v in pp.items() if (v.get("n") or 0) > 0 and not body_sgz.get(pid))
total_pei = sum(v.get("n") or 0 for v in pp.values())
print(
    f"裴注人物 {len(pp)} 总处 {total_pei}；"
    f"正文∩裴注 {both} 仅正文 {only_body} 仅裴注 {only_pei}"
)
top = sorted(pp.items(), key=lambda kv: -(kv[1].get("n") or 0))[:12]
print("裴注 top:", ", ".join(f"{v.get('name') or k}×{v.get('n')}" for k, v in top))
# 裴注有、词典 aliases 极薄
thin_pei = []
for pid, v in pp.items():
    if (v.get("n") or 0) >= 20:
        p = byid.get(pid)
        if p and len(p.get("aliases") or []) <= 2:
            thin_pei.append((v["n"], p["tradName"], p.get("aliases")))
thin_pei.sort(reverse=True)
print("裴注≥20 且别名≤2:", thin_pei[:12])

# ---------- 9. 泛称规模 ----------
sec("9. 泛称归属 tier 分布（guess 占比）")
for b in BOOKS:
    guess = tot = 0
    for p in bd["persons"]:
        ts = (p.get("tierStat") or {}).get(b) or (p.get("tierStat") or {})
        # tierStat structure may be global or per-book
    # use titles / tierStat on person
    g = t = 0
    for p in bd["persons"]:
        st = p.get("tierStat") or {}
        # if per-book dict of tier->n
        if b in st and isinstance(st[b], dict):
            for k, n in st[b].items():
                t += n or 0
                if k == "guess":
                    g += n or 0
        else:
            for k, n in st.items():
                if isinstance(n, int):
                    t += n or 0
                    if k == "guess":
                        g += n or 0
    if t:
        print(f"{b}: tier 总 {t} guess {g} ({g/t:.1%})")
    else:
        # fallback: titlesOf style
        pass

# try alternate: titles list
print("--- titles.tiers 汇总 ---")
for b in BOOKS:
    g = t = 0
    for p in bd["persons"]:
        for title in p.get("titles") or []:
            tiers = (title.get("tiers") or {}).get(b) or title.get("tiers") or {}
            if not isinstance(tiers, dict):
                continue
            for k, n in tiers.items():
                if not isinstance(n, int):
                    continue
                # only count if per-book key present or global
                if b in (title.get("tiers") or {}):
                    if k != b:
                        continue
                t += n
                if k == "guess":
                    g += n
    # simpler: if tiers is global not per book
    pass

# recount properly from sample person
sample = next(p for p in bd["persons"] if p.get("titles"))
print("sample titles keys:", sample.get("titles")[0].keys(), sample.get("tierStat"))

# ---------- 10. 缺人探针：语料高频未归 ---
sec("10. 语料表面高频但未进索引的疑似人名（启发式）")
# 从 corpus 取「X傳」「字X」「侯X」等
corpus_dir = ROOT / "data/corpus"
known = set()
for p in ppl["persons"]:
    for a in (p.get("aliases") or []) + [p.get("name"), p.get("tradName")]:
        if a and len(a) >= 2:
            known.add(a)
            known.add(a[1:])  # 省姓? too noisy - skip
known = set()
for p in ppl["persons"]:
    for a in (p.get("aliases") or []) + [p.get("name"), p.get("tradName")]:
        if a and len(a) >= 2:
            known.add(a)

# pattern: 與X、/ X曰 / 姓+名 2-3 字 before 曰/云/等
NAME_CTX = re.compile(r"([一-鿿]{2,3})(?=曰|云|謂|等|者也|傳|侯)")
# better: 「封X侯」「拜X」「以X為」
CAND = re.compile(
    r"(?:封|拜|以|與|及|從|將|遣|使|擊|殺|獲|表|上|下)([一-鿿]{2,3})(?=侯|為|曰|將|軍|王|守|令|長|相|掾|吏|卒|兵|眾|等|也|。|，|、)"
)
for b in ("hhs", "sgz"):
    freq = Counter()
    files = sorted(corpus_dir.glob(f"{b}-*.json"))
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))
        paras = data.get("paragraphs") or data if isinstance(data, list) else data.get("paragraphs") or []
        if isinstance(data, dict) and "paragraphs" in data:
            paras = data["paragraphs"]
        elif isinstance(data, list):
            paras = data
        else:
            # structure?
            paras = data.get("paragraphs") or data.get("blocks") or []
        texts = []
        for para in paras:
            if isinstance(para, dict):
                t = para.get("text") or para.get("sentence") or ""
                if isinstance(t, list):
                    texts.extend(t)
                else:
                    texts.append(t)
            elif isinstance(para, str):
                texts.append(para)
        blob = "\n".join(texts)
        for m in CAND.finditer(blob):
            name = m.group(1)
            if name in known:
                continue
            if any(name in k for k in known if len(k) > len(name)):
                # covered as substring of longer alias? skip only if exact not needed
                pass
            if name not in known:
                freq[name] += 1
    top_miss = [(n, c) for n, c in freq.most_common(40) if c >= 8]
    print(f"{b}: 未登录名候选≥8 次: {len(top_miss)}")
    for n, c in top_miss[:20]:
        print(f"   {n} ×{c}")

print("\nDONE")
