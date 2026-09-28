# -*- coding: utf-8 -*-
"""从原始 HTML 提取正文，切分为 篇 -> 段 -> 句，输出结构化语料。

维基文库的页面里混着两类内容，必须分开处理：
  1. **正文散文**：在 <p> / <dd> / <li> 里（本纪、世家、列传都属此类）
  2. **正文表格**：在 <table class="wikitable"> / class="dynlayout-exempt" 里
     （「十表」整篇都是表格，只抽 <p> 会得到近乎空篇）
同时要剔除导航与版权模板：<table class="ws-header">（上一篇/下一篇）、
<table class="ws-footer">（授权信息）、<style>、HTML 注释。

产物：data/corpus/sj-008.json
用法：python build.py
"""
import glob
import html as html_mod
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import books_sorted, slug_number, volume_sort_key   # noqa: E402
from tag_uids import stable_uid                                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CORPUS = os.path.join(ROOT, "data", "corpus")
DICT = os.path.join(ROOT, "data", "dict")

BOOK = "史记"
BOOK_CODE = "sj"

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
STYLE_RE = re.compile(r"<(style|script)\b.*?</\1>", re.S | re.I)
OPEN_TABLE_RE = re.compile(r"<table\b[^>]*>", re.I)
CLOSE_TABLE_RE = re.compile(r"</table\s*>", re.I)
TABLE_CLASS_RE = re.compile(r'class="([^"]*)"', re.I)
PROSE_BLOCK_RE = re.compile(r"<(p|dd|li)\b[^>]*>(.*?)</\1\s*>", re.S | re.I)
CELL_RE = re.compile(r"<(td|th)\b[^>]*>(.*?)</\1\s*>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
FOOTNOTE_RE = re.compile(r"\[\d+\]")
# ---- 校改标记 / 校勘记 / 维基链接（后汉书独有，用户拍板：保留但隔离统计）----
# 校改 `*(x)**[y]*`＝原文 x、校改 y；`*[z]*`＝补字 z；`*(x)*`＝衍字 x（删）。
# 括号有 [ ] 与 〔 〕 两种（维基渲染不统一）。`*` 是排版符号，插在词中会打断匹配
# （「屯*[田]*函谷關」），故：校改→取 y、补字→取 y、衍字→删。用户要「校勘保留」
# 保留的是校勘记「按：」段（见 split_body_note()），不是这些排版符号。
CORRECTION_RE = re.compile(r"\*\([^)]*\)\*\*[\[〔]([^\]〕]*)[\]〕]\*")
INSERT_RE = re.compile(r"\*[\[〔]([^\]〕]*)[\]〕]\*")
DELETE_RE = re.compile(r"\*\([^)]*\)\*")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
# 补字半截残留：〔延平〕/[延平]（非脚注数字）→ 取内容；脚注 [一] 是数字，排除在括号集外。
STRAY_BRACKET_RE = re.compile(r"[\[〔]([^\]〕一二三四五六七八九十百0-9０-９]+)[\]〕]")
# 校勘记「按：」：点校本编辑附记，形如「…厥中惟虛按：汲本、殿本…」。保留阅读、
# 但不参与切句统计（切句只切「按：」之前）。
NOTE_AN_RE = re.compile(r"按[：:]")
# 纯校勘记段（无「按：」）：段首是页行号（「三二一六頁七行…據…改」）
NOTE_PAGE_RE = re.compile(r"^[一二三四五六七八九十百〇○0-9０-９]+頁")
# 校勘/版本对照（可无「按：」）：據汲本改、殿本正文作、校補引、^36.036.1據…
NOTE_COLLAB_RE = re.compile(
    r"(?:按[：:]|據(?:汲本|殿本|局本|監本|閩本|官本|校補|校勘)|校補引|殿本正文作|汲本.{0,8}作"
    r"|集解引|臣昭曰|臣賢曰|賢按|昭按)"
)
# 维基链接 [[目标|显示]] → 显示；{{}} 模板残块 → 去花括号。
WIKI_LINK_RE = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
TEMPLATE_RE = re.compile(r"\{\{|\}\}")
# 维基文库的正文里把「三家注」（集解/索隱/正義）与校勘夹注写在 〈…〉 内。
# 不清掉的话，页面上展示的「原句」会是注释而不是正文——
# 例如卷027《天官書》正文仅约五千字，夹注使其膨胀到三万四千余字。
# 长度上限须放宽：史记/汉书的三家注多短，600 字够；但后汉书的刘昭注/李贤注
# 常整段引证（长逾千字），600 字上限会漏剥，实测残留 85 处「〈」（史记仅 1 处）。
# 放宽到 50000 字仍要求 `〉` 配对，无配对的开括号不会误吃正文。
ANGLE_NOTE_RE = re.compile(r"〈[^〈〉]{0,50000}〉")

# ---- 跨段注文（block 内配不上对的那一类）----------------------------------
# 注文在源码里写作 {{*|…}}，渲染成一对**不可见的透明标记 span**：
#   <span style="color:transparent;font-size:0px">〈</span> …注文… <span …>〉</span>
# 注文可以横跨几十个 <p>（后汉书的刘昭注/李贤注尤甚），而 clean_text() 是
# **按 block** 剥注的，跨段的一对永远配不上——于是注文以「正文」身份留在语料里，
# 页面「原句」会显示成注解。故须在**整页层面**先把这一段剥掉。
#
# 判据不能只看「被透明标记包住」：史记卷006 的班固《秦論》附录同样被 {{*|}} 包住
# （源站按注文小字排版），那是正文，误剥就丢内容。实测三书的跨段标记对：
#   史记    1 处（班固《秦論》，通篇无注条目编号）        → 保留
#   汉书   93 处（〔一〕師古曰…，有编号；卷100下叙传）    → 剥
#   后汉书 63 处（注[一]…，有编号）                      → 剥
# 故主判据取「内含注条目编号」（汉书用〔一〕，后汉书用注[一]，编号含全角数字）。
# 兜底：标记落在注文小字块 <small …996666…> 内且整段 < 200 字者，视为无编号的
# 零散夹注（后汉书卷36 有 1 处：〈史記曰「黃帝崩…」〉）。
ANGLE_MARK_OPEN = re.compile(r'<span[^>]*color:transparent[^>]*>\s*〈\s*</span>')
ANGLE_MARK_CLOSE = re.compile(r'<span[^>]*color:transparent[^>]*>\s*〉\s*</span>')
NOTE_ENTRY_RE = re.compile(
    r"注\[[一二三四五六七八九十百千0-9０-９]+\]|〔[一二三四五六七八九十百千0-9０-９]+〕")
NOTE_SMALL_RE = re.compile(r'<small\b[^>]*996666[^>]*>')
SHORT_NOTE_LIMIT = 200

# ---- 行内夹注（既无 {{*|}} 包裹、也无成对标记）----------------------------
# 后汉书的列传/志里，注常**直接写在正文段尾**，两种形态：
#   ① 整段即注：段首就是 `注…` / `注[N]…` → 整段进 note
#   ② 段尾夹注：句读后接 `注…`（`注左傳曰`、`注《孫卿子》曰`、`注[N]…`）→ 从该处切到段末
# 裸「注」（无编号）如「注左傳曰」「注音某」同样进 note（用户报：袁紹劉表列傳下）。
# 排除「注意/注釋/注水/注疏」等非注义（语料中极罕见，宁窄勿滥）。
INLINE_HEAD_NOTE_RE = re.compile(
    r"^(?:注(?:\[[一二三四五六七八九十百千0-9０-９]+\])?|臣昭曰|臣賢曰|賢按|昭按)"
)
# 段中/段尾夹注：句读后，或数字/脚注号后接 `注[N]` / 裸 `注` / 臣昭曰
INLINE_TAIL_NOTE_RE = re.compile(
    r"(?<=[。！？」』）〕：\]*0-9０-９一二三四五六七八九十百千])"
    r"(?:注(?:\[[一二三四五六七八九十百千0-9０-９]+\]|(?![意釋释水疏注]))"
    r"|臣昭曰|臣賢曰)"
)

SENT_END = "。！？"

# 句末标点后紧跟的**闭合**符号（引号/括号）必须跟着本句走。
# 不这么做就会「把第二个引号甩到下一句开头」——用户 2026-09-26 报，
# 实测 96,444 句里有 **7,259 句**以 」』 开头（7.5%），例如上一句断成
# 「……堯曰：「吁」　下一句变成　」堯又曰：「誰可者？
# 闭合符号可嵌套多层（。」』、。」）），所以要**连续**吃。
SENT_CLOSERS = set("」』）〕】》〉”’］｝〉」』)〕】>")

# 导航、版权模板与「三家注」残渣的关键词：出现即丢弃该段
NAV_KEYWORDS = (
    "姊妹计划", "姊妹計畫", "参阅维基百科", "閲文言維基大典", "数据项", "評論",
    "維基百科", "维基百科", "維基大典", "维基大典", "@media", "mw-parser-output",
    "中华人民共和国", "三家註版", "三家注版", "三家注", "註版",
    "公有領域", "公有领域", "Public domain", "版權", "版权",
    "知識共享", "知识共享", "Creative Commons", "許可協議", "授权条款",
    "NewPP", "Transclusion", "parser cache", "維基媒體", "维基媒体",
    "Subclass", "Template:", "渲染", "本作品", "此作品",
    "爲便利閲讀", "為便利閱讀", "便利閲讀", "便利閱讀", "校勘記", "參見", "参见",
    "【索隱】", "【集解】", "【正義】", "索隱述贊", "札記", "作者：", "史記巻",
    "↑", "==",
)

# 导航表格的 class 特征（保留 wikitable / dynlayout-exempt 等正文表）
NAV_TABLE_CLASSES = ("ws-header", "ws-footer", "ws-noexport")

# 单元格与散文段的最小长度：单元格允许短（如「蕭何」），散文段过短多为导航残渣
MIN_CELL_LEN = 2
MIN_PROSE_LEN = 4
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3005]")
# 纯标题行，如「曆書第四」「封禪書第六」——页面内小节标题的残留
TITLE_ONLY_RE = re.compile(
    r"^[\u4e00-\u9fff]{2,8}(第[一二三四五六七八九十百]+|卷[一二三四五六七八九十百]+)$"
)


