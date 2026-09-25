# 只读：从空篇主卷的正文首段抽「传主候选人」+ 泛称 guess 构成
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
people = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
co = people["chapterOwners"]
persons = {p["id"]: p for p in people["persons"]}
name_to_id = {}
for p in persons.values():
    name_to_id[p["name"]] = p["id"]
    name_to_id[p["tradName"]] = p["id"]

# 已知不在词典的姓氏（常见）——仅用于展示
empty_sg = sorted(k for k, v in co.items() if not v and k.startswith("sgz-"))
empty_h85 = sorted(
    k for k, v in co.items()
    if not v and k.startswith("hhs-") and int(k.split("-")[1]) <= 90
)

# 标题里的姓氏链（魏蜀吴合传常见「X Y Z 傳」）
# 从 volumes 取标题
for code, keys in (("sgz", empty_sg), ("hhs", empty_h85)):
    vols = json.loads((ROOT / f"data/dict/volumes/{code}.json").read_text(encoding="utf-8"))
    print(f"\n=== {code} 标题提取候选（需人工映射到 pid）===")
    for key in keys:
        slug = key.split("-", 1)[1]
        title = vols.get(slug, "?")
        # strip 魏書· / 蜀書· / 吳書· / 列傳 / 傳
        t = re.sub(r"^[^·]*·", "", title)
        t = t.replace("列傳", "").replace("傳", "")
        print(f"  {key:10} {title:20} | 碎片: {t}")

# 首段人名探针：找「X，……」式 传主开头 + 姓+名双字
print("\n=== 空篇主卷首段（前 200 字）===")
for key in empty_sg + empty_h85:
    path = ROOT / f"data/corpus/{key}.json"
    if not path.exists():
        print(key, "NO CORPUS")
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    # collect first non-nav paragraphs
    texts = []
    for p in data.get("paragraphs", []):
        if p.get("note") and not p.get("text"):
            continue
        t = (p.get("text") or "").strip()
        if t and not re.match(r"^(魏書|蜀書|吳書|後漢書)", t):
            texts.append(t)
        if sum(len(x) for x in texts) >= 300:
            break
    head = "".join(texts)[:240].replace("\n", "")
    print(f"\n{key}: {head}")

# 泛称 guess 构成
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
chapters = {c["id"]: c for c in bd["chapters"]}
# need alias from marks - check mark structure
sample_mark = None
for s in bd["sentences"][:50]:
    for m in s.get("marks", []):
        if m.get("tier") == "guess":
            sample_mark = m
            break
    if sample_mark:
        break
print("\n sample mark keys:", sorted(sample_mark.keys()) if sample_mark else None)
print(" sample mark:", sample_mark)

# Guess composition by surface alias if present, else by matched text
alias_counter = defaultdict(Counter)
for s in bd["sentences"]:
    cid = s["chapterId"]
    bk = chapters.get(cid, {}).get("bookId", "")
    for m in s.get("marks", []):
        if m.get("tier") != "guess":
            continue
        surface = m.get("alias") or m.get("text") or m.get("matched") or ""
        if not surface and "start" in m and "end" in m:
            # sentence-relative?
            pass
        alias_counter[bk][surface or "?"] += 1

for bk in ("sgz", "hhs", "hs", "sj"):
    print(f"\n=== {bk} guess TOP alias ===")
    for a, n in alias_counter[bk].most_common(30):
        print(f"  {n:4} {a}")
