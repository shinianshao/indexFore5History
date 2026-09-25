# -*- coding: utf-8 -*-
"""简 → 繁 转换层（**只改显示字段**，一个字都不参与匹配）。

为什么单独抽一层
----------------
语料（维基文库《史记》）本身是繁体，词典里参与匹配的字段（aliases、marks）
也早已是繁体；真正还是简体的只剩「显示用元数据」——人物/地名的正名、朝代、
称号、简介、篇目体例、书名，以及正文语料里的篇名与体例。这些字段只影响观感、
不参与匹配，所以集中在这里一次转干净，匹配层一个字都不动。

三条硬约束（全部是实测踩出来的，不是想出来的）
--------------------------------------------
1) **只能转一次，而这个「一次」不能靠标记来保证。** OpenCC 的 s2t 不是幂等的：
       「單于」→(一转)「單于」→(二转)「單於」     錯
       「十餘里」→(一转)「十餘里」→(二转)「十餘裏」 錯
   早先的做法是「在产物里打标 meta.script，第二次调用直接短路跳过」。**这是错的**：
   地名层每次运行都会用简体词典重建地名对象，整份产物虽已转过，这一部分仍是简体、
   必须再转一次——短路一开，地名类型标签就退回「国/朝代」（实测踩过）。
   正确做法：让 TRAD_FIXUPS 把那些会漂移的形态**收敛到同一个不动点**，
   于是 to_trad() 本身成为幂等函数，tradify() 每次直转即可。
   meta.script 只**记录**状态，不参与任何判断。
   这条不变量由一个全量守卫兜住：pipeline/check_trad.py 断言产物里每一条显示串
   都是 to_trad 的不动点。**别把幂等寄托在「整份产物已转过」的标记上。**

1b) **s2t 带短语规则，会「该转的不转」，且转出来的结果恰好是不动点。**
       「云阳宫」→「雲陽宮」（对）
       「秦有云阳宫」→「秦有云陽宮」（错！「有云」是词表里的引语短语，
                                     把「云→雲」挡掉了）
   这类错误**不动点检查抓不到**（错的形态再转一次还是它），所以只能显式登记：
   见 PHRASE_TRAPS，trad.py 自检与 check_trad.py 都会逐条断言。

2) **s2t 不懂「一简对多繁」的语义**，只会按词表猜。猜错的地方必须人工修回来：
       「夏后氏」→「夏後氏」（后＝君主，不是「後」）
       「同里」  →「同裏」  （里＝鄉里，不是「裏」）
       「范睢」  →「範睢」  （范是姓，不是「範」）
       「樗里子」→「樗裏子」
       「以筑击」→「以築擊」（筑＝樂器，不是「築」）
   这些进 TRAD_FIXUPS，转完再按长度降序修回去。

3) **人名/地名的正名不要用 s2t，直接用词典里已审定的 tradName。**
   s2t 猜不出「余善」该作「餘善」还是「余善」，也猜不出「范睢」不是「範睢」，
   但词典的 tradName 已经定过了——那是人工审定的结果，比词表可信。
   实测有 10 条两者不一致，全部以 tradName 为准：
       人名：启/微子启/刘启（啟 vs 啓）、姜子牙（→姜尚）、荀子（→荀卿）、
             范睢、樗里子、晁错（→鼂錯）
       地名：犍为（為 vs 爲）、荆山（荆 vs 荊）

不转的字段（有意为之）
----------------------
    aliases / aliasList[].w / sentences[].text / marks[].alias / genericAliases
    —— 前三个是匹配与检索的输入；genericAliases 的 alias 本来就取自语料
       （已是繁体），forms 里必须同时保留繁简两套供查找，转了反而查不到。

唯一的例外是 tradify() 顺带写出的 meta["variants"]：它不改任何文本，
只是把异体字表交给前端，好让用户输入简体时也能搜到繁体产物
（「转繁」和「交出变体表」是同一件事的两半，分开写就会漏）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import VARIANTS                               # noqa: E402
from opencc import OpenCC                                 # noqa: E402

_S2T = OpenCC("s2t")

# 转完之后逐条修正（繁体 → 繁体）。按**长度降序**替换，避免短串先命中把长串切碎。
TRAD_FIXUPS = [
    # —— 后（君主／皇后）不能转「後」——
    ("後稷", "后稷"), ("後羿", "后羿"), ("後土", "后土"),
    ("夏後", "夏后"), ("高後", "高后"), ("太後", "太后"), ("皇後", "皇后"),
    # —— 里（鄉里／里程）不能转「裏」——
    ("同裏", "同里"), ("鄰裏", "鄰里"), ("鄉裏", "鄉里"), ("餘裏", "餘里"),
    # —— 姓「范」不是「範」——
    ("範睢", "范睢"), ("範增", "范增"), ("範陽", "范陽"), ("範蠡", "范蠡"),
    ("範升", "范升"), ("種暠", "种暠"), ("範滂", "范滂"),
    ("範冉", "范冉"), ("範式", "范式"), ("包鹹", "包咸"),
    ("樗裏", "樗里"),
    # —— 啓／啟：异体收敛到正字 ——
    # s2t 把「启」猜成「啓」（异体），而词典正名与人名层规范形统一用「啟」（正字）。
    # 不修的话显示层会出现「夏后啓」（title）与「啟」（name）并存；
    # 且 check_trad 的「正名一致」检查会因此把 p_qi/p_weizi/p_hanjingdi
    # 三人当成笔误（它们本来要靠人工例外表豁免，加这条后例外表就该删掉三条）。
    # 注意：正文语料**不经** tradify，所以书里的「啓」照原样保留（原文照录）。
    ("啓", "啟"),
    # —— 筑＝樂器，不是「築」——
    ("以築擊", "以筑擊"), ("擊築", "擊筑"),
    # —— 音译地名 ——
    ("費爾幹納", "費爾干納"),
    # —— 爲／為：**OpenCC 选错了多数形** ——
    # s2t 把「为」转成「爲」，但本语料里「為」才是多数形：
    #     语料实测 為=5657 次、爲=2490 次；
    #     词典里唯一含该字的地名「犍為」用的也是「為」。
    # 不修的话，同一页里会出现「爲項羽所弒」和「犍為」两种写法（实测 42 : 1）。
    # 注意这**只影响显示**；匹配层的 VARIANTS 没有收 爲／為
    # （两者是同一个词，但收了也只能多救「犍為」一个条目，不值得动匹配）。
    ("爲", "為"),
    # —— 以下两条是为了让 to_trad **真正幂等**（OpenCC 的 s2t 对繁体输入会再猜一次）——
    #   「咸阳」一转得「咸陽」（对）；但拿「咸陽」再转，s2t 会把它当「咸→鹹」的简体，
    #   变成「鹹陽」（错）。同理「凤台」一转「鳳台」、二转「鳳臺」。
    #   加了这两条，两个形态都收敛到同一个不动点，于是重复调用不再改动文本。
    #   为什么必须幂等：annotate_places.py 每次运行都会**用简体词典重建地名对象**，
    #   所以即使整份产物已经转过，这一部分也必须再转一遍。见 tradify()。
    ("鹹陽", "咸陽"),
    ("鳳台", "鳳臺"),
    # —— OpenCC 短语规则挡住的转换（详见 PHRASE_TRAPS）——
    #   「有云」被 s2t 词表当成引语短语（「詩有云」），于是「秦有云阳宫」
    #   只转出「秦有云陽宮」，那个「云」永远不会自己变「雲」。
    ("云陽", "雲陽"),
    # —— 二次转换兜底：正常路径不会触发，一旦出现即说明被转了两次 ——
    ("單於", "單于"), ("淳於", "淳于"),
    # —— 姓「于」不是「於」——
    # s2t 把「于」一律猜成「於」，但《汉书》丞相于定国的「于」是姓。
    # 与「淳于」「單于」同类，只是这两个早在兜底表里，姓于的是汉书补人时才撞上。
    ("於定國", "于定國"), ("於曼倩", "于曼倩"),
]
TRAD_FIXUPS.sort(key=lambda kv: -len(kv[0]))

# 短语陷阱回归表：(简体输入, 期望繁体)。
#
# **不动点检查覆盖不到这一类错误**——「秦有云陽宮」既不是正确繁体、又恰好是
# to_trad 的不动点（再转一次还是它）。只有拿一个"已知正确答案"去比才发现得了。
# 所以这里把已知陷阱显式登记，trad.py 自检与 pipeline/check_trad.py 都逐条断言。
# 正例（本该保留原样、不许被转）也一并锁住，防止哪天修过头。
PHRASE_TRAPS = (
    # 反例：同一个词，单独出现时 s2t 是对的，跟在「有」后面就被短语规则挡住。
    # 这两条必须成对存在，否则「修好一个、改坏一个」不会被发现。
    ("秦有云阳宫", "秦有雲陽宮"),
    ("云阳宫", "雲陽宮"),
    # 正例：这些「云」「于」本来就该留着。
    ("云云", "云云"),                    # 山名「云云」，也是「如是说」
    ("古人云", "古人云"),                 # 引语，不能转「古人雲」
    ("单于", "單于"),                    # 匈奴單于，不是介词「於」
    ("淳于髡", "淳于髡"),                 # 复姓淳于
    # 篇名沿用源文写法：s2t 不会把「閒」转成「間」，也不该转。
    ("惠景间侯者年表", "惠景間侯者年表"),
    ("惠景閒侯者年表", "惠景閒侯者年表"),
)

# 显示层要转的文字字段（按实体分组）。**白名单**，不用通配。
PERSON_FIELDS = ("dynasty", "title", "summary")
PLACE_FIELDS = ("kindLabel", "era", "summary")
CHAPTER_FIELDS = ("book", "title", "fullTitle", "category")
# 正文语料（web/corpus-data.js）里的**元数据**字段。
# 段落正文 paragraphs **绝不转**——读全篇是逐字对照源文，正文就是源文本身。
# 这两个字段目前前端没读（篇名一律取 book-data 的 chapters），但留着半简半繁
# 的「史记·五帝本紀」就是颗地雷：谁哪天顺手拿来显示，简体就漏到页面上了。
CORPUS_FIELDS = ("fullTitle", "category")


def to_trad(text):
    """简体 → 繁体（显示用）。只应调用一次，见模块头约束 1。"""
    if not text:
        return text
    out = _S2T.convert(text)
    for wrong, right in TRAD_FIXUPS:
        if wrong in out:
            out = out.replace(wrong, right)
    return out


def tradify(data, marker="trad", corpus=None):
    """把产物里的显示字段就地转繁，并顺带导出检索层需要的异体字表。

    **总是转换，不做「已转过就跳过」的短路**——因为 annotate_places.py 每次运行
    都会用简体词典重建地名对象（place["kindLabel"] 等），即使整份产物早已是繁体，
    这一部分也必须是简体、必须再转一次。早先版本靠 meta.script 短路，
    结果单跑 `run_pipeline.py place` 会把地名类型标签退回「国/朝代」「县邑都城」。
    现在改为依赖 to_trad 自身的幂等性——这个前提由 `pipeline/check_trad.py` 全量守住
    （它断言产物里每条显示串都是 to_trad 的不动点，且 PHRASE_TRAPS 逐条成立）。

    顺带写 meta["variants"]：显示层一旦转成繁体，用户的简体输入就必须在前端
    归一回繁体才搜得到。「转繁」与「交出变体表」是同一件事的两半，放在一处
    就不会出现「转了繁却忘了导出表、简繁检索静默失效」。

    corpus 传入正文语料字典（{chapterId: {...}}）时，只转它的元数据字段
    （CORPUS_FIELDS）；paragraphs 是源文，一个字都不动。

    返回 True 表示本次确实做了转换；data["meta"]["script"] 记录当前脚本状态。
    """
    meta = data.setdefault("meta", {})
    already = meta.get("script") == marker
    meta["variants"] = VARIANTS

    for person in data.get("persons") or []:
        # 正名以词典审定的 tradName 为准；它同时是「繁体形」与「史記用名」
        person["name"] = person.get("tradName") or to_trad(person.get("name", ""))
        for key in PERSON_FIELDS:
            if person.get(key):
                person[key] = to_trad(person[key])

    for place in data.get("places") or []:
        place["name"] = place.get("tradName") or to_trad(place.get("name", ""))
        for key in PLACE_FIELDS:
            if place.get(key):
                place[key] = to_trad(place[key])

    for chapter in data.get("chapters") or []:
        for key in CHAPTER_FIELDS:
            if chapter.get(key):
                chapter[key] = to_trad(chapter[key])

    for kind in data.get("placeKinds") or []:
        if kind.get("label"):
            kind["label"] = to_trad(kind["label"])

    # 正文语料：只转元数据，paragraphs（源文）不动。
    for chapter_doc in (corpus or {}).values():
        for key in CORPUS_FIELDS:
            if chapter_doc.get(key):
                chapter_doc[key] = to_trad(chapter_doc[key])

    if meta.get("book"):
        meta["book"] = to_trad(meta["book"])

    meta["script"] = marker
    return not already


if __name__ == "__main__":
    # 自检一：修订表生效 + 幂等
    probe = "禹之子，继位为夏后。刘邦同里同日生，后叛降匈奴。代范睢为秦相。"
    once = to_trad(probe)
    again = to_trad(once)
    print("原文:", probe)
    print("一转:", once)
    print("二转:", again)
    assert "夏后" in once and "夏後" not in once, "夏后 修订失效"
    assert "同里" in once and "同裏" not in once, "同里 修订失效"
    assert "范睢" in once and "範睢" not in once, "范睢 修订失效"
    assert "爲" not in once and "為秦相" in once, "爲→為 修订失效"
    assert once == again, "to_trad 对本例应幂等"

    # 自检二：短语陷阱逐条回归（不动点检查抓不到的那一类）
    print("\n短语陷阱回归:")
    for simp, want in PHRASE_TRAPS:
        got = to_trad(simp)
        flag = "OK " if got == want else "FAIL"
        print("  [{}] {} -> {}  (期望 {})".format(flag, simp, got, want))
        assert got == want, "短语陷阱: {!r} 应为 {!r}，实得 {!r}".format(simp, want, got)
        assert to_trad(got) == got, "短语陷阱 {!r} 的结果不是不动点".format(simp)
    print("自检通过（{0} 条修订 + {1} 条短语陷阱；全量不动点由 check_trad.py 守）"
          .format(len(TRAD_FIXUPS), len(PHRASE_TRAPS)))