def strip_angle_notes(text):
    """迭代剥离 〈…〉，直到不动点。

    注文内部会**嵌套** 〈…〉——维基文库用 〈土累〉 这类写法表示合体字（如「壘」），
    于是出现 `〈袁山松書曰：「禱于龍〈土累〉。」〉`。单次 `sub` 只会剥掉**内层**，
    外层残留为 `〈袁山松書曰：「禱于龍。」〉`（实测后汉书 63 处、汉书 19 处、史记 1 处）。
    反复剥到不动点即可清干净。无配对 `〉` 的开括号不会被误吃。
    """
    prev = None
    while prev != text:
        prev = text
        text = ANGLE_NOTE_RE.sub("", text)
    return text


def peel_angle_notes(text):
    """剥下 〈…〉 并**收集**注文，返回 (正文, 注文拼接)。

    与 strip_angle_notes 同一套不动点剥离，但把注文留下——三国志裴注按用户口径
    「保留为注、不参与统计」：paragraph.text 仍可带注供阅读，sentences 只切正文。
    段末悬空 `〈`（注跨段）与段首悬空 `〉`（跨段注收尾）一并收进 note，
    避免残段落进 sentences（实测 sgz 初版 29 句残留）。
    """
    notes = []

    def _repl(m):
        notes.append(m.group(0))
        return ""

    prev = None
    while prev != text:
        prev = text
        text = ANGLE_NOTE_RE.sub(_repl, text)
    i = text.find("〈")
    if i >= 0:
        notes.append(text[i:])
        text = text[:i]
    j = text.find("〉")
    if j >= 0 and "〈" not in text[:j]:
        notes.append(text[: j + 1])
        text = text[j + 1 :]
    return text, "".join(notes)


