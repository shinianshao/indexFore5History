# -*- coding: utf-8 -*-
"""管线共用模块：异体字归一、JSON 读写、别名正则编译。

为什么单独抽出来
----------------
异体字归一表（VARIANTS）要被 build / annotate / resolve 三处共用。
复制多份一定逐渐走样——本项目已经踩过「用简体词判断繁体篇名」导致
130 篇全部归错体例的坑，所以凡是跨脚本共享的规则一律放这里，改一处生效一处。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "data", "corpus")
RAW = os.path.join(ROOT, "data", "raw")
DICT = os.path.join(ROOT, "data", "dict")
INDEX = os.path.join(ROOT, "data", "index")
WEB = os.path.join(ROOT, "web")
PIPELINE = os.path.join(ROOT, "pipeline")

# 异体字归一表（1 换 1，因此**不改变字符位置**，高亮下标依然对得上原文）。
# 维基文库《史记》正文混用大量异体字，不做归一会导致整批别名漏配：
#   实证：「河間獻王」0 命中 / 「河閒獻王」12 命中；髙 167 次、閒 387 次、
#   歳 278 次、彊 574 次、説 117 次、巻 7 次、戸 30 次、鄕 24 次
VARIANTS = {
    "髙": "高", "巻": "卷", "戸": "戶", "鄕": "鄉", "閒": "間", "歳": "歲",
    "恱": "悅", "説": "說", "羣": "群", "眞": "真", "愼": "慎", "飮": "飲",
    "塡": "填", "冨": "富", "圎": "圓", "幷": "并", "畱": "留", "曁": "暨",
    "蠭": "蜂", "冩": "寫", "敎": "教", "昬": "昏", "犂": "犁", "甯": "寧",
    "徳": "德", "彊": "強", "竝": "並", "冡": "冢", "暦": "曆", "惪": "德",
    "飜": "翻", "甞": "嘗", "冝": "宜", "冦": "寇", "昜": "陽", "髪": "髮",
    "寳": "寶", "熈": "熙", "煕": "熙", "頥": "頤", "顔": "顏", "鶏": "雞",
    "壊": "壞", "竪": "豎", "闘": "鬥", "飬": "養", "冪": "冪",
    # 「雒」是「洛」的通假异写、「钜」是「巨」的通假异写，均 1:1，不改变下标。
    # 实证：全书「雒」85 次，其中 73 次正是雒陽（56）/雒邑（9）/雒汭等，
    # 与洛陽／洛邑同指一地。不归一的话，「地名的各种写法」表会把同一处
    # 拆成「洛陽×15」与「雒陽×56」两行，界面文案「洛陽／雒陽已并为一条」
    # 就成了假话。人物词典中无任何别名含「洛」，故不影响人物层。
    # 「钜」同理：OpenCC 把 鉅→巨 却把 钜→钜，导致同一处拆成
    # 「鉅鹿×30」与「钜鹿×1」两行。规范简体地名本就是巨鹿（河北巨鹿县）。
    # 人物词典中无任何别名含「巨/钜」，故也不影响人物层。
    "雒": "洛", "钜": "巨",
}

# ---------------------------------------------------------------------------
# 第二批异体字（同样 1:1，不改变字符位置）
#
# 收录方法（可复现，不是凭印象加的）：
#   1. 扫全语料 694,054 字，找出所有「s2t 会改写」的字（即非繁体形），共 157 种；
#   2. 对每一种，看它的规范形是否出现在**词典别名**里——只有会真正影响匹配的才收；
#   3. 逐个核对两者是否**同一个词**：若是两个不同的词（如 后/後、里/裏），
#      收进来只会把不相干的别名并成一条，一律不收。
# 实测这批共可新增覆盖 1,563 处，是「异体字表」真正的价值所在。
#
# 为什么这批比第一批重要：维基文库的《史记》正文里**混进了简体形**，
# 不只是繁体异体。例如「河內」的别名一直是「河內」，而正文写的是「内」，
# 全书 112 处「内」全部漏配；「荊軻／荊楚」漏 8 处、「恆山」漏 14 处。
# ---------------------------------------------------------------------------
VARIANTS.update({
    # —— 正文混入的简体形（整字就是简体）——
    "内": "內", "无": "無", "齐": "齊", "鲁": "魯", "韩": "韓", "赵": "趙",
    "黄": "黃", "乐": "樂", "汉": "漢", "将": "將", "时": "時", "单": "單",
    "军": "軍", "伤": "傷", "仓": "倉", "纪": "紀", "济": "濟", "泽": "澤",
    "隐": "隱", "阴": "陰", "阳": "陽", "闵": "閔", "间": "間", "释": "釋",
    "骑": "騎", "哙": "噲", "横": "橫", "荥": "滎", "郸": "鄲", "酂": "酇",
    # —— 繁体异体字 ——
    "温": "溫", "虚": "虛", "恒": "恆", "荆": "荊", "涂": "塗", "鸱": "鴟",
    "仆": "僕", "峣": "嶢",
    #   啓／啟：夏后啟。正文两形并用（啓=17 次、啟=7 次），词典只登记了「啟」，
    #           不归一的话 17 处「啓」一处也匹配不上（实测 p_qi 只收 6 处，
    #           其中还有 3 处是把「微子啟／啟弟／不憤不啟」误算进来的）。
    #           取「啟」为规范形：它是正字，也是词典正名（p_qi/p_weizi/p_hanjingdi
    #           三人的 tradName 用的都是「啟」）。
    #   鼂／晁：鼂錯／晁錯。异体同指一人，**两形在词典里都已登记**，所以匹配本来
    #           不漏；归一的意义在**归并键**——`t2s(norm())` 否则会把同一个人的
    #           称谓表拆成「晁錯×23」「鼂錯×15」两行。取「晁」为规范形：它是现代
    #           通行写法，也是语料多数形（晁 25 : 鼂 16）。
    #           「鼌」是「鼂」的简体（t2s(鼂)=鼌），语料里 0 次，只出现在词典
    #           自动生成的简体正名「鼌错」里；不一起归一的话，归并键会多出一行
    #           「鼌错（本批未用）」，同一个人的称谓表又变成两行。
    "啓": "啟", "鼂": "晁", "鼌": "晁",
    # —— 同词异写（不是两个词，归一后仍指同一事）——
    #   于／於：正文两形并用，归一后「樊於期」不再漏配；
    #           「單于」「淳于」两侧都归一，所以不会被打散。
    #   云／雲：正文「云」既作「曰」也作「雲」省写，归一后「雲中／雲陽」不再漏配；
    #           「云云」（泰山下小山）两侧同归一，仍照常命中。
    #   余／餘：正文「余」既作「我」也通「餘」，归一后「陳餘／餘善」不再漏配。
    "于": "於", "云": "雲", "余": "餘",
    #   卽／即：同一字的两种写法（卩／阝 之别），处处同义、无第二义项。
    #           正文两形并用（即 594 次、卽 65 次；即位 122∶25、即墨 24∶6、即殺 3∶2）。
    #           除地名「即墨」外，无任何别名含「即」→ 归一是零副作用。
    #           取「即」为规范形：现代通行写法，也正是 t2s 的目标形。
    #           修后 pl_jimo 即墨 24 → 30 处。
    "卽": "即",
})
VARIANT_TABLE = str.maketrans(VARIANTS)


def norm(text):
    """异体字归一。1:1 映射，长度不变，因此可安全用于下标定位。"""
    return text.translate(VARIANT_TABLE)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        # 別讓「上一輪被中斷留下的半截檔」偽裝成「你的改動寫壞了」
        raise SystemExit(
            "{} 不是合法 JSON（{}）。\n"
            "多半是上一輪寫到一半被中斷（Ctrl-C / 測試超時）留下的半截檔，"
            "而不是你的改動有問題——重跑 app/tools/rebuild.py 即可再生。".format(path, e))


def write_json(path, obj, indent=None):
    """原子寫：先寫同目錄的 .tmp，再 os.replace 頂掉舊檔。

    ⚠️ 為什麼必須原子：book-data.json 有 8MB，「open(w) 清空原檔 → 慢慢 dump」
    中間只要被打斷（Ctrl-C、測試超時 SIGTERM、機器卡死），留下的就是**半截 JSON**。
    半截檔比沒有更糟——下一次 load_json 報的是
    「Expecting ',' delimiter: line 1 column 6775237」，
    看不出是「上一輪被中斷」，只會讓人以為是自己的改動寫壞了。
    原子寫之後，這種情況最多留下一個 .tmp 垃圾，原檔永遠是上一輪完整的。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=indent,
                  separators=None if indent else (",", ":"))
        # 先 flush 再 fsync，確保真的落到磁盤上——os.replace 只保證目錄項原子，
        # 不保證數據已寫完（掉電時仍可能換上一個空殼）
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def compile_alias_pattern(alias_pairs):
    """把 (别名, pid) 列表编译成单个正则。

    排序按「长度降序」——长别名优先命中，避免「漢高祖」被「高祖」截断成两截。
    同一别名归属多人时按 pid 兜底排序，保证结果可复现（不依赖字典序随机）。
    """
    pairs = sorted(set((norm(a), pid) for a, pid in alias_pairs if a),
                   key=lambda item: (-len(item[0]), item[0], item[1]))
    mapping = {}
    ordered = []
    for alias, pid in pairs:
        mapping[alias] = pid        # 同一别名只留首个（长者优先）
        ordered.append(alias)
    if not ordered:
        return None, {}
    return re.compile("|".join(re.escape(a) for a in ordered)), mapping


