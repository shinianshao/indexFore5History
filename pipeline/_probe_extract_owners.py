# 只读：从空篇主卷首段提取「X字Y」传主 + 现有 pid 命中
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
people = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
persons = {p["id"]: p for p in people["persons"]}
by_trad = {}
for p in persons.values():
    by_trad.setdefault(p["tradName"], []).append(p["id"])
    by_trad.setdefault(p["name"], []).append(p["id"])
    for a in p["aliases"]:
        by_trad.setdefault(a, []).append(p["id"])

co = people["chapterOwners"]
empty = sorted(k for k, v in co.items() if not v and k.startswith("sgz-"))

# 「X字Y，」at paragraph starts; also mid 合传「又…X字Y」
BI_ZI = re.compile(r"(?:^|。)([一-鿿]{1,3})字([一-鿿]{1,4})[，,]")
# skip common non-name
SKIP = {"其", "曰", "者", "所謂", "時", "初", "後", "為", "以", "於"}

print("=== sgz empty volume 传主提取 ===")
for key in empty:
    path = ROOT / f"data/corpus/{key}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    title = data.get("title", "")
    # gather full text (text only, notes stripped already in sentences)
    full_parts = []
    for para in data.get("paragraphs", []):
        t = para.get("text") or ""
        # strip angle notes
        t = re.sub(r"〈[^〉]*〉", "", t)
        full_parts.append(t)
    full = "\n".join(full_parts)
    hits = []
    for m in BI_ZI.finditer(full):
        name = m.group(1)
        if name in SKIP:
            continue
        if name not in hits:
            hits.append(name)
    # also first sentence pattern
    first = ""
    for para in data.get("paragraphs", []):
        t = re.sub(r"〈[^〉]*〉", "", para.get("text") or "").strip()
        if t:
            first = t[:80]
            break
    print(f"\n{key} {title}")
    print(f"  首: {first}")
    print(f"  字X候选: {hits[:20]}")
    for h in hits[:15]:
        pids = by_trad.get(h, [])
        print(f"    {h} -> {pids if pids else '—缺—'}")
