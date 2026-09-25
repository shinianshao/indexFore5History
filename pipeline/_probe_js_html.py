# -*- coding: utf-8 -*-
"""晋书 HTML 侦察：注释标记、篇名、导航形态。只读。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def probe(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    print(f"\n===== {path.name}  {len(html)} bytes =====")
    for pat in ("〈", "〉", "【", "】", "{{", "}}", "史臣", "臣松之", "校勘",
                "wikitable", "<small", "ws-noexport", "注", "音"):
        print(f"  {pat!r:16} {html.count(pat)}")

    # 去标签后头部
    text = TAG.sub("", html)
    text = WS.sub("", text)
    print("  HEAD:", text[:180])

    # 导航 ◄ ►
    nav = re.search(r"◄(.{1,60}?)►", text)
    print("  NAV:", nav.group(0) if nav else None)

    # 疑似篇名行：卷一…第…
    for m in re.finditer(r"(晉書)?卷[一二三四五六七八九十百零〇\d]+[^〈]{0,40}", text[:2000]):
        print("  VOLHEAD:", m.group(0)[:80])
        break

    # 尖括号注样例
    for m in re.finditer(r"〈[^〉]{0,60}〉", html):
        print("  ANGLE sample:", m.group(0)[:80])
        break
    # small
    for m in re.finditer(r"<small[^>]{0,80}>.{0,40}", html, re.I):
        print("  SMALL sample:", m.group(0)[:100])
        break


for name in ("js-001.html", "js-002.html", "js-003.html"):
    p = RAW / name
    if p.exists():
        probe(p)
    else:
        print("missing", name)
