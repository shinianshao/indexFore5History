# -*- coding: utf-8 -*-
"""验收脚本：模拟网页端的呈现逻辑，把检索结果打印出来。

支持两种用法：
    python verify.py                 回放若干人物（含称号消歧明细）
    python verify.py 刘邦 梁王        指定检索词
    python verify.py --check         跑回归断言（消歧是否真的生效）

--check 里的每条断言都对应一个已知的、曾经错过的坑，改动管线后先跑它。
"""
import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = json.load(open(os.path.join(ROOT, "data", "index", "book-data.json"), encoding="utf-8"))

persons = DATA["persons"]
chapters = {c["id"]: c for c in DATA["chapters"]}
by_id = {p["id"]: p for p in persons}
by_name = {p["name"]: p for p in persons}
generic_of = {}
for g in DATA.get("genericAliases", []):
    for form in g["forms"]:
        generic_of[form] = g["alias"]

main_by_person = {}
for c in DATA["chapters"]:
    for pid in c["mainPersons"]:
        main_by_person.setdefault(pid, []).append(c["id"])

mentions = {}
marks_index = []          # (alias, pid, tier, chapterId)
for s in DATA["sentences"]:
    for pid in s["persons"]:
        mentions.setdefault(pid, {}).setdefault(s["chapterId"], []).append(s)
    for m in s["marks"]:
        marks_index.append((m["alias"], m["pid"], m["tier"], s["chapterId"]))

TIER_LABEL = {"core": "专属别名", "scoped": "限定单字", "owner": "篇目主人公",
              "related": "篇内相关人物", "sentence": "同句共现", "paragraph": "同段共现",
              "chapter": "本篇共现", "era": "本篇时代", "guess": "未能判定"}


def resolve(query):
    """与网页端一致：先精确匹配名字/别名，命中多人则列出候选。"""
    hits = [p for p in persons
            if p["name"] == query or p["tradName"] == query or query in p["aliases"]]
    return hits


def show(query):
    hits = resolve(query)
    if not hits:
        print("未收录「{}」".format(query))
        return
    if len(hits) > 1:
        print("=" * 72)
        print("检索「{}」→ 该称谓对应 {} 人：".format(query, len(hits)))
        for p in hits:
            print("    · {}（{} · {}）{} 篇专述 / 共 {} 处".format(
                p["name"], p["dynasty"], p["title"],
                len(main_by_person.get(p["id"], [])), p["mentionCount"]))
        print()
        return

    p = hits[0]
    pid = p["id"]
    prim = main_by_person.get(pid, [])
    mm = mentions.get(pid, {})
    other = [(cid, lst) for cid, lst in mm.items() if cid not in prim]
    other.sort(key=lambda kv: -len(kv[1]))
    total = sum(len(l) for _, l in other)
    print("=" * 72)
    print("检索「{}」 → {} · {} · 共 {} 处".format(
        query, p["dynasty"], p["title"], p["mentionCount"]))
    print("  原文中写作：", "　".join("{}×{}".format(a["alias"], a["n"]) for a in p["topAliases"]))

    # 称号归属：哪些称号算到了他头上、依据是什么
    title_stats = {}
    for alias, mpid, tier, cid in marks_index:
        if mpid != pid or alias not in generic_of:
            continue
        row = title_stats.setdefault(alias, {})
        row[tier] = row.get(tier, 0) + 1
    if title_stats:
        print("\n  【称号归属】称号不固定属于谁，按篇目上下文判定：")
        for alias, tiers in sorted(title_stats.items(),
                                   key=lambda kv: -sum(kv[1].values())):
            detail = "、".join("{} {}".format(TIER_LABEL.get(t, t), n)
                              for t, n in sorted(tiers.items(), key=lambda kv: -kv[1]))
            rivals = [r["name"] for r in persons
                      if r["id"] != pid and alias in r["aliases"]]
            print("    · {}　共 {} 处　[{}]".format(
                alias, sum(tiers.values()), detail))
            if rivals:
                print("        同称号他人：{}".format("、".join(rivals[:6])))

    print("\n  【整篇讲述】{} 篇（只给篇名）".format(len(prim)))
    for cid in prim:
        c = chapters[cid]
        print("    · {}　{} 字 / {} 句".format(c["fullTitle"], c["charCount"], c["sentenceCount"]))

    print("\n  【其他篇目提及】{} 篇 / {} 处（篇名 + 原句）".format(len(other), total))
    for cid, lst in other[:5]:
        c = chapters[cid]
        print("    · {}　{} 处".format(c["fullTitle"], len(lst)))
        print("        {}".format(lst[0]["text"][:58]))
    if len(other) > 5:
        print("    …（另有 {} 篇）".format(len(other) - 5))
    print()


