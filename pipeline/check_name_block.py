# -*- coding: utf-8 -*-
"""人名阻断表的**逐条抽检**：确认挡掉的每一处都真的是人名，不是地名。

阻断表是"收紧召回"的操作——挡错了就是静默丢失真实地名，比误收更难发现
（误收看得见，误挡看不见）。所以每条都要把上下文摊出来看。

检查三件事：
  1. 每个阻断串在语料里出现几次、被挡几处、差在哪（守卫放行的要单独看）
  2. 逐条打印上下文，人工判读是不是人名
  3. 专门盯住"既是人名又可能是地名"的高危条目（鄭國/宋襄/周文/宋建…）
"""
import glob
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, CORPUS, norm, DICT      # noqa: E402

RISKY = ["鄭國", "宋襄", "周文", "周最", "周生", "宋建", "曹襄", "蔡義", "薛宣",
         "魏尚", "韓說", "陳武", "周霸", "周丘", "夏育", "宋留", "趙利"]


def main():
    doc = load_json(os.path.join(DICT, "places.json"))
    blocks = [norm(w) for w in doc["nameBlock"]]
    peerage = set(doc.get("nameBlockPeerage", ""))
    posthumous = set(doc.get("nameBlockPosthumous", ""))
    by_first = defaultdict(list)
    for w in blocks:
        by_first[w[0]].append(w)
    for k in by_first:
        by_first[k].sort(key=len, reverse=True)

    total = Counter()
    blocked = Counter()
    passed = defaultdict(list)
    ctx_of = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(CORPUS, "sj-*.json"))):
        src = load_json(path)
        for para in src["paragraphs"]:
            for s in para["sentences"]:
                t = norm(s["text"])
                for i in range(len(t) - 1):
                    for w in by_first.get(t[i], ()):
                        if not t.startswith(w, i):
                            continue
                        total[w] += 1
                        # 与 annotate_places.name_hit 同一判据：只有
                        # 「2 字 + 末字是谥号 + 后接爵位字」（地名+谥+爵）才放行
                        nxt = t[i + 2:i + 3] if len(w) == 2 else ""
                        if len(w) == 2 and w[1] in posthumous and nxt and nxt in peerage:
                            passed[w].append((s["id"], t[max(0, i - 8):i + len(w) + 8]))
                        else:
                            blocked[w] += 1
                        if len(ctx_of[w]) < 3:
                            ctx_of[w].append((s["id"], t[max(0, i - 10):i + len(w) + 10]))

    print("阻断串 %d 条" % len(blocks))
    print()
    print("=== 差异条目（出现次数 ≠ 被挡次数：说明守卫放行了几处）===")
    diff = [w for w in blocks if total[w] != blocked[w]]
    if not diff:
        print("  （无：每条都全额命中，守卫未放行任何一处）")
    for w in diff:
        print("  %-8s 出现%-3d 挡住%-3d 放行%d" % (w, total[w], blocked[w], total[w] - blocked[w]))
        for sid, c in passed[w][:4]:
            print("        放行 %s | %s" % (sid, c))
    print()
    print("=== 零命中条目（写进表但语料里没有，属死规则）===")
    zero = [w for w in blocks if total[w] == 0]
    print("  " + ("，".join(zero) if zero else "（无）"))
    print()
    print("=== 高危条目逐条上下文（既是人名、也可能是地名）===")
    for w in RISKY:
        wn = norm(w)
        if wn not in [norm(x) for x in blocks]:
            print("  %s（不在表中）" % w)
            continue
        print("  %s 共 %d 次，挡 %d 次" % (w, total[wn], blocked[wn]))
        for sid, c in ctx_of[wn][:3]:
            print("        %s | %s" % (sid, c))
    print()
    print("=== 全部条目一览（出现/挡住/上下文）===")
    for w in sorted(blocks, key=lambda x: -blocked[x]):
        if total[w] == 0:
            continue
        print("  %-8s %-3d/%-3d | %s" % (w, blocked[w], total[w], ctx_of[w][0][1] if ctx_of[w] else ""))


if __name__ == "__main__":
    main()
