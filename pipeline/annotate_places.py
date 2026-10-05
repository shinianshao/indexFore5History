# -*- coding: utf-8 -*-
"""地名标注：在语料中匹配地名，给检索索引补上「地名层」。

为什么要单独一层、而不是塞进 annotate.py
---------------------------------------
人物层与地名层**共用同一份语料、同一份篇目元数据**，但匹配规则完全不同：
人物靠「同称异人的上下文判定」，地名靠「单字与姓氏/常用字撞车的守卫」。
分开写，改地名规则不会碰坏已经验证过的人物结果；两层各自可单独重跑。

三层结构对应的候选难度
--------------------
① **具名地名**（多字）  咸陽、滎陽、邯鄲、鉅鹿、淮陰、函谷關……
   字串唯一，直接全局匹配。tier="core"，高置信。
② **单字地名**（单字）  齊、陳、趙、魏、衛、越……
   与姓氏、动词、常见词撞车，需三道关卡：
     a. **人名占用区间**——该字落在已鉴定的人名标记内就不算地名（趙高、陳平）
     b. **bare=False**——该字作地名是少数义的（許之/代立/相隨）只保留多字写法
     c. **邻字守卫**——前后紧邻字命中 CHAR_GUARDS 的排除表（陳師/齊政/執劍以衛）
   tier="char"，前端可单独关闭。
③ **同名异地**       v1 未做运行时消歧，靠 build_places.py 的字串唯一性校验兜底；
                     已知「梁」兼指魏都大梁与汉梁国，在词典说明里写明。

产物（就地并入人物层已写好的索引，人物数据一个字节不改）：
  data/index/book-data.json   + places / placeMeta / sentences[].pmarks
  web/app-data.js             同步重写
  pipeline/_annotate_places_report.json
用法：python annotate_places.py（须在 annotate.py 之后）
"""
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CORPUS, DICT, INDEX, PIPELINE, WEB,
                    compile_alias_pattern, corpus_paths, load_json, norm,
                    stable_uid, write_json)
from trad import tradify

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
except Exception:
    _T2S = None

# 类型展示顺序（前端按此分组）与中文名
KIND_ORDER = ["国", "州", "郡", "县", "关", "山", "川", "湖", "域", "外"]
KIND_LABEL = {"国": "国/朝代", "州": "州部", "郡": "郡", "县": "县邑都城", "关": "关隘",
              "山": "山岳", "川": "河川", "湖": "湖泽",
              "域": "地域", "外": "域外"}


# 「整篇讲述」的判据：**篇名里含这个地名**。
#
# 这与人物索引的「篇目主人公」同构，而且比「篇内高频」好得多：
#   秦本紀 → 秦    齊太公世家 → 齊    趙世家 → 趙
#   匈奴列傳 → 匈奴    大宛列傳 → 大宛    淮南衡山列傳 → 淮南/衡山
#   河渠書 → 河
# 篇名不含地名、但该地确实在篇内高密度出现的（田敬仲完世家之于齊、
# 孔子世家之于魯），再用「篇内地名榜前 N 且达到最低次数」兜底。
MAIN_TOP_RANK = 3
MAIN_MIN_COUNT = 8


def t2s(text):
    return _T2S.convert(text) if _T2S else text


def char_ok(text, start, end, guard):
    """单字地名的邻字守卫：前后紧邻字若命中排除表，判为非地名用法。"""
    if not guard:
        return True
    if start > 0 and text[start - 1] in guard.get("bfr", ""):
        return False
    if end < len(text) and text[end] in guard.get("aft", ""):
        return False
    return True


def name_hit(text, start, name_by_first, peerage, posthumous):
    """单字地名是否落在「姓+名」里；命中则返回阻断串。

    「人名占用区间」只能挡词典里那 388 位主角，长尾人物（秦嘉/周市/魏冉/蔡澤）
    不在表里，他们的姓氏就顺着单字地名漏出来——秦始皇本紀里「秦嘉」的「秦」
    被标成秦国，就是这么来的。NAME_BLOCK 是**审读过**的人名表（见 build_places.py
    里的收录标准），挖掘器只负责召回候选，精确性由人 + 语料实证负责。

    守卫：**「地名+谥号+爵位」三段式**才放行。「宋襄」是宋义之子（人名），
    但「宋襄公」是宋国+谥号+爵位，仍是地名读法——所以要求阻断串是 2 字、
    末字是谥号字、且其后紧跟爵位字。

    第一版守卫只看「后接字是不是爵位/职官字」，判据过宽：軍/兵/將/相/守
    在人名后面是谓语或宾语（「秦嘉軍敗走」「晉鄙軍」「雍齒守豐」「宋襄相齊」），
    结果 393 处里被放行了 60 多处。加上「末字须是谥号字」这一条后，
    「吳娃子」（娃非谥号）「秦嘉軍」（嘉非谥号）都不再被放行。
    """
    for word in name_by_first.get(text[start], ()):
        if text.startswith(word, start):
            if len(word) == 2 and word[1] in posthumous:
                nxt = text[start + 2:start + 3]
                if nxt and nxt in peerage:
                    continue
            return word
    return None