# ---------------------------------------------------------------------------
# 书注册表
#
# 新增古籍只改 data/dict/books.json，**不改代码**。
# 注册表缺失时退化成单书《史记》，保证老产物照跑。
# ---------------------------------------------------------------------------
BOOKS_FILE = os.path.join(DICT, "books.json")
_BOOKS_CACHE = None


def load_books():
    """返回 {code: {code,name,order,volumes,source}}。带缓存——
    chapter_sort_key 会逐章调用，不能每次都读盘。"""
    global _BOOKS_CACHE
    if _BOOKS_CACHE is None:
        _BOOKS_CACHE = load_json(BOOKS_FILE) or {
            "sj": {"code": "sj", "name": "史記", "order": 0,
                   "volumes": "volumes/sj.json"},
        }
    return _BOOKS_CACHE


def books_sorted(ready_only=False):
    """按 order 排好的 [(code, meta), ...]。

    ready_only=True 时只返回 books.json 里 ready 为真的书——
    汉书抓取完、篇主表与人物词典补齐之前先挂着 ready:false，
    免得半成品语料混进流水线把史记的产物搅乱。
    """
    items = sorted(load_books().items(),
                   key=lambda kv: (kv[1].get("order", 99), kv[0]))
    if ready_only:
        items = [(c, m) for c, m in items if m.get("ready", True)]
    return items


