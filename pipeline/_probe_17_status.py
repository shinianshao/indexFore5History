# -*- coding: utf-8 -*-
"""按原文片段回查「裸帝号」当前归属，用来核对 docs/17 里人工判定是否已生效。

用法：python pipeline/_probe_17_status.py
片段表 SNIPPETS 直接抄 docs/17-条目-*.md 的原文列（去掉【】）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = json.loads((ROOT / "data" / "index" / "book-data.json").read_text(encoding="utf-8"))
NAMES = {p["id"]: p.get("tradName") or p.get("name") for p in D["persons"]}

# (别名, 原文片段, 人工判定)
SNIPPETS = [
    ("高祖", "無廢我【高祖】之景命", "司马懿"),
    ("高祖", "昔【高祖】宣皇帝以雄才碩量", "司马懿"),
    ("高祖", "廟稱【高祖】", "司马懿(对)"),
    ("高祖", "思【高祖】納婁敬之策", "刘邦"),
    ("高祖", "【高祖】六年，分蜀置廣漢", ""),
    ("高祖", "況【高祖】宣皇帝肇開王業", "司马懿"),
    ("武帝", "魏【武帝】為司空", "曹操"),
    ("武帝", "【武帝】時，涼州覆敗", "司马炎"),
    ("武帝", "【武帝】第二十五子也", "司马炎"),
    ("武帝", "魏【武帝】曰", "曹操"),
    ("武帝", "封魏【武帝】玄孫曹勵", "曹操"),
    ("武帝", "今日復見【武帝】之世矣", "司马炎"),
    ("元帝", "【元帝】之渡江也", "司马睿(对)"),
    ("元帝", "【元帝】之少子也", "司马睿"),
    ("元帝", "及【元帝】南遷", "司马睿"),
    ("元帝", "而生【元帝】，亦有符云", "司马睿(对)"),
    ("元帝", "爲【元帝】所愛", "司马睿"),
    ("元帝", "【元帝】時，郎中京房", "汉元帝(对)"),
    ("惠帝", "知【惠帝】弗克負荷", "司马衷(对)"),
    ("惠帝", "而繼【惠帝】擾亂之後", "司马衷"),
    ("惠帝", "【惠帝】可廢而不廢", "司马衷(对)"),
    ("惠帝", "又況我【惠帝】以放蕩之德", "司马衷"),
    ("惠帝", "謝安稱爲【惠帝】之流", "司马衷(对)"),
    ("惠帝", "【惠帝】世為護軍將軍", "司马衷"),
    ("明帝", "【明帝】長子也", ""),
    ("明帝", "【明帝】即位，改封舞陽侯", ""),
    ("明帝", "閏月戊子，【明帝】崩", ""),
    ("明帝", "【明帝】時，王導侍坐", ""),
    ("明帝", "葬【明帝】於武平陵", ""),
    ("明帝", "【明帝】以面覆牀", ""),
]

for alias, raw, judge in SNIPPETS:
    frag = raw.replace("【", "").replace("】", "")
    hits = []
    for s in D["sentences"]:
        t = s.get("text") or ""
        if frag not in t:
            continue
        for m in s.get("marks") or []:
            if m.get("alias") == alias:
                seg = t[max(0, m.get("s", 0) - 14): m.get("e", 0) + 14]
                hits.append((s["chapterId"], NAMES.get(m["pid"], m["pid"]), m.get("tier")))
        if not hits:
            hits.append((s["chapterId"], "—未标注—", ""))
    mark = "✓" if any(n.startswith(judge.replace("(对)", "")) for _, n, _ in hits) else "✗"
    print("{:<4} {:<22} 判={:<12} 现={}".format(
        alias, frag[:20], judge or "（空）",
        " / ".join("{}.{}·{}".format(c, n, t) for c, n, t in hits[:2]) or "—"))
    print("      {}".format(mark))
