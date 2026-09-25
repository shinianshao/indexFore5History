# -*- coding: utf-8 -*-
"""实体标注：在语料中匹配人物别名，生成检索索引。

匹配的三层结构
--------------
1. **全局别名**（core）：姓名与专属称谓（「韓信」「淮陰侯」「留侯」），
   全库匹配，编译成单个正则按长度降序扫描——长别名优先，
   避免「漢高祖」被「高祖」截断。
2. **限定篇目的单字指代**（scoped）：如《太史公自序》的「談」、
   《項羽本紀》的「虞」。单字全局匹配会误伤「旦日」「不虞」这类普通词。
3. **泛称**（generic）：称号类别名（「梁王」「淮南王」「湯」），
   **不参与全局匹配**，按上下文逐条判定归属——见 resolve_generic()。

为什么泛称要单独处理
--------------------
纪传体史书里同一称号在不同篇目指不同人：「梁王」在《魏豹彭越列傳》是彭越，
在《梁孝王世家》是劉武；「湯」在《殷本紀》是商湯，在《酷吏列傳》是張湯。
若固定挂在一人名下，别人的篇目会整片错配——搜「彭越」会在《梁孝王世家》
里冒出一堆并非彭越的「梁王」。

归属判定是**篇内两遍扫描**：第一遍取所有非泛称命中，得到句/段/篇三级信号；
第二遍再据信号判定每处泛称归谁。三级信号都用得到，所以必须先扫完一遍。

数据裁剪
--------
《史记》130 卷约 4.6 万句，全量输出会到几十 MB。
小程序/网页只关心「哪句提到了谁」，因此**只保留有命中的句子**。

产物：
  data/index/book-data.json   完整索引
  web/app-data.js             供本地网页工具加载
  web/corpus-data.js          全篇正文，按需注入
  pipeline/_annotate_report.json
"""
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CORPUS, DICT, INDEX, PIPELINE, WEB, books_sorted,
                    compile_alias_pattern, corpus_paths, load_json, norm,
                    write_json)
from trad import tradify

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
    _S2T = OpenCC("s2t")
except Exception:                       # opencc 缺失时退化：繁简写法会各算一条
    _T2S = None
    _S2T = None


def t2s(text):
    """繁体转简体。用于把「一人多写法」归并成一条称谓。"""
    return _T2S.convert(text) if _T2S else text


def build_simp2trad_map():
    """简→繁**单字**映射（前端简体检索用）。

    逐字 s2t，只收「一字对一字」的（跳过多字输出与不变字）。一简对多繁
    （后/裏、里、干、云、发…）s2t 会猜一个形——**没关系**：前端把 s2t(q)
    作为「并列候选」加入，原串 q 仍保留试，猜错的繁体形不会顶掉正确的命中。
    """
    if _S2T is None:
        return {}
    m = {}
    for cp in range(0x4e00, 0x9fff + 1):
        ch = chr(cp)
        t = _S2T.convert(ch)
        if len(t) == 1 and t != ch:
            m[ch] = t
    return m


# 称谓类别的判定规则。
# 只用来看得懂，不参与匹配——所以宁可粗一点也不要漏：
# 「王/公/侯/君/帝/后/祖」这类字一旦出现，基本就是爵位、封号或谥号、庙号；
# 官职词表覆盖「丞相斯」「中車府令」这类「官职+名」的写法。
TITLE_MARK = re.compile(r"王|公|侯|伯|君|帝|后|祖|太后|夫人")
OFFICE_MARK = re.compile(r"相國|丞相|相国|太尉|太傅|御史|中車府|中车府|"
                         r"將軍|将军|太守|單于|单于|太子|大夫|僕射|令")
# 「公孫」「公子」是姓氏不是爵位——不先剥掉，「公孫僑」（子產本名）、
# 「公子小白」会被当成称号。注意这里必须写**简体**：类别是按简体键判定的。
GONG_SURNAMES = ("公孙", "公子", "公叔", "公伯", "公上", "公玉", "公仪",
                 "公输", "公西", "公羊", "公冶", "公良", "公罔", "公仲",
                 "公皙", "公冉", "公明")
KIND_ORDER = {"name": 0, "title": 1, "generic": 2, "short": 3, "other": 4}


def alias_kind(simp, name_simp, generic_simp):
    """给一条称谓定类别（按简体写法判定，繁简同条不会分成两类）。"""
    if simp == name_simp:
        return "name"
    if simp in generic_simp:
        return "generic"                # 泛称：归属按篇目上下文逐条判定
    if len(simp) == 1:
        return "short"                  # 单字指代，只在本篇内有效
    probe = simp
    for prefix in GONG_SURNAMES:
        probe = probe.replace(prefix, "")
    if TITLE_MARK.search(probe) or OFFICE_MARK.search(probe):
        return "title"
    return "other"