def build_place_matcher(places):
    """地名匹配器：全部写法编成单个正则，长度降序——长写法优先。

    带 books 的地名**只在指定书内匹配**（《地理志》郡县即如此）：
    为每本书单独编译一份「全局写法 + 该书专属写法」，
    与人物层的 book_pat 同一套约定——合并编译才能保住「長名優先」，
    否则「田廣明」这类整名会被同书更短的别名截断。
    """
    base_pairs = []
    book_pairs = {}
    for place in places:
        codes = place.get("books") or []
        for alias in place["aliases"]:
            if codes:
                for code in codes:
                    book_pairs.setdefault(code, []).append((alias, place["id"]))
            else:
                base_pairs.append((alias, place["id"]))
    base_pat, base_map = compile_alias_pattern(base_pairs)
    base_alias = {norm(a) for a, _ in base_pairs}
    book_pat = {}
    for code, pairs in book_pairs.items():
        extra = [p for p in pairs if norm(p[0]) not in base_alias]
        book_pat[code] = compile_alias_pattern(base_pairs + extra)
    by_id = {p["id"]: p for p in places}
    return base_pat, base_map, book_pat, by_id


def build_alias_list(place, stats, stats_by_book=None):
    """地名的「写法表」：把繁简/异写并成一条，显示原文里出现最多的那一种。

    归并键 = 异体字归一 → 繁转简。与人物层的 build_alias_list 同一思路，
    但地名没有「本名/称号/泛称」之分，只有「本名」与「异写」。
    """
    name_simp = t2s(norm(place["name"]))
    groups, order = {}, []

    def slot(raw):
        key = t2s(norm(raw))
        if key not in groups:
            groups[key] = {"declared": [], "forms": {}, "n": 0}
            order.append(key)
        return groups[key]

    for raw in place["aliases"]:
        one = slot(raw)
        if raw not in one["declared"]:
            one["declared"].append(raw)
    for raw, num in stats.items():
        one = slot(raw)
        one["forms"][raw] = one["forms"].get(raw, 0) + num
        one["n"] += num
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
        rep = seen[0][0] if seen else None
        if rep is None:                      # 词典收录但本书未用：显示繁体写法
            trad = [x for x in one["declared"] if t2s(norm(x)) != norm(x)]
            rep = trad[0] if trad else one["declared"][0]
        rows.append({
            "w": rep,
            "simp": key,
            "n": one["n"],
            "isName": key == name_simp,
            "variants": sorted(set(one["declared"]) | set(one["forms"])),
            "byBook": per_book.get(key, {}),
        })
    rows.sort(key=lambda r: (not r["isName"], -r["n"], r["w"]))
    return rows


