# -*- coding: utf-8 -*-
"""P2-a 表字补录：用「与本人同句共现率」当置信度门槛。

为什么不能直接批量补：抽查 14 条里有 9 条是误抽——
  跨词边界：博士**弟子治**《尚書》、王**季思**慮、遭**世康**平、露**次道**南
  被更长串包含：申**叔時**（楚臣申叔時）
  同字他人：**叔平**在语料里是敞/參的字，不是淳于智
  亲属称谓：伯祖、元孫
所以补录必须过一道质量闸：统计该表字在语料里**每处出现**是否与本人
（姓 / 全名）同句共现，比例够高才补。

用法：
    python pipeline/_gen_zi_fill.py                       # 默认阈值 0.7 / 至少 2 处
    python pipeline/_gen_zi_fill.py --ratio 0.8 --min 3
    python pipeline/_gen_zi_fill.py --out pipeline/_zi_ok.json
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sentences():
    for f in sorted(glob.glob(str(ROOT / "data" / "corpus" / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for para in d.get("paragraphs") or []:
            for s in para.get("sentences") or []:
                t = s.get("text") or ""
                if t:
                    yield t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(ROOT / "pipeline" / "_zi_fill_plan.json"))
    ap.add_argument("--ratio", type=float, default=0.7)
    ap.add_argument("--min", type=int, default=2, help="同句共现处数下限")
    ap.add_argument("--out", default=str(ROOT / "pipeline" / "_zi_ok.json"))
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--md", default=None, help="另产出人工判定批次 markdown")
    ap.add_argument("--md-n", type=int, default=40)
    a = ap.parse_args()

    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    BD = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
    BY_ID = {p["id"]: p for p in BD["persons"]}

    # 先把所有句子读进来（语料不大，一次读完比反复扫文件快）
    sents = list(sentences())

    ok, low = [], []
    for row in plan:
        pid, zi = row["pid"], row["zi"]
        p = BY_ID.get(pid)
        if not p:
            continue
        name = p.get("tradName") or p.get("name") or ""
        if not name:
            continue
        surname, full = name[0], name
        hit = co = 0
        for t in sents:
            if zi not in t:
                continue
            hit += 1
            # 同句共现：出现全名，或「姓+表字」（嵇叔夜、陸士光）
            if full in t or (surname + zi) in t:
                co += 1
        if hit == 0:
            continue
        r = co / hit
        rec = {"pid": pid, "name": name, "zi": zi, "hit": hit, "co": co,
               "ratio": round(r, 2)}
        (ok if (co >= a.min and r >= a.ratio) else low).append(rec)

    ok.sort(key=lambda r: (-r["co"], -r["ratio"]))
    low.sort(key=lambda r: -r["hit"])
    print("表字补录：可补 {} 条（同句 ≥{} 且共现率 ≥{}），待判 {} 条".format(
        len(ok), a.min, a.ratio, len(low)))
    print("{:<8} {:<8} {:<5} {:<5} {}".format("人名", "表字", "出现", "同句", "共现率"))
    for r in ok[: a.top]:
        print("{:<8} {:<8} {:<5} {:<5} {}".format(
            r["name"], r["zi"], r["hit"], r["co"], r["ratio"]))
    print("\n待判（共现率低，多半是跨词边界或同字他人）Top10：")
    for r in low[:10]:
        print("    {:<8} {:<8} 出现{} 同句{} 率{}".format(
            r["name"], r["zi"], r["hit"], r["co"], r["ratio"]))

    Path(a.out).write_text(
        json.dumps({"ok": ok, "low": low}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("\n-> {}".format(a.out))

    if a.md:
        out = [
            "# 「表字长尾」待判批次",
            "",
            "> 生成器：`python pipeline/_gen_zi_fill.py --md <路径>`　"
            "生成日期：见文件末尾。",
            "> 判据：**共现率**＝该表字在语料里的出现中，与本人（全名或「姓+表字」）"
            "同句共现的比例。",
            "> 它只是**可计算的置信度代理**，不是结论——率低≠一定错（如「叔夜」"
            "单独出现时多半仍指嵇康），率高也不保证对。人工看原文再定。",
            "",
            "## 怎么判",
            "",
            "| 你写的 | 含义 |",
            "|---|---|",
            "| `收` | 确认是此人表字，补进别名 |",
            "| `不收` | 确认不是（跨词边界 / 同字他人 / 亲属称谓 / 更长串的片段） |",
            "| 留空 | 没判，执行方跳过，不猜 |",
            "",
            "**四类典型误抽**（抽查 14 条里 9 条中招）：",
            "1. 跨词边界：博士**弟子治**《尚書》、王**季思**慮、遭**世康**平、露**次道**南",
            "2. 被更长串包含：申**叔時**（楚臣申叔時）",
            "3. 同字他人：**叔平**在语料里是敞、參的字，不是淳于智",
            "4. 亲属称谓：**伯祖**、**元孫**",
            "",
            "## 待判条目",
            "",
            "| # | 人名 | 表字 | 出现 | 同句 | 共现率 | 原文上下文 | 你的判定 |",
            "|---:|---|---|---:|---:|---:|---|---|",
        ]
        for i, r in enumerate(low[: a.md_n], 1):
            ctx = ""
            for t in sents:
                if r["zi"] in t:
                    j = t.find(r["zi"])
                    ctx = t[max(0, j - 14): j + len(r["zi"]) + 14]
                    break
            out.append("| {} | {} | {} | {} | {} | {} | {} |  |".format(
                i, r["name"], r["zi"], r["hit"], r["co"], r["ratio"], ctx))
        out += ["", "---", "",
                "（共 {} 条待判，此处列出命中最高的 {} 条）".format(len(low), a.md_n)]
        Path(a.md).write_text("\n".join(out), encoding="utf-8")
        print("-> {}".format(a.md))


if __name__ == "__main__":
    main()
