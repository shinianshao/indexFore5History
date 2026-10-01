# -*- coding: utf-8 -*-
"""关系证据取证（P6-3）：给「没有证据句」的关系，从语料里找候选证据句。

为什么需要这一步
----------------
P6-2 抽的 62 条关系全部来自**人物简介**，没有 `evidence_uid`，
于是 confidence 被压到推断档（0.4）、图上只能画虚线。
关系属主观判断，**没出处不敢信**（docs/21 §12）,
所以回到语料里找句子给它补证据。

⚠️ 红线：**共现不是关系**（docs/25 P0）。本脚本**不产生新边**，
只给**已存在的边**找佐证句；而且候选必须自带可计算信号，交人工/AI 判。

判据（方向敏感，这是关键）
--------------------------
边 (a, rel, b) 的语义是「a 是 b 的 rel」。所以句里若写「a 之 反义词」，
例如边是 (秦惠王, 兄, 樗里子)、句作「秦惠王之弟也」，那是**一致**的；
若句里写「a 之 兄」，方向就反了（说的是 a 自己的兄长），**不算证据**。

    score 5  两人名字之间出现「之 + rel/inv」且方向一致
    score 3  两人名字之间出现 rel/inv 单字（如「勃子賢者…亞夫」）
    score 1  两人名字紧邻（间距 ≤ 12 字）
    score 0  仅共现（默认不算证据，只列出供人工看）

自动落盘只认 score≥5 且最佳候选唯一；其余进人工判定清单。

用法
----
    python pipeline/_gen_rel_evidence.py                 # 生成 JSON + 清单
    python pipeline/_gen_rel_evidence.py --stats         # 只看分布
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import relations as R                        # noqa: E402

DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
OUT_JSON = os.path.join(HERE, "_rel_evidence.json")
VERDICTS = os.path.join(HERE, "_rel_evidence_verdicts.json")
OUT_MD = os.path.join(ROOT, "docs", "27-关系证据待判.md")
AUTO_MIN = 5          # 自动落盘的分数门槛


def _names(conn, pid: str):
    """一人的所有写法：正名 + 别名（长名优先，避免用短名去套）。"""
    out = []
    r = conn.execute("SELECT trad_name, name FROM persons WHERE id=?",
                     (pid,)).fetchone()
    if r:
        out += [x for x in r if x]
    for row in conn.execute("SELECT alias FROM aliases WHERE person_id=?",
                            (pid,)):
        if row[0]:
            out.append(row[0])
    # 长名优先：先试「秦惠王」再试「惠王」，防止短名误套
    return sorted(set(out), key=len, reverse=True)


def _pair_sentences(conn, pid_a: str, pid_b: str, limit: int = 6):
    """同时提到两人的句子（active 句），并数出**句里还有几个别人**。

    `others` 是防误判的关键：「虢仲、虢叔，王季之子也，爲文王卿士」这句里
    既有王季（a）又有文王（b），句式也像，但「之子」指的是**虢仲虢叔**——
    只要句里还标了第三个人，这条证据就不能自动落（降权交人工）。
    """
    sql = ("SELECT s.uid, s.chapter_id, s.text, "
           "       (SELECT COUNT(DISTINCT m2.person_id) FROM mentions m2 "
           "        WHERE m2.sentence_uid = s.uid "
           "          AND m2.person_id NOT IN (?, ?)) AS others "
           "FROM mentions ma "
           "JOIN mentions mb ON ma.sentence_uid = mb.sentence_uid "
           "JOIN sentences s ON s.uid = ma.sentence_uid "
           "WHERE ma.person_id=? AND mb.person_id=? AND s.status='active' "
           "ORDER BY length(s.text) LIMIT ?")
    return [dict(zip(("uid", "chapter_id", "text", "others"), r))
            for r in conn.execute(sql, (pid_a, pid_b, pid_a, pid_b, limit))]


def score_sentence(text: str, names_a, names_b, rel: str):
    """给一句打分。返回 (score, signals)。

    判据是「a 名之后紧跟着『之 X』」，X 必须是 **b 对 a 的称呼**（`relations.CALL_INVERSE`，
    ⚠️ 不是 REL_INVERSE——那是反向边表，用来禁止双写）。
    称呼带**性别变体**（父 → 子 / 女），两个都算命中：只认「子」会漏掉
    「陳留董祀妻者，同郡蔡邕之女也」这种完美证据（docs/28 P1-2）。
    同句里若写的是「a 之父」而边是 (a,父,b)，那是 a 自己的父亲，**方向反了，不算**。
    句中谁先出现无所谓——古籍常写「b 者，a 之子也」。
    """
    targets = R.CALL_INVERSE.get(rel, ())
    pa = pb = -1
    sa = sb = ""
    for na in names_a:
        i = text.find(na)
        if i >= 0:
            pa, sa = i, na
            break
    for nb in names_b:
        j = text.find(nb)
        if j >= 0:
            pb, sb = j, nb
            break
    if pa < 0 or pb < 0 or pa == pb:
        return 0, []
    signals = []
    tail = text[pa + len(sa): pa + len(sa) + 8]
    for target in targets:
        i = text.find("之" + target)
        if i >= 0 and 0 <= i - (pa + len(sa)) <= 4:
            return 5, ["「{a} 之{t}」＝{b} 对 {a} 的称呼，与边一致".format(
                a=sa, t=target, b=sb)]
    for target in targets:
        if target in tail:
            return 3, ["{a} 名后紧接「{t}」（未带「之」）".format(a=sa, t=target)]
    gap = abs(pb - (pa + len(sa)))
    if rel in tail:
        signals.append("注意：附近有「{}」，方向可能是反的".format(rel))
    if gap <= 12:
        return 1, (signals or ["紧邻共现（间隔 {} 字）".format(gap)])
    return 0, (signals + ["仅共现（间隔 {} 字）".format(gap)])


def build() -> dict:
    conn = sqlite3.connect(DB_PATH)
    rows = R._read_rows()
    todo = [r for r in rows
            if (r.get("状态(status)") or "active") == "active"
            and not (r.get("证据uid") or "")]
    # ⚠️ **判过的不再进清单**（含判「否」的）。不这么做就会出这种事：
    # 判定完 27 条，重跑生成器清单还是 59 行——人第二次打开以为一条都没判，
    # 于是重判一遍。判定只认 verdicts 文件里有没有这个 rel_id（`_` 开头的是说明键）。
    done = set()
    if os.path.exists(VERDICTS):
        try:
            with open(VERDICTS, encoding="utf-8") as f:
                done = {k for k in json.load(f) if not k.startswith("_")}
        except ValueError:
            done = set()
    skipped = sum(1 for r in todo if r["rel_id"] in done)
    if skipped:
        print("已判定（不再列）：{} 条".format(skipped))
    todo = [r for r in todo if r["rel_id"] not in done]
    items = []
    for r in todo:
        a, b, rel = r["person_a"], r["person_b"], r["关系(rel)"]
        na, nb = _names(conn, a), _names(conn, b)
        cands = []
        for s in _pair_sentences(conn, a, b):
            sc, sig = score_sentence(s["text"], na, nb, rel)
            others = int(s["others"] or 0)
            if others:
                sig = sig + ["句里还有 {} 个人，「之X」可能指别人".format(others)]
                # 硬句式一旦有第三人就不敢自动落：典籍里「A 之子也」常指句首那人
                sc = min(sc, 2) if sc >= 5 else sc
            # mentions 覆盖不到的第三人照样会误判（「虢仲、虢叔，王季之子也，爲文王卿士」
            # 里虢仲虢叔根本没被标注）。长句里塞了别的事，是这类误判的**形状**，
            # 所以再用句长兜一道：能一句话说完的（≤24 字）才敢自动落。
            if sc >= 5 and len(s["text"]) > 24:
                sc = 2
                sig = sig + ["句子较长（{} 字），「之X」可能另有所指".format(
                    len(s["text"]))]
            cands.append({"uid": s["uid"], "chapter": s["chapter_id"],
                          "text": s["text"], "score": sc, "signals": sig,
                          "others": others})
        cands.sort(key=lambda x: -x["score"])
        items.append({
            "rel_id": r["rel_id"], "person_a": a, "person_b": b, "rel": rel,
            "surface_a": r.get("原文用字a") or "", "surface_b": r.get("原文用字b") or "",
            "name_a": (na[0] if na else a), "name_b": (nb[0] if nb else b),
            "cands": cands[:5],
        })
    conn.close()
    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "语料共现（方向敏感）", "items": items}


def stats(data: dict) -> None:
    n = {"5": 0, "3": 0, "1": 0, "0": 0, "none": 0}
    for it in data["items"]:
        if not it["cands"]:
            n["none"] += 1
            continue
        n[str(it["cands"][0]["score"])] += 1
    print("关系总数（无证据）：{}".format(len(data["items"])))
    print("  硬句式(5)：{}   单字(3)：{}   紧邻(1)：{}   仅共现(0)：{}   无共现：{}"
          .format(n["5"], n["3"], n["1"], n["0"], n["none"]))
    print("  可自动落盘（5 分且唯一）：{}".format(
        sum(1 for it in data["items"]
            if it["cands"] and it["cands"][0]["score"] >= AUTO_MIN
            and (len(it["cands"]) == 1 or it["cands"][1]["score"] < AUTO_MIN))))


def write_md(data: dict) -> None:
    auto, manual = [], []
    for it in data["items"]:
        top = it["cands"][0] if it["cands"] else None
        if top and top["score"] >= AUTO_MIN and (
                len(it["cands"]) == 1 or it["cands"][1]["score"] < AUTO_MIN):
            auto.append((it, top))
        elif it["cands"]:
            manual.append(it)
        else:
            manual.append(it)
    lines = [
        "# 27 · 关系证据 · 待判清单",
        "",
        "> 由 `python pipeline/_gen_rel_evidence.py` 生成，数据变了可重跑。",
        "> 只给**已存在的边**找佐证句；**共现不等于关系**（docs/25 P0）。",
        "> 判定写进 `pipeline/_rel_evidence_verdicts.json`：",
        "",
        "```json",
        '{ "0431c8ee4e39": {"uid": "sj-001-0002-0a1", "accept": true},'
        ' "xxxx": {"accept": false} }',
        "```",
        "",
        "## 一、可自动落盘（硬句式，方向一致）　{} 条".format(len(auto)),
        "",
        "| # | 关系 | 证据句 | 信号 |",
        "|---|---|---|---|",
    ]
    for i, (it, c) in enumerate(auto, 1):
        lines.append("| {} | {a} —{rel}→ {b} | {t} | {s} |".format(
            i, a=it["name_a"], rel=it["rel"], b=it["name_b"],
            t=c["text"][:44].replace("|", "｜"),
            s="；".join(c["signals"])[:40]))
    lines += ["", "## 二、待人工判定　{} 条".format(len(manual)), "",
              "| # | 关系 | 候选句 | 信号 | 你的判定 |", "|---|---|---|---|---|"]
    for i, it in enumerate(manual, 1):
        if not it["cands"]:
            lines.append("| {} | {a} —{rel}→ {b} | （语料里找不到两人共现） | — |  |".format(
                i, a=it["name_a"], rel=it["rel"], b=it["name_b"]))
            continue
        c = it["cands"][0]
        lines.append("| {} | {a} —{rel}→ {b} | {t} | {s} |  |".format(
            i, a=it["name_a"], rel=it["rel"], b=it["name_b"],
            t=c["text"][:44].replace("|", "｜"),
            s=("；".join(c["signals"]) or "—")[:40]))
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("清单：{}".format(OUT_MD))


def main() -> int:
    ap = argparse.ArgumentParser(description="关系证据取证（P6-3）")
    ap.add_argument("--stats", action="store_true", help="只看分布，不写文件")
    args = ap.parse_args()
    data = build()
    stats(data)
    if not args.stats:
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print("取证 JSON：{}".format(OUT_JSON))
        write_md(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