def is_book_ready(code):
    return load_books().get(code, {}).get("ready", True)


def book_order(code):
    for i, (c, _meta) in enumerate(books_sorted()):
        if c == code:
            return i
    return 0


def volume_sort_key(slug):
    """卷 slug 排序键 (卷号, 子序号, 余串)。

    汉书卷号不规则，必须同时能排 "001"、"015b"、"027下之上"、"099中"：
        无后缀 0 < 上 1 < 中 2 < 下 3 < 其它 5 < b 9
    **只此一份**：build.py 与 fetch_book.py 都调它，不在各自文件里另抄
    （抄一份就会漂移，本项目踩过「用简体词判断繁体篇名」的坑）。
    """
    m = re.match(r"^(\d+)", slug)
    num = int(m.group(1)) if m else 9999
    rest = slug[m.end():] if m else slug
    if not rest:
        sub = 0
    elif rest.startswith("上"):
        sub = 1
    elif rest.startswith("中"):
        sub = 2
    elif rest.startswith("下"):
        sub = 3
    elif rest == "b":
        sub = 9
    else:
        sub = 5
    return (num, sub, rest)


def slug_number(slug):
    """slug → 卷号整数。"015b" → 15、"027下之上" → 27。"""
    m = re.match(r"^(\d+)", slug)
    return int(m.group(1)) if m else 0


def corpus_paths(codes=None, ready_only=False):
    """按「书序 → 卷序」返回全部语料路径。

    多书之后不能再写 glob("sj-*.json")——汉书会整本漏掉。
    这里按 books.json 的书序遍历，卷内再用 volume_sort_key 排，
    保证产物里篇目的先后与书架顺序一致。
    """
    import glob
    out = []
    for code, _meta in books_sorted(ready_only=ready_only):
        if codes and code not in codes:
            continue
        paths = glob.glob(os.path.join(CORPUS, "{}-*.json".format(code)))
        paths.sort(key=lambda p: volume_sort_key(
            os.path.basename(p)[len(code) + 1:-len(".json")]))
        out.extend(paths)
    return out


def chapter_sort_key(chapter_id):
    """篇目排序键。

    sj-008 → (0, 8, 0, '')；汉书卷号不规则，必须也能排：
        hs-015b        → (1, 15, 9, 'b')
        hs-027下之上    → (1, 27, 3, '下之上')
        hs-099中       → (1, 99, 2, '中')
    之所以要带书序：多书之后 sj-001 与 hs-001 必须能分开排序。
    """
    code, _sep, tail = chapter_id.rpartition("-")
    num, sub, rest = volume_sort_key(tail)
    return (book_order(code), num, sub, rest)


# ---------------------------------------------------------------------------
# 称号族判定
# 「梁王」「梁孝王」属同一族（都是梁国之王的称号），「魏其侯」不是——
# 后者核心词是「魏其」，与魏国无关。判断依据：核心词之后紧跟爵位后缀，
# 或紧跟谥号再接爵位（梁＋孝＋王）。
# 词典生成（判断谁可能持有某称号）与体检（判断某称号是否真的只属一人）
# 都要用，故放这里共用。
# ---------------------------------------------------------------------------
GENERIC_CORE_SUFFIXES = ("王", "公", "侯", "君", "后", "太后", "夫人", "相国", "将军")