def build_alias_list(person, stats, generic_simp, stats_by_book=None):
    """把一个人的全部称谓整理成完整清单。

    词典里别名繁简两套并列，正文里还会出现异体字（髙祖 / 高祖），
    三者必须并成同一条，否则人物页会列出「髙祖、高祖」两条重复项。
    归并键 = 异体字归一 → 繁转简；显示写法取实际出现最多的一种。
    """
    name_simp = t2s(norm(person["name"]))
    groups, order = {}, []

    def slot(raw):
        key = t2s(norm(raw))
        one = groups.get(key)
        if one is None:
            one = groups[key] = {"declared": [], "forms": {}, "n": 0}
            order.append(key)
        return one

    for raw in [person["name"], person["tradName"]] + list(person["aliases"]):
        one = slot(raw)
        if raw not in one["declared"]:
            one["declared"].append(raw)
    for raw, num in stats.items():
        one = slot(raw)
        one["forms"][raw] = one["forms"].get(raw, 0) + num
        one["n"] += num
    # 按书分账：同一称谓在各书里各出现多少处（前端选单书时用）
    per_book = {}
    for code, amap in (stats_by_book or {}).items():
        for raw, num in amap.items():
            key = t2s(norm(raw))
            per_book.setdefault(key, {})
            per_book[key][code] = per_book[key].get(code, 0) + num

    rows = []
    for key in order:
        one = groups[key]
        seen = sorted(one["forms"].items(), key=lambda kv: (-kv[1], kv[0]))
        # 显示写法：原文里出现过就取出现最多的那一种；没出现过（词典收录了但
        # 本书不用）则取繁体写法——语料是繁体，这样与正文观感一致。
        rep = seen[0][0] if seen else None
        if rep is None:
            trad = [x for x in one["declared"] if t2s(norm(x)) != norm(x)]
            rep = trad[0] if trad else one["declared"][0]
        variants = sorted(set(one["declared"]) | set(one["forms"]))
        rows.append({
            "w": rep,
            "simp": key,
            "n": one["n"],
            "kind": alias_kind(key, name_simp, generic_simp),
            "variants": variants,        # 全部写法，供提示与检索
            "byBook": per_book.get(key, {}),
        })
    rows.sort(key=lambda r: (KIND_ORDER.get(r["kind"], 9), -r["n"], r["w"]))
    return rows

# 泛称归属的置信度分级，由强到弱。前端据此决定是否标注「存疑」。
TIER_ORDER = ["owner", "related", "sentence", "paragraph", "chapter", "era", "guess"]
# guess 之外的分级都算有上下文依据，不必提示用户存疑
CONFIDENT_TIERS = ("owner", "related", "sentence", "paragraph", "chapter", "era")

# 段级/篇级共现晋级所需的信号强度
PARA_SIGNAL_MIN = 1
CHAPTER_SIGNAL_MIN = 2

# 泛称归属的定点迭代上限：每轮把上一轮的判定回灌为信号，稳定即止。
# 3 轮足够——信息只在同段/同篇内传播，链路很短。
GENERIC_ROUNDS = 3

# 时代先后序。「判不出就不标」这条规则要靠它区分两种情形：
#   默认归属**晚于**本篇时代——此人当时尚未出生，绝不可能是他（判 none）；
#   默认归属**早于**本篇时代——只是后人追述前朝，完全正常（照旧兜底）。
# 少了这把尺子就会一刀切：《殷本紀》讲商代却提「武王伐紂」，「武王」的默认
# 归属是周武王（西周），与篇内时代不符就被判 none，实测会让周武王白丢 65 处。
ERA_ORDER = ["上古", "夏", "商", "西周", "東周", "春秋",
             "戰國", "秦", "秦末", "西漢", "新", "東漢",
             # 三国志/晋：缺了会导致 era_index 恒 None，sgz 泛称 era 档整档失效
             "三國", "西晉", "東晉", "十六國"]
ERA_INDEX = {name: i for i, name in enumerate(ERA_ORDER)}

# ⚠️ 查表必须走 era_index()，不能直接 ERA_INDEX.get()。
# 词典里人物的 dynasty 是**简体**（build_dict.PERSONS 写的是「西汉」），
# 而 ERA_ORDER 按传统字形写（「西漢」）。两套字形里只有「夏商秦新」等
# 本就同形，偏偏「東周／戰國／西漢／東漢」四个是简繁异形——直接 get 会静默
# 返回 None，闸门就成了摆设（踩过：韓王 的四篇误标全靠这一条挡，结果一处没挡）。
# era_index 用 t2s 归一到简体再查，两种写法都能命中。
ERA_INDEX_S = {t2s(name): i for i, name in enumerate(ERA_ORDER)}

# 断代史「本书记载时代」的 era 下标区间（含端点）。史記为通史，不拆。
# 相邻书有意重叠：漢書↔後漢書 共「新」（王莽）；後漢書↔三國志 共「東漢」（汉末）；
# 三國志↔晉書 共「三國」（晋书自司马懿时代起，故三國人物对晋书算「本纪时代」）。
BOOK_ERA = {
    "sj": None,
    "hs": (8, 10),    # 秦末～新
    "hhs": (10, 11),  # 新～東漢
    "sgz": (11, 12),  # 東漢～三國
    "js": (12, 15),   # 三國～十六國
}


def era_index(name):
    """朝代名 → 时代序（简繁不限），查不到返回 None。"""
    if not name:
        return None
    idx = ERA_INDEX.get(name)
    if idx is not None:
        return idx
    return ERA_INDEX_S.get(t2s(name))