def in_note_small(html, pos):
    """pos 之前最近的 <small>/</small> 是否为注文色小字块（即 pos 落在注文块内）。"""
    seg = html[max(0, pos - 400):pos]
    open_i = seg.rfind("<small")
    close_i = seg.rfind("</small")
    if open_i < 0 or open_i < close_i:
        return False
    return "996666" in seg[open_i:seg.find(">", open_i) + 1]


def strip_cross_block_notes(html):
    """剥掉**跨段**的注文，返回 (新 html, 剥掉的段数)。

    只处理「开标记与闭标记分处不同 <p>」的那一类——段内成对的仍由
    clean_text()/strip_angle_notes() 负责（那段逻辑已能处理嵌套，不必重写）。

    标记用**栈**配对（注文里会嵌套 〈土累〉 这类合体字标记，顺序配对会配错、
    留下孤立括号）；配对后由外到内处理，被外层吞掉的内层直接跳过。
    判为正文的（如史记卷006 班固《秦論》）原样保留。
    """
    tokens = [(m.start(), m.end(), True) for m in ANGLE_MARK_OPEN.finditer(html)]
    tokens += [(m.start(), m.end(), False) for m in ANGLE_MARK_CLOSE.finditer(html)]
    tokens.sort()

    stack, pairs = [], []
    for start, end, is_open in tokens:
        if is_open:
            stack.append((start, end))
        elif stack:
            ostart, oend = stack.pop()
            pairs.append((ostart, end, oend, start))
    pairs.sort()

    out, pos, removed, consumed_to = [], 0, 0, -1
    for span_start, span_end, inner_start, inner_end in pairs:
        if span_start < consumed_to:
            continue                       # 已随外层一起剥掉
        inner = html[inner_start:inner_end]
        if "</p>" not in inner:
            continue                       # 段内的交给 clean_text()
        text = re.sub(r"\s+", "", TAG_RE.sub("", inner))
        is_note = bool(NOTE_ENTRY_RE.search(text))
        if not is_note and len(text) < SHORT_NOTE_LIMIT:
            # 无编号的零散夹注：须落在注文小字块内
            is_note = in_note_small(html, span_start)
        if is_note:
            out.append(html[pos:span_start])
            pos = span_end
            consumed_to = span_end
            removed += 1
    out.append(html[pos:])
    return "".join(out), removed


