# -*- coding: utf-8 -*-
"""人物召回：从"未被标注覆盖"的正文里捞出尚未入典的人物候选。

定位
----
build_dict.py 的 PERSONS 是人工维护的资产，越编越全但**必然有漏**。
resolve.py 查的是"已入典但消歧没做全"（泛称），它查不出"根本没入典"。
本脚本补的就是这一块：**只取证、不下判定**，产出一份滚动待办清单。

用法
----
    python extract_persons.py            # 打印报表 + 写 _persons_candidates.json
    python extract_persons.py --min 3    # 只报全文出现 >=3 次的候选

四类模式
--------
  A 国名+谥号+爵位   齊景公 晉悼公 楚靈王 燕昭王 …   全形，无歧义，价值最高
  B 汉初诸侯王       濟北王 常山王 膠東王 城陽頃王 …   同称多，需逐个核
  C 公子/王子/公孫+X  公子光 公子糾 公孫敖 …           专名，需排动词/虚词
  D 姓+名            曹咎 龍且 周殷 薛公 …             量最大，噪声也最大

每类都只保留"整串未被任何人名标记覆盖"的串——已经被识别出来的不算候选。
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

REPORT = os.path.join(common.PIPELINE, "_persons_candidates.txt")
JSONOUT = os.path.join(common.PIPELINE, "_persons_candidates.json")

# 春秋战国主要诸侯国（用于 A/B）
STATES = ("周", "魯", "齊", "晉", "秦", "楚", "宋", "衛", "陳", "蔡", "曹", "鄭",
          "燕", "吳", "越", "趙", "魏", "韓", "杞", "滕", "薛", "莒", "邾",
          "許", "虞", "虢", "息", "隨", "鄧", "巴", "蜀", "中山")
# 汉初封国（用于 B）
HAN_STATES = ("濟北", "常山", "膠東", "膠西", "濟南", "菑川", "淮陽", "汝南",
              "城陽", "河間", "中山", "長沙", "臨江", "廣陵", "琅邪", "瑯邪",
              "東牟", "衡山", "淮南", "廬江", "清河", "信都", "六安", "濟川")
POSTHUMOUS = ("孝悼惠文武功哀頃共敬桓景昭宣元平靜隱厲幽剌簡靈獻思靖節殤釐"
              "高光戴繆莊嚴閔湣懿出康定聲懷襄考成貞頃易殤胡剛頃")
PEER = "侯王君公"

GLUE_BEFORE = set("之其為而與使是今願故乃以若且亦必皆莫不無有將士民人主臣能欲請從辭令見聞知則於所")
# 公子X / 公孫X / 王子X 里 X 是这些字 → 动词/虚词，不是名
NOT_NAME = set("曰乃之也而為與不亦皆能可必多天先大妄威宗少就得從忘怪往來使請令見聞知欲辭讓是則於以所"
               "有無將士民人主臣子兄弟姊妹女男孫族黨國邑地土兵馬車甲金玉"
               "爭共各相自至立死生出入上下內外東西南北中前後左右"
               "年月日歲氏者矣乎哉邪耳焉諸百姓軍馬")

# D 类收尾闸门：以这些字结尾的串不是"姓名"
#   爵位字 → 归 A/B/C 管（景公=泛称、常山王=诸侯王）
#   官职字 → 是官不是人（中尉/尚書/大夫/將軍/太守/令尹/宗正/相國）
D_BAD_TAIL = set("侯王君公后")
D_BAD_TAIL2 = set("尉書夫軍守尹正相國史令牧卿監")
# "国名+爵位"里爵位前若无谥号，多半是泛称（晉君=晋国君主），不算专名
SURNAME_MIN = 2   # D 类：姓名至少出现次数

# D 类"是人"的语境：前一字表示"对某人做某事"，或后一字是谓语动词
NAME_PREV = set("、及與從使令拜封立遣誅殺攻擊破虜得執囚赦賜召問謂告語見用除免徙遷")
NAME_FOLLOW = set("曰為死奔反降走諫謀弒殺擊攻守相將戰亡立封拜使令從與及至入出"
                  "圍拔虜誅叛畔疾病卒薨諫说説怒喜恐亡歸奔降")

# 单姓（《史记》常见；不含复姓用字，避免把「司」「馬」当单姓）
SINGLE_SURNAMES = set(
    "姬姜嬴姒媯風羋曹龍灌酈靳欒卻郤狐先荀智范鮑隰晏崔慶陳田夷孟季叔仲孔顔閔"
    "冉宰端言卜商樊周呂吳孫龐樂蘇張甘嚴盧扁倉華薛毛藺廉趙魏韓李蒙王尉屠白"
    "蔡項彭黥英蕭任郟陸朱婁傅石竇衛霍金桑兒鄭汲甯郅杜楊義尹閻減溫咸主徐終"
    "樓翼會苦杞蒯莊申董路黃馮郭薄費曼牟滕闞成歐侯蓋段籍袁晁程漢將單軍紀濟"
    "澤隱陽間釋騎郡眭綰緱壯蕢摯樗鞠闌昭胡石沈許尤何施謝鄒喻柏卓章雲潘葛奚"
    "方俞柳酆唐岑雷賀倪殷羅畢郝鄔安常于時皮卞齊康伍余卜顧平和穆姚邵汪祁禹"
    "狄米貝臧計伏戴談宋茅熊舒屈祝梁阮藍席季麻強賈危江童梅盛刁鍾邱駱夏凌萬"
    "支柯昝管莫經房裘繆干解應宗丁賁鄧郁杭洪包左崔吉龔嵇邢滑裴榮翁羊惠甄芮"
    "儲邴糜松井段富烏焦巴弓牧隗山谷車宓全郗班仰秋宮仇暴厲戎祖符景詹束葉幸"
    "韶郜黎薊印宿懷蒲邰鄂索賴屠喬陰胥能蒼雙聞莘党翟譚貢勞逄扶堵雍璩桂濮牛"
    "壽通邊扈燕冀浦尚農別柴瞿充慕連茹習宦艾魚容向古易慎戈廖庾暨衡步都耿滿"
    "弘匡國文寇廣祿闕東歐殳沃利蔚越夔隆師鞏聶勾敖融冷辛那簡饒空曾毋沙養須"
    "豐巢關相查后荊紅游竺權逯益桓万俟聞司寇仉督車顓端巫漆良拓跋夾穀晉楚閆"
    "法汝鄢涂欽段百里郭南門呼延歸海羊舌微生岳帥緱亢況有琴丘商牟佘伯賞墨哈"
    "譙笪年愛佟第五言福甘武符劉景詹")
# 复姓（整条匹配，不拆字）
COMPOUND_SURNAMES = set((
    "公孫", "司馬", "歐陽", "上官", "夏侯", "東方", "西門", "淳于", "樗里",
    "尉遲", "澹臺", "端木", "公羊", "公儀", "公輸", "王子", "公叔", "公伯",
    "仲孫", "叔孫", "季孫", "南宮", "百里", "樂正", "公冶", "巫馬", "申屠",
    "主父", "鍾離", "宇文", "長孫", "慕容", "鮮于", "閭丘", "司徒", "司空",
    "子車", "顓孫", "公西", "漆雕", "壤駟", "公良", "宰父", "穀梁", "段干",
    "東郭", "南門", "呼延", "梁丘", "左丘", "東門", "太史", "中行", "成公",
))

RE_TAIL_WORD = re.compile(r"(功侯|功王|王子弟|王子孫)$")


def build_surnames(people):
    """姓氏表：既有词典里 3 字以上人名的首字/首二字（复姓）+ 常见单姓。

    注意：单姓表与复姓表必须分开——把复姓串逐字拆开会把「司、馬、上、官」
    这类字也当成单姓，D 类立刻被「司馬遷→司馬」这类噪声淹没。
    """
    su = set()
    for p in people["persons"]:
        t = p["tradName"]
        if len(t) >= 3:
            su.add(t[0])
            if t[:2] in COMPOUND_SURNAMES:
                su.add(t[:2])
    su |= set(SINGLE_SURNAMES)
    su |= COMPOUND_SURNAMES
    return su


def main():
    floor = 2
    if "--min" in sys.argv:
        floor = int(sys.argv[sys.argv.index("--min") + 1])

    data = common.load_json(os.path.join(common.INDEX, "book-data.json"))
    people = common.load_json(os.path.join(common.DICT, "people.json"))
    places = common.load_json(os.path.join(common.DICT, "places.json"))

    alias_set = set()
    for p in people["persons"]:
        alias_set.update(p["aliases"])
    place_set = set()
    for pl in places.get("places", []):
        for k in ("name", "tradName"):
            if pl.get(k):
                place_set.add(pl[k])
        place_set.update(pl.get("aliases", []))
    # 别名的最长 6 前缀集合，用于快速判断"x 是某别名的子串"
    surnames = build_surnames(people)

    sentences = data["sentences"]
    full_text = "\n".join(s["text"] for s in sentences)

    cats = {k: collections.Counter() for k in "ABCD"}
    samples = {}
    spans_total = 0

    A_re = re.compile("(?:%s)[%s]{1,2}[%s]" % (
        "|".join(sorted(STATES, key=len, reverse=True)), POSTHUMOUS, PEER))
    B_re = re.compile("(?:%s)[%s]{0,2}[%s]" % (
        "|".join(sorted(HAN_STATES, key=len, reverse=True)), POSTHUMOUS, PEER))
    C_re = re.compile(r"(?:公子|王子|公孫)[\u4e00-\u9fff]")
    TOKEN_re = re.compile(r"[\u4e00-\u9fff]{2,3}")

    def clean(x):
        if len(x) < 2:
            return False
        if x in alias_set or x in place_set:
            return False
        if RE_TAIL_WORD.search(x):
            return False
        for a in alias_set:
            if x in a:
                return False
        for a in place_set:
            if x in a:
                return False
        return True

    def is_name_like(x):
        """D 类判据：首字是姓（或首二字复姓），且末字不是功能字。"""
        if x[:2] in surnames:
            return True
        return x[0] in surnames

    for s in sentences:
        text = s["text"]
        n = len(text)
        mask = bytearray(n)
        for m in s.get("marks", []):
            for i in range(m["s"], min(m["e"], n)):
                mask[i] = 1
        cid = s["chapterId"]

        def uncovered(a, b):
            return all(mask[i] == 0 for i in range(a, b))

        for cat, rx in (("A", A_re), ("B", B_re), ("C", C_re)):
            for m in rx.finditer(text):
                x = m.group(0)
                a, b = m.start(), m.end()
                if not uncovered(a, b):
                    continue
                if a > 0 and text[a - 1] in GLUE_BEFORE:
                    continue
                if cat == "C" and x[-1] in NOT_NAME:
                    continue
                if not clean(x):
                    continue
                cats[cat][x] += 1
                samples.setdefault(x, (cat, cid, text))
        for m in TOKEN_re.finditer(text):
            x = m.group(0)
            a, b = m.start(), m.end()
            if x[-1] in NOT_NAME or x[-1] in D_BAD_TAIL or x[-1] in D_BAD_TAIL2:
                continue
            if not is_name_like(x):
                continue
            if not uncovered(a, b):
                continue
            if a > 0 and text[a - 1] in GLUE_BEFORE:
                continue
            if not clean(x):
                continue
            # 必须出现在"人"的语境里：前有使令封立…、或后接曰為死奔…
            prev = text[a - 1] if a > 0 else ""
            nxt = text[b] if b < n else ""
            nxt2 = text[b:b + 2]
            if not (prev in NAME_PREV or nxt in NAME_FOLLOW or nxt2 == "者，"):
                continue
            cats["D"][x] += 1
            samples.setdefault(x, ("D", cid, text))

    # 过滤 D：要求全文出现次数达标（挡掉一次性串）
    Drows = []
    for x, uc in cats["D"].items():
        fc = full_text.count(x)
        if fc >= SURNAME_MIN:
            Drows.append((fc, uc, x))

    lines = []
    lines.append("=" * 86)
    lines.append("人物召回候选（未被标注覆盖；只取证不下判定）")
    lines.append("别名 %d / 地名 %d / 姓氏表 %d" % (len(alias_set), len(place_set), len(surnames)))
    lines.append("=" * 86)

    def head(t):
        lines.append("")
        lines.append("### " + t)

    def block(cat, title, rows):
        head("%s  %s  —— %d 条" % (cat, title, len(rows)))
        for fc, uc, x in rows:
            c, cid, sent = samples.get(x, ("", "", ""))
            lines.append("  %4d %4d  %-10s %-8s | %s" % (fc, uc, x, cid, sent[:52]))

    def rows_of(cat, minfc=1):
        out = []
        for x, uc in cats[cat].items():
            out.append((full_text.count(x), uc, x))
        out = [r for r in out if r[0] >= minfc]
        out.sort(key=lambda r: (-r[0], -r[1], r[2]))
        return out

    block("A", "春秋战国 国名+谥号+爵位", rows_of("A"))
    block("B", "汉初诸侯王", rows_of("B"))
    block("C", "公子/王子/公孫 + 名", rows_of("C"))
    block("D", "姓+名（全文出现 >=%d 次）" % SURNAME_MIN, sorted(Drows, key=lambda r: (-r[0], -r[1], r[2])))

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    out = {}
    for cat in "ABCD":
        out[cat] = [{"text": x, "full": int(full_text.count(x)), "uncovered": int(uc)}
                    for x, uc in cats[cat].items()]
    out["D"] = [{"text": x, "full": fc, "uncovered": uc} for fc, uc, x in Drows]
    for cat in "ABCD":
        out[cat].sort(key=lambda d: (-d["full"], -d["uncovered"], d["text"]))
    common.write_json(JSONOUT, out, indent=1)

    print("A %d / B %d / C %d / D %d（>=%d次）" % (
        len(cats["A"]), len(cats["B"]), len(cats["C"]), len(Drows), SURNAME_MIN))
    print("报表:", REPORT)
    print("候选:", JSONOUT)


if __name__ == "__main__":
    main()