# 单字别名的上下文排除表。
# 「湯」在《夏本紀》是「湯湯洪水滔天」（形容水势），不是商湯；
# 「旦」在三王世家指劉旦，但「旦日」是普通词。
#
# ⚠️ 键按**异体归一后**的字形写（见 single_char_ok 的 norm(surface)）：
#    匹配是在 norm(text) 上做的，守卫表若按原文写，同一个字就得为
#    「啟」「啓」各备一份，改一边忘一边。
SINGLE_CHAR_STOP = {
    "湯": set("湯沐藥火池旱"),
    "旦": set("日夕"),
    "胥": set("靡"),
    "虞": set("人人"),
    "談": set("說论論"),
    "閎": set("大"),
    # 「啟」既是夏后啟的单字别名，也是「微子啟」的末字、「不憤不啟」的动词。
    # 归一后「啓」也走这条，所以三个误配源都要挡：
    #   啓母（微子启之母）、啟弟（微仲，微子启之弟）→ 后接限制；
    #   不憤不啟 → 前接限制。⚠️ 紧邻「啟」的前一个字是**不**不是「憤」——
    #   守卫只看 ±1 字，写「憤」是拦不住的（这里踩过一次）。
    # 不能挡「子」：夏本紀「禹子啓賢」「帝禹之子啓」都要靠它（那才是夏后啟）。
    # 「微子啓／宋微子啟」另有正解：词典补了「宋微子啟」别名，整串被吃掉。
    "啟": set("母弟不"),
}

# 单字别名的**单向**守卫。
# 同一个字在两侧构成的反证未必相同，混进一张双向表必然误伤。「桀」即一例：
#   只有**前接**才错的——豪桀／俊桀／雄桀／儁桀／暴桀（皆豪杰义）、
#                        軍桀／官桀／父桀／侯桀（皆上官桀的简称）；
#   只有**后接**才错的——桀黠／桀宋／桀溺／桀等／桀子／桀黨。
# 若把「暴」并进双向表，「紂負桀暴之累」（夏桀之暴）会被一并挡掉。
# 两侧都不该挡的：「桀紂」并称（28 处）、「雖桀」（雖桀紂惡／雖桀在上）、
# 「桀之時」「堯、桀之分」——用的都是夏桀。
SINGLE_CHAR_PRE = {
    "桀": set("豪俊儁雄暴陰軍官父侯劉疑與斬予立是後授僕封敢"),
    # R3 #B：裸「禹」「舜」前接误伤（霍禹/侯舜/太保舜/皇子舜…），docs/07 #B
    "禹": set("霍侯傅臣賜保子王鄧張貢趙許郭絮矦"),
    "舜": set("侯王傅臣保子許郭絮矦鄧"),
}
SINGLE_CHAR_POST = {
    "桀": set("黠宋溺等子黨心追令因輒已奉頓常欲惡父驁妻"),
}

# 单字别名的「后两字」守卫。
# 紧邻字是标点时，±1 字判断不够用：漢書「桀、安父子」「桀、安與大將軍光爭權」
# 里的「桀」是上官桀（与子上官安并称），前一字是顿号、不携带信息，
# 但后两字「、安」是固定搭配，据此判掉。
SINGLE_CHAR_STOP2 = {
    "桀": {"、安", "為安", "爲安"},
}

# 多字别名的邻字守卫。
# 「老子」在「父老子弟」「父老子孫」「母老子弱」里是被跨词切出来的
# （父老／子弟、母老／子弱），并非李耳。前接「父」「母」一律不认。
# 真老子前面从不接这两个字——「黃帝、老子」「問禮於老子」「老子曰」都不受影响。
ALIAS_STOP = {
    "老子": set("父母"),
}
# 多字别名的**单向**前接/后接守卫（ALIAS_STOP 是双向共用一字集，这里前后接字不同时分开）。
# 「有若」假阳性是结构性的「有＋若（像）」：則有若伊陟／未有若此者／有若自然／
# 未有若公孫弘者 —— 前接「則/未」、后接「此/自/公/富」；真阳性「有若」是句首人名
# （后接 曰/狀/默/少），两不相犯。
ALIAS_STOP_PRE = {
    "有若": set("則未"),
    # 「章武王」「元文王」等王号含文王/武王二字
    "文王": set("章元景宣成"),
    "武王": set("章文成宣元"),
    # 「趙王倫」「齊王冏」等：短王号后接单字名，是长号的一部分
    "趙王": set("倫冏乂穎颙"),
    "齊王": set("冏倫乂"),
    "梁王": set("肜彤倫"),
    "吳王": set("晏恪"),
    "燕王": set("皝俊垂"),
    "魏王": set("丕操叡彰植熊"),
    # 「漢元帝」「魏元帝」：裸「元帝」不得从专名前缀里截出来
    "元帝": set("漢汉魏晉晋蜀吳吴"),
}
ALIAS_STOP_POST = {
    "有若": set("此自公富"),
    # 短王号后接单字名（趙王倫 / 齊王冏）
    "趙王": set("倫冏乂穎颙"),
    "齊王": set("冏倫乂"),
    "梁王": set("肜彤倫"),
    "吳王": set("晏恪"),
    "燕王": set("皝俊垂"),
    "魏王": set("丕操叡彰植熊"),
}