def strip_inline_notes(text):
    """（兼容）行内夹注现由 split_body_note 切入 note 展示，此处不再静默丢弃。

    仅返回原串；保留函数以免调用点改动。整段/段尾「注…」在 split_body_note 处理。
    """
    return text, False


def strip_correction_marks(text):
    """规整维基校改/补字标记：`*(x)**[y]*` → y、`*[z]*` → z、`*(x)*` → 删、`**x**` → x。"""
    text = CORRECTION_RE.sub(r"\1", text)
    text = INSERT_RE.sub(r"\1", text)
    text = DELETE_RE.sub("", text)
    text = BOLD_RE.sub(r"\1", text)
    # 不成对的边角残留：补字半截 [延平] → 延平（脚注 [一] 是数字，不匹配、保留）；
    # 剩下散落的 * 一律清掉（史记/汉书无 *，不受影响）。
    text = STRAY_BRACKET_RE.sub(r"\1", text)
    text = text.replace("*", "")
    return text


def strip_wiki_links(text):
    """`[[目标|显示]]` → 显示；`{{`/`}}` 残块去花括号。"""
    text = WIKI_LINK_RE.sub(r"\1", text)
    text = TEMPLATE_RE.sub("", text)
    return text


def split_body_note(para):
    """把段落切成 (正文, 注文)。

    注文都**保留供阅读**、**不进切句统计**。
    取「最早注起点」一次切开，避免先剥「注」却把前面的「按：」留在正文。
    起点：段首注 / 句读·数字后夹注 `注…`·`臣昭曰` / 校勘 `按：`·`據汲本`·`集解引`…
    """
    if not para:
        return "", ""
    if NOTE_PAGE_RE.match(para):
        return "", para
    if INLINE_HEAD_NOTE_RE.match(para):
        return "", para

    starts = []
    for rx in (INLINE_TAIL_NOTE_RE, NOTE_COLLAB_RE):
        m = rx.search(para)
        if m:
            starts.append(m.start())
    if not starts:
        return para, ""
    cut = min(starts)
    body = para[:cut].rstrip()
    note = para[cut:]
    # 砍点前若只是页行号 → 整段是注
    if not body or NOTE_PAGE_RE.match(body) or re.match(
        r"^[一二三四五六七八九十百〇○0-9０-９]+頁?[0-9０-９]*行", body
    ):
        return "", para
    return body, note


def clean_text(raw, keep_angle=False):
    """keep_angle=True: keep 〈…〉 in text (sgz pei notes as note); peel before sentences.
    Default False: strip angle notes (sj/hs/hhs legacy).
    """
    text = TAG_RE.sub("", raw)
    text = html_mod.unescape(text)
    if not keep_angle:
        text = strip_angle_notes(text)
    text = strip_wiki_links(text)
    text = strip_correction_marks(text)
    text = text.replace("\u00a0", "").replace("\u3000", "")
    text = FOOTNOTE_RE.sub("", text)
    # 维基脚注锚点 ^2.02.1 / ^46.046.1（后汉书校勘段常见）
    text = re.sub(r"\^\d+(?:\.\d+)+", "", text)
    return re.sub(r"\s+", "", text)


