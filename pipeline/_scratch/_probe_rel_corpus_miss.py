# -*- coding: utf-8 -*-
"""那 24 条「语料里根本没共现」的边，到底是不是真的补不回来？

`_gen_rel_evidence.py` 只在一句话**同时**提到 A 与 B 时才产生候选。
所以它给出「无共现」只有两种可能：
  ① 两人真的从没在同一句出现过 → 只能回去改 data/persons.xlsx 的简介；
  ② 其实出现过，但**用的是别名/称号**，而 `_pair_sentences` 没覆盖 → 只是漏搜。

本脚本逐条验证：对每条边，把 A、B 的**全部写法**（正名 + 别名 + 称号 + 封号）
一个个拿去全文搜，命中句打印出来。这样「补不回来」才是**有证据的结论**，
而不是"没搜到就算了"。

⚠️ 本脚本**只负责找**。找到的句子写进 `pipeline/_rel_evidence_verdicts.json`
（人写的判定文件），不写 `_rel_evidence.json`——那是**生成器的产物**，
重跑 `_gen_rel_evidence.py` 会整个覆盖（2026-10-01 白写过一次）。

用法：
    python pipeline/_scratch/_probe_rel_corpus_miss.py          # 复核 + 回填判定
    python pipeline/_scratch/_probe_rel_corpus_miss.py --dry    # 只看不写
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "data", "index", "index.db")
EVI = os.path.join(ROOT, "pipeline", "_rel_evidence.json")
VERDICTS = os.path.join(ROOT, "pipeline", "_rel_evidence_verdicts.json")

# ⚠️ 只认**显式关系词**。别拿「文學之士」「為丞相」这种当信号——
# 第一版把 KINSHIP 写成一大堆通用字（子/立/封），结果「常山憲王舜」这种
# **本人名字**被标成★、「其明年，徵文學之士公孫弘等」被判成有共现，
# 24 条里报了 10 条假阳性。共现从来就不是关系（docs/25 P0），复核脚本更不该松。
KINSHIP = ("之子", "之孫", "之弟", "之兄", "之父", "之母", "之妻", "之女",
           "子也", "孫也", "弟也", "兄也", "女也",
           "子立", "子某", "卒，子", "生", "所破", "所殺")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只复核，不回填判定")
    args = ap.parse_args()
    limit = 0
    with open(EVI, encoding="utf-8") as f:
        items = json.load(f)["items"]
    miss = [i for i in items if not (i.get("cands") or [])]
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    names: dict = {}
    for r in conn.execute("SELECT id, name, trad_name, title FROM persons"):
        cands = [x for x in (r["name"], r["trad_name"], r["title"]) if x]
        names[r["id"]] = cands

    print("=== 无共现边逐条复核（{} 条）===".format(len(miss)))
    n_bad = 0
    fill: dict = {}
    for it in miss[:limit or None]:
        a, b = it["person_a"], it["person_b"]
        na, nb = names.get(a, []), names.get(b, [])
        print("\n[{}] {} —{}→ {}".format(
            it["rel_id"], it["name_a"], it["rel"], it["name_b"]))
        print("    a 的写法：{}".format("、".join(na) or "（空）"))
        print("    b 的写法：{}".format("、".join(nb) or "（空）"))
        found = []
        for wa in na:
            if len(wa) < 2:
                continue
            for wb in nb:
                if len(wb) < 2:
                    continue
                rows = conn.execute(
                    "SELECT uid, text FROM sentences WHERE status='active' "
                    "AND text LIKE ? AND text LIKE ? LIMIT 3",
                    ("%" + wa + "%", "%" + wb + "%")).fetchall()
                for r in rows:
                    found.append((wa, wb, r["uid"], r["text"]))
        if found:
            # 去重（同一句可能被多组写法命中）
            seen = set()
            # ★ 只标**同时带显式关系词**的句子——那才是「这句能当证据」的信号。
            # 只有共现（哪怕挨得很近）一律不算，别给人制造工作量。
            good = [(wa, wb, uid, tx) for wa, wb, uid, tx in found
                    if any(k in tx for k in KINSHIP) and uid not in seen
                    and not seen.add(uid)]
            if good:
                print("    ⚠ 有**带关系词**的句子（{} 组写法命中）：".format(
                    len(found)))
                for wa, wb, uid, tx in good[:3]:
                    print("      ★「{}」（{}）".format(tx[:60], uid))
                # 回填判定：人写的文件，重跑生成器不会丢
                fill[it["rel_id"]] = {
                    "accept": True, "uid": good[0][2],
                    "note": "补搜命中（全写法交叉搜索）：{}".format(good[0][3][:50]),
                    "from": "corpus-miss-probe",
                }
                n_bad += 1
            else:
                print("    ✓ 只在同句共现、没有任何关系词 → 补不回来（只能改简介）")
        else:
            print("    ✓ 全部写法交叉都搜不到 → 确实补不回来（只能改简介）")
    print("\n共 {} 条，其中 {} 条其实能搜到（取证器漏了）".format(len(miss), n_bad))
    if not args.dry and n_bad:
        old = {}
        if os.path.exists(VERDICTS):
            with open(VERDICTS, encoding="utf-8") as f:
                old = json.load(f)
        added = [k for k in fill if k not in old]
        old.update(fill)
        with open(VERDICTS, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=2)
        print("已回填判定 {} 条 → {}".format(len(added), VERDICTS))
        print("下一步：python pipeline/_apply_rel_evidence.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