def single_char_ok(text, start, end, ch):
    """单字别名命中处是否可信：排除叠字与常见复合词。

    `ch` 是**原文**里匹配到的那一个字（未归一），因此查守卫表前要 norm 一下——
    与匹配所用的 norm(text) 保持同一套字形标准。
    """
    if start > 0 and text[start - 1] == ch:
        return False            # 叠字（湯湯、旦旦）
    if end < len(text) and text[end] == ch:
        return False
    stops = SINGLE_CHAR_STOP.get(norm(ch), ())
    if end < len(text) and text[end] in stops:
        return False
    if start > 0 and text[start - 1] in stops:
        return False
    pre = SINGLE_CHAR_PRE.get(norm(ch))
    if pre and start > 0 and text[start - 1] in pre:
        return False
    post = SINGLE_CHAR_POST.get(norm(ch))
    if post and end < len(text) and text[end] in post:
        return False
    stop2 = SINGLE_CHAR_STOP2.get(norm(ch))
    if stop2 and text[end:end + 2] in stop2:
        return False
    return True


def alias_ok(text, start, end, surface):
    """别名命中处是否可信。

    单字别名走 single_char_ok（叠字／复合词／邻字守卫），
    多字别名查 ALIAS_STOP（防「父亲老子弟」这类跨词切开）。
    """
    if len(surface) == 1:
        return single_char_ok(text, start, end, surface)
    stops = ALIAS_STOP.get(norm(surface))
    if stops:
        if end < len(text) and text[end] in stops:
            return False
        if start > 0 and text[start - 1] in stops:
            return False
    pre = ALIAS_STOP_PRE.get(norm(surface))
    if pre and start > 0 and text[start - 1] in pre:
        return False
    post = ALIAS_STOP_POST.get(norm(surface))
    if post and end < len(text) and text[end] in post:
        return False
    return True


def build_scoped(people):
    """限定篇目的单字指代：按篇目编译小正则，只在该篇目内参与匹配。"""
    by_chapter = {}
    for item in people.get("scopedAliases", []):
        ch = norm(item["char"])
        for cid in item["chapters"]:
            by_chapter.setdefault(cid, {})[ch] = item["pid"]
    patterns = {}
    for cid, mapping in by_chapter.items():
        pat, _ = compile_alias_pattern([(c, pid) for c, pid in mapping.items()])
        patterns[cid] = (pat, mapping)
    return patterns


def bump(counter, pid, delta):
    """计数增减，减到 0 就删键（避免残留 0 值干扰 dominant 的比较）。"""
    value = counter.get(pid, 0) + delta
    if value > 0:
        counter[pid] = value
    else:
        counter.pop(pid, None)


def dominant(counts, cands, need):
    """某个候选是否在信号上明显领先：达到最低强度，且唯一最高。"""
    ranked = sorted(((c, counts.get(c, 0)) for c in cands),
                    key=lambda kv: (-kv[1], kv[0]))
    if ranked[0][1] < need:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None             # 并列则不敢判定
    return ranked[0][0]


def resolve_generic(entry, chapter_owners, chapter_local, sent_count,
                    para_count, chapter_count, chapter_dynasty, dynasty_of,
                    book_id=None, person_books=None):
    """判定一处泛称归谁。

    依据由强到弱，逐级放宽，每级都记下来源以便呈现与复核：
      ① owner     —— 本篇主人公里只有一位持有此称号
      ② related   —— 篇内相关人物里只有一位持有此称号
      ③ sentence  —— 本句里某候选用姓名/专属别名出现过
      ④ paragraph —— 本段里某候选的信号明显领先
      ⑤ chapter   —— 本篇里某候选的信号明显领先
      ⑥ era       —— 本篇所属时代的候选只有一位（「燕王」在战国篇章里
                     不该落到西汉的刘泽）
      ⑦ guess     —— 都判不出，落到词典默认归属（前端标注存疑）
    """
    cands = entry["candidates"]
    # 分书收束：断代史里裸帝号优先本纪传统含义（後漢書「武帝」= 漢武帝）
    book_cands = entry.get("bookCandidates") or {}
    if book_id and book_id in book_cands:
        narrowed = [c for c in book_cands[book_id] if c in cands] or list(book_cands[book_id])
        cands = narrowed
        if len(cands) == 1:
            return cands[0], "era"
    # R-fix：泛称候选过书作用域——books:["sgz"] 的人不得在史汉被选中
    if book_id is not None and person_books:
        cands = [c for c in cands
                 if not person_books.get(c)
                 or book_id in (person_books.get(c) or [])]
        if not cands:
            return None, "none"
        # R1：过滤后只剩一人时直接归他。否则 default 常是外书人物
        # （宣帝 default=汉宣帝），在三国志里被书闸打掉后整处判 none，
        # 表现为「司马懿名下宣帝/宣王几乎空」。
        if len(cands) == 1:
            return cands[0], "era"

    hit = [c for c in cands if c in chapter_owners]
    if len(hit) == 1:
        return hit[0], "owner"

    hit = [c for c in cands if c in chapter_local]
    if len(hit) == 1:
        return hit[0], "related"

    pid = dominant(sent_count, cands, 1)
    if pid:
        return pid, "sentence"
    pid = dominant(para_count, cands, PARA_SIGNAL_MIN)
    if pid:
        return pid, "paragraph"
    pid = dominant(chapter_count, cands, CHAPTER_SIGNAL_MIN)
    if pid:
        return pid, "chapter"

    if chapter_dynasty:
        era = chapter_dynasty.most_common(1)[0][0]
        same_era = [c for c in cands if dynasty_of.get(c) == era]
        if len(same_era) == 1:
            return same_era[0], "era"
        default = entry["default"]
        if person_books and person_books.get(default) and \
                book_id not in (person_books.get(default) or []):
            default = None
        if default:
            ahead = era_index(dynasty_of.get(default))
            here = era_index(era)
            if ahead is not None and here is not None and ahead - here >= 2:
                return None, "none"
            # 后人追述前朝（三国志提周公/文王/湯）：default 早于本篇且**无同代候选**
            # 时才记 era。载记里「齊王→田儋」这类是同号异人，不得伪称时代依据。
            if ahead is not None and here is not None and ahead < here:
                # 有「接近本篇」的候选（晋书景帝=司马师）则优先，不落到上古 default
                nearer = []
                for c in cands:
                    ei = era_index(dynasty_of.get(c))
                    if ei is not None and ei >= here - 3:
                        nearer.append(c)
                if len(nearer) == 1:
                    return nearer[0], "era"
                if nearer:
                    return default, "guess"
                return default, "era"
            return default, "guess"
        return None, "none"

    default = entry["default"]
    if person_books and person_books.get(default) and \
            book_id not in (person_books.get(default) or []):
        return None, "none"
    return default, "guess"


