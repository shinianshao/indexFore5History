# -*- coding: utf-8 -*-
"""人名挖掘探针：单字地名的「后接字」里，哪些是「姓+名」（人名），哪些是地名读法。

要解决的实例：秦始皇本紀/項羽本紀里的「秦嘉」——秦是姓，却被单字地名规则
标成了秦国。根因是地名层只看「人名占用区间」，而人物词典只收了 388 位主角，
长尾人物（秦嘉、周市、魏冉、蔡澤…）不在表里，他们的姓氏就漏成了地名。

难点：两类字面完全一样，必须靠**结构**区分——
    秦昭（国+谥号，后必接王）    vs   周昌（姓+名）
    秦王、楚将、魏相（国+爵位）  vs   蔡澤、魏冉、宋義
    秦戰、秦破（地名作主语）      vs   秦嘉（姓+名，后接谓语）
    秦韓、燕齊（两地名并列）      vs   魏齊、周市（两姓名并列）

判据：
    [1] 后接字是爵位/职官/亲属/集体字        → 国+称号，地名
    [2] 后接字是谥号字，且其后紧跟爵位字      → 国+谥+爵，地名
    [3] 后接字是虚词/动词/方位/数量/地理通名   → 地名在句中作成分
    [4] 后接字本身就是另一个单字地名          → 地名并列
    [5] 后接字的再下一字是地理通名            → 地名（魏襄陵）
余下候选还须有「人名槽位证据」：紧前是强及物动词（擊/殺/遣/虜/并…）
或紧后是人物谓语（曰/為/亡/走/謀/弒…）。

注意：语料是繁体，字表按简体写，所以比较前一律 t2s 归一。
输出 pipeline/_name_candidates.json，并打印分层结果供人工判读。
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, CORPUS, norm, POSTHUMOUS_CHARS   # noqa: E402

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
except Exception:                       # 没有 opencc 就退化为原字
    _T2S = None

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_name_candidates.json")
_cache = {}


def simp(ch):
    """单字转简体（带缓存）。t2s 对单字是 1:1，不改变下标语义。"""
    if ch not in _cache:
        _cache[ch] = _T2S.convert(ch) if _T2S else ch
    return _cache[ch]


# [1] 爵位、职官、亲属、集体、朝廷 —— 接这些字说明前字是「国」，不是「姓」
RANK_CHARS = set(
    "王公君侯帝后皇天子男伯仲叔季相将军师人民众兵吏守令长"
    "母弟兄父妾女族氏主宗社稷室家朝廷国土大夫妃姬姜嬴姒"
    "太子太后大王天王天下丞相贵骑贾夷丞")

# [2] 先秦谥号用字：复用 common.py 的共享表（权威在那边），再补通假字
POSTHUMOUS = set(POSTHUMOUS_CHARS) | set("威易繆釐湣闵殇炀戴靖")
POSTHUMOUS = set(simp(c) for c in POSTHUMOUS)

# [3] 虚词、动词、方位、数量、时间 —— 地名在句中作成分
FUNC_CHARS = set(
    # 虚词、判断词、代词
    "之也者不必以而所时是为与及至自于因乃则皆已未无有可欲能得见闻知曰云"
    "矣焉耳乎哉夫盖唯惟苟且若故虽然遂诚既尝"
    # 动词（地名作主宾语）
    "战击破降称合虏卒急接平共救霸围攻侵败胜取予助守屯反叛畔服兴盛衰乱治"
    "附属怨怒恐惧畏惮疑亡存灭强弱缓畔入出来去归徙迁并兼会盟朝聘质释刺弑"
    # 方位、数量、时间
    "上下东西南北中内外前后左右大小多少一二三四五六七八九十百千万年月日"
    "春夏秋冬初始终先后今昔新旧远近高深"
)
FUNC_CHARS = set(simp(c) for c in FUNC_CHARS)

# [3b] 地理通名后缀 —— 接这些字是地名而非人名
GEO_SUFFIX = set(
    "州陵郡县邑城丘亭台山木水川泽湖海江河池泉谷原滨汭阴阳边郊鄙塞关津"
    "彭岐丰镐郢宛道市乡里聚落")
GEO_SUFFIX = set(simp(c) for c in GEO_SUFFIX)

# 人名槽位：紧前是**强及物动词**——后接的宾语只能是人。
# 刻意不收 與/從/及/為/使/令/謂/告/見/聞/怨/畏：
#   「與秦會」（介词）、「使秦」（出使秦国）、「聞秦」（听说秦国）都是地名读法，
#   把它们算作人名证据会让「秦會」「秦使」这类地名读法混进人名表。
VERB_BEFORE = set(
    "击破杀立遣拜封虏并降逐戮诛说谏让迎送囚免赦任举用害辱禽执射伤败围距拒"
    "逆叛畔获质释刺弑憎敬罢废迁赐遗献赂赠报谢责禽诛禽")
VERB_BEFORE = set(simp(c) for c in VERB_BEFORE)

# 人名槽位：紧后是人物谓语（只有人才会「曰/亡/走/謀/弒」）
PRED_AFTER = set("曰为等之已乃亦皆卒死亡走奔降反叛相见知说谏让谋从事惧怒恐喜怨病遁逃诛杀弒畔")
PRED_AFTER = set(simp(c) for c in PRED_AFTER)


def main():
    data = load_json(os.path.join(HERE, "..", "data", "index", "book-data.json"))
    char_places = [p["name"] for p in data["places"] if p.get("isChar")]
    char_set = set(simp(c) for c in char_places)

    known = set()               # 词典里的地名写法（简体，用于排除秦國/陳留这类）
    for p in data["places"]:
        known.update(simp(norm(a)) for a in p["aliases"])
        for a in p.get("aliasList", []):
            known.add(simp(norm(a["w"])))

    # 已在人物词典里的（曹參/周勃/商鞅…）由「人名占用区间」那道闸门负责，
    # 不必也不该再进人名阻断表，否则两处规则重叠、以后改一处漏一处。
    person_forms = set()
    for p in data["persons"]:
        person_forms.update(simp(norm(a)) for a in (p.get("aliases") or []))
        for a in p.get("aliasList", []):
            person_forms.add(simp(norm(a["w"])))

    texts = []
    for path in sorted(glob.glob(os.path.join(CORPUS, "sj-*.json"))):
        doc = load_json(path)
        for para in doc["paragraphs"]:
            for s in para["sentences"]:
                texts.append((doc["chapterId"], norm(s["text"])))

    PUNCT = set("，。、；：！？「」『』（）《》〈〉—…·　 ")
    pair = Counter()
    ev_before = Counter()          # 前接强及物动词的次数
    ev_after = Counter()           # 后接人物谓语的次数
    killed = defaultdict(Counter)
    ctx = defaultdict(list)

    for cid, t in texts:
        for i, ch in enumerate(t):
            if ch not in char_set or i + 1 >= len(t):
                continue
            nx_raw = t[i + 1]
            if nx_raw in PUNCT:
                continue
            nx = simp(nx_raw)
            two = ch + nx
            if two in known:            # 已是词典里的地名写法
                continue
            if two in person_forms:     # 已是人物词典里的写法，另有闸门负责
                continue
            pair[two] += 1
            if len(ctx[two]) < 4:
                ctx[two].append((cid, t[max(0, i - 10):i + 12]))

            nx2 = simp(t[i + 2]) if i + 2 < len(t) else ""
            if nx in RANK_CHARS:
                killed["爵位职官"][two] += 1
                continue
            if nx in POSTHUMOUS and nx2 in RANK_CHARS:
                killed["国+谥+爵"][two] += 1
                continue
            if nx in FUNC_CHARS:
                killed["虚词动词"][two] += 1
                continue
            if nx in GEO_SUFFIX:
                killed["地理通名"][two] += 1
                continue
            if nx in char_set:
                killed["地名并列"][two] += 1
                continue
            if nx2 in GEO_SUFFIX or nx2 in char_set:
                killed["双字地名"][two] += 1
                continue
            prev = simp(t[i - 1]) if i > 0 else ""
            if prev in VERB_BEFORE:
                ev_before[two] += 1
            if nx2 in PRED_AFTER:
                ev_after[two] += 1

    cands = []
    for two, n in pair.items():
        if ev_before[two] + ev_after[two] == 0:
            continue
        cands.append({"w": two, "n": n,
                      "before": ev_before[two], "after": ev_after[two],
                      "ctx": [c[1] for c in ctx[two][:2]]})
    cands.sort(key=lambda r: (-(r["before"] + r["after"]), -r["n"]))

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"candidates": cands, "charPlaces": char_places}, fh,
                  ensure_ascii=False, indent=1)

    print("单字地名 %d 个；候选 2 字串 %d 个；含人名槽位证据 %d 个" %
          (len(char_places), len(pair), len(cands)))
    print("各判据挡掉的串数：" +
          "，".join("%s %d" % (k, len(v)) for k, v in killed.items()))
    print("输出：" + OUT)

    for lo, hi, tag in ((2, 99, "甲 证据≥2（自动收）"),
                        (1, 1, "乙 证据=1（待人工判读）")):
        rows = [r for r in cands if lo <= r["before"] + r["after"] <= hi]
        print()
        print("=== %s：%d 个 ===" % (tag, len(rows)))
        for r in rows[:80]:
            print("  %-4s 前%-3d 后%-3d 总%-4d | %s" %
                  (r["w"], r["before"], r["after"], r["n"],
                   " ¦ ".join(r["ctx"])))


if __name__ == "__main__":
    main()
