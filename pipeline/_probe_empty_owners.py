# 只读：空篇主卷名 + 现有 PERSONS 是否已有候选 pid
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
people = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
persons = {p["id"]: p for p in people["persons"]}
co = people["chapterOwners"]

# titles
for code in ("sgz", "hhs", "hs", "sj"):
    vpath = ROOT / f"data/dict/volumes/{code}.json"
    vols = json.loads(vpath.read_text(encoding="utf-8"))
    empty = sorted(k for k, v in co.items() if not v and k.startswith(code + "-"))
    if not empty:
        continue
    print(f"\n=== {code} 空 {len(empty)} ===")
    for key in empty:
        slug = key.split("-", 1)[1]
        title = vols.get(slug, "?")
        # suggest persons whose name/trad appears in title tokens (2+ chars)
        # extract candidate name-ish chunks from title by removing 纪传等
        print(f"  {key:12} {title}")

# index persons by trad and name for lookup helpers
by_trad = {}
for p in persons:
    by_trad.setdefault(p["tradName"], []).append(p["id"])
    by_trad.setdefault(p["name"], []).append(p["id"])
    for a in p["aliases"]:
        by_trad.setdefault(a, []).append(p["id"])

# Known high-value missing-person queries for sgz empty volumes
queries = [
    "鍾繇", "華歆", "王朗", "管寧", "邴原", "田疇", "袁渙", "涼茂", "國淵",
    "王脩", "劉馥", "司馬朗", "梁習", "張既", "溫恢", "賈逵", "任峻", "蘇則",
    "杜畿", "鄭渾", "倉慈", "王衞", "傅嘏", "桓階", "陳群", "徐宣", "衛臻",
    "盧毓", "和洽", "常林", "楊俊", "杜襲", "趙儼", "裴潛", "韓暨", "崔林",
    "高柔", "孫禮", "王觀", "辛毗", "楊阜", "高堂隆", "滿寵", "田豫", "牽招",
    "郭淮", "徐邈", "胡質", "王基", "鄧艾", "鍾會", "華佗", "朱建平", "周宣",
    "管輅", "烏丸", "鮮卑", "霍峻", "王謀", "向舉", "張裔", "楊洪", "費詩",
    "杜微", "周羣", "許靖", "孟達", "來敏", "尹默", "李譙", "郤正", "張溫",
    "嚴畯", "程秉", "闞澤", "薛綜", "吳範", "劉惇", "趙達", "何姬", "甄皇后",
    "郭皇后", "曹皇后", "卞皇后", "董貴人", "李貴人", "潘淑", "王魯班",
    "東夷", "夫餘", "挹婁", "高句麗", "沃沮", "濊", "韓", "倭",
    "鄧方", "王連", "劉巴", "伊籍", "秦宓", "董允", "陳祗", "黃皓",
    "張裔", "楊洪", "費詩", "杜祺", "劉琰", "魏延", "楊儀",
]
print("\n=== 现有词典命中（繁名/别名包含查询）===")
hits = {}
for q in queries:
    found = []
    for p in persons.values():
        if q in p["tradName"] or q in p["name"] or any(q in a for a in p["aliases"]):
            found.append((p["id"], p["tradName"], p.get("books")))
    if found:
        hits[q] = found
        print(f"  {q}: {found}")
    else:
        print(f"  {q}: —")

print("\npersons total", len(persons))