def check():
    """回归断言：每条都对应一个曾经真实出错的场景。"""
    cases = []

    def count(alias, pid, cid=None, tier=None):
        return sum(1 for a, p, t, c in marks_index
                   if a == alias and p == pid
                   and (cid is None or c == cid) and (tier is None or t == tier))

    def pid_at(frag, alias):
        """某句里某个别名的归属人（逐句核对用）。"""
        for s in DATA["sentences"]:
            if frag in s["text"]:
                for m in s["marks"]:
                    if m["alias"] == alias:
                        return by_id[m["pid"]]["name"]
        return None

    def reduplication():
        """单字别名不该落在叠字里（湯湯洪水 / 旦旦）。"""
        bad = []
        for s in DATA["sentences"]:
            t = s["text"]
            for m in s["marks"]:
                if len(m["alias"]) != 1:
                    continue
                i, j = m["s"], m["e"]
                ch = t[i:j]
                if len(ch) != 1:
                    continue
                if (i > 0 and t[i - 1] == ch) or (j < len(t) and t[j] == ch):
                    bad.append("{}({})".format(ch, s["chapterId"]))
        return bad

    # ① 「梁王」在《梁孝王世家》指刘武，不应算到彭越头上
    cases.append(("梁王@梁孝王世家 → 刘武",
                  count("梁王", "p_liuwu", "sj-058") > 0,
                  "刘武 {} 处".format(count("梁王", "p_liuwu", "sj-058"))))
    cases.append(("梁王@梁孝王世家 → 不是彭越",
                  count("梁王", "p_pengyue", "sj-058") == 0,
                  "彭越 {} 处".format(count("梁王", "p_pengyue", "sj-058"))))
    # ② 「梁王」在《魏豹彭越列传》仍是彭越
    cases.append(("梁王@魏豹彭越列传 → 彭越",
                  count("梁王", "p_pengyue", "sj-090") > 0,
                  "彭越 {} 处".format(count("梁王", "p_pengyue", "sj-090"))))
    # ③ 「湯」在《酷吏列传》是张汤，不是商汤；在《殷本纪》才是商汤
    cases.append(("湯@酷吏列传 → 张汤",
                  count("湯", "p_zhangtang", "sj-122") > 0,
                  "张汤 {} 处".format(count("湯", "p_zhangtang", "sj-122"))))
    cases.append(("湯@殷本纪 → 商汤",
                  count("湯", "p_tang", "sj-003") > 0,
                  "商汤 {} 处".format(count("湯", "p_tang", "sj-003"))))
    # ④ 「厲王」裸称三家分立。它在《淮南衡山列传》是刘长——此前整片错配给周厉王，
    #    而且这个错配在体检里是**静默**的：只有周厉王声明过「厲王」这个别名，
    #    刘长的称号「淮南厉王」虽然含「厲王」，却不是同名竞争。修好之后，
    #    又靠「泛称判定回灌」让同段的「淮南王」也落回刘长。
    cases.append(("厲王@淮南衡山列传 → 刘长",
                  count("厲王", "p_liuchang", "sj-118") > 15,
                  "刘长 {} 处".format(count("厲王", "p_liuchang", "sj-118"))))
    cases.append(("厲王@淮南衡山列传 → 不再是周厉王",
                  count("厲王", "p_zhouli", "sj-118") == 0,
                  "周厉王 {} 处".format(count("厲王", "p_zhouli", "sj-118"))))
    cases.append(("厲王@周本纪 → 周厉王",
                  count("厲王", "p_zhouli", "sj-004") > 5,
                  "周厉王 {} 处".format(count("厲王", "p_zhouli", "sj-004"))))
    cases.append(("厲王@齐悼惠王世家 → 齐厉王刘次景",
                  count("厲王", "p_liucijing", "sj-052") > 0,
                  "刘次景 {} 处".format(count("厲王", "p_liucijing", "sj-052"))))
    # ⑤ 「淮南王」在《淮南衡山列传》以刘长/刘安为主，黥布只在「淮南王黥布」同句处
    an = count("淮南王", "p_liu_an", "sj-118")
    chang = count("淮南王", "p_liuchang", "sj-118")
    qing = count("淮南王", "p_qingbu", "sj-118")
    cases.append(("淮南王@淮南衡山列传 → 刘长/刘安为主",
                  chang + an >= 30 and qing <= 3,
                  "刘长{} 刘安{} 黥布{}".format(chang, an, qing)))
    # ⚠️ 比较对象写成 by_id[...]["name"] 而不是「刘长」字面量：
    #    pid_at 返回的是**显示名**，繁体化之后是「劉長」。写字面量会在下次
    #    改字形时静默失效（这条就因此失败过一次）。
    cases.append(("淮南王@「自以為最親」句 → 刘长（靠泛称回灌）",
                  pid_at("淮南王自以為最親", "淮南王") == by_id["p_liuchang"]["name"],
                  "判为 {}".format(pid_at("淮南王自以為最親", "淮南王"))))
    # ⑥ 「趙王」在《吕后本纪》是刘氏诸王，不是张耳
    cases.append(("趙王@吕后本纪 → 不归张耳",
                  count("趙王", "p_zhang_er", "sj-009") == 0,
                  "张耳 {} 处".format(count("趙王", "p_zhang_er", "sj-009"))))
    # ⑦ 单字别名防护：任何单字别名都不该被叠字吃掉。语料里「湯湯」其实并不存在，
    #    所以这条断言查的是**不变量**，而不是某个具体位置。
    bad = reduplication()
    cases.append(("单字别名不落在叠字中", not bad,
                  "违规 {} 处：{}".format(len(bad), "、".join(bad[:4]))))
    # ⑧ 异体字归一：劉德靠「河閒獻王」命中。
    #    ⚠️ 用 id 而不是 by_name["刘德"]——显示层繁体化之后 persons[].name 是
    #    「劉德」，按简体名查表会 KeyError（这里踩过一次，整份断言因此跑不完）。
    de = by_id["p_liude"]
    cases.append(("劉德（异体字 河閒獻王）有命中", de["mentionCount"] > 0,
                  "{} 处".format(de["mentionCount"])))
    # ⑨ 无零命中的收录人物（除个别确实不见于《史记》者）
    zero = [p["name"] for p in persons if p["mentionCount"] == 0]
    # —— 本轮：sgz 官名/帝号/启 错挂回归 ——
    wen = [
        x
        for m in DATA["sentences"]
        if m["chapterId"].startswith("sgz-")
        for x in m.get("marks", [])
        if x.get("alias") == "文帝"
    ]
    wen_pids = {x["pid"] for x in wen}
    cases.append(
        (
            "sgz 文帝只归曹丕（不是司马昭）",
            bool(wen) and wen_pids == {"p_caopi"},
            "n={} pids={}".format(len(wen), sorted(wen_pids)),
        )
    )
    qi_sgz = sum(
        1
        for m in DATA["sentences"]
        if m["chapterId"].startswith("sgz-")
        for x in m.get("marks", [])
        if x.get("pid") == "p_qi"
    )
    cases.append(("夏后启不在三国志命中", qi_sgz == 0, "sgz={}".format(qi_sgz)))
    cheng = [
        x
        for m in DATA["sentences"]
        if m["chapterId"].startswith("sgz-")
        for x in m.get("marks", [])
        if x.get("alias") in ("丞相", "太尉", "司徒", "太傅", "侍中")
    ]
    cases.append(
        (
            "sgz 无裸官名 core 命中（丞相/太尉/…）",
            len(cheng) == 0,
            "残留 {}".format(len(cheng)),
        )
    )
    # 裴注独立索引：不进主统计；有产物且非空
    pei_path = os.path.join(ROOT, "data", "index", "pei-data.json")
    if os.path.exists(pei_path):
        pei = json.load(open(pei_path, encoding="utf-8"))
        pei_meta = pei.get("meta") or {}
        pei_persons = pei.get("persons") or {}
        cases.append(
            (
                "裴注索引存在且有命中",
                pei_meta.get("mentionCount", 0) > 0 and len(pei_persons) > 0,
                "命中 {} / 人 {}".format(
                    pei_meta.get("mentionCount", 0), len(pei_persons)
                ),
            )
        )
        # 隔离：pei 脚本只写 pei-data，meta 不得携带正文 tierStat
        cases.append(
            (
                "裴注索引不写入正文 tierStat（产物隔离）",
                "tierStat" not in pei_meta,
                "ok" if "tierStat" not in pei_meta else "含 tierStat",
            )
        )
    else:
        cases.append(("裴注索引文件存在", False, pei_path))
    # —— 别名覆盖：字/专属尊称（#D）——
    def _n_alias_sgz(alias, pid):
        return sum(
            1
            for m in DATA["sentences"]
            if m["chapterId"].startswith("sgz-")
            for x in m.get("marks", [])
            if x.get("alias") == alias and x.get("pid") == pid
        )

    cases.append(
        (
            "sgz 孟德归曹操 ≥ 5",
            _n_alias_sgz("孟德", "p_caocao") >= 5,
            "n={}".format(_n_alias_sgz("孟德", "p_caocao")),
        )
    )
    caogong_caocao = _n_alias_sgz("曹公", "p_caocao")
    caogong_other = sum(
        1
        for m in DATA["sentences"]
        if m["chapterId"].startswith("sgz-")
        for x in m.get("marks", [])
        if x.get("alias") == "曹公" and x.get("pid") != "p_caocao"
    )
    cases.append(
        (
            "sgz 曹公归曹操（非他挂）",
            caogong_caocao >= 200 and caogong_other == 0,
            "曹操={} 其他={}".format(caogong_caocao, caogong_other),
        )
    )
    cases.append(("零命中人物 ≤ 3", len(zero) <= 3, "{}：{}".format(len(zero), zero)))
    # ⑩ 泛称大部分有上下文依据。
    #    多书之后必须**分书**看：只报合计的话，汉书的短板会把史记的真实水平
    #    一起拉下来（或反过来被史记掩盖），两边都看不清。
    #    汉书偏低的根因是表/志（諸侯王表、外戚恩澤侯表…）一篇之内同称异人——
    #    「厲王」在同一篇里既指齊厲王次昌、又指淮南厲王劉長，按篇判定天然无解，
    #    只能落到 guess（界面上是虚线，不冒充确定结论）。
    #    所以汉书单列一条更宽的基线；**《史记》的 75% 一个字不松**。
    GENERIC_TIERS = ("owner", "related", "sentence", "paragraph", "chapter", "era", "guess")
    book_name = {b["code"]: b["name"] for b in DATA["meta"].get("books", [])}
    book_tier = {}
    for s_ in DATA["sentences"]:
        bk = chapters[s_["chapterId"]].get("bookId", "")
        d_ = book_tier.setdefault(bk, [0, 0])
        for m in s_.get("marks", []):
            if m["tier"] in GENERIC_TIERS:
                d_[0] += 1
                if m["tier"] != "guess":
                    d_[1] += 1
    for bk in sorted(book_tier):
        tot, conf = book_tier[bk]
        r = conf / max(tot, 1)
        # 分书泛称基线（实测钉死，不照抄）：
        #   sj 82% / hs 64% / hhs 40% / sgz 7%（2026-09-23 篇主补满后）。
        #   hhs 正式目标 60% 仍差「跨时代追述」合理兜底（docs/09），先收到 35%；
        #   sgz 17/18 合传篇主已满（仅民族卷 30 留空），但泛称多为周秦旧号
        #   （宣王/文王/周公），owner 档提升有限，正式 60% 另待泛称专项，先收到 7%。
        if bk == "sj":
            floor = 0.75
        elif bk == "hs":
            floor = 0.70
        elif bk == "sgz":
            # R4：ERA 补三国 + 文帝收 core 后目标 35%（docs/12）
            floor = 0.35
        elif bk == "js":
            # docs/13 用户拍板：晋书泛称有依据 ≥60%
            floor = 0.60
        else:
            # 后汉书：实测约 50%
            floor = 0.45
        cases.append(("泛称有依据占比《{}》≥ {:.0%}".format(book_name.get(bk, bk), floor),
                      r >= floor, "{:.0%}（{} / {}）".format(r, conf, tot)))

    # ⑪ 异体字归一：「啓」必须与「啟」同归到夏后啟。
    #    此前 VARIANTS 没收「啓」，夏本紀 10 处、燕召公世家 4 处「啓」
    #    一处也匹配不上——旧计数只有 6，其中 3 处还是把
    #    「微子啟／啟弟／不憤不啟」误算进来的（真值 3）。
    #    语料实测：啓 17 次、啟 7 次，词典只登记了「啟」。
    qi = by_id["p_qi"]
    cases.append(("夏后啟（异体 啓 已归一）≥ 18 处",
                  qi["mentionCount"] >= 18,
                  "{} 处 / {} 篇".format(qi["mentionCount"], qi["mentionChapterCount"])))
    cases.append(("夏后啟覆盖《夏本紀》单字「啓」≥ 7 处",
                  count("啓", "p_qi", "sj-002") >= 7,
                  "夏本紀 {} 处".format(count("啓", "p_qi", "sj-002"))))

    # ⑫ 单字别名「啟」的上下文防护。归一之后「啟」成了活跃单字别名（6→18 处），
    #    三类误配源必须挡住：不憤不啟（前接「不」）、啓母／啟弟（后接「母」「弟」）。
    #    ⚠️ 紧邻「啟」的前一个字是**不**不是「憤」——守卫只看 ±1 字，写「憤」拦不住。
    #    同句的「微子啓／宋微子啟」另有正解：词典补了「宋微子啟」别名整串吃掉。
    def bad_qi_marks():
        bad = []
        for s in DATA["sentences"]:
            t = s["text"]
            for m in s["marks"]:
                if m["pid"] != "p_qi" or len(m["alias"]) != 1:
                    continue
                i, j = m["s"], m["e"]
                if j < len(t) and t[j] in "母弟":
                    bad.append("{}後接{}".format(m["alias"], t[j]))
                if i > 0 and t[i - 1] == "不":
                    bad.append("不{}".format(m["alias"]))
        return bad

    bad = bad_qi_marks()
    cases.append(("单字「啟」不落在 不啟／啓母／啟弟 里", not bad,
                  "违规 {} 处：{}".format(len(bad), "、".join(bad[:4]))))

    # ⑬ 异体归并：鼂錯／晁錯 同指一人，称谓表必须并成**一行**。
    #    归并键是 t2s(norm())，所以 VARIANTS 里「鼂→晁」和「鼌→晁」缺一不可：
    #    只收「鼂」会在词典自动生成的简体正名「鼌错」上漏掉，多出一行「本批未用」。
    cc = by_id["p_chaocuo"]["aliasList"]
    name_rows = [a for a in cc if a["kind"] == "name"]
    #    38 处是**史记单书**的数：汉书接入后鼂錯在《汉书》里也有命中，
    #    绝对数必然变大。要钉的是「并成一行」，不是这个数。
    cases.append(("鼂錯／晁錯 归并为一行（≥38 处，含两异体）",
                  len(name_rows) == 1 and name_rows[0]["n"] >= 38
                  and "鼂錯" in name_rows[0]["variants"],
                  "name 行 {} 个，n={}".format(len(name_rows),
                                              name_rows[0]["n"] if name_rows else 0)))

    # ⑭ 单字别名「桀」的三道守卫（用户报的一类错标）。
    #    正解只有夏桀；豪桀（豪杰义）、上官桀（前接 父/侯/軍/官/授/僕/封…）、
    #    桀黠奴/桀溺/桀宋（后接）都不是他。守卫表镜像 annotate.py 的
    #    SINGLE_CHAR_PRE / SINGLE_CHAR_POST / SINGLE_CHAR_STOP2——
    #    这里**故意重抄一份**：断言若从被测代码里 import 常量，改错表也会一起"通过"。
    def bad_jie_marks():
        pre = set("豪俊儁雄暴陰軍官父侯劉疑與斬予立是後授僕封敢")
        post = set("黠宋溺等子黨心追令因輒已奉頓常欲惡父驁妻")
        stop2 = {"、安", "為安", "爲安"}
        bad = []
        for s in DATA["sentences"]:
            t = s["text"]
            for m in s["marks"]:
                if m["pid"] != "p_jie" or len(m["alias"]) != 1:
                    continue
                i, j = m["s"], m["e"]
                if i > 0 and t[i - 1] in pre:
                    bad.append("{}桀".format(t[i - 1]))
                if j < len(t) and t[j] in post:
                    bad.append("桀{}".format(t[j]))
                if t[j:j + 2] in stop2:
                    bad.append("桀{}".format(t[j:j + 2]))
        return bad

    bad = bad_jie_marks()
    cases.append(("单字「桀」不落在 豪桀／上官桀／桀溺 里", not bad,
                  "违规 {} 处：{}".format(len(bad), "、".join(bad[:4]))))
    #    守卫收紧後仍须保住真夏桀：桀紂并称、雖桀、桀之時都是他。
    cases.append(("夏桀「桀」仍有 ≥ 90 处（守卫没一刀切）",
                  count("桀", "p_jie") >= 90,
                  "{} 处".format(count("桀", "p_jie"))))

    # ⑮ 多字别名跨词守卫：「老子」在 父老子弟／父老子孫／母老子弱 里是
    #    「父老／子弟」被切开，前接「父」「母」一律不认（见 ALIAS_STOP）。
    def bad_laozi_marks():
        bad = []
        for s in DATA["sentences"]:
            t = s["text"]
            for m in s["marks"]:
                if m["pid"] != "p_laozi" or m["alias"] != "老子":
                    continue
                i, j = m["s"], m["e"]
                if i > 0 and t[i - 1] in "父母":
                    bad.append("{}{}".format(t[i - 1], m["alias"]))
                if j < len(t) and t[j] in "父母":
                    bad.append("{}{}".format(m["alias"], t[j]))
        return bad

    bad = bad_laozi_marks()
    cases.append(("「老子」不落在 父老子弟／母老子弱 里", not bad,
                  "违规 {} 处：{}".format(len(bad), "、".join(bad[:4]))))

    # ⑰ R1 司马懿：字/宣王/晋宣帝 不得整段漏召（docs/11 P0-2）
    def alias_n(pid, alias):
        p = by_id.get(pid)
        if not p:
            return 0
        for a in p.get("aliasList") or []:
            if a.get("w") == alias:
                return a.get("n") or 0
        return 0

    _sima = by_id.get("p_simayi") or {}
    sima_sgz = ((_sima.get("byBook") or {}).get("sgz") or {}).get("mentionCount") or 0
    cases.append(("司馬懿 sgz 正文命中 ≥ 18（名+字+宣王）", sima_sgz >= 18,
                  "sgz={}；仲達={}；司馬宣王={}；晉宣帝={}；宣王泛称另计".format(
                      sima_sgz, alias_n("p_simayi", "仲達"),
                      alias_n("p_simayi", "司馬宣王"),
                      alias_n("p_simayi", "晉宣帝"))))
    # 裸「仲達」在《諸葛亮傳》多随裴注（《漢晉春秋》等）出现，句层正文常写
    # 全名「司馬懿/司馬宣王/司馬仲達」；断言看「字面合计」而非只看裸字。
    _pei_sima = 0
    try:
        _pd = json.load(open(os.path.join(ROOT, "data", "index", "pei-data.json"),
                             encoding="utf-8"))
        _pei_sima = ((_pd.get("persons") or {}).get("p_simayi") or {}).get("n") or 0
    except Exception:
        pass
    zhongda = (alias_n("p_simayi", "仲達") + alias_n("p_simayi", "司馬仲達") + _pei_sima)
    cases.append(("仲達/司馬仲達/裴注 合计归司馬懿 ≥ 8", zhongda >= 8,
                  "仲達={} 司馬仲達={} 裴注={}".format(
                      alias_n("p_simayi", "仲達"),
                      alias_n("p_simayi", "司馬仲達"), _pei_sima)))
    _han = by_id.get("p_hanxuandi") or {}
    han_sgz = ((_han.get("byBook") or {}).get("sgz") or {}).get("mentionCount") or 0
    cases.append(("宣帝 不再落汉宣帝的 sgz 账", han_sgz == 0,
                  "汉宣帝.sgz={}".format(han_sgz)))
    cases.append(("司馬炎 有命中 ≥ 2",
                  ((by_id.get("p_simayan") or {}).get("mentionCount") or 0) >= 2,
                  "{}".format((by_id.get("p_simayan") or {}).get("mentionCount"))))
    cases.append(("諸葛瞻 有命中 ≥ 2",
                  ((by_id.get("p_zhugezhan") or {}).get("mentionCount") or 0) >= 2,
                  "{}".format((by_id.get("p_zhugezhan") or {}).get("mentionCount"))))
    cases.append(("史汉 宣帝（劉詢）hs 命中不归零",
                  (((_han.get("byBook") or {}).get("hs") or {}).get("mentionCount") or 0) >= 150,
                  "hs={}".format(((_han.get("byBook") or {}).get("hs") or {}).get("mentionCount"))))

    # ⑱ R2 双字表字批量（董卓/曹叡/劉禪 等）。
    # 古籍正文表字本身极少（多在传首「字X」），阈值按语料表面钉：
    # 登录后凡出现即须归对人，不要求虚高次数。
    for pid, zi, need in (
        ("p_dongzhuo", "仲穎", 1),
        ("p_cao_rui", "元仲", 1),
        ("p_liushan", "公嗣", 1),
        ("p_chenfan", "仲舉", 1),
        ("p_zhangliao", "文遠", 1),
        ("p_yuanshao", "本初", 10),
    ):
        n = alias_n(pid, zi)
        cases.append(("表字「{}」归 {} ≥ {}".format(zi, by_id.get(pid, {}).get("name", pid), need),
                      n >= need, "{} 处".format(n)))

    # ⑲ R3 裸官职不得挂在单人 aliases（骑都尉/破虜將軍/參軍…）
    OFFICE_CORE = {
        "丞相", "太尉", "太傅", "太保", "司徒", "司空", "侍中", "尚書", "尚书",
        "大將軍", "大将军", "將軍", "将军", "太守", "刺史",
        "騎都尉", "骑都尉", "都尉", "校尉", "大司馬", "大司马", "相國", "相国",
        "破虜將軍", "破虏将军", "蕩寇將軍", "荡寇将军", "安漢將軍", "安汉将军",
        "鎮軍大將軍", "镇军大将军", "參軍", "参军", "軍師祭酒", "军师祭酒",
        "征西大將軍", "征西大将军", "上大將軍", "上大将军",
    }
    bad_office = []
    for p in persons:
        for a in p.get("aliases") or []:
            if a in OFFICE_CORE:
                bad_office.append("{}:{}".format(p.get("name"), a))
    cases.append(("裸官职 core 为 0（含騎都尉/破虜將軍）", not bad_office,
                  "残留 {}".format(bad_office[:8])))

    # ⑳ 曹操称谓补全（阿瞞/魏武）；汉贼/奸雄/曹瞞传 故意不进 core
    # 「小字阿瞞」在裴注《曹瞞傳》引文里；正文多写太祖/曹公。
    _pei_cao = 0
    _pei_am = 0
    try:
        _pd2 = json.load(open(os.path.join(ROOT, "data", "index", "pei-data.json"),
                              encoding="utf-8"))
        _pc = (_pd2.get("persons") or {}).get("p_caocao") or {}
        _pei_cao = _pc.get("n") or 0
        for _it in _pc.get("items") or []:
            if "阿瞞" in (_it.get("alias") or "") or "阿瞞" in (_it.get("text") or ""):
                _pei_am += 1
    except Exception:
        pass
    cases.append(("阿瞞 已入词典且裴注可追 ≥ 1",
                  alias_n("p_caocao", "阿瞞") >= 0 and (_pei_am >= 1 or alias_n("p_caocao", "阿瞞") >= 1),
                  "body={} pei_samples={}".format(alias_n("p_caocao", "阿瞞"), _pei_am)))
    cases.append(("魏武 归曹操 ≥ 2（史记魏武侯/魏武子不抢）",
                  alias_n("p_caocao", "魏武") >= 2,
                  "{}".format(alias_n("p_caocao", "魏武"))))
    bad_hanzei = 0
    for s in DATA["sentences"]:
        for m in s.get("marks") or []:
            if m.get("pid") == "p_caocao" and m.get("alias") in ("漢賊", "汉贼", "奸雄", "曹瞞", "曹瞒"):
                bad_hanzei += 1
    cases.append(("漢賊/奸雄/曹瞞 不进曹操 core", bad_hanzei == 0,
                  "误标 {}".format(bad_hanzei)))

    # ⑯ 泛称「韓王」按篇归位。四篇战国纪传里的「韓王」是历代韩君，
    #    汉初那位韩王信比他们晚两三个时代，时代序闸门判 none（不标）；
    #    《秦楚之際月表》「韓王成始」是韩成，「韓王鄭昌始」是郑昌。
    #    ⚠️ 闸门靠 era_index() 查表，曾因词典朝代写简体（西汉）、
    #    ERA_ORDER 写繁体（西漢）而静默失效——这四条就是那次的看门狗。
    for cid, label in (("sj-005", "秦本紀"), ("sj-006", "秦始皇本紀"),
                       ("sj-063", "老子韓非列傳"), ("sj-070", "張儀列傳")):
        n = count("韓王", "p_hanwangxin", cid)
        cases.append(("韓王@{} → 不再是韓王信".format(label), n == 0,
                      "韓王信 {} 处".format(n)))
    n16 = count("韓王", "p_hanwangxin", "sj-016")
    cases.append(("韓王@秦楚之際月表 → 不再是韓王信", n16 == 0,
                  "韓王信 {} 处".format(n16)))
    cases.append(("韓王成@秦楚之際月表「韓王成始」→ 韓王成",
                  pid_at("韓王成始", "韓王成") == by_id["p_hanwangcheng"]["name"],
                  "判为 {}".format(pid_at("韓王成始", "韓王成"))))
    zc = by_id["p_hanwangzhengchang"]
    cases.append(("韓王鄭昌（故吳令）有命中 ≥ 10 处",
                  zc["mentionCount"] >= 10,
                  "{} 处 / {} 篇".format(zc["mentionCount"],
                                       zc["mentionChapterCount"])))

    # ⑰ 补录人物：鄭袖（楚懷王寵姬）与桀溺（隐者）都要能检索到。
    for pid, label, floor in (("p_zhengxiu", "鄭袖", 10),
                              ("p_jiemi", "桀溺", 4)):
        p = by_id[pid]
        cases.append(("{} 有命中 ≥ {} 处".format(label, floor),
                      p["mentionCount"] >= floor,
                      "{} 处 / {} 篇".format(p["mentionCount"],
                                          p["mentionChapterCount"])))

    # ⑱ 「有若」守卫（用户报的错标：103 处里 ~95 是「有＋若（像）」假阳性）。
    #    修法：撤「有子」别名（真阳性仅 2 处，损失可接受）+「有若」加前后接守卫
    #    （前接 則/未、后接 此/自/公/富）。验收：假阳性清零 + 真阳性保底。
    def bad_youruo():
        bad = []
        for s_ in DATA["sentences"]:
            t = s_["text"]
            for m in s_["marks"]:
                if m["pid"] != "p_youruo":
                    continue
                i, j = m["s"], m["e"]
                if i > 0 and t[i - 1] in "則未":
                    bad.append("{}{}".format(t[i - 1], m["alias"]))
                if j < len(t) and t[j] in "此自公富":
                    bad.append("{}{}".format(m["alias"], t[j]))
        return bad

    bad = bad_youruo()
    cases.append(("「有若」不落 則有若/未有若/有若自然 里", not bad,
                  "违规 {} 处：{}".format(len(bad), "、".join(bad[:4]))))
    cases.append(("「有若」真阳性保底（仲尼弟子列传 ≥4 处）",
                  count("有若", "p_youruo", "sj-067") >= 4,
                  "sj-067 {} 处".format(count("有若", "p_youruo", "sj-067"))))

    # ===== R3 禹舜断言（docs/07 #B）=====
    yu_pre = set("霍侯傅臣賜保子王鄧張貢趙許郭絮矦")
    shun_pre = set("侯王傅臣保子許郭絮矦鄧")
    bad_yu, bad_shun = [], []
    n_yu = n_shun = 0
    for s in DATA["sentences"]:
        t = s["text"]
        for m in s.get("marks") or []:
            if m.get("alias") == "禹" and m.get("pid") == "p_yu":
                n_yu += 1
                i = m["s"]
                if i > 0 and t[i - 1] in yu_pre:
                    bad_yu.append(t[i - 1] + "禹")
            if m.get("alias") == "舜" and m.get("pid") == "p_shun":
                n_shun += 1
                i = m["s"]
                if i > 0 and t[i - 1] in shun_pre:
                    bad_shun.append(t[i - 1] + "舜")
    cases.append(("裸「禹」不落 霍侯王傅臣…禹", not bad_yu,
                  "违规 " + str(len(bad_yu)) + "：" + "、".join(bad_yu[:4])))
    cases.append(("裸「舜」不落 侯王子保…舜", not bad_shun,
                  "违规 " + str(len(bad_shun)) + "：" + "、".join(bad_shun[:4])))
    cases.append(("大禹裸禹保底 ≥ 150", n_yu >= 150, str(n_yu)))
    cases.append(("帝舜裸舜保底 ≥ 120", n_shun >= 120, str(n_shun)))
    if "p_huoyu" in by_id:
        cases.append(("霍禹有命中 ≥ 5",
                      by_id["p_huoyu"]["mentionCount"] >= 5,
                      str(by_id["p_huoyu"]["mentionCount"])))

    # ===== 曹芳/齐王（R-fix：泛称跨书抢命中）=====
    cf = by_id.get("p_caofang")
    if cf:
        sj_cf = (cf.get("byBook") or {}).get("sj", {}).get("mentionCount", 0)
        hs_cf = (cf.get("byBook") or {}).get("hs", {}).get("mentionCount", 0)
        cases.append(("曹芳不进史记/汉书 byBook",
                      sj_cf == 0 and hs_cf == 0,
                      "sj={} hs={}".format(sj_cf, hs_cf)))
    qi_to_cf = sum(
        1 for s in DATA["sentences"]
        for m in s.get("marks") or []
        if m.get("pid") == "p_caofang"
        and m.get("alias") in ("齐王", "齊王")
        and not s["chapterId"].startswith("sgz"))
    cases.append(("齐王不归史汉里的曹芳", qi_to_cf == 0,
                  "非sgz残留 " + str(qi_to_cf)))
    qi_to_cf_sgz = sum(
        1 for s in DATA["sentences"]
        for m in s.get("marks") or []
        if m.get("pid") == "p_caofang"
        and m.get("alias") in ("齐王", "齊王")
        and s["chapterId"].startswith("sgz"))
    # 三国志内可为魏废帝齐王语境；不强制>0
    print_debug = qi_to_cf_sgz  # noqa: F841
    qi_pids = Counter(m.get("pid") for s in DATA["sentences"]
                      for m in s.get("marks") or []
                      if m.get("alias") in ("齐王", "齊王"))
    cases.append(("齐王仍有历史归属命中", sum(qi_pids.values()) >= 50,
                  "top {}".format(qi_pids.most_common(3))))

    # ===== R4 地名断言（单字整篇 + 截断 + 目标地名）=====
    place_by_id = {p["id"]: p for p in DATA["places"]}
    chen_main = {r["cid"] for r in (place_by_id.get("pl_chen") or {}).get("mainChapters", [])}
    cases.append(("陳整篇含 陳杞世家", "sj-036" in chen_main,
                  "main n={}".format(len(chen_main))))
    false_main = sorted(chen_main & {
        "sj-089", "hs-032", "sj-048", "hs-031", "hhs-18", "hhs-62",
        "sgz-22", "sgz-19", "hhs-46", "hhs-51", "hs-040", "hhs-56",
        "hhs-36", "hs-070", "hs-066", "sgz-39"})
    cases.append(("陳整篇不再挂 張耳陳餘/陳涉等合传", not false_main,
                  "残留 " + ",".join(false_main)))
    chen_cut = 0
    for s in DATA["sentences"]:
        for m in s.get("pmarks") or []:
            if m.get("pid") == "pl_chen" and len(m.get("alias") or "") == 1:
                t = s["text"]
                j = m.get("e", 0)
                if j < len(t) and t[j] in "留":
                    chen_cut += 1
    cases.append(("陳留不再截成单字「陳」", chen_cut == 0, str(chen_cut)))
    for pid, label in (("pl_zhangzan", "章安"), ("pl_linhai_jun", "臨海")):
        p = place_by_id.get(pid)
        cases.append(("地名 {} 已收录且有命中".format(label),
                      p is not None and (p.get("mentionCount") or 0) > 0,
                      str(p["mentionCount"]) if p else "缺失"))
    linhai = place_by_id.get("pl_linhai_jun") or {}
    al = " ".join(linhai.get("aliases") or [])
    cases.append(("臨海含别名 台州/臺州", "台州" in al and "臺州" in al, al))

    # ===== 散见人物补齐 + 武帝/魏王丕 错归修复（2026 用户报）=====
    cases.append(("人物总数 ≥ 2000（散见补齐后）",
                  len(DATA["persons"]) >= 2000,
                  str(len(DATA["persons"]))))
    wudi_hhs_cc = sum(
        1 for s in DATA["sentences"]
        for m in s.get("marks") or []
        if m.get("alias") == "武帝" and m.get("pid") == "p_caocao"
        and s["chapterId"].startswith("hhs"))
    wudi_hhs_lc = sum(
        1 for s in DATA["sentences"]
        for m in s.get("marks") or []
        if m.get("alias") == "武帝" and m.get("pid") == "p_hanwudi"
        and s["chapterId"].startswith("hhs"))
    cases.append(("後漢書「武帝」→ 漢武帝（不再砸曹操）",
                  wudi_hhs_cc == 0 and wudi_hhs_lc >= 50,
                  "曹操={} 漢武帝={}".format(wudi_hhs_cc, wudi_hhs_lc)))
    weipi = [
        (s["chapterId"], m.get("pid"))
        for s in DATA["sentences"]
        for m in s.get("marks") or []
        if m.get("alias") == "魏王丕"
    ]
    cases.append(("「魏王丕」→ 曹丕（不再挂曹操）",
                  weipi and all(p == "p_caopi" for _, p in weipi),
                  str(weipi[:3])))
    caocao_wei = sum(
        1 for s in DATA["sentences"]
        for m in s.get("marks") or []
        if m.get("pid") == "p_caocao" and m.get("alias") == "魏王丕")
    cases.append(("曹操名下无「魏王丕」", caocao_wei == 0, str(caocao_wei)))

    # 注文不进句层统计（校勘/版本对照/按：/汲本殿本）
    note_leak = 0
    for s in DATA["sentences"]:
        t = s.get("text") or ""
        if "按：" in t or "汲本" in t or "殿本正文" in t or "校補引" in t or "校补引" in t:
            note_leak += 1
    cases.append(("校勘/版本注不进句层统计", note_leak == 0, "leak={}".format(note_leak)))

    # 「青徐二州」类州部连称不得进人物表
    bad_zhou = []
    for p in DATA["persons"]:
        n = p.get("tradName") or p.get("name") or ""
        if n in ("徐二州", "徐兗二", "益二州", "梁二州", "冀二州", "雍二州", "冀四州",
                 "江二州", "雍六州", "東海二", "江三州", "荊二州"):
            bad_zhou.append(n)
    cases.append(("州部连称不进人物表（徐二州等）", not bad_zhou, str(bad_zhou)))

    # ===== P1-a 裸短名错挂修复（2026-09，晋书帝号）=====
    def js_marks(alias, pid=None):
        return [m for s in DATA["sentences"]
                for m in (s.get("marks") or [])
                if s["chapterId"].startswith("js-")
                and m.get("alias") == alias
                and (pid is None or m.get("pid") == pid)]

    # 惠帝：晋书裸称一律晋惠帝，汉惠帝走「漢惠帝/孝惠帝」长名
    huidi_js_liuying = len(js_marks("惠帝", "p_hanhuidi"))
    huidi_js_zhong = len(js_marks("惠帝", "p_simazhong"))
    cases.append(("晉書裸「惠帝」不歸漢惠帝劉盈",
                  huidi_js_liuying == 0 and huidi_js_zhong >= 200,
                  "劉盈={} 司馬衷={}".format(huidi_js_liuying, huidi_js_zhong)))

    # 元帝：晋书裸称绝大多数晋元帝；曹奐只保留「景元/咸熙」年号那几处
    yuandi_js_huan = len(js_marks("元帝", "p_caohuan"))
    yuandi_js_rui = len(js_marks("元帝", "p_simarui"))
    cases.append(("晉書裸「元帝」曹奐只剩年號那幾處",
                  0 < yuandi_js_huan <= 10 and yuandi_js_rui >= 280,
                  "曹奐={} 司馬睿={}".format(yuandi_js_huan, yuandi_js_rui)))
    huan_bad = 0
    for s in DATA["sentences"]:
        for m in s.get("marks") or []:
            if m.get("alias") == "元帝" and m.get("pid") == "p_caohuan":
                tail = s["text"][m.get("e", 0): m.get("e", 0) + 6]
                if "景元" not in tail and "咸熙" not in tail:
                    huan_bad += 1
    cases.append(("曹奐的裸「元帝」必帶景元/咸熙年號", huan_bad == 0,
                  "无年号 {}".format(huan_bad)))

    # 元帝景元/太興：年号守卫双向生效（不再互串）
    def yuandi_post(key):
        pids = Counter()
        for s in DATA["sentences"]:
            for m in s.get("marks") or []:
                if m.get("alias") == "元帝" and \
                        key in s["text"][m.get("e", 0): m.get("e", 0) + 6]:
                    pids[m.get("pid")] += 1
        return pids
    jy = yuandi_post("景元")
    tx = yuandi_post("太興")
    cases.append(("「元帝景元」→ 曹奐、「元帝太興」→ 司馬睿",
                  jy.get("p_caohuan", 0) >= 4
                  and jy.get("p_simarui", 0) == 0
                  and tx.get("p_simarui", 0) >= 20
                  and tx.get("p_caohuan", 0) == 0,
                  "景元{} 太興{}".format(jy.most_common(2), tx.most_common(2))))

    # 高祖宣皇帝：司马懿庙号+谥号，长名优先不得被裸「高祖」截走
    gx = [(s["chapterId"], m.get("pid"))
          for s in DATA["sentences"]
          for m in (s.get("marks") or [])
          if m.get("alias") == "高祖宣皇帝"]
    cases.append(("「高祖宣皇帝」→ 司馬懿", len(gx) >= 4
                  and all(p == "p_simayi" for _, p in gx),
                  "{} 处 {}".format(len(gx), gx[:2])))

    # 高祖作「高祖父」亲属称谓时不标（宁缺勿滥）
    gaozu_kin = 0
    for s in DATA["sentences"]:
        t = s.get("text") or ""
        if "曾祖" not in t:
            continue
        for m in s.get("marks") or []:
            if m.get("alias") == "高祖":
                i, j = m.get("s", 0), m.get("e", 0)
                if "曾祖" in t[max(0, i - 12): j + 12]:
                    gaozu_kin += 1
    cases.append(("「高祖…曾祖」親屬稱謂不標", gaozu_kin == 0, str(gaozu_kin)))

    print("=" * 72)
    print("回归断言")
    bad = 0
    for name, ok, detail in cases:
        print("  [{}] {}{}".format("通过" if ok else "失败", name,
                                   "　（{}）".format(detail) if detail else ""))
        if not ok:
            bad += 1
    print("\n  {}/{} 通过".format(len(cases) - bad, len(cases)))
    return bad


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if "--check" in args:
        sys.exit(1 if check() else 0)
    queries = args or ["刘邦", "韩信", "梁王", "彭越", "刘武", "张汤", "汤",
                       "刘德", "虞姬", "司马谈", "司马相如"]
    for q in queries:
        show(q)