def is_nav(text, kind="prose"):
    """判断是否为导航/模板残渣。

    表格单元格允许更短（如「蕭何」），但仍要求含汉字——
    否则「←」「元」「一」这类箭头、数字、单字表头会混进正文。
    """
    if not text:
        return True
    if not CJK_RE.search(text):
        return True
    min_len = MIN_CELL_LEN if kind == "cell" else MIN_PROSE_LEN
    if len(text) < min_len:
        return True
    # 「三家注」标记：繁简两种写法都要覆盖（正文里出现过【索隐述赞】这种简体形式）
    if "【" in text or "】" in text:
        return True
    # 页面内小节标题残留
    if TITLE_ONLY_RE.match(text):
        return True
    # 竖线分隔的链式导航行，如「史記音義|史記集解|史記索隱|史記正義」
    if "|" in text and len(text) < 60:
        return True
    # 三国志页眉/上下卷导航篇题：魏書•文帝紀 / 三國志蜀書五諸葛亮傳（无句读）
    if re.match(
        r"^(三國志)?(魏書|蜀書|吳書|呉書|吴書)[•·]?([一二三四五六七八九十0-9]{0,4})?"
        r"[^，。！？；]{0,24}(紀|傳)$",
        text,
    ):
        return True
    return any(kw in text for kw in NAV_KEYWORDS)


def strip_nav_tables(html):
    """移除导航/版权表格（用栈配对 <table>，避免嵌套时误删）。"""
    out = []
    pos = 0
    while True:
        m = OPEN_TABLE_RE.search(html, pos)
        if not m:
            out.append(html[pos:])
            break
        cls_match = TABLE_CLASS_RE.search(m.group(0))
        cls = cls_match.group(1) if cls_match else ""
        is_nav_table = any(k in cls for k in NAV_TABLE_CLASSES)
        if not is_nav_table:
            out.append(html[pos:m.end()])
            pos = m.end()
            continue
        # 配对到对应的 </table>
        depth = 1
        scan = m.end()
        while depth > 0:
            nxt_open = OPEN_TABLE_RE.search(html, scan)
            nxt_close = CLOSE_TABLE_RE.search(html, scan)
            if not nxt_close:
                scan = len(html)
                break
            if nxt_open and nxt_open.start() < nxt_close.start():
                depth += 1
                scan = nxt_open.end()
            else:
                depth -= 1
                scan = nxt_close.end()
        out.append(html[pos:m.start()])
        pos = scan
    return "".join(out)


def extract_blocks(html, keep_angle=False):
    """返回 ([(kind, text)], 行内夹注剥掉的段数)，kind 为 'prose' 或 'cell'，保持文档顺序。"""
    blocks = []
    inline_notes = 0

    def harvest(segment, cell_mode):
        nonlocal inline_notes
        pattern = CELL_RE if cell_mode else PROSE_BLOCK_RE
        for m in pattern.finditer(segment):
            body = m.group(m.lastindex)
            text = clean_text(body, keep_angle=keep_angle)
            text, stripped = strip_inline_notes(text)
            if stripped:
                inline_notes += 1
            kind = "cell" if cell_mode else "prose"
            if not is_nav(text, kind):
                blocks.append((kind, text))

    # 先处理表格（内容表），再处理表格外的散文，用位置还原大致顺序
    segments = []
    pos = 0
    for m in OPEN_TABLE_RE.finditer(html):
        if m.start() > pos:
            segments.append((pos, m.start(), False))
        # 找该表格结束位置
        depth, scan, end = 1, m.end(), len(html)
        while depth > 0:
            nxt_open = OPEN_TABLE_RE.search(html, scan)
            nxt_close = CLOSE_TABLE_RE.search(html, scan)
            if not nxt_close:
                break
            if nxt_open and nxt_open.start() < nxt_close.start():
                depth += 1
                scan = nxt_open.end()
            else:
                depth -= 1
                scan = nxt_close.end()
        end = scan
        segments.append((m.start(), end, True))
        pos = end
    if pos < len(html):
        segments.append((pos, len(html), False))

    ordered = []
    for start, end, is_table in segments:
        chunk = html[start:end]
        before = len(blocks)
        harvest(chunk, is_table)
        ordered.append((start, blocks[before:]))

    ordered.sort(key=lambda x: x[0])
    result = []
    for _, items in ordered:
        result.extend(items)
    return result, inline_notes


