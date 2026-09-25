# -*- coding: utf-8 -*-
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]  # 已移入 _scratch/
p = ROOT / "web" / "corpus-data.js"
t = p.read_text(encoding="utf-8")
print("size", len(t))
print("notes count", t.count('"notes"'))
i = t.find('"notes"')
print("first notes at", i)
if i >= 0:
    print(t[i : i + 120])
m = re.search(r'"hhs-20":\{', t)
if m:
    print(t[m.start() : m.start() + 400])
