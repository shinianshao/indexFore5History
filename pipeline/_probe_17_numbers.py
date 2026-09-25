# -*- coding: utf-8 -*-
"""取 docs/17 回填后要写进 verify.py 的**实测数字**，避免断言编错。

用法：python pipeline/_probe_17_numbers.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = json.loads((ROOT / "data" / "index" / "book-data.json").read_text(encoding="utf-8"))
N = {p["id"]: (p.get("tradName") or p.get("name")) for p in D["persons"]}


def js_marks(alias):
    for s in D["sentences"]:
        if not s["chapterId"].startswith("js-"):
            continue
        for m in s.get("marks") or []:
            if m.get("alias") == alias:
                yield s, m


print("── 「魏武帝」长名 @js ──")
c = Counter(m["pid"] for _, m in js_marks("魏武帝"))
print("   ", [(N.get(k, k), v) for k, v in c.most_common()])

for alias in ("武帝", "元帝", "高祖", "惠帝", "明帝"):
    c = Counter(m["pid"] for _, m in js_marks(alias))
    print("── 裸「{}」@js ──".format(alias))
    print("   ", [(N.get(k, k), v) for k, v in c.most_common()])


def with_ctx(alias, key):
    out = Counter()
    for s, m in js_marks(alias):
        t = s.get("text") or ""
        i, j = m.get("s", 0), m.get("e", 0)
        if key in t[max(0, i - 12): j + 12]:
            out[m["pid"]] += 1
    return out


print("── js 里含该串但**无标注**的句（真漏标）──")
for alias in ("武帝", "元帝", "高祖", "惠帝", "明帝"):
    miss = []
    for s in D["sentences"]:
        if not s["chapterId"].startswith("js-"):
            continue
        t = s.get("text") or ""
        if alias not in t:
            continue
        # 被更长别名接管（孝武帝/漢武帝/魏武帝…）不算漏标
        if any(alias in (m.get("alias") or "")
               and (m.get("alias") or "") != alias for m in s.get("marks") or []):
            continue
        if any(m.get("alias") == alias for m in s.get("marks") or []):
            continue
        miss.append(s["chapterId"])
    print("    {}: {} 处".format(alias, len(miss)))

for alias, key in (("武帝", "泰始"), ("武帝", "咸寧"), ("武帝", "太康"),
                   ("元帝", "京房"), ("元帝", "渡江"), ("元帝", "南遷"),
                   ("高祖", "婁敬"), ("高祖", "景命")):
    print("── 「{}」+「{}」@js ──".format(alias, key))
    print("   ", [(N.get(k, k), v) for k, v in with_ctx(alias, key).most_common()])
