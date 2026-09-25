# -*- coding: utf-8 -*-
"""裸短名「上下文框架」探针：找出其实该收长名、却被短名截走的情形。只读。

为什么需要它
------------
泛称（高祖/武帝/元帝…）的裸短名命中里，有一批其实**不是泛称**，
而是某个稳定长名被短名抢先截走了。典型：

    昔【高祖】宣皇帝以雄才碩量   → 「高祖宣皇帝」= 司馬懿，短名却归了别人
    況【高祖】宣皇帝肇開王業     → 同上

这类不能靠「换 default」解决（换了会打乱真正的高祖=刘邦追述），
正确做法是**补长名 core**（长名优先自然覆盖）。本脚本就是找这种长名。

用法
----
    python pipeline/_probe_generic_frame.py --alias 高祖 --book js
        # 看「高祖」在晋书里，命中串前后邻字的分布

    python pipeline/_probe_generic_frame.py --alias 元帝 --post 3 --tier guess
        # 只看硬兜 default（最可疑）的那些，后邻 3 字

    python pipeline/_probe_generic_frame.py --alias 武帝 --book js --min 5
        # 只显示出现 ≥5 次的框架

判读
----
- 某个 post 框架（如 `宣皇帝`）**集中指向同一人**且当前归属混乱 → 收长名 core。
- 某个 pre 框架（如 `漢`+`高祖`）已被长名接管则不会出现在这里（本脚本只统计 marks）。
- `tier=guess` 占比高的框架优先处理。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "data" / "index" / "book-data.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", required=True)
    ap.add_argument("--book", default=None)
    ap.add_argument("--pre", type=int, default=0, help="取前邻几字（0=不取）")
    ap.add_argument("--post", type=int, default=3, help="取后邻几字")
    ap.add_argument("--tier", default=None, help="只看某个 tier，如 guess")
    ap.add_argument("--pid", default=None, help="只看归给某个 pid 的命中，如 p_caohuan")
    ap.add_argument("--min", type=int, default=3, help="框架最少出现次数")
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()

    d = json.loads(BD.read_text(encoding="utf-8"))
    chapters = {c["id"]: c for c in d["chapters"]}
    persons = {p["id"]: p for p in d["persons"]}

    # 泛称的规范形（只按规范形统计，避免简繁重复计数）
    core = a.alias
    for g in d.get("genericAliases", []):
        if a.alias in (g.get("forms") or []) or a.alias == g["alias"]:
            core = g["alias"]
            break

    frames: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "pid": Counter(), "tier": Counter(), "sample": None, "ch": Counter()})

    for s in d["sentences"]:
        ch = chapters.get(s.get("chapterId"))
        if not ch:
            continue
        if a.book and ch["bookId"] != a.book:
            continue
        text = s.get("text") or ""
        for m in s.get("marks") or []:
            if m.get("alias") != core:
                continue
            if a.tier and m.get("tier") != a.tier:
                continue
            if a.pid and m.get("pid") != a.pid:
                continue
            i, j = m.get("s", 0), m.get("e", 0)
            pre = text[max(0, i - a.pre):i] if a.pre else ""
            post = text[j:j + a.post]
            key = (pre + "｜" if a.pre else "") + post
            fr = frames[key]
            fr["n"] += 1
            fr["pid"][m.get("pid")] += 1
            fr["tier"][m.get("tier") or "?"] += 1
            fr["ch"][ch["fullTitle"]] += 1
            if fr["sample"] is None:
                fr["sample"] = text[max(0, i - 10):i] + "【" + text[i:j] + "】" + text[j:j + 14]

    tot = sum(f["n"] for f in frames.values())
    print("「{}」{}：命中 {} 处（框架 {} 种，显示 ≥{} 次）\n".format(
        core, ("@" + a.book) if a.book else "全库", tot, len(frames), a.min))

    rows = sorted(frames.items(), key=lambda kv: -kv[1]["n"])
    shown = 0
    for key, fr in rows:
        if fr["n"] < a.min or shown >= a.top:
            continue
        shown += 1
        pids = "、".join(
            "{}×{}".format(persons.get(p, {}).get("name", p) or p, n)
            for p, n in fr["pid"].most_common(3))
        tiers = "/".join("{}{}".format(k, v) for k, v in fr["tier"].most_common())
        print("[{}×{}] post/pre={}  {}".format(key, fr["n"], key, ""))
        print("    归属: {}   tier: {}".format(pids, tiers))
        print("    例: {}".format((fr["sample"] or "").replace("|", "｜")))
    print("\nDONE")


if __name__ == "__main__":
    main()