def split_sentences(text):
    out, buf = [], ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        buf += ch
        if ch in SENT_END:
            # 句末标点后**连续**吃掉闭合符号，让它留在本句
            j = i + 1
            while j < n and text[j] in SENT_CLOSERS:
                buf += text[j]
                j += 1
            out.append(buf)
            buf = ""
            i = j
            continue
        i += 1
    if buf:
        out.append(buf)
    return [s for s in out if s]


# 分卷后缀：汉书多篇分上下（「匈奴傳上」「五行志下之上」），
# 判体例前先剥掉，否则一律掉进「其他」。史记篇名不带这种后缀，剥了也不影响。
# 后汉书志分编号卷（「五行志一」「郡國志五」「百官志四」），编号也是分卷后缀，
# 不剥则「五行志一」不以「志」结尾 → 判「其他」。故一并纳入。
VOLUME_PART_RE = re.compile(r"(上|中|下|[一二三四五六七八九十])(之(上|下))?$")


def classify(title):
    """按篇名后缀判定体例。

    两部书的后缀不同，必须都认：
        史记：本紀 / 表 / 書 / 世家 / 列傳
        汉书：紀   / 表 / 志 / （無） / 傳
    统一归到同一套体例名上（本纪/表/书/世家/列传），
    前端的体例分组才不用为每本书各写一份。
    """
    base = VOLUME_PART_RE.sub("", title) or title
    if base == "太史公自序":
        return "列传"          # 七十列传末篇，体例同列传
    # 晋书：「列傳第N」「志第N」「載記第N」剥掉序号后只剩体例词，
    # 用**前缀**判定，不能只看 endswith。
    if title.startswith(("載記", "载记")) or "載記" in title:
        return "载记"
    if title.startswith(("列傳", "列传", "傳")):
        return "列传"
    if title.startswith(("帝紀", "帝纪", "本紀", "本纪")):
        return "本纪"
    if title.startswith("志"):
        return "书"
    if base.endswith("世家"):
        return "世家"
    if base.endswith(("列传", "列傳", "傳")):
        return "列传"
    if base.endswith(("本纪", "本紀", "紀")):
        return "本纪"
    if base.endswith("表"):
        return "表"
    if base.endswith(("书", "書", "志")):
        return "书"
    return "其他"


def build_volume(book, slug, title):
    """切分一卷。slug 是卷标识（史记 "001"；汉书 "015b" / "027下之上"）。

    卷号不再假定是三位整数——汉书卷号不规则，108 卷里还有 上/中/下/b 后缀，
    "{:03d}" 那套写法对它不成立。`volume` 字段仍保留整数序号，供「卷 N」展示。
    """
    path = os.path.join(RAW, "{}-{}.html".format(book["code"], slug))
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    # 三国志裴注 / 晋书旧史注：保留为注（text 带注、sentences 不带）。
    keep_angle = book["code"] in ("sgz", "js")

    html = COMMENT_RE.sub(" ", html)
    html = STYLE_RE.sub(" ", html)
    html = strip_nav_tables(html)
    # 跨段注文：史汉 hhs 仍整页剥；sgz 保留 〈〉 进 text，句层 peel 到 note。
    if not keep_angle:
        html, cross_notes = strip_cross_block_notes(html)
    else:
        cross_notes = 0
    blocks, inline_notes = extract_blocks(html, keep_angle=keep_angle)

    paragraphs = [text for _, text in blocks if text]

    chapter_id = "{}-{}".format(book["code"], slug)
    result_paragraphs = []
    total_sentences = 0
    pei_note_paras = 0
    for p_index, para in enumerate(paragraphs, 1):
        if keep_angle:
            sent_src, pei_note = peel_angle_notes(para)
            # 句源再清不成对括号（跨句切开的收尾等），不进 sentences
            sent_src = sent_src.replace("〈", "").replace("〉", "")
            if pei_note:
                pei_note_paras += 1
        else:
            sent_src, pei_note = para, ""
        body, note = split_body_note(sent_src)
        if pei_note:
            note = pei_note + note if note else pei_note
        sents = []
        for s_index, sent in enumerate(split_sentences(body), 1):
            sents.append({
                "id": "{}-{:04d}-{:03d}".format(chapter_id, p_index, s_index),
                "seq": s_index,
                # uid 跟著句子走（P4-0）：往後語料 → book-data → index.db 一路透傳，
                # 編輯切分時按「拆前半繼承 / 併留第一 / 棄用標 dead」維護。
                "uid": stable_uid(chapter_id, p_index, s_index),
                "text": sent,
            })
        total_sentences += len(sents)
        result_paragraphs.append({
            # text=正文 only（校勘/夹注进 note）；句层与读全篇正文都走 text，
            # 注文单独渲染为小字，且绝不进 mentionCount。
            "seq": p_index, "text": body, "note": note, "sentences": sents,
        })

    if keep_angle:
        char_count = sum(len(peel_angle_notes(p["text"])[0])
                         for p in result_paragraphs)
    else:
        char_count = sum(len(p) for p in paragraphs)

    return {
        "bookId": book["code"],
        "book": book["name"],
        "volume": slug_number(slug),
        "slug": slug,
        "chapterId": chapter_id,
        "title": title,
        "fullTitle": "{}·{}".format(book["name"], title),
        "category": classify(title),
        "charCount": char_count,
        "paragraphCount": len(paragraphs),
        "sentenceCount": total_sentences,
        "cellParagraphs": sum(1 for kind, _ in blocks if kind == "cell"),
        "paragraphs": result_paragraphs,
    }, {"crossNotes": cross_notes, "inlineNotes": inline_notes,
        "peiNoteParas": pei_note_paras}