def main():
    os.makedirs(INDEX, exist_ok=True)
    os.makedirs(WEB, exist_ok=True)

    people = load_json(os.path.join(DICT, "people.json"),
                       {"persons": [], "chapterOwners": {}})
    persons = people["persons"]
    owners = people["chapterOwners"]
    related = people.get("chapterRelated", {})
    generics = people.get("genericAliases", [])

    # 泛称的表层写法不参与全局匹配，否则会与上下文判定结果打架
    generic_forms = set()
    generic_simp = set()
    generic_entry_map = {}
    for entry in generics:
        for form in entry["forms"]:
            generic_forms.add(norm(form))
            generic_simp.add(t2s(norm(form)))
            generic_entry_map[norm(form)] = entry
    generic_pat, generic_map = compile_alias_pattern(
        [(form, entry["alias"]) for entry in generics for form in entry["forms"]])

    # 书作用域：person["books"] 限定的人只在指定书内匹配（汉书补人物用），
    # 其余进全局表。限书的人不能进 base_pairs——否则史记侧会被误命中。
    base_pairs = []
    book_pairs = {}
    for person in persons:
        books = person.get("books") or []
        for alias in person["aliases"]:
            if norm(alias) in generic_forms:
                continue
            if books:
                for code in books:
                    book_pairs.setdefault(code, []).append((alias, person["id"]))
            else:
                base_pairs.append((alias, person["id"]))
    base_pat, base_map = compile_alias_pattern(base_pairs)
    # 每本書把「全局別名 + 本書專屬別名」編成**一個**模式。
    # 為什麼必須合併：分開跑就是「全局先佔位、專屬只能撿漏」，
    # 《史記》的「田廣」（齊王田廣）會把《漢書》的「田廣明」整名截走前兩字
    # ——兩個人毫不相干，實測 12 處因此誤標。合在一個模式裡，
    # compile_alias_pattern 的「長度降序」才起作用：三字的田廣明先於兩字的田廣。
    # 同名時仍以全局為準（維持既有歸屬，零回歸），所以先剔掉與 base 撞名的項。
    base_alias = {norm(a) for a, _ in base_pairs}
    book_pat = {}
    for code, pairs in book_pairs.items():
        extra = [(a, pid) for a, pid in pairs if norm(a) not in base_alias]
        book_pat[code] = compile_alias_pattern(base_pairs + extra)

    scoped_patterns = build_scoped(people)

    person_ids = [p["id"] for p in persons]
    dynasty_of = {p["id"]: p.get("dynasty", "") for p in persons}
    person_books_map = {
        p["id"]: p.get("books") or []
        for p in persons if p.get("books")
    }
    mention_count = {pid: 0 for pid in person_ids}
    mention_sentence = {pid: 0 for pid in person_ids}
    mention_chapters = {pid: set() for pid in person_ids}
    alias_stat = {pid: {} for pid in person_ids}
    # —— 按书分账（多书检索的数据基础）——
    # 顶层 mentionCount 仍是**两书合计**，一个字都不改（旧断言全靠它）；
    # byBook 只是**新增**维度，前端按书筛选时读它。
    mention_by_book = {pid: {} for pid in person_ids}     # pid -> {code: 处}
    chapter_by_book = {pid: {} for pid in person_ids}     # pid -> {code: {篇}}
    alias_by_book = {pid: {} for pid in person_ids}       # pid -> {code: {写法: 处}}
    tier_stat = Counter()
    guess_count = Counter()
    generic_resolution = {}

    chapters = []
    hit_sentences = []
    corpus_out = {}
    total_sentences = 0
    total_chars = 0

    # ready:false 的书（准备期，语料已切但人物/篇主未补齐）不并入产物——
    # 与 build.py 的 ready 闸门一致，否则半成品会把史记/汉书的产物搅乱。
    for path in corpus_paths(ready_only=True):
        doc = load_json(path)
        chapter_id = doc["chapterId"]
        book_id = doc.get("bookId", "")
        main_persons = owners.get(chapter_id, [])
        related_persons = related.get(chapter_id, [])
        chapter_owners = set(main_persons)
        chapter_local = chapter_owners | set(related_persons)

        corpus_out[chapter_id] = {
            "fullTitle": doc["fullTitle"],
            "category": doc["category"],
            "charCount": doc["charCount"],
            "paragraphs": [p["text"] for p in doc["paragraphs"]],
            # 校勘/夹注与正文平行；读全篇小字蓝色展示，不参与句层统计
            "notes": [p.get("note") or "" for p in doc["paragraphs"]],
        }
        chapters.append({
            "id": chapter_id,
            "bookId": doc["bookId"],
            "book": doc["book"],
            "title": doc["title"],
            "fullTitle": doc["fullTitle"],
            "category": doc["category"],
            "volume": doc["volume"],
            "charCount": doc["charCount"],
            "paragraphCount": doc["paragraphCount"],
            "sentenceCount": doc["sentenceCount"],
            "mainPersons": main_persons,
            "relatedPersons": related_persons,
        })
        total_sentences += doc["sentenceCount"]
        total_chars += doc["charCount"]

        # ---- 第一遍：全局别名 + 限定单字，累计句/段/篇三级信号 ----
        processed = []
        para_counts = {}
        chapter_count = {}

        # 本章要跑的附加模式：篇內單字指代（本書專屬人物已併入 scope_pat）
        if book_id in book_pat:
            scope_pat, scope_map = book_pat[book_id]
        else:
            scope_pat, scope_map = base_pat, base_map
        extra_patterns = [p for p in (scoped_patterns.get(chapter_id),)
                          if p is not None]

        for para in doc["paragraphs"]:
            para_count = {}
            for sent in para["sentences"]:
                text = sent["text"]
                normalized = norm(text)
                marks = []

                if scope_pat is not None:
                    for match in scope_pat.finditer(normalized):
                        pid = scope_map.get(match.group(0))
                        if not pid:
                            continue
                        surface = text[match.start():match.end()]
                        if not alias_ok(
                                text, match.start(), match.end(), surface):
                            continue
                        marks.append({"s": match.start(), "e": match.end(),
                                      "pid": pid, "tier": "core", "alias": surface})

                for spat, smap in extra_patterns:
                    occupied = [False] * len(text)
                    for mk in marks:
                        for i in range(mk["s"], mk["e"]):
                            occupied[i] = True
                    for match in spat.finditer(normalized):
                        if occupied[match.start()]:
                            continue
                        pid = smap.get(match.group(0))
                        if not pid:
                            continue
                        surface = text[match.start():match.end()]
                        if not alias_ok(text, match.start(), match.end(), surface):
                            continue
                        occupied[match.start()] = True
                        marks.append({"s": match.start(), "e": match.end(),
                                      "pid": pid, "tier": "scoped", "alias": surface})

                marks.sort(key=lambda m: m["s"])
                processed.append((para["seq"], sent, text, marks, normalized))
                for mk in marks:
                    pid = mk["pid"]
                    para_count[pid] = para_count.get(pid, 0) + 1
                    chapter_count[pid] = chapter_count.get(pid, 0) + 1
            para_counts[para["seq"]] = para_count

        # 篇属时代：篇内出场人物的朝代分布，用于末年兜底
        chapter_dynasty = Counter()
        for pid, n in chapter_count.items():
            era = dynasty_of.get(pid)
            if era:
                chapter_dynasty[era] += n

        # ---- 第二遍：泛称按上下文判定归属 ----------------------------------
        # 先用「非泛称命中」作信号把泛称判一遍，再把**判定结果回灌**成信号重判，
        # 反复至稳定（定点迭代）。为什么要回灌：泛称之间不互相引用的话，有些段
        # 落里一个可用信号都没有。例如《淮南衡山列传》「淮南王自以為最親」所在段，
        # 刘长本人没有任何专属别名出现，只有一堆泛称「厲王」——只有让上一轮判出的
        # 「厲王→刘长」参与本轮信号，这一句的「淮南王」才能落到刘长而不是黥布。
        generic_hits = []
        for si, (para_seq, sent, text, marks, normalized) in enumerate(processed):
            if generic_pat is None:
                continue
            occupied = [False] * len(text)
            for mk in marks:
                for i in range(mk["s"], mk["e"]):
                    occupied[i] = True
            for match in generic_pat.finditer(normalized):
                if occupied[match.start()]:
                    continue        # 已被更长的专属别名覆盖（如「淮南王安」）
                entry = generic_entry_map.get(match.group(0))
                if entry is None:
                    continue
                surface = text[match.start():match.end()]
                if not alias_ok(
                        text, match.start(), match.end(), surface):
                    continue
                occupied[match.start()] = True
                generic_hits.append({
                    "si": si, "paraSeq": para_seq, "s": match.start(),
                    "e": match.end(), "surface": surface, "entry": entry,
                })

        assign = {}
        for _round in range(GENERIC_ROUNDS):
            sent_sig = [{} for _ in processed]
            para_sig = {}
            chap_sig = {}
            for si, (para_seq, sent, text, marks, normalized) in enumerate(processed):
                sc = sent_sig[si]
                pc = para_sig.setdefault(para_seq, {})
                for mk in marks:                        # 专属/限定别名命中
                    pid = mk["pid"]
                    sc[pid] = sc.get(pid, 0) + 1
                    pc[pid] = pc.get(pid, 0) + 1
                    chap_sig[pid] = chap_sig.get(pid, 0) + 1
            for gi, gh in enumerate(generic_hits):      # 上一轮泛称判定回灌
                got = assign.get(gi)
                if not got or not got[0]:
                    continue
                pid = got[0]
                sc = sent_sig[gh["si"]]
                pc = para_sig.setdefault(gh["paraSeq"], {})
                sc[pid] = sc.get(pid, 0) + 1
                pc[pid] = pc.get(pid, 0) + 1
                chap_sig[pid] = chap_sig.get(pid, 0) + 1

            # 判定某称号时，把「该称号自身」的全部命中从信号里扣除：
            # 同一称号不能自证，否则第一轮的判断（哪怕错）会原地锁死；
            # 不同称号之间则可以互相支撑，这正是要把结果回灌的原因。
            by_alias = {}
            for gi, gh in enumerate(generic_hits):
                by_alias.setdefault(gh["entry"]["alias"], []).append(gi)

            new_assign = {}
            for _alias, gis in by_alias.items():
                for gi in gis:                          # 扣除本称号贡献
                    got = assign.get(gi)
                    if not got or not got[0]:
                        continue
                    gh = generic_hits[gi]
                    bump(sent_sig[gh["si"]], got[0], -1)
                    bump(para_sig[gh["paraSeq"]], got[0], -1)
                    bump(chap_sig, got[0], -1)
                for gi in gis:
                    gh = generic_hits[gi]
                    new_assign[gi] = resolve_generic(
                        gh["entry"], chapter_owners, chapter_local,
                        sent_sig[gh["si"]], para_sig.get(gh["paraSeq"], {}),
                        chap_sig, chapter_dynasty, dynasty_of,
                        book_id=book_id, person_books=person_books_map)
                for gi in gis:                          # 还原
                    got = assign.get(gi)
                    if not got or not got[0]:
                        continue
                    gh = generic_hits[gi]
                    bump(sent_sig[gh["si"]], got[0], 1)
                    bump(para_sig[gh["paraSeq"]], got[0], 1)
                    bump(chap_sig, got[0], 1)
            if new_assign == assign:
                break               # 已稳定
            assign = new_assign

        for gi, gh in enumerate(generic_hits):
            pid, tier = assign[gi]
            if pid is None:
                # 判不出归属（resolve_generic 的 none 档）：不写标记、不占位。
                # 前端查这个称号时宁可不显示，也不显示错人。
                tier_stat["none"] = tier_stat.get("none", 0) + 1
                continue
            processed[gh["si"]][3].append(
                {"s": gh["s"], "e": gh["e"], "pid": pid, "tier": tier,
                 "alias": gh["surface"]})
            tier_stat[tier] += 1
            if tier == "guess":
                guess_count[gh["entry"]["alias"]] += 1
            slot = generic_resolution.setdefault(gh["entry"]["alias"], {})
            key = "{}|{}".format(pid, tier)
            slot[key] = slot.get(key, 0) + 1

        # ---- 写出命中句 ----
        for para_seq, sent, text, marks, normalized in processed:
            marks.sort(key=lambda m: m["s"])
            for mk in marks:
                pid = mk["pid"]
                mention_count[pid] += 1
                alias_stat[pid][mk["alias"]] = alias_stat[pid].get(mk["alias"], 0) + 1
                mention_by_book[pid][book_id] = mention_by_book[pid].get(book_id, 0) + 1
                abook = alias_by_book[pid].setdefault(book_id, {})
                abook[mk["alias"]] = abook.get(mk["alias"], 0) + 1

            pids = []
            for mk in marks:
                if mk["pid"] not in pids:
                    pids.append(mk["pid"])
            if not pids:
                continue
            for pid in pids:
                mention_sentence[pid] += 1
                mention_chapters[pid].add(chapter_id)
                chapter_by_book[pid].setdefault(book_id, set()).add(chapter_id)
            hit_sentences.append({
                "id": sent["id"],
                "chapterId": chapter_id,
                "paraSeq": para_seq,
                "seq": sent["seq"],
                "text": text,
                "persons": pids,
                "marks": marks,
            })

    name_of = {p["id"]: p["name"] for p in persons}
    person_out = []
    for person in persons:
        pid = person["id"]
        item = dict(person)
        item["mentionCount"] = mention_count.get(pid, 0)
        item["mentionChapterCount"] = len(mention_chapters.get(pid, ()))
        item["guessCount"] = guess_count.get(pid, 0)
        # 按书分账：前端选单书时读这里；顶层计数不动，旧断言照旧成立
        item["byBook"] = {
            code: {
                "mentionCount": n,
                "mentionChapterCount": len(chapter_by_book[pid].get(code, ())),
            }
            for code, n in sorted(mention_by_book.get(pid, {}).items())
        }

        def _by_book_alias(alias):
            return {code: a.get(alias, 0)
                    for code, a in sorted(alias_by_book.get(pid, {}).items())
                    if a.get(alias)}

        item["topAliases"] = sorted(
            ({"alias": a, "n": n, "byBook": _by_book_alias(a)}
             for a, n in alias_stat.get(pid, {}).items()),
            key=lambda x: -x["n"],
        )[:6]
        # 完整称谓清单（人物页「称谓表」的数据源）——topAliases 只留 6 条，
        # 那是给摘要用的；完整清单要含词典已收录但本批未出现的写法。
        item["aliasList"] = build_alias_list(person, alias_stat.get(pid, {}),
                                             generic_simp,
                                             alias_by_book.get(pid, {}))
        # 断代史前端拆「本书记载时代 / 相对古人」用
        item["eraRank"] = era_index(person.get("dynasty") or "")
        person_out.append(item)
    person_out.sort(key=lambda p: (-p["mentionCount"], p["name"]))

    generic_report = []
    for alias, slot in generic_resolution.items():
        rows = []
        for key, n in sorted(slot.items(), key=lambda kv: -kv[1]):
            pid, tier = key.split("|")
            rows.append({"person": name_of.get(pid, pid), "tier": tier, "n": n})
        generic_report.append({"alias": alias, "total": sum(r["n"] for r in rows),
                               "breakdown": rows})
    generic_report.sort(key=lambda r: -r["total"])

    confident = sum(tier_stat[t] for t in CONFIDENT_TIERS)
    # 书清单：前端的书选择器与「每本书独立的条目列表」都读这一份。
    # 由 books.json 驱动，新增古籍不用改这里。
    book_meta = []
    for code, meta in books_sorted():
        rows = [c for c in chapters if c["bookId"] == code]
        if not rows:
            continue
        book_meta.append({
            "code": code,
            "name": meta["name"],
            "order": meta.get("order", 0),
            "chapterCount": len(rows),
            "sentenceCount": sum(c["sentenceCount"] for c in rows),
            "charCount": sum(c["charCount"] for c in rows),
            "personCount": sum(1 for p in person_out
                               if p.get("byBook", {}).get(code)),
            "eraRange": BOOK_ERA.get(code),
            "placeCount": 0,        # 地名层 annotate_places.py 跑完才填
        })
    data = {
        "meta": {
            "book": "、".join(b["name"] for b in book_meta) or "史记",
            "books": book_meta,
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "chapterCount": len(chapters),
            "sentenceCount": total_sentences,
            "hitSentenceCount": len(hit_sentences),
            "personCount": len(person_out),
            "aliasCount": len(base_map) + len(generic_map),
            "charCount": total_chars,
            "genericAliasCount": len(generics),
            "genericMarks": sum(tier_stat.values()),
            "genericConfident": confident,
            "tierStat": {t: tier_stat[t] for t in TIER_ORDER if tier_stat[t]},
            "simp2trad": build_simp2trad_map(),
        },
        "persons": person_out,
        "chapters": chapters,
        "genericAliases": generics,
        "sentences": hit_sentences,
    }

    # 显示层转繁。人物层是**自己产物**的写入口，就在自己这儿转干净，
    # 不要指望下游的 annotate_places.py 顺手把人物字段也转了——那是反向依赖：
    # 单跑 annotate.py（或将来地名层被替换掉）时，人物层就会输出半简半繁的产物。
    # corpus_out 一并传进去：正文语料的篇名/体例也是显示字段（曾经漏掉，
    # corpus-data.js 里留下过半简半繁的「史记·五帝本紀」）。
    # tradify 每次都真转、不做短路，靠 to_trad 自身幂等收敛；
    # 顺带写出的 meta.variants 是前端简繁双向检索必需的（详见 trad.py）。
    converted = tradify(data, corpus=corpus_out)

    write_json(os.path.join(INDEX, "book-data.json"), data)
    with open(os.path.join(WEB, "app-data.js"), "w", encoding="utf-8") as fh:
        fh.write("window.BOOK_DATA = ")
        fh.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        fh.write(";\n")
    with open(os.path.join(WEB, "corpus-data.js"), "w", encoding="utf-8") as fh:
        fh.write("window.BOOK_CORPUS = ")
        fh.write(json.dumps(corpus_out, ensure_ascii=False, separators=(",", ":")))
        fh.write(";\n")

    report = {
        "meta": data["meta"],
        "script": data["meta"].get("script", "simp"),
        "tradifiedThisRun": converted,
        "genericResolution": generic_report,
        "guessAliases": sorted(
            ({"alias": a, "n": n} for a, n in guess_count.items()),
            key=lambda x: -x["n"]),
        "top_persons": [
            {"id": p["id"], "name": p["name"], "mentions": p["mentionCount"],
             "chapters": p["mentionChapterCount"],
             "topAliases": [a["alias"] for a in p["topAliases"]]}
            for p in person_out[:30]
        ],
        "zero_mention_persons": [p["name"] for p in person_out if p["mentionCount"] == 0],
        "chapters_without_owner": [c["id"] for c in chapters if not c["mainPersons"]],
        "sizes": {
            "book_data_kb": round(os.path.getsize(os.path.join(INDEX, "book-data.json")) / 1024, 1),
            "web_data_kb": round(os.path.getsize(os.path.join(WEB, "app-data.js")) / 1024, 1),
            "corpus_data_kb": round(os.path.getsize(os.path.join(WEB, "corpus-data.js")) / 1024, 1),
        },
    }
    write_json(os.path.join(PIPELINE, "_annotate_report.json"), report, indent=2)

    print("句 {} / 命中 {} / 人物 {} / 别名 {} / 泛称 {}".format(
        total_sentences, len(hit_sentences), len(person_out),
        data["meta"]["aliasCount"], len(generics)))
    print("泛称归属分级: {}".format(dict(tier_stat)))


if __name__ == "__main__":
    main()