def main():
    places_doc = load_json(os.path.join(DICT, "places.json"))
    if not places_doc:
        raise SystemExit("缺少 data/dict/places.json，请先跑 build_places.py")
    places = places_doc["places"]
    guards_raw = {norm(k): v for k, v in places_doc.get("charGuards", {}).items()}
    # 全局禁用的单字（按**匹配到的字串**判定，不按地名本体长度）——
    # 「漢水」的单字别名「漢」就靠这一条挡住，否则 1640 处「漢」（多为朝代/漢王）
    # 会全部算成汉水。
    bare_off = set(norm(c) for c in places_doc.get("bareOff", []))
    # 「姓+名」人名阻断表（首字 -> 该首字开头的全部阻断串，长串优先）
    name_by_first = {}
    for w in places_doc.get("nameBlock", []):
        name_by_first.setdefault(norm(w[0]), []).append(norm(w))
    for key in name_by_first:
        name_by_first[key].sort(key=len, reverse=True)     # 长串优先（鄭安平 > 鄭安）
    title_chars = set(places_doc.get("nameBlockPeerage", ""))
    posthumous = set(places_doc.get("nameBlockPosthumous", ""))

    data = load_json(os.path.join(INDEX, "book-data.json"))
    if not data:
        raise SystemExit("缺少 data/index/book-data.json，请先跑 annotate.py")

    place_pat, place_map, place_book_pat, by_id = build_place_matcher(places)
    # R4：全部多字地名别名（不分书）——单字截断压制用
    all_multi_aliases = set()
    for _p in places:
        for _a in _p["aliases"]:
            if len(_a) >= 2:
                all_multi_aliases.add(norm(_a))
    blocked_trunc = Counter()

    # 人名占用的行号表：句子 id -> [(s,e)]
    #
    # 直接取人物层已经算好的标记，不再另外跑一遍人名匹配——好处有二：
    #   ① 泛称（梁王/淮南王）的消歧结果也一并用来挡，比只挡专属别名更严；
    #   ② 只需保证「索引里的句子 ⊇ 有人名标记的句子」，而这正是 annotate.py
    #      的写入口径（有标记才入索引），所以没进索引的句子必然没有任何人名标记，
    #      不会被漏挡。
    person_spans = {}
    for sent in data["sentences"]:
        spans = [(m["s"], m["e"]) for m in sent.get("marks", [])]
        if spans:
            person_spans[sent["id"]] = spans

    mention = Counter()
    mention_chapter = {}
    alias_stat = {}
    chapter_place = {}                 # cid -> Counter(pid)
    # —— 按书分账（与人物层同一套约定：顶层不变，byBook 只增）——
    mention_by_book = {}               # pid -> {code: 处}
    chapter_by_book = {}               # pid -> {code: {篇}}
    alias_by_book = {}                 # pid -> {code: {写法: 处}}
    char_marks = 0
    core_marks = 0
    blocked_person = Counter()
    blocked_guard = Counter()
    blocked_bare = Counter()
    blocked_name = Counter()

    new_sentences = []
    existing = {}
    for sent in data["sentences"]:
        sent.setdefault("pmarks", [])
        existing[sent["id"]] = sent
    for sent in data["sentences"]:
        new_sentences.append(sent)

    chapter_meta = {c["id"]: c for c in data["chapters"]}

    def annotate(sent, chapter_id):
        """给一句标记地名；返回是否有命中。"""
        text = sent["text"]
        normalized = norm(text)
        spans = person_spans.get(sent["id"], [])
        # 本书专属地名（《地理志》郡县）并入当前书的模式；无专属则用全局模式
        bk = chapter_meta.get(chapter_id, {}).get("bookId", "")
        ppat, pmap = place_book_pat.get(bk) or (place_pat, place_map)
        marks = []
        for match in ppat.finditer(normalized):
            alias = match.group(0)
            place = by_id[pmap[alias]]
            surface = text[match.start():match.end()]
            if len(surface) == 1:
                if surface in bare_off:
                    blocked_bare[surface] += 1
                    continue
                # R4：单字后若恰成词典任一多字地名，禁止截断
                # （陳留→只标陳、江陵→只标江：长名可能不在本书模式里）
                trunc = False
                for L in range(2, min(6, len(normalized) - match.start() + 1)):
                    piece = normalized[match.start():match.start() + L]
                    if piece in all_multi_aliases:
                        trunc = True
                        break
                if trunc:
                    blocked_trunc[surface] += 1
                    continue
                if any(match.start() < e and s < match.end() for s, e in spans):
                    # 例外：**「国+谥+爵」三段式仍按地名读**。
                    # 曹襄公＝曹国＋谥襄＋爵公，首字「曹」指的还是曹国，
                    # 宋襄公／陳武公／周文王同理——与 name_hit() 里的守卫同判据。
                    # 批量补入各国君主之后，这类人名区间会把整串盖住；
                    # 不在此放行的话，单字国名会被人名区间整批吃掉
                    # （实测：曹襄公 的「曹」一度被挡，地名标记变空）。
                    if not any(s == match.start() and e - s == 3
                               and text[s + 1] in posthumous
                               and text[s + 2] in title_chars
                               for s, e in spans):
                        blocked_person[place["name"]] += 1
                        continue
                hit_name = name_hit(text, match.start(), name_by_first,
                                    title_chars, posthumous)
                if hit_name:
                    blocked_name[hit_name] += 1
                    continue
                if not char_ok(text, match.start(), match.end(),
                               guards_raw.get(surface)):
                    blocked_guard[place["name"]] += 1
                    continue
                tier = "char"
            else:
                tier = "core"
            marks.append({"s": match.start(), "e": match.end(),
                          "pid": place["id"], "tier": tier, "alias": surface})
        # 必须**无条件覆盖**：本脚本是就地修改 book-data.json，
        # 上一轮留下的 pmarks 若不抹掉，收紧守卫后（如把「紀」列入禁用单字）
        # 旧的错误标记会原样残留——表现为 mentionCount 与标记数对不上。
        sent["pmarks"] = marks
        if not marks:
            return False
        for mk in marks:
            pid = mk["pid"]
            mention[pid] += 1
            mention_chapter.setdefault(pid, set()).add(chapter_id)
            alias_stat.setdefault(pid, {})
            alias_stat[pid][mk["alias"]] = alias_stat[pid].get(mk["alias"], 0) + 1
            chapter_place.setdefault(chapter_id, Counter())[pid] += 1
            book_id = chapter_meta.get(chapter_id, {}).get("bookId", "")
            mention_by_book.setdefault(pid, {})
            mention_by_book[pid][book_id] = mention_by_book[pid].get(book_id, 0) + 1
            chapter_by_book.setdefault(pid, {}).setdefault(book_id, set()).add(chapter_id)
            alias_by_book.setdefault(pid, {}).setdefault(book_id, {})
            ab = alias_by_book[pid][book_id]
            ab[mk["alias"]] = ab.get(mk["alias"], 0) + 1
        return True

    # ---- 逐篇逐句标注 ----
    # 语料是权威来源：索引里只有「有人物命中」的句子，地名不能只在这些句子里找，
    # 否则「只提地名不提人」的句子会整批丢失。
    total_sentences = 0
    # ready:false 的书（准备期）不并入——与 annotate.py / build.py 的闸门一致。
    for path in corpus_paths(ready_only=True):
        doc = load_json(path)
        cid = doc["chapterId"]
        for para in doc["paragraphs"]:
            for sent in para["sentences"]:
                total_sentences += 1
                record = existing.get(sent["id"])
                if record is None:
                    # uid 必须带上（P4-0）：这批是「只有地名命中」的句子，
                    # annotate.py 那边没给它们建记录，漏了就整批没有稳定主键。
                    record = {
                        "id": sent["id"], "chapterId": cid,
                        "paraSeq": para["seq"], "seq": sent["seq"],
                        "uid": sent.get("uid") or stable_uid(
                            cid, para["seq"], sent["seq"]),
                        "text": sent["text"], "persons": [], "marks": [],
                        "pmarks": [],
                    }
                    existing[sent["id"]] = record
                    new_sentences.append(record)
                annotate(record, cid)

    # 保留全量句子入库，保证正文阅读层无洞且注文跳转 100% 可达
    place_only = sum(1 for s in new_sentences if s.get("pmarks") and not s.get("persons"))

    char_marks = sum(1 for s in new_sentences for m in s.get("pmarks", [])
                     if m["tier"] == "char")
    core_marks = sum(1 for s in new_sentences for m in s.get("pmarks", [])
                     if m["tier"] == "core")

    # ---- 篇内地名榜 + 篇名含地名：共同决定「整篇讲述」----
    chapter_top = {}
    dense = {}                     # pid -> {cid: n}「篇内高频」兜底用
    for cid, counter in chapter_place.items():
        ranked = counter.most_common()
        chapter_top[cid] = [{"pid": pid, "n": n} for pid, n in ranked[:6]]
        for rank, (pid, n) in enumerate(ranked, 1):
            if rank <= MAIN_TOP_RANK and n >= MAIN_MIN_COUNT:
                dense.setdefault(pid, {})[cid] = n

    # 篇名含地名：用词典里的全部写法去比篇名（都做异体字归一）
    # R4 单字复核：isChar 不用「篇名里出现该字」——合传「張耳陳餘」「荀韓鍾陳」
    # 会把单字国名整篇误挂。只认多字别名，或单字位于篇名起首且后非人名起首。
    CHAR_TITLE_TAIL = {
        "陳": ("涉", "勝", "胜", "餘", "余", "丞", "王列", "平", "宮"),
        "魏": ("公子", "豹", "冉"),
        "吳": ("濞", "芮", "漢", "王濞", "延史", "延", "蓋"),
        "韓": ("信", "非", "王", "長孺", "彭", "崔"),
        "趙": ("括", "奢", "盾", "尹", "充國"),
        "楚": ("元", "懷", "靈", "莊", "頃", "考", "平", "共", "惠", "負"),
        "秦": ("始", "莊", "繆", "孝", "惠", "文", "武", "昭", "襄", "厲", "懷", "靈", "二世"),
        "周": ("勃", "昌", "苛", "亞", "平", "宣", "幽", "厲", "赧", "瑜"),
        "齊": ("桓", "景", "湣", "閔", "襄", "宣", "威", "建", "田"),
        "魯": ("仲", "連", "隱", "桓", "莊", "僖", "文", "宣", "成", "襄", "昭", "定", "哀"),
        "蔡": ("邕", "澤", "仲"),
        "梁": ("孝", "王", "冀", "商", "丘", "統"),
        "曹": ("參", "操", "仁", "洪", "爽", "植", "丕", "髦", "奂"),
        "夏": ("侯", "禹", "桀", "后"),
        "蜀": ("先", "後", "主", "書"),
        "越": (),  # 越王勾踐世家须放行；人名彭越等不以「越」起首篇名
        "鄭": ("範", "孔", "當時"),
        "虞": ("傅", "詡", "仲翔"),
        "商": ("君",),
        "吳書": (),
    }

    def title_is_char_ok(place, title):
        aliases = [norm(a) for a in place["aliases"]]
        if any(len(a) >= 2 and a in title for a in aliases):
            return True
        if not place.get("isChar"):
            return any(a and a in title for a in aliases)
        t = re.sub(r"^(魏書|蜀書|吳書|吴書)·", "", title)
        t = re.sub(r"^《[^》]+》·", "", t)
        for a in aliases:
            if len(a) != 1 or not t.startswith(a):
                continue
            rest = t[1:]
            tails = CHAR_TITLE_TAIL.get(a, ())
            if any(rest.startswith(bad) for bad in tails):
                return False
            return True
        return False

    title_hit = {}
    for c in data["chapters"]:
        cid = c["id"]
        title = norm(c["title"])
        for place in places:
            if title_is_char_ok(place, title):
                title_hit.setdefault(place["id"], []).append(cid)

    # 单字地名的 dense 兜底：也须篇名起首认可，否则王莽傳/孔子世家凭裸字进整篇
    place_by_id = {p["id"]: p for p in places}
    filtered_dense = {}
    for pid, cmap in dense.items():
        pobj = place_by_id.get(pid)
        if not pobj or not pobj.get("isChar"):
            filtered_dense[pid] = cmap
            continue
        keep = {}
        for cid, n in cmap.items():
            if title_is_char_ok(pobj, norm(chapter_meta[cid]["title"])):
                keep[cid] = n
        if keep:
            filtered_dense[pid] = keep
    dense = filtered_dense

    main_by_place = {}
    all_ids = set(title_hit) | set(dense)
    for pid in all_ids:
        rows = []
        for cid in title_hit.get(pid, []):
            rows.append({"cid": cid, "n": chapter_place.get(cid, {}).get(pid, 0),
                         "byTitle": True})
        for cid, n in (dense.get(pid) or {}).items():
            if cid in title_hit.get(pid, ()):
                continue
            rows.append({"cid": cid, "n": n, "byTitle": False})
        rows.sort(key=lambda r: (not r["byTitle"], -r["n"], r["cid"]))
        main_by_place[pid] = rows

    place_out = []
    for place in places:
        pid = place["id"]
        item = dict(place)
        item["mentionCount"] = mention.get(pid, 0)
        item["mentionChapterCount"] = len(mention_chapter.get(pid, ()))
        item["byBook"] = {
            code: {
                "mentionCount": n,
                "mentionChapterCount": len(chapter_by_book.get(pid, {}).get(code, ())),
            }
            for code, n in sorted(mention_by_book.get(pid, {}).items())
        }
        item["mainChapters"] = main_by_place.get(pid, [])
        item["aliasList"] = build_alias_list(place, alias_stat.get(pid, {}),
                                             alias_by_book.get(pid, {}))
        item["kindLabel"] = KIND_LABEL.get(place["kind"], place["kind"])
        place_out.append(item)
    place_out.sort(key=lambda p: (-p["mentionCount"], p["name"]))

    chapters = data["chapters"]
    for c in chapters:
        c["topPlaces"] = chapter_top.get(c["id"], [])

    data["sentences"] = new_sentences
    data["places"] = place_out
    data["placeKinds"] = [{"key": k, "label": KIND_LABEL[k], "n": sum(
        1 for p in place_out if p["kind"] == k)} for k in KIND_ORDER
        if any(p["kind"] == k for p in place_out)]
    data["meta"]["placeCount"] = len(place_out)
    data["meta"]["placeMarkCount"] = core_marks + char_marks
    data["meta"]["placeCoreMarks"] = core_marks
    data["meta"]["placeCharMarks"] = char_marks
    data["meta"]["placeOnlySentences"] = place_only
    data["meta"]["sentenceCountWithPlaces"] = len(new_sentences)
    data["meta"]["placeGeneratedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 书清单里的地名条目数：人物层跑的时候地名还没标，只能在这里补
    for bmeta in data["meta"].get("books", []):
        bmeta["placeCount"] = sum(1 for p in place_out
                                  if p.get("byBook", {}).get(bmeta["code"]))

    # 异体字归一表带出去给前端：前端拿它把**用户输入**做一次同样的归一，
    # 于是「髙祖」「説苑」这类正文异体写法也能查到（词典只收了规范形）。
    # 表本身是 1:1 的，前端只用于「查询→规范形」这一步，不用于展示。
    # 注：这一行现在由 tradify() 统一负责（转繁与交出变体表是同一件事的两半），
    #     此处不再重复设置；仍单跑 tradify 也不会漏。
    # data["meta"]["variants"] = VARIANTS      ← 已移入 trad.py:tradify()

    # 显示层转繁。**必须放在这里**——本函数是 app-data.js / book-data.json 的最后
    # 一个写入口，且必须在所有按 name 排序、按 kind 取字典的操作之后（转繁只改观感，
    # 不改任何键）。tradify 每次都真转（不做短路），靠 to_trad 自身幂等收敛，
    # 因此重复运行不会把繁体再转坏一次。详见 pipeline/trad.py 的模块头。
    converted = tradify(data)

    write_json(os.path.join(INDEX, "book-data.json"), data)
    with open(os.path.join(WEB, "app-data.js"), "w", encoding="utf-8") as fh:
        fh.write("window.BOOK_DATA = ")
        fh.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        fh.write(";\n")

    zero = [p["name"] for p in place_out if p["mentionCount"] == 0]
    report = {
        "placeCount": len(place_out),
        "placeMarkCount": core_marks + char_marks,
        "coreMarks": core_marks,
        "charMarks": char_marks,
        "sentencesTotal": total_sentences,
        "sentencesKept": len(new_sentences),
        "sentencesAddedByPlace": place_only,
        "blockedByPerson": blocked_person.most_common(),
        "blockedByGuard": blocked_guard.most_common(),
        "blockedByBareOff": blocked_bare.most_common(),
        "blockedTrunc": blocked_trunc.most_common(20),
        "blockedByName": blocked_name.most_common(),
        "blockedTotal": (sum(blocked_person.values()) + sum(blocked_guard.values())
                         + sum(blocked_bare.values()) + sum(blocked_name.values())
                         + sum(blocked_trunc.values())),
        "zeroMention": zero,
        "script": data["meta"].get("script", "simp"),
        "tradifiedThisRun": converted,
        "topPlaces": [{"name": p["name"], "kind": p["kind"], "n": p["mentionCount"],
                       "chapters": p["mentionChapterCount"],
                       "main": len(p["mainChapters"])} for p in place_out[:40]],
        "sizes": {
            "book_data_kb": round(os.path.getsize(
                os.path.join(INDEX, "book-data.json")) / 1024, 1),
            "web_data_kb": round(os.path.getsize(
                os.path.join(WEB, "app-data.js")) / 1024, 1),
        },
    }
    write_json(os.path.join(PIPELINE, "_annotate_places_report.json"), report, indent=2)

    print("地名 {} / 标记 {}（具名 {} + 单字 {}）/ 句 {}（新增纯地名句 {}）".format(
        len(place_out), core_marks + char_marks, core_marks, char_marks,
        len(new_sentences), place_only))
    print("单字被挡：人名 {} / 姓名表 {} / 守卫 {} / 关闭裸匹 {}（合计 {}）".format(
        sum(blocked_person.values()), sum(blocked_name.values()),
        sum(blocked_guard.values()), sum(blocked_bare.values()),
        (sum(blocked_person.values()) + sum(blocked_name.values())
         + sum(blocked_guard.values()) + sum(blocked_bare.values()))))
    if blocked_name:
        print("  被人名表挡掉的 Top10：{}".format(
            "，".join("{}×{}".format(w, n) for w, n in blocked_name.most_common(10))))
    print("零命中地名 {} 个".format(len(zero)))


if __name__ == "__main__":
    main()
