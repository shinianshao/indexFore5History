# 只读探针：篇主空缺 + 分书泛称占比
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- people.json 篇主空缺 ---
d = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
co = d.get("chapterOwners", {})
empty = defaultdict(list)
nonempty = defaultdict(int)
for k, v in sorted(co.items()):
    book = k.split("-")[0]
    if v:
        nonempty[book] += 1
    else:
        empty[book].append(k)

print("=== 篇主表 ===")
print("total keys:", len(co))
for bk in sorted(set(list(empty) + list(nonempty))):
    print(f"  {bk}: 非空 {nonempty.get(bk,0)} / 空 {len(empty.get(bk,[]))}")
    if empty.get(bk):
        print("    empty:", ", ".join(empty[bk]))

# chaptersWithoutOwner 等 meta
for k in d:
    if "hapter" in k or "wner" in k.lower():
        if k == "chapterOwners":
            continue
        val = d[k]
        if isinstance(val, list) and len(val) < 80:
            print("meta", k, val)
        else:
            print("meta", k, type(val).__name__, (len(val) if hasattr(val, "__len__") else ""))

# --- book-data.json 泛称 ---
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
chapters = {c["id"]: c for c in bd.get("chapters", [])}
GEN = ("owner", "related", "sentence", "paragraph", "chapter", "era", "guess")
book_tier = defaultdict(lambda: [0, 0])
tier_by_book = defaultdict(lambda: defaultdict(int))
for s in bd.get("sentences", []):
    bk = chapters.get(s.get("chapterId"), {}).get("bookId", "")
    for m in s.get("marks", []):
        t = m.get("tier")
        if t in GEN:
            book_tier[bk][0] += 1
            tier_by_book[bk][t] += 1
            if t != "guess":
                book_tier[bk][1] += 1

names = {b["code"]: b["name"] for b in bd.get("meta", {}).get("books", [])}
print("\n=== 分书泛称有依据占比 ===")
for bk in sorted(book_tier):
    tot, conf = book_tier[bk]
    r = conf / max(tot, 1)
    tiers = dict(tier_by_book[bk])
    print(f"  {bk} {names.get(bk, bk)}: {r:.1%} ({conf}/{tot}) tiers={tiers}")