# 爵位用字。
# 地名层用它做「国+谥+爵」的守卫：人名阻断表里收了「宋襄」（宋义之子宋襄），
# 但「宋襄公」是宋国+谥号+爵位，仍是地名读法。
#
# 这个集合必须**窄**。第一版把 軍/兵/將/相/守/令/長/大/夫 也算进来，
# 结果「秦嘉軍敗走」「晉鄙軍」「雍齒守豐」「宋襄相齊」全被当成
# 「国+谥+爵」放行了——那些字在人名后面是**谓语或宾语**（X 的军队、X 守某地），
# 不是爵位。真正的爵位字只有下面这些。
PEERAGE_CHARS = set("王公侯君后帝子男伯仲叔季")
# 只有「地名 + 谥号 + 爵位」这个三段式才该放行，所以守卫还要求阻断串的
# **末字是谥号字**（周**文**王 / 宋**襄**公 / 陳**武**公 会放行，
# 「吳娃子」「秦嘉軍」不会——娃、嘉 都不是谥号字）。
POSTHUMOUS_CHARS = set("孝悼惠文武功哀頃共敬桓景昭宣元平靜隱厲幽剌簡靈獻思靖節殤釐高光")

# 完整谥法用字表。
# 与上面的 POSTHUMOUS_CHARS **刻意分开**：那张表服务于「称号族」判定（只关心
# 王侯称号里出现频率高的谥号），往里加字会改动人物层的称号归属结论。
# 这张表服务于地名层的「国+谥+爵」守卫，必须尽量收全——漏一个字就会误伤：
# 第一版用 POSTHUMOUS_CHARS，因为里面没有「襄」，导致「宋襄公」的「宋」
# 被当成姓氏挡掉（周文王 / 陳武公 / 曹襄公 同理）。
POSTHUMOUS_ALL = set(
    "文武成康昭穆共懿孝夷厲宣幽平桓莊僖釐惠襄頃匡定簡獻考靈景悼敬慎聲隱湣閔殤煬胡哀出懷元靖明戴威易繆剌高光荒節思靜白")



def title_like(simp, core):
    """简体称号 simp 是否属于核心词 core 的称号族（宽判据）。"""
    if not simp.startswith(core):
        return False
    rest = simp[len(core):]
    if not rest:
        return True
    if any(rest.startswith(suf) for suf in GENERIC_CORE_SUFFIXES):
        return True
    return rest[0] in POSTHUMOUS_CHARS and any(ch in rest for ch in "王公侯君")


def same_title_family(simp, core, suffix):
    """严判据：称号不仅同核心词，爵位后缀也要一致。

    宽判据用来「找候选」（宁可多找，反正后面还有上下文过滤），
    严判据用来「判是否有竞争者」，两者不能混用：
      - 梁孝王 / 梁王      → 同族（都是梁之王）
      - 武安君 / 武安侯    → 不同族（君 ≠ 侯，白起不是田蚡的竞争者）
      - 吕王产 / 吕后      → 不同族
      - 周文王 / 周公      → 不同族
    用宽判据判竞争者，会报出一堆不存在的冲突。
    """
    if not simp.startswith(core):
        return False
    rest = simp[len(core):]
    if suffix in GENERIC_CORE_SUFFIXES and len(suffix) > 1:
        return rest.startswith(suffix)
    if not rest:
        return False
    if rest.startswith(suffix):
        return True
    if rest[0] in POSTHUMOUS_CHARS and len(rest) > 1 and rest[1:].startswith(suffix):
        return True
    return False


def stable_uid(chapter_id, para, seq) -> str:
    """句子的穩定主鍵（P4-0）。

    三處共用同一個算法：`build.py`（切分時分配）、`tag_uids.py`（補打老語料）、
    `app/tools/build_index_db.py`（建庫時兜底）。**改一處必須改三處**，
    否則歷史命中、override 錨點、快照 diff 會全部對不上。

    注意它吃的是**位置**（篇/段/句序），所以編輯切分後會位移——
    正解是讓 uid 在語料層就定好、一路透傳，而不是每次現算。
    """
    import hashlib
    raw = "{}|{}|{}".format(chapter_id, para, seq)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def safe_save_workbook(wb, path: str) -> None:
    """安全原子保存 openpyxl 工作簿，防 Windows 下 open('wb') 截斷損壞原表。

    原理：先在內存 io.BytesIO() 完成 Zip 封包，成功後再寫入臨時文件原子替換目標。
    若生成過程報錯或目標被佔用，原文件 100% 保持完好，絕不留 0 字節或 2.3KB 損壞檔。
    """
    import io
    bio = io.BytesIO()
    wb.save(bio)
    buf = bio.getvalue()
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)
    tmp = path + ".tmp." + str(os.getpid())
    try:
        with open(tmp, "wb") as f:
            f.write(buf)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