def slug_of(path):
    """data/raw/hs-015b.html → "015b"（兼容 Windows 反斜杠）。"""
    m = re.search(r"-([^/\\]+)\.html$", path)
    return m.group(1) if m else ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # --book hs：显式指定某书，绕过 ready 闸门（汉书准备期用）
    force_codes = []
    while "--book" in argv:
        i = argv.index("--book")
        force_codes.extend(argv[i + 1].split(","))
        del argv[i:i + 2]

    os.makedirs(CORPUS, exist_ok=True)

    summary = []
    for code, book in books_sorted():
        if not force_codes and not book.get("ready", True):
            print("[{}] 《{}》ready=false，跳过".format(code, book["name"]))
            continue
        if force_codes and code not in force_codes:
            continue
        vol_path = os.path.join(DICT, book.get("volumes",
                                               "volumes/{}.json".format(code)))
        volumes = {}
        if os.path.exists(vol_path):
            with open(vol_path, encoding="utf-8") as fh:
                volumes = json.load(fh)

        paths = sorted(glob.glob(os.path.join(RAW, "{}-*.html".format(code))),
                       key=lambda p: volume_sort_key(slug_of(p)))
        for path in paths:
            slug = slug_of(path)
            num = slug_number(slug)
            # 篇名表两种键都试：汉书按 slug（"015b"），史记按卷号字符串（"1"）
            title = (volumes.get(slug) or volumes.get(str(num))
                     or "卷{}".format(slug))
            data, notes = build_volume(book, slug, title)
            out_path = os.path.join(CORPUS, "{}.json".format(data["chapterId"]))
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            summary.append({
                "chapterId": data["chapterId"],
                "title": title,
                "category": data["category"],
                "chars": data["charCount"],
                "paras": data["paragraphCount"],
                "cells": data["cellParagraphs"],
                "sents": data["sentenceCount"],
                "crossNotes": notes["crossNotes"],
                "inlineNotes": notes["inlineNotes"],
                "peiNoteParas": notes.get("peiNoteParas", 0),
                "head": data["paragraphs"][0]["text"][:36] if data["paragraphs"] else "",
            })
        mine = [item for item in summary if item["chapterId"].startswith(code + "-")]
        pei = sum(i.get("peiNoteParas") or 0 for i in mine)
        pei_suf = " | 含裴注段 {}".format(pei) if pei else ""
        print("[{}] 《{}》切分 {} 卷 | 剥跨段注文 {} 处 | 剥行内夹注 {} 处{}".format(
            code, book["name"], len(paths),
            sum(i["crossNotes"] for i in mine),
            sum(i["inlineNotes"] for i in mine),
            pei_suf))

    with open(os.path.join(ROOT, "pipeline", "_build_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
