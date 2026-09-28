# -*- coding: utf-8 -*-
"""人名索引「正名」问题的取证生成器。

用户反馈（2026-09-26）：索引名里①有的带身份名、②有不少是错的。
本脚本把**可疑条目**导出成带证据的批次，交 AI / 人工判定，不直接改数据。

可疑的四类（W = wrong name）：
  W1 切词噪声  ：尾字是虚词/动词/副词（時匈奴、單于既、趙分、王如故…）
  W2 官职+名   ：正名由「官职/封号 + 人名」粘成（相國何、尉竇固、京兆尹防…）
  W3 非人实体  ：地名、官署、星名、族名、神名冒充人名（荊門、倉部、文昌、盧水胡…）
  W4 身份外壳  ：正名是「国/谥 + 爵」或「封号 + 姓」而非本名（越王勾踐、城陽懷王劉淑、
                章德竇皇后…）——这类**不是错，只是长得像标题**，应剥壳后把整串留作别名

每类都给**可计算信号** + **语料上下文**，判定后由 _apply_names.py 落地。

用法
----
    python pipeline/_gen_name_batch.py                # 全量扫描，写 _name_batch.json
    python pipeline/_gen_name_batch.py --show 20      # 只打印前 20 条待判
    python pipeline/_gen_name_batch.py --unjudged     # 只看还没判的
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "data" / "index" / "book-data.json"
OUT = ROOT / "pipeline" / "_name_batch.json"

# ── W1：几乎不会做人名的「虚词/动词/副词」字 ────────────────────────────
# 说明：只收**几乎不可能**做名的字，宁漏勿错（韓遂的「遂」、呂不韋的「不韋」都不收）。
FUNC_TAIL = set("於之而其所以乃則者也矣焉哉且遂復追逐恐或率特當尚目令使至在自從與及若如"
                "斯茲曰云謂有無不弗毋未必將欲能可足得見聞既又再皆俱咸凡")
FUNC_TAIL |= set("分屬即亦然故耳為由當")
FUNC_TAIL = set(c for c in FUNC_TAIL if "\u4e00" <= c <= "\u9fff")

# ── W2：官职/身份词（出现在正名**非末尾**且后面还跟人名用字 = 粘连）────────
OFFICE = ("太守", "將軍", "将军", "相國", "相国", "丞相", "太尉", "太傅", "太師", "太师",
          "太保", "御史", "尚書", "尚书", "刺史", "校尉", "中郎", "京兆", "司馬", "司马",
          "司徒", "司空", "大夫", "單于", "单于", "太后", "皇后", "太子", "公子", "皇后")

# ── W3：非人实体的形/尾 ─────────────────────────────────────────────────
ENTITY_TAIL = ("營", "部", "郡", "縣", "县", "門", "门", "山", "水", "河", "關", "关",
               "塞", "亭", "寺", "宮", "宫", "殿", "署", "府", "州", "國", "国",
               "胡", "戎", "狄", "夷", "蠻", "蛮", "羌", "軍", "军", "師", "师")

# ── W4：身份外壳的「爵/位」字 ───────────────────────────────────────────
RANK = set("王公侯伯子男君帝后妃主")
POSTHUMOUS = set("文武昭宣桓莊莊襄惠穆懷厲幽平景悼頃哀思隱閔湣簡獻聲元孝康靖戴共釐靜懿惠元")

STATE = ("周", "秦", "漢", "汉", "楚", "齊", "齐", "燕", "趙", "赵", "魏", "韓", "韩",
         "魯", "鲁", "宋", "衛", "卫", "陳", "陈", "蔡", "鄭", "郑", "曹", "杞", "滕",
         "邾", "吳", "吴", "越", "晉", "晋", "虢", "虞", "中山", "清河", "城陽", "城阳",
         "膠東", "胶东", "廣陵", "广陵", "濟北", "济北", "常山", "琅邪", "河間", "河间",
         "臨江", "临江", "濟南", "济南")


def clip(text, lo, hi, pad=12):
    a = max(0, lo - pad)
    b = min(len(text), hi + pad)
    return ("…" if a > 0 else "") + text[a:b] + ("…" if b < len(text) else "")


def scan_corpus(names, sentences, chapters, per=4):
    """**一遍**语料取全：给每个可疑名最多 per 条上下文（按篇去重）+ 命中统计。

    注意：names 可能上千、sentences 近十万，**不能** 名字×句子双层循环。
    这里倒过来：先按名建索引可能漏 spans；实际用「句子里是否含任一可疑串」
    代价同样高，所以对**长句居多的语料**采用 substring 一次 probe：
    每个句子对每个名字做 in 判定之前，先用一个宽表（按首字分桶）过滤。
    """
    from collections import defaultdict
    bucket = defaultdict(list)
    for nm in names:
        if nm:
            bucket[nm[0]].append(nm)
    ctx = defaultdict(list)
    n_hit = Counter()
    chapters_seen = defaultdict(set)
    for s in sentences:
        t = s.get("text") or ""
        cand = []
        seen_chars = set()
        for ch in t:
            if ch in bucket and ch not in seen_chars:
                seen_chars.add(ch)
                cand.extend(bucket[ch])
        if not cand:
            continue
        cid = s.get("chapterId")
        for nm in cand:
            if nm not in t:
                continue
            n_hit[nm] += 1
            chapters_seen[nm].add(cid)
            if len(ctx[nm]) < per and cid not in {c["cid"] for c in ctx[nm]}:
                k = t.find(nm)
                ch = chapters.get(cid, {})
                ctx[nm].append({"cid": cid,
                                "title": ch.get("fullTitle", cid),
                                "book": ch.get("bookId", "?"),
                                "ctx": clip(t, k, k + len(nm))})
    return ctx, n_hit, {k: len(v) for k, v in chapters_seen.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--from", dest="frm", type=int, default=0, help="从排好序的第几条开始显示")
    ap.add_argument("--auto", action="store_true",
                    help="纳入**全部**自动补齐条目（不只闸门命中的）——"
                         "四类召回里真人与噪声混杂，闸门漏掉的得靠这一档人工过")
    ap.add_argument("--unjudged", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    d = json.loads(BOOK.read_text(encoding="utf-8"))
    chapters = {c["id"]: c for c in d["chapters"]}

    # ── 阶段一：只扫 persons，定出可疑名（不碰语料，毫秒级）────────────────
    cand = []
    for p in d["persons"]:
        tn = p.get("tradName") or ""
        if not tn:
            continue
        pid = p["id"]
        auto = pid.startswith("p_x") or "各书提及人物" in (p.get("summary") or "")
        kinds, why = [], []

        # W1：尾字虚词。**只对自动补齐条目开**——手工收的張耳/李斯/韓遂/酈食其
        #     都是真人，虚词照样能做名字，一刀切的闸门会误伤一大片。
        if auto and len(tn) >= 2 and tn[-1] in FUNC_TAIL:
            kinds.append("W1")
            why.append("尾字「{}」几乎不做人名（疑似切词噪声）".format(tn[-1]))
        # W2：官职粘连（官职词后还有字）
        if auto:
            for w in OFFICE:
                i = tn.find(w)
                if 0 <= i < len(tn) - len(w):
                    kinds.append("W2")
                    why.append("官职/身份词「{}」后还粘着「{}」".format(w, tn[i + len(w):]))
                    break
        # W3：非人实体尾
        if len(tn) >= 2 and tn[-1] in ENTITY_TAIL and auto:
            kinds.append("W3")
            why.append("以「{}」结尾，更像地名/官署/军队/族名".format(tn[-1]))
        # W4：身份外壳（国/谥 + 爵）
        if len(tn) >= 3 and tn[-1] in RANK:
            st = next((s for s in STATE if tn.startswith(s)), None)
            if st and any(c in POSTHUMOUS for c in tn[len(st):-1]):
                kinds.append("W4")
                why.append("「{}」+谥+「{}」是封号外壳，不是本名".format(st, tn[-1]))
        # --auto：闸门没命中也要列出，否则「安定三」这类既无虚词尾、
        # 也无官职词、也不以非人实体收尾的噪声会整批漏网。
        if not kinds and not (a.auto and auto):
            continue
        if not kinds:
            why.append("闸门未命中，按 --auto 全量列出待人工判")
        cand.append((p, tn, auto, kinds, why))

    # ── 阶段二：语料只走一遍，取上下文与统计 ───────────────────────────────
    ctx, n_hit, n_chap = scan_corpus({tn for _, tn, _, _, _ in cand},
                                     d["sentences"], chapters, per=4)

    items = []
    for p, tn, auto, kinds, why in cand:
        items.append({
            "id": "nm|{}".format(p["id"]),
            "kinds": kinds,
            "pid": p["id"],
            "name": p.get("name") or "",
            "tradName": tn,
            "dynasty": p.get("dynasty") or "",
            "title": p.get("title") or "",
            "auto": auto,
            "books": sorted((p.get("byBook") or {}).keys()),
            "mention": p.get("mentionCount", 0),
            "guess": p.get("guessCount", 0),
            "signals": {"命中处数": n_hit.get(tn, 0),
                        "分布篇数": n_chap.get(tn, 0),
                        "别名数": len(p.get("aliases") or [])},
            "why": "；".join(why),
            "contexts": [{k: v for k, v in c.items() if k != "cid"}
                         for c in ctx.get(tn, [])],
            "ai": None,
        })

    # 同名异物说明：如果一个 surface 被多人占，标出来（删/改前必看）
    owner = Counter(it["tradName"] for it in items)
    for it in items:
        if owner[it["tradName"]] > 1:
            it["signals"]["同名异物"] = True

    items.sort(key=lambda x: (-x["mention"], x["tradName"]))
    Path(a.out).write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1),
                           encoding="utf-8")

    cnt = Counter(k for it in items for k in it["kinds"])
    print("可疑人名 {} 条：".format(len(items)))
    for k in ("W1", "W2", "W3", "W4"):
        print("  {} {:22s} {:4d}".format(k, {"W1": "切词噪声", "W2": "官职粘连",
                                             "W3": "非人实体", "W4": "身份外壳"}[k], cnt.get(k, 0)))
    print("\n-> {}".format(a.out))

    if a.show:
        show = [it for it in items if not it["ai"]] if a.unjudged else items
        for it in show[a.frm:a.frm + a.show]:
            print("\n── {} {} 【{}】{}  book={} n={} ({})".format(
                it["pid"], it["tradName"], it["dynasty"], "/".join(it["kinds"]),
                "/".join(it["books"]), it["mention"], it["why"]))
            for c in it["contexts"][:3]:
                print("     《{}》{}".format(c["title"], c["ctx"]))


if __name__ == "__main__":
    main()
