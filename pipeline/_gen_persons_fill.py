# -*- coding: utf-8 -*-
"""从 extract_persons 候选生成批量入典计划。

目标：把各书**提及但未入典**的人物补进 PERSONS（不限有传者）。
- A/B/C 高置信全形（國+諡+爵 / 諸侯王 / 公子孫）
- D 仅收强人名形（姓+名，过滤官职/地名/虚词）
- 能在上下文挂到既有 pid 的合并为别名，不新建
- 按出现书分配 books（跨书并集）
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import common  # noqa: E402

CANDS = json.loads((ROOT / "pipeline" / "_persons_candidates.json").read_text(encoding="utf-8"))
PEOPLE = common.load_json(str(ROOT / "data" / "dict" / "people.json"))
CORPUS = ROOT / "data" / "corpus"

# 官职/地名/虚词黑名单（D 类误报主力）
OFFICE_OR_NOISE = set(
    "常侍散騎黃門司隸太僕司農都護主簿宗廟宗室印綬郡縣萬戶明堂"
    "有功有罪有子有若春秋戰國漢興周室唐虞諸呂黃巾烏桓烏丸車師車駕"
    "金吾左馮翊右扶風京兆河南江夏武昌吳興魏郡趙國齊國楚國燕國韓國"
    "王道天子天命大將軍左將軍右將軍前將軍後將軍偏將軍裨將軍牙門"
    "尚書令尚書僕中書監中書令給事黃門羽林虎賁期門僕射"
    "刺史太守郡守縣令縣長從事掾屬門下舍人學士博士弟子"
    "將軍校尉都尉中郎長史司馬司空司徒太尉太傅太保太常光祿"
    "大鴻臚宗正少府大司農執金吾將作大匠城門校尉北軍中候"
).split() if False else set()
# 上面 split 不适用中文；直接用子串黑名单
NOISE_SUBSTR = (
    "常侍", "散騎", "黃門", "司隸", "太僕", "司農", "都護", "主簿", "宗廟", "宗室",
    "印綬", "郡縣", "萬戶", "明堂", "有功", "有罪", "春秋", "戰國", "漢興", "周室",
    "唐虞", "諸呂", "黃巾", "烏桓", "烏丸", "車師", "車駕", "金吾", "馮翊", "扶風",
    "京兆", "河南尹", "江夏", "武昌", "吳興", "魏郡", "王道", "天子", "天命",
    "將軍", "校尉", "都尉", "中郎", "長史", "司馬", "司空", "司徒", "太尉", "太傅",
    "太保", "太常", "光祿", "鴻臚", "宗正", "少府", "執金", "將作", "城門",
    "刺史", "太守", "郡守", "縣令", "縣長", "從事", "掾屬", "門下", "舍人",
    "尚書", "中書", "給事", "羽林", "虎賁", "期門", "僕射", "博士", "弟子",
    "學士", "大夫", "議郎", "郎中", "謁者", "符節", "御史", "廷尉", "大理",
    "典屬", "典客", "奉常", "郎中令", "衛尉", "太僕", "少府", "中尉",
    "使持", "都督", "開府", "儀同", "散騎", "侍中", "中領", "護軍",
    "狀貌", "顏色", "容貌", "意氣", "志氣", "風骨", "神采", "舉動",
    "天地", "日月", "星辰", "風雨", "陰陽", "五行", "天下", "國家", "百姓",
    "將相", "公卿", "群臣", "百官", "有司", "州郡", "郡國", "州縣",
    "男子", "女子", "丈夫", "婦人", "父母", "兄弟", "妻子", "子孫",
    "將士", "吏民", "兵馬", "車騎", "舟船", "兵器", "甲兵", "糧食",
    "年月", "歲時", "春夏", "秋冬", "甲子", "乙丑", "建安", "延康", "黃初",
    "太和", "青龍", "景初", "正始", "嘉平", "正元", "甘露", "景元", "咸熙",
    "泰始", "咸寧", "太康", "永熙", "元康", "永康", "永寧", "太安", "永安",
    "建武", "永平", "建初", "元和", "章和", "永元", "元興", "延平", "永初",
    "元初", "永寧", "建光", "延光", "永建", "陽嘉", "永和", "漢安", "建康",
    "永憙", "本初", "建和", "和平", "元嘉", "永興", "永壽", "延熹", "永康",
    "建寧", "熹平", "光和", "中平", "初平", "興平", "建安",
    "一人", "二人", "三人", "數人", "眾人", "何人", "無人", "有人",
    "如此", "於是", "然後", "然則", "所以", "可以", "足以", "難以",
    "將軍", "明府", "府君", "使君", "先生", "夫子", "君子",
    # 截断官职/词组/书名/地名片段（2026 用户报，五书统一）
    "尚方", "國子", "金紫", "時人", "萬餘", "將萬", "能直", "何不", "先零",
    "左氏", "公羊", "穀梁", "毛詩", "流言", "直言", "國政", "相與", "終不",
    "於黎", "于黎", "黎丘", "黎陽", "黎阳",
)
# 形态闸：截断官职 / 列表缀 / 词组尾巴
DROP_NAME_RE = re.compile(
    r"^[^等]{1,4}太$"      # 東郡太（太守截断）
    r"|^[^等]{1,4}校$"     # 越騎校（校尉截断）
    r"|^[^等]{1,6}等$"     # 韓遂等
    r"|^[^等]{1,3}[傳詩書號稱騎級]$"
)
    "都督荊州司徒尚書將軍太守刺史丞相太尉侍中校尉長史大夫司空司馬"
    "太傅太保太常少府宗正博士議郎郎中謁者御史廷尉衛尉中尉奉常"
    "有功有罪春秋戰國天地日月國家天下百姓公卿群臣百官有司州郡"
    "男子女子丈夫婦人父母兄弟妻子子孫將士吏民兵馬車騎"
    "一人二人三人眾人何人無人有人如此於是然後然則所以可以"
    "明府府君使君先生夫子君子狀貌顏色容貌意氣志氣風骨神采"
    "建安黃初泰始咸寧太康元康永康建武永平建初元和永元永初"
    "散騎常侍中常侍黃門侍郎尚書令尚書僕射中書監中書令"
    "左馮翊右扶風京兆尹河南尹執金吾城門校尉北軍中候"
    "使持節都督開府儀同散騎侍中中領護軍"
)

D_BAD_TAIL = set("侯王君公后等號稱騎級傳詩書")
D_BAD_TAIL2 = set("尉書夫軍守尹正相國史令牧卿監")
NOT_NAME = set("曰乃之也而為與不亦皆能可必多天先大妄威宗少就得從忘怪往來使請令見聞知欲辭讓是則於以所有無將士民人主臣子兄弟姊妹女男孫族黨國邑地土兵馬車甲金玉爭共各相自至立死生出入上下內外東西南北中前後左右年月日歲氏者矣乎哉邪耳焉諸百姓軍馬")

SINGLE_SURNAMES = set(
    "姬姜嬴姒媯風羋曹龍灌酈靳欒卻郤狐先荀智范鮑隰晏崔慶陳田夷孟季叔仲孔顔閔"
    "冉宰端言卜商樊周呂吳孫龐樂蘇張甘嚴盧扁倉華薛毛藺廉趙魏韓李蒙王尉屠白"
    "蔡項彭黥英蕭任郟陸朱婁傅石竇衛霍金桑兒鄭汲甯郅杜楊義尹閻減溫咸主徐終"
    "樓翼會苦杞蒯莊申董路黃馮郭薄費曼牟滕闞成歐侯蓋段籍袁晁程漢將單軍紀濟"
    "澤隱陽間釋騎郡眭綰緱壯蕢摯樗鞠闌昭胡沈許尤何施謝鄒喻柏卓章雲潘葛奚"
    "方俞柳酆唐岑雷賀倪殷羅畢郝鄔安常于時皮卞齊康伍余卜顧平和穆姚邵汪祁禹"
    "狄米貝臧計伏戴談宋茅熊舒屈祝梁阮藍席季麻強賈危江童梅盛刁鍾邱駱夏凌萬"
    "支柯昝管莫經房裘繆干解應宗丁賁鄧郁杭洪包左崔吉龔嵇邢滑裴榮翁羊惠甄芮"
    "儲邴糜松井段富烏焦巴弓牧隗山谷車宓全郗班仰秋宮仇暴厲戎祖符景詹束葉幸"
    "韶郜黎薊印宿懷蒲邰鄂索賴屠喬陰胥能蒼雙聞莘党翟譚貢勞逄扶堵雍璩桂濮牛"
    "壽通邊扈燕冀浦尚農別柴瞿充慕連茹習宦艾魚容向古易慎戈廖庾暨衡步都耿滿"
    "弘匡國文寇廣祿闕東歐殳沃利蔚越夔隆師鞏聶勾敖融冷辛那簡饒空曾毋沙養須"
    "豐巢關相查后荊紅游竺權逯益桓法汝鄢涂欽段劉景"
)
COMPOUND_SURNAMES = set((
    "公孫", "司馬", "歐陽", "上官", "夏侯", "東方", "西門", "淳于", "樗里",
    "尉遲", "澹臺", "端木", "公羊", "公儀", "公輸", "王子", "公叔", "公伯",
    "仲孫", "叔孫", "季孫", "南宮", "百里", "樂正", "公冶", "巫馬", "申屠",
    "主父", "鍾離", "宇文", "長孫", "慕容", "鮮于", "閭丘", "司徒", "司空",
    "子車", "顓孫", "公西", "漆雕", "壤駟", "公良", "宰父", "穀梁", "段干",
    "東郭", "南門", "呼延", "梁丘", "左丘", "東門", "太史", "中行", "成公",
))


def is_person_name(x: str) -> bool:
    if len(x) < 2 or len(x) > 3:
        return False
    if x in NOISE_EXACT:
        return False
    if DROP_NAME_RE.match(x):
        return False
    for s in NOISE_SUBSTR:
        if s in x:
            return False
    if x[-1] in D_BAD_TAIL or x[-1] in D_BAD_TAIL2 or x[-1] in NOT_NAME:
        return False
    if x[:2] in COMPOUND_SURNAMES:
        return True
    return x[0] in SINGLE_SURNAMES


def load_corpus_hits(strings: list[str]) -> dict[str, dict]:
    """统计每个串出现在哪些书，并抓一句样例。用 book-data 扁平句层。"""
    want = set(strings)
    hits: dict[str, dict] = {
        s: {"books": set(), "count": 0, "sample": None} for s in want
    }
    if not want:
        return hits
    order = sorted(want, key=len, reverse=True)
    data = common.load_json(str(ROOT / "data" / "index" / "book-data.json"))
    for sent in data.get("sentences") or []:
        text = sent.get("text") or ""
        if not text:
            continue
        bid = (sent.get("chapterId") or "").split("-")[0]
        for s in order:
            if s in text:
                h = hits[s]
                h["books"].add(bid)
                h["count"] += text.count(s)
                if h["sample"] is None:
                    h["sample"] = (sent.get("chapterId"), text[:80])
    return hits


def main() -> None:
    existing_names = set()
    existing_aliases = set()
    existing_pids = set()
    for p in PEOPLE["persons"]:
        existing_pids.add(p["id"])
        existing_names.add(p.get("tradName") or "")
        existing_names.add(p.get("name") or "")
        existing_aliases.update(p.get("aliases") or [])
    existing_names.discard("")
    existing_aliases.discard("")

    plan_new = []
    plan_alias = []  # 挂到既有 pid

    def skip(s: str) -> bool:
        return (not s) or s in existing_names or s in existing_aliases

    # ---- A/B/C ----
    raw_abc = []
    for cat in "ABC":
        for item in CANDS[cat]:
            t = item["text"]
            if skip(t):
                continue
            raw_abc.append((cat, t, item.get("full", 0)))

    # ---- D 强人名 ----
    raw_d = []
    for item in CANDS["D"]:
        t = item["text"]
        if skip(t) or not is_person_name(t):
            continue
        if item.get("full", 0) < 3 or item.get("uncovered", 0) < 3:
            continue
        raw_d.append(("D", t, item.get("full", 0)))

    all_strings = sorted({t for _, t, _ in raw_abc + raw_d}, key=len, reverse=True)
    print(f"候选待查：ABC={len(raw_abc)} D={len(raw_d)} 去重串={len(all_strings)}")
    hits = load_corpus_hits(all_strings)

    # 合并启发：样例句里若紧跟着既有全名/别名，则把候选挂到该 pid
    alias_to_pid = {}
    for p in PEOPLE["persons"]:
        for a in [p.get("tradName"), p.get("name")] + list(p.get("aliases") or []):
            if a:
                alias_to_pid.setdefault(a, p["id"])

    used_pids = set(existing_pids)

    def make_pid(name: str) -> str:
        # 简单可读 slug：p_ + 去掉非汉字后的小写拼音占位（用 unicode 稳定 hash 后缀防撞）
        base = "p_x" + format(abs(hash(name)) % 100000, "05d")
        pid = base
        n = 2
        while pid in used_pids:
            pid = f"{base}_{n}"
            n += 1
        used_pids.add(pid)
        return pid

    book_map = {"sj": "sj", "hs": "hs", "hhs": "hhs", "sgz": "sgz", "js": "js"}
    dynasty_guess = {
        "sj": "先秦", "hs": "西汉", "hhs": "东汉", "sgz": "三国", "js": "晋",
    }

    for cat, t, full in raw_abc + raw_d:
        h = hits.get(t) or {"books": set(), "count": 0, "sample": None}
        books = sorted(b for b in h["books"] if b in book_map)
        if not books:
            continue
        sample = h["sample"][1] if h.get("sample") else ""
        # 合并：仅当样例呈「候选+名」且该名是既有全名/末字，才挂到既有 pid
        # 例：齊武閔王冏 → 司馬冏；禁止仅因同句出现他人就合并
        merged_pid = None
        for a, pid in alias_to_pid.items():
            if len(a) < 2 or a == t:
                continue
            # 「候选+全名」或「候选+末字」紧邻
            if t + a in sample or (len(a) >= 2 and t + a[-1] in sample and a.endswith(a[-1])):
                if t + a in sample:
                    merged_pid = pid
                    break
                # 候选+单字名（全名末字），且全名本身也在附近 20 字窗内
                idx = sample.find(t)
                if idx >= 0:
                    window = sample[max(0, idx - 20): idx + len(t) + 20]
                    if a in window and t + a[-1] in sample:
                        merged_pid = pid
                        break
        title = t if cat in "AB" else ""
        if cat == "C":
            title = t[:2]
        # 朝代：取首本书猜
        dyn = dynasty_guess.get(books[0], "未知")
        if cat in ("A", "B"):
            dyn = "先秦" if t[0] in "周魯齊晉秦楚宋衛陳蔡曹鄭燕吳越趙魏韓杞滕薛莒邾許虞虢息隨鄧巴蜀中山" else dyn
            if any(x in t for x in ("孝", "哀", "思", "頃", "繆", "厲", "夷", "閔", "釐", "釐")):
                dyn = "汉" if books[0] in ("hs", "hhs") else dyn

        if merged_pid and merged_pid in existing_pids:
            plan_alias.append({
                "pid": merged_pid, "form": t, "books": books, "cat": cat,
            })
        else:
            plan_new.append({
                "pid": make_pid(t),
                "name_simp": t,  # 繁体名先用原串（语料为繁）
                "name_trad": t,
                "dynasty": dyn,
                "title": title or "散见",
                "summary": f"各书提及人物（{cat}类召回），出现在 {','.join(books)}。",
                "aliases_trad": [t] if cat != "D" else [],
                "books": books,
                "cat": cat,
                "full": full,
            })

    out = {
        "new": plan_new,
        "alias": plan_alias,
        "stats": {
            "raw_abc": len(raw_abc),
            "raw_d": len(raw_d),
            "new": len(plan_new),
            "alias": len(plan_alias),
        },
    }
    dest = ROOT / "pipeline" / "_persons_fill_plan.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("stats:", out["stats"])
    print("plan:", dest)
    # 预览
    for r in plan_new[:15]:
        print(" NEW", r["pid"], r["name_trad"], r["books"], r["cat"])
    for r in plan_alias[:10]:
        print(" ALIAS", r["pid"], r["form"], r["books"])


if __name__ == "__main__":
    main()
