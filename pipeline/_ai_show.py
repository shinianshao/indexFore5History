# -*- coding: utf-8 -*-
"""AI 概率判定闭环 · 第 2 段：把批次打印成人（和 AI）能批量读的紧凑文本。

一条一屏太浪费，一条一行又看不到证据——这里折中：
**信号一行 + 上下文 3 行**，一条 4 行，一屏能看 10 条。

用法
----
    python pipeline/_ai_show.py --kind zi --n 40
    python pipeline/_ai_show.py --kind zi --from 41 --n 40
    python pipeline/_ai_show.py --kind gen --n 20
    python pipeline/_ai_show.py --kind zi --n 40 --form pipeline/_ai_judged/01.txt
        # 另产出一份待填判定表（每行一条，填完交给 _ai_judge.py 合并）

字段含义见 `docs/17-待办-人工判断清单.md` §二「怎么读一行证据」。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "pipeline" / "_ai_batch.json"


def sig_line(it):
    s = it["signals"]
    out = []
    for k, v in s.items():
        if isinstance(v, dict):
            v = " ".join("{}{}".format(a, b) for a, b in list(v.items())[:6])
        elif isinstance(v, list):
            v = ",".join(v[:4]) if v else "-"
        out.append("{}={}".format(k, v))
    return "  ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default=str(BATCH))
    ap.add_argument("--kind", default=None, choices=["zi", "gen"])
    ap.add_argument("--from", dest="start", type=int, default=1, help="从第几条开始（1 起）")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--ctx", type=int, default=3, help="每条打印几行上下文")
    ap.add_argument("--form", default=None, help="另产出待填判定表")
    a = ap.parse_args()

    b = json.loads(Path(a.batch).read_text(encoding="utf-8"))
    items = b["items"]
    if a.kind:
        items = [it for it in items if it["kind"] == a.kind]
    total = len(items)
    page = items[a.start - 1: a.start - 1 + a.n]
    print("共 {} 条，本页 {} 条（第 {}–{}）\n".format(
        total, len(page), a.start, a.start + len(page) - 1))

    form = []
    for i, it in enumerate(page, a.start):
        ai = it.get("ai")
        head = "[{}] {}".format(i, it["id"])
        if ai:
            head += "  已判：{} → {} (p={})".format(
                ai.get("action"), ai.get("target"), ai.get("prob"))
        print(head)
        print("    Q: {}".format(it["q"]))
        print("    信号: {}".format(sig_line(it)))
        if it["kind"] == "gen":
            print("    候选: {}".format("、".join(
                "{} {}（{}）".format(c["pid"], c["name"], c["dynasty"])
                for c in it["candidates"])))
        for c in it["contexts"][: a.ctx]:
            tail = "  ←{}".format(c["pid"]) if c.get("pid") else ""
            tail += " [共现]" if c.get("co") else ""
            print("      · {}　{}{}".format(c["title"], c["ctx"], tail))
        print()
        form.append("\t".join([it["id"], "", "", "", ""]))

    if a.form:
        Path(a.form).write_text(
            "# 判定表：id<TAB>action<TAB>prob<TAB>target<TAB>依据\n"
            "# action ∈ alias / reject / ctxrule / bookcand / default / unknown\n"
            "# 合并：python pipeline/_ai_judge.py --file {}\n".format(a.form)
            + "\n".join(form) + "\n", encoding="utf-8")
        print("-> 待填判定表 {}".format(a.form))

    print("kind 分布：{}".format(dict(Counter(it["kind"] for it in items))))


if __name__ == "__main__":
    main()
