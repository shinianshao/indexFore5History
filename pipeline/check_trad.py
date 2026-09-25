# -*- coding: utf-8 -*-
"""字面层守卫：断言产物与界面都停在**正确的不动点**上。

为什么必须单有一个守卫
----------------------
tradify() 已经改成「每次都真转、不做短路」，前提是 to_trad 本身幂等。
这个前提一旦被破坏（比如往 TRAD_FIXUPS 里加了一条与 s2t 互相打架的规则），
产物就会在两个形态之间来回跳、每跑一次变一次，而且**毫无症状**——
页面照样打开，只是字悄悄变了。本脚本把这个前提变成可执行的断言。

六组断言（任一不过 → 退出码 1，run_pipeline.py 会据此中断）
    A 不动点     每条显示串 to_trad(s) == s
    B 幂等       to_trad(s) == to_trad(to_trad(s))（「每次真转」的前提）
    C 正名一致    产物侧 name == tradName；词典侧 tradName == to_trad(name)
                  （人工审定的例外登记在 TRADNAME_EXCEPTIONS，且不许陈旧）
    D 元信息      meta.script == "trad" 且 meta.variants 非空
    E 短语陷阱    trad.PHRASE_TRAPS 逐条成立
    F 界面        index.html 标 zh-Hant；界面源码无残留简体文案、无修订表左值
    G 正文语料    corpus-data.js 的篇名/体例也是不动点（paragraphs 是源文，不查）

**A 与 E 不可互相替代**：A 只证明「已经稳定」，证明不了「是对的」。
OpenCC 的短语规则会产出「既错、又稳定」的形态（「秦有云陽宮」——
「有云」被当成引语短语，把「云→雲」挡掉了），只有 E 兜得住。
同源的实证：pl_jingshan 的繁体名一度误写成「荆山」，A 抓到了它（语料里
「荊」148 次对「荆」8 次，VARIANTS 也把「荆」归到「荊」）——但那是因为
tradName 恰好短到一眼可见；短语类错误没有这个运气。

**G 的必要性**：corpus-data.js 里的 fullTitle 曾经是半简半繁的
「史记·五帝本紀」——因为人物层写自己产物时忘了把正文语料的元数据一起转。
正文（paragraphs）**必须**保持源文原样，所以这一路只查元数据字段。

（app-data.js 不单独查：它与 book-data.json 由同一段代码、同一份 data 写出，
内容恒等；查 book-data.json 即可。）

用法：
    python check_trad.py              数据 + 界面
    python check_trad.py --data-only  只查数据产物
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import DICT, INDEX, WEB, load_json                   # noqa: E402
from trad import (CHAPTER_FIELDS, CORPUS_FIELDS, PERSON_FIELDS,   # noqa: E402
                  PLACE_FIELDS, PHRASE_TRAPS, TRAD_FIXUPS, to_trad)

DATA = os.path.join(INDEX, "book-data.json")
UI_HTML = os.path.join(WEB, "index.html")
UI_JS = os.path.join(WEB, "app.js")
CORPUS_JS = os.path.join(WEB, "corpus-data.js")
DICT_PEOPLE = os.path.join(DICT, "people.json")
DICT_PLACES = os.path.join(DICT, "places.json")

# tradName 允许与 to_trad(name) 不同的**人工审定例外**。
# 只有三种情形能进这张表，且必须写明理由：
#   ① s2t 猜错字形（启→啓），以史記原文写法为准；
#   ② 该实体在史記里不以本名出现，正名取史記用名（姜尚、荀卿）；
#   ③ 异体字：s2t 只会收敛到其中一形（钟→鍾），而语料写的是另一形
#      （鐘/卹/沖/鑒/説/勛）。这类**必须**以语料写法为正名，否则显示串
#      与正文对不上。批量补人时每遇一个就登记一条，别图省事改语料。
# 除这三类之外，tradName 与 to_trad(name) 不一致就是**笔误**，一律拦下。
TRADNAME_EXCEPTIONS = {
    # ⚠️ p_qi / p_weizi / p_hanjingdi 三条已删除：加了 TRAD_FIXUPS 的
    #    ("啓","啟") 之后，to_trad("启") 自己就能收敛到「啟」，
    #    不再需要人工豁免（这正是那条修订要解决的问题）。
    "p_jiangshang": "史記用名「姜尚」，非字面转写",
    "p_xunzi": "史記用名「荀卿」，非字面转写",
    #   ② 「鼂錯」不在例外表里：VARIANTS 收的是**匹配层**的鼂→晁，
    #      显示层的 tradName 仍是史記写的「鼂錯」（与篇名〈袁盎鼂錯列傳〉一致），
    #      to_trad("晁错") 得不到「鼂錯」，所以这条豁免必须留着。
    "p_chaocuo": "史記作「鼂錯」，s2t 会保留「晁」",
    # ③ 异体字（类传/附传批量补人时登记，均以语料写法为准）
    "p_x72805": "慕容鐘：语料作「鐘」，s2t(钟) 只给「鍾」",
    "p_x67108": "曹卹：仲尼弟子，语料作「卹」，s2t(恤) 不回「卹」",
    "p_x77449": "朱沖：语料作「沖」，s2t(冲) 收敛到「衝」",
    "p_x29127": "石鑒：语料作「鑒」，s2t(鉴) 收敛到「鑑」",
    "p_x52961": "羊鑒：语料作「鑒」，s2t(鉴) 收敛到「鑑」",
    "p_x93818": "郗鑒：语料作「鑒」，s2t(鉴) 收敛到「鑑」",
    "p_x41026": "鄭沖：语料作「沖」，s2t(冲) 收敛到「衝」",
    "p_x70177": "韓説：语料作「説」，s2t(说) 不再回「説」",
    "p_x54664": "鮑勛：语料作「勛」，s2t(勋) 收敛到「勳」",
}

# 界面源码里**绝不该再出现**的简体文案（每条都是本项目历史上出现过的界面原文）。
# 只列"长词"，不列单字——单字必误报：app.js 的 PLACE_KIND_ORDER 故意保留简体
# 数据键（国/郡/县…），那是数据契约，不是文案。
SIMP_UI_WORDS = ("检索", "篇目一览", "显示全部", "单字地名", "邻字", "称号",
                 "虚线下划线", "没有以该地为主体")

FAILS = []
NOTES = []


def fail(msg):
    FAILS.append(msg)


def note(msg):
    NOTES.append(msg)


def display_strings(data):
    """按 tradify 的白名单收集显示串，返回 [(来源, 值), ...]。

    白名单**直接从 trad.py 导入**，不在本文件另抄一份——抄一份就会漂移，
    守卫与被测对象一旦不同源，守卫就失去意义。
    """
    out = []
    for p in data.get("persons") or []:
        out.append(("person.name[{}]".format(p.get("id")), p.get("name") or ""))
        for key in PERSON_FIELDS:
            if p.get(key):
                out.append(("person.{}[{}]".format(key, p.get("id")), p[key]))
    for p in data.get("places") or []:
        out.append(("place.name[{}]".format(p.get("id")), p.get("name") or ""))
        for key in PLACE_FIELDS:
            if p.get(key):
                out.append(("place.{}[{}]".format(key, p.get("id")), p[key]))
    for c in data.get("chapters") or []:
        for key in CHAPTER_FIELDS:
            if c.get(key):
                out.append(("chapter.{}[{}]".format(key, c.get("id")), c[key]))
    for k in data.get("placeKinds") or []:
        if k.get("label"):
            out.append(("placeKinds.label", k["label"]))
    if (data.get("meta") or {}).get("book"):
        out.append(("meta.book", data["meta"]["book"]))
    return [(src, v) for src, v in out if v]


def check_strings(strings):
    """A 不动点 + B 幂等。"""
    not_fixed, not_idem = [], []
    for src, val in strings:
        conv = to_trad(val)
        if conv != val:
            not_fixed.append((src, val, conv))
        if to_trad(conv) != conv:
            not_idem.append((src, val, conv, to_trad(conv)))
    if not_fixed:
        fail("A 不动点: {} 条显示串不是 to_trad 的不动点（未转干净 / 含需修订的错形）"
             .format(len(not_fixed)))
        for src, val, conv in not_fixed[:12]:
            FAILS.append("    {}: {!r} → 应为 {!r}".format(src, val, conv))
    if not_idem:
        fail("B 幂等: {} 条显示串转两次还会变（转换函数本身在发散）".format(len(not_idem)))
        for src, val, conv, twice in not_idem[:12]:
            FAILS.append("    {}: {!r} → 一次 {!r} → 两次 {!r}"
                         .format(src, val, conv, twice))


def check_names(data):
    """C 正名一致，两层都要查：

    产物侧 —— 显示名必须**就是**词典审定的 tradName（不得绕过审定值另转一次）；
    词典侧 —— tradName 必须与自动转写一致，除非登记在 TRADNAME_EXCEPTIONS 里。

    词典侧才是真正抓笔误的那一层：产物里的 name 已经被 tradify 换成了 tradName，
    只查产物等于自己跟自己比（恒真）。实证：pl_jingshan 的繁体名曾误写成「荆山」，
    就是词典侧对比 to_trad("荆山") = "荊山" 才暴露出来的。
    """
    for group, tag in (("persons", "person"), ("places", "place")):
        for p in data.get(group) or []:
            trad = p.get("tradName")
            if trad and p.get("name") != trad:
                fail("C 正名一致: 产物 {}.{} 的显示名 {!r} 不是词典审定的 {!r}"
                     .format(tag, p.get("id"), p.get("name"), trad))

    known = set()
    for path, key in ((DICT_PEOPLE, "persons"), (DICT_PLACES, "places")):
        if not os.path.exists(path):
            note("C 正名一致: 找不到 {}，跳过词典侧核对".format(os.path.basename(path)))
            continue
        for p in (load_json(path) or {}).get(key) or []:
            pid, trad = p.get("id"), p.get("tradName")
            if not trad:
                continue
            want = to_trad(p.get("name") or "")
            if want == trad:
                continue
            if pid in TRADNAME_EXCEPTIONS:
                known.add(pid)
                continue
            fail("C 正名一致（词典）: {} 的正名 {!r} 与自动转写 {!r} 不符，"
                 "且不在例外表里（多半是笔误）".format(pid, trad, want))
    for pid in sorted(set(TRADNAME_EXCEPTIONS) - known):
        fail("C 正名一致: 例外表里的 {} 已不再需要对账（词典已改？），请删掉该条"
             .format(pid))


def check_meta(data):
    """D 元信息：脚本标记 + 变体表。"""
    meta = data.get("meta") or {}
    if meta.get("script") != "trad":
        fail("D 元信息: meta.script = {!r}，应为 'trad'（字面层没跑，或跑在写盘之后）"
             .format(meta.get("script")))
    variants = meta.get("variants")
    if not isinstance(variants, dict) or not variants:
        fail("D 元信息: meta.variants 缺失或为空——前端拿不到变体表，"
             "用户输入简体就搜不到繁体产物")
    else:
        note("meta.variants: {} 对异体字".format(len(variants)))


def check_phrase_traps():
    """E 短语陷阱：不动点检查抓不到的那一类，只能靠显式回归表。"""
    for simp, want in PHRASE_TRAPS:
        got = to_trad(simp)
        if got != want:
            fail("E 短语陷阱: {!r} 应为 {!r}，实得 {!r}".format(simp, want, got))
        elif to_trad(got) != got:
            fail("E 短语陷阱: {!r} 的结果 {!r} 不是不动点".format(simp, got))


def check_ui():
    """F 界面：语言标记 + 无残留简体文案 + 无修订表左值。

    界面（app.js / index.html）**不在 tradify 的白名单里**——它是源码，不是数据，
    当初由一次性脚本转过再手工编辑。所以这一层最容易漏：
    实测界面文案里曾留着 8 个「爲」（应为「為」），正是靠这里发现的。

    为什么不查 `VARIANTS` 的键：界面里**故意**会写变体形作例子
    （「河『內』寫作『内』」「『荊軻』寫作『荆軻』」），查了必误报。
    而 TRAD_FIXUPS 左值（爲／鹹陽／單於／同裏／範睢…）在界面文案里全是错的，
    不存在正当用法——所以只查这一组。
    """
    if not os.path.exists(UI_HTML):
        note("F 界面: 找不到 {}，跳过".format(UI_HTML))
        return
    html = open(UI_HTML, encoding="utf-8").read()
    if 'lang="zh-Hant"' not in html:
        fail("F 界面: index.html 没有 lang=\"zh-Hant\"")
    if "古籍檢索" not in html:
        fail("F 界面: index.html 里找不到繁体标题「古籍檢索」")
    for path in (UI_HTML, UI_JS):
        if not os.path.exists(path):
            continue
        name = os.path.basename(path)
        text = open(path, encoding="utf-8").read()
        for word in SIMP_UI_WORDS:
            if word in text:
                fail("F 界面: {} 里还有简体文案 {!r}".format(name, word))
        for wrong, right in TRAD_FIXUPS:
            if wrong in text:
                fail("F 界面: {} 里出现了应修订的写法 {!r}（应为 {!r}）"
                     .format(name, wrong, right))


def load_js_var(path, var):
    """拆出 web/*.js 里的 `window.VAR = {...};` 并解析（仅供守卫使用）。"""
    text = open(path, encoding="utf-8").read()
    prefix = "window." + var + " = "
    if not text.startswith(prefix):
        return None
    body = text[len(prefix):].strip()
    if body.endswith(";"):
        body = body[:-1]
    return json.loads(body)


def check_corpus():
    """G 正文语料：元数据字段必须是繁体不动点（paragraphs 是源文，不查）。"""
    if not os.path.exists(CORPUS_JS):
        note("G 正文语料: 找不到 {}，跳过".format(CORPUS_JS))
        return
    corpus = load_js_var(CORPUS_JS, "BOOK_CORPUS")
    if corpus is None:
        fail("G 正文语料: corpus-data.js 结构不认识（应为 window.BOOK_CORPUS = {...};）")
        return
    bad = []
    for cid, chap in corpus.items():
        for key in CORPUS_FIELDS:
            val = chap.get(key)
            if val and to_trad(val) != val:
                bad.append((cid, key, val, to_trad(val)))
    if bad:
        fail("G 正文语料: {} 处元数据不是不动点（正文 paragraphs 不在此列）".format(len(bad)))
        for cid, key, val, want in bad[:8]:
            FAILS.append("    {}.{}: {!r} → 应为 {!r}".format(cid, key, val, want))
    else:
        note("G 正文语料: {} 篇元数据均为不动点".format(len(corpus)))


def main():
    data_only = "--data-only" in sys.argv
    if not os.path.exists(DATA):
        print("找不到 {}，请先跑 annotate.py / annotate_places.py".format(DATA))
        return 1
    data = load_json(DATA)

    strings = display_strings(data)
    check_strings(strings)
    check_names(data)
    check_meta(data)
    check_phrase_traps()
    if not data_only:
        check_ui()
        check_corpus()

    print("字面层守卫：显示串 {} 条（人物 {} / 地名 {} / 篇目 {}）".format(
        len(strings), len(data.get("persons") or []),
        len(data.get("places") or []), len(data.get("chapters") or [])))
    for msg in NOTES:
        print("  · " + msg)
    if FAILS:
        print("\n不通过 {} 项：".format(len(FAILS)))
        for msg in FAILS:
            print("  ✗ " + msg)
        return 1
    print("  ✓ A 不动点 / B 幂等 / C 正名一致 / D 元信息 / E 短语陷阱{}"
          .format(" / F 界面 / G 正文语料" if not data_only else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
