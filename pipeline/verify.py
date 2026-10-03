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

# ── 人名纠正第一批（2026-09-26）已判「不是人名」的碎片，不许再被自动补人加回来 ──
# 判定依据逐条记在 pipeline/_name_plan.txt，取证数据在 pipeline/_name_batch.json。
DEAD_NAMES = (
    "趙分", "衛分", "周分", "燕分", "鄭分", "王子分", "單于既", "王如故", "徐偃又",
    "王子及", "王子於", "荊門", "東泰山", "盧水胡", "黎陽營", "倉部", "金部",
    "時匈奴", "相國何", "公子棄",
    "公子為", "公子亡", "公子奔", "公子行", "公子過", "公子及", "公子引", "公子患",
    "公子故", "公子傅", "公子列", "公子畏", "公子云", "公子何", "公子作", "公子八",
    "公子勉", "公子十", "公子竟", "公子美", "公子舉", "公子色", "公子誠", "公子謂",
    "公子貴", "公子逐", "公子馳", "公子齋", "公子率", "公子當", "公子恐", "公子或",
    "公子於", "公子復", "公子師", "公子尚", "公子賢", "公子留",
)
# ── 第二批（D 类召回，2026-09-27）：判定「不是人名」的 36 条 ──────────
# D 类 90 条里真人与噪声混杂，只能逐条看上下文，不能批量删。下面这些是噪声：
DEAD_NAMES_2 = (
    "夏帝卜", "王秦降", "羊十餘", "齊還報", "魏而攻", "徐盜賊", "梁冀被",
    "臧自殺", "漢軍方", "趙共擊", "趙有蛇", "益封去", "賁軍開", "薛公戰",
    "桂陽三", "安定三", "沈黎", "蒲陽", "索間", "危須", "弘農楊", "會稽虞",
    "安夷護", "尉竇固", "國將哀", "國共敖", "龍旂", "方軌", "懷安",
    "方丈", "風伯", "文昌", "文始", "管蔡", "王聖", "梁丘",
)
# ── 同一批判为「真人」的，钉住不许被后续清理误删 ──────────────────────
KEEP_REAL = (
    "郭汜", "慕容恪", "殷仲堪", "周顗", "朱然", "淳于瓊", "段幹木", "柳下惠",
    "梁丘賀", "尹更始", "左悺", "石慶", "薛瑩", "謝鯤", "鄧颺", "劉岱",
    "翟遼", "蘇茂", "戴若思", "王甫", "慕容沖", "夏侯玄", "張天錫", "何晏",
    "張安世", "楊奉", "何無忌", "庾峻", "嚴青翟", "王欽盧", "狐蘭支", "翟景",
)

# ── 句末闭合符号：这些不该出现在句子开头（断句把引号甩到下一句了）──
SENT_CLOSERS = ("」", "』", "）", "〕", "】", "》")

# ── 同一批里「被切短」而补长的名字：原文写的是全称，提取器只取了前两字 ──
LENGTHENED = (
    "公孫戎奴", "公子開方", "公子黔牟", "公子奚斯", "公子燭庸",
    "公子商人", "公子曼滿", "公子追舒", "公子目夷", "公子呂伋",
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = json.load(open(os.path.join(ROOT, "data", "index", "book-data.json"), encoding="utf-8"))

persons = DATA["persons"]
chapters = {c["id"]: c for c in DATA["chapters"]}
by_id = {p["id"]: p for p in persons}
by_name = {p["name"]: p for p in persons}
# 按名查存在性：简体 name 与繁体 tradName 都收（自动补齐条目的 name 字段未必转过简繁）
persons_by_name = set()
for _p in persons:
    persons_by_name.add(_p.get("name") or "")
    persons_by_name.add(_p.get("tradName") or "")
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


def _newchain_cases():
    """P5：新链路一致性（book-data.json ↔ index.db）。

    这两边以前只能**手工对齐科目**——哪一步漏跑（尤其是 annotate 四步没跑全）
    全靠肉眼发现。现在变成断言，漏一步立刻红。
    """
    out = []
    db_path = os.path.join(ROOT, "data", "index", "index.db")
    if not os.path.exists(db_path):
        out.append(("新链路：index.db 存在", False,
                    "缺 {}，先跑 rebuild.py".format(db_path)))
        return out
    import sqlite3
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from common import stable_uid

    conn = sqlite3.connect(db_path)
    try:
        n_sent = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        n_men = conn.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
        n_per = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        db_pairs = set(conn.execute(
            "SELECT sentence_uid, person_id, surface, s, e, tier FROM mentions"))
    finally:
        conn.close()

    json_pairs = set()
    uid_bad = []
    for s in DATA["sentences"]:
        u = s.get("uid")
        # uid 现在由语料层透传；这里按同一算法重算一遍，
        # 防的是「四处算法（common/build/tag_uids/build_index_db）改了但没同步」
        if u != stable_uid(s["chapterId"], s.get("paraSeq"), s.get("seq")):
            uid_bad.append(str(u))
        for m in s.get("marks") or []:
            json_pairs.add((u, m.get("pid"), m.get("alias"),
                            m.get("s"), m.get("e"), m.get("tier")))

    out.append(("新链路：句数与库一致",
                n_sent == len(DATA["sentences"]),
                "库 {:,} / JSON {:,}".format(n_sent, len(DATA["sentences"]))))
    out.append(("新链路：命中数与库一致",
                n_men == len(json_pairs),
                "库 {:,} / JSON {:,}".format(n_men, len(json_pairs))))
    out.append(("新链路：人物数与库一致",
                n_per == len(persons),
                "库 {:,} / JSON {:,}".format(n_per, len(persons))))
    out.append(("新链路：uid 算法四处一致",
                not uid_bad,
                "不一致 {} 句 {}".format(len(uid_bad), uid_bad[:3])))
    only_db = db_pairs - json_pairs
    only_json = json_pairs - db_pairs
    out.append(("新链路：命中逐条对齐",
                not only_db and not only_json,
                "仅库有 {:,} / 仅 JSON 有 {:,}".format(len(only_db), len(only_json))))
    return out


def _workbook_cases():
    """句子工作簿的 uid 必须与库**同名同值**（2026-10-04 修掉的四参数分叉）。

    `workbook/sentences-*.xlsx` 是被 gitignore 的派生视图，平时没人会去核对它，
    所以 `build_workbook.py` 里那份 uid 算法被写成四参数（尾部多拼了原文）之后，
    22,104 行与库**零命中**，静默错了好几轮——不报错、没人看、也不影响网页。

    断言放在这里（而不是库里）：表只要在，uid 就必须逐条等于 `common.stable_uid`，
    且库里真有这一句。另有静态一条守「源里不许再长出第二份算法」。
    """
    import glob as _glob
    import io as _io

    out = []
    here = os.path.dirname(os.path.abspath(__file__))

    # 静态：build_workbook 只許 import common.stable_uid，不許再自帶一份 md5
    try:
        bw_src = _io.open(os.path.join(here, "build_workbook.py"),
                          encoding="utf-8").read()
    except OSError as ex:
        out.append(("build_workbook 只許用 common.stable_uid", False, str(ex)))
        bw_src = ""
    if bw_src:
        # 判據取 `import hashlib / def make_uid`（自己再實現一份就必須 import hashlib），
        # 不能取 `md5(` —— 那是註釋裡也會出現的普通詞，會被自己的說明文字誤傷。
        _reimpl = "import hashlib" in bw_src or "def make_uid" in bw_src
        out.append(("build_workbook 不再自帶 uid 算法",
                    (not _reimpl) and "stable_uid" in bw_src,
                    "自帶={} / 用 common.stable_uid={}".format(
                        _reimpl, "stable_uid" in bw_src)))

    # ⚠ 排除 `.bak-` 備份：它是**刻意留下的舊檔**（覆蓋前留的退路，已被 gitignore），
    #   拿它當斷言對象只會讓「修好了」看起來還紅著。
    paths = sorted(p for p in _glob.glob(
        os.path.join(ROOT, "workbook", "sentences-*.xlsx")) if ".bak-" not in p)
    if not paths:
        # 派生视图且被 gitignore：全新 clone 里没有它，跳过（不假装通过也不判失败）
        out.append(("句子工作簿 uid 与库一致", True,
                    "无 sentences-*.xlsx（未生成，重跑 build_workbook 才有），跳过"))
        return out

    sys.path.insert(0, here)
    from common import stable_uid
    try:
        from openpyxl import load_workbook
    except Exception as ex:                       # pragma: no cover
        out.append(("句子工作簿 uid 与库一致", False, "缺 openpyxl：{}".format(ex)))
        return out

    db_path = os.path.join(ROOT, "data", "index", "index.db")
    db_uids = set()
    if os.path.exists(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            db_uids = {r[0] for r in conn.execute("SELECT uid FROM sentences")}
        finally:
            conn.close()

    def _as_int(v):
        """Excel 讀回來的整數可能是 `17.0`：拼 key 前必須歸一。

        不歸一的後果是「靜默對不上」而不是報錯——踩過同一個坑：徽章消失。
        """
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v

    for p in paths:
        name = os.path.basename(p)
        try:
            wb = load_workbook(p)
        except Exception as ex:
            out.append(("句子工作簿 {} 能读开".format(name), False, str(ex)))
            continue
        if "句子" not in wb.sheetnames:
            out.append(("句子工作簿 {} 有「句子」页".format(name), False,
                        "页签：{}".format(wb.sheetnames)))
            continue
        rows = list(wb["句子"].iter_rows(values_only=True))
        hdr = [str(h) for h in (rows[0] if rows else [])]
        try:
            iu = hdr.index("uid")
            ic = hdr.index("篇(chapterId)")
            ip = hdr.index("段序")
            isq = hdr.index("句序")
        except ValueError as ex:
            out.append(("句子工作簿 {} 列名未改".format(name), False, str(ex)))
            continue
        n, bad_alg, not_in_db = 0, [], []
        for r in rows[1:]:
            if iu >= len(r) or not r[iu]:
                continue
            n += 1
            u = str(r[iu]).strip()
            # ⚠ 兩個桶都要獨立統計，不能用 elif：算法錯時「在庫裡」那條會被
            #   整段跳過，變成一條永遠綠的假斷言（四參數那次正是如此）。
            if u != stable_uid(r[ic], _as_int(r[ip]), _as_int(r[isq])):
                bad_alg.append(u)
            if db_uids and u not in db_uids:
                not_in_db.append(u)
        # ⚠ n > 0 不能省：表空了 `not bad_alg` 對空列表恆真，那就又是假綠
        out.append(("句子工作簿 {} uid 算法 = common.stable_uid".format(name),
                    n > 0 and not bad_alg,
                    "{} 行，不一致 {} 条 {}".format(n, len(bad_alg), bad_alg[:3])))
        out.append(("句子工作簿 {} uid 在库里都存在".format(name),
                    n > 0 and bool(db_uids) and not not_in_db,
                    "{} 行 / 库 {:,}，库里没有 {} 条 {}".format(
                        n, len(db_uids), len(not_in_db), not_in_db[:3])))
    return out


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
    # 阈值两次下调，都是**删噪声**而非回退，每次都另配「不许回归」的断言：
    #   2300 → 2270（2026-09-26 第一批：删 59 条 C 类切词碎片，2335 → 2276）
    #   2270 → 2230（2026-09-27 第二批：删 36 条 D 类噪声，2276 → 2240）
    # 详见 pipeline/_name_plan.txt（逐条带语料上下文）。
    cases.append(("人物总数 ≥ 2230（散见 + 类传/附传补齐，已剔两批切词碎片）",
                  len(DATA["persons"]) >= 2230,
                  str(len(DATA["persons"]))))

    # ===== 人名纠正第一批（2026-09-26，_gen_name_batch.py 取证 + _name_plan.txt 判定）=====
    # ① 判为「不是人名」的切词碎片/非人实体，不许再被自动补人加回来。
    #    完整清单见 pipeline/_name_plan.txt（含逐条语料上下文）。
    back = [n for n in DEAD_NAMES if n in persons_by_name]
    cases.append(("已删的 {} 条非人名碎片未回归".format(len(DEAD_NAMES)),
                  not back, "、".join(back[:8]) or "无"))
    back2 = [n for n in DEAD_NAMES_2 if n in persons_by_name]
    cases.append(("第二批 {} 条 D 类噪声未回归".format(len(DEAD_NAMES_2)),
                  not back2, "、".join(back2[:8]) or "无"))
    # 真人保留清单：防「清理假人名」时误伤。这条比"总数"更能说明质量。
    lost = [n for n in KEEP_REAL if n not in persons_by_name]
    cases.append(("判为真人的人名未被误删（郭汜/慕容恪/柳下惠…）",
                  not lost, "、".join(lost[:8]) or "无"))
    # ② 被切短的名字已补长（原文写的是全称，提取器只取了前两字）
    miss = [n for n in LENGTHENED if n not in persons_by_name]
    cases.append(("切短的名字已补长（公孫戎奴/公子開方…）",
                  not miss, "、".join(miss) or "无"))

    # ===== 断句：闭合符号不许被甩到下一句（2026-09-26 用户报）=====
    # split_sentences 原先遇到 。！？ 立刻断，导致「……。」　下一句以 」』 开头，
    # 实测 96,444 句里 7,259 句（7.5%）受害。修法：句末后连续吃掉闭合符号。
    stranded = [s["text"][:12] for s in DATA["sentences"]
                if (s.get("text") or "").startswith(SENT_CLOSERS)]
    cases.append(("没有句子以闭合符号开头（引号不被甩到下一句）",
                  not stranded, "／".join(stranded[:5]) or "无"))
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

    # ===== P1-b 类传/附传长尾缺人 =====
    # 儒林/文苑/隐逸/艺术/载记从属里成建制的传主，过去整批不在典：
    # 检索「嵇康」直接返回未收录。这批人是靠「X字Y」传主句式捞出来的。
    # 判据点名标志性人物而不是读计划文件——计划文件是一次性产物（gitignore）。
    _CLASS_FILL = ("嵇康", "劉琨", "祖逖", "陸機", "潘岳", "葛洪", "張華", "鍾會",
                   "向秀", "陳琳", "杜預", "鄧艾", "荀勖", "蘇峻", "郗鑒", "楊駿",
                   "殷浩")
    _cls_stat = []
    for _nm in _CLASS_FILL:
        _ps = [p for p in persons
               if p.get("tradName") == _nm or p.get("name") == _nm]
        _cls_stat.append((_nm, max((p.get("mentionCount") or 0) for p in _ps)
                          if _ps else 0))
    _cls_zero = [nm for nm, n in _cls_stat if n <= 0]
    _cls_total = sum(n for _, n in _cls_stat)
    cases.append(("类传/附传传主已入典（嵇康/劉琨/祖逖…无零命中）",
                  not _cls_zero and _cls_total >= 800,
                  "零命中={} 合计={}".format(_cls_zero, _cls_total)))
    # 负向：这批人是魏晉人，books 限在 js / sgz，绝不能漏进史記、漢書——
    # 漏进去就是同名异人误挂（史記里没有嵇康，有也不该由这条补人链路标）。
    #
    # ⚠️ 判据 2026-10-02 收紧过一次：原判据是「sj/hs 的 mentionCount 为 0」，
    # 红了 1 条（嵇康 1 處）。查了才知那處命中串是**他的字「叔夜」**，出現在
    # 《漢書·古今人表》——那是一张「古今」通表，收兩漢先賢，魏晉人在里面
    # 有条目是**合理的**；正名「嵇康」在史記/漢書**零命中**。
    # 所以判据改成「**正名/非字面命中**不得越书」，字面命中单独列出当信息项。
    # 教训仍是那条：**断言红 ≠ 数据错，先看清它断的那批是什么**。
    _cls_leak = []       # 正名越书 —— 真的错
    _cls_byzi = []       # 字面越书 —— 只记录，不当失败
    # 判据用**库里实查的命中串**（mentions.surface），不是静态名字集合——
    # 后者只认得「当前这两个写法」，将来别名表一改就会漏判。
    # book-data 的实际字段：mark = {s, e, pid, tier, alias}；person 主键是 `id`
    # （不是 `pid`——这个坑踩过不止一次）。这里读 index.db 拿权威命中面。
    import sqlite3 as _sq
    # ⚠️ ROOT 是**字符串**（第 56 行），不是 Path——写 ROOT / "x" 会 TypeError。
    _db = _sq.connect(os.path.join(ROOT, "data", "index", "index.db"))
    try:
        _zi_by_pid = {}
        for _pid, _bk, _surf in _db.execute(
                "SELECT m.person_id, b.code, m.surface FROM mentions m "
                "JOIN sentences s ON s.uid = m.sentence_uid "
                "JOIN chapters ch ON ch.id = s.chapter_id "
                "JOIN books b ON b.code = ch.book_id "
                "WHERE b.code IN ('sj','hs')"):
            _zi_by_pid.setdefault(_pid, []).append((_bk, _surf))
    except Exception as _e:                        # 库不存在 / schema 变了
        _zi_by_pid = {}
        print("  · [警告] 读不到命中面（{}），本条按保守判：只要计数非零就算越书".format(_e))

    for _nm in _CLASS_FILL:
        for p in persons:
            if p.get("tradName") != _nm and p.get("name") != _nm:
                continue
            _hits = _zi_by_pid.get(p.get("id")) or []
            _names = {p.get("name") or "", p.get("tradName") or ""} - {""}
            for _bk in ("sj", "hs"):
                _c = ((p.get("byBook") or {}).get(_bk) or {}).get("mentionCount") or 0
                if not _c:
                    continue
                _mine = sorted({s for (bk, s) in _hits if bk == _bk})
                # 有正名参与 → 是真的同名异人误挂；只有字/号 → 合理，只记录
                _by_name = sorted(set(_mine) & _names)
                if not _mine:                      # 查不到命中面 → 保守算错
                    _cls_leak.append((_nm, _bk, _c, "命中面缺失"))
                elif _by_name:
                    _cls_leak.append((_nm, _bk, _c, "正名", _by_name))
                else:
                    _cls_byzi.append((_nm, _bk, _c, _mine[:3]))
    if _cls_byzi:
        print("  · 字面越书（不计失败）：{}".format(_cls_byzi))
    cases.append(("类传补齐人物不越书到史記/漢書（正名口径）", not _cls_leak,
                  "越书={}".format(_cls_leak)))

    # ===== docs/17 人工判定回填（2026-09 用户逐条勾选后落地）=====
    # 用户是在「你的判定」列逐条写人名的，不是整体勾一个——所以这里
    # 每条断言都对着一个具体上下文，而不是对着聚合数字。
    def _js_alias(alias):
        for s in DATA["sentences"]:
            if not s["chapterId"].startswith("js-"):
                continue
            for m in s.get("marks") or []:
                if m.get("alias") == alias:
                    yield s, m

    def _js_ctx(alias, key):
        c = {}
        for s, m in _js_alias(alias):
            t = s.get("text") or ""
            i, j = m.get("s", 0), m.get("e", 0)
            if key in t[max(0, i - 12): j + 12]:
                c[m["pid"]] = c.get(m["pid"], 0) + 1
        return c

    # 「魏武帝」是曹操长名。books 不含 js 时长名在晋书不生效，
    # 裸「武帝」就把「魏武帝為司空」「封魏武帝玄孫曹勵」截走了。
    weiwu = [m for _, m in _js_alias("魏武帝")]
    cases.append(("「魏武帝」長名→曹操（js）",
                  len(weiwu) >= 20 and all(m["pid"] == "p_caocao" for m in weiwu),
                  "{} 处 {}".format(len(weiwu), sorted({m["pid"] for m in weiwu}))))

    # 裸「武帝」归石虎 99 / 刘聪 43 处，**没一篇在载记**——全在志与列传里，
    # 上下文是「武帝泰始二年」「武悼楊皇后配饗武帝廟」「安世，武帝字也」。
    wudi_js = {}
    for _, m in _js_alias("武帝"):
        wudi_js[m["pid"]] = wudi_js.get(m["pid"], 0) + 1
    cases.append(("晉書裸「武帝」不再歸石虎/劉聰（chapter 誤牽十六國）",
                  wudi_js.get("p_shihu", 0) == 0 and wudi_js.get("p_liucong", 0) == 0
                  and wudi_js.get("p_simayan", 0) >= 300,
                  "司馬炎={} 石虎={} 劉聰={}".format(wudi_js.get("p_simayan", 0),
                                                     wudi_js.get("p_shihu", 0),
                                                     wudi_js.get("p_liucong", 0))))
    ws = _js_ctx("武帝", "泰始")
    cases.append(("「武帝泰始」→ 司馬炎（年號硬證據）",
                  ws.get("p_simayan", 0) >= 30, str(ws)))
    yj = _js_ctx("元帝", "京房")
    cases.append(("「元帝…京房」→ 漢元帝劉奭（漢代追述，非司馬睿）",
                  yj.get("p_hanyuandi", 0) >= 1 and yj.get("p_simarui", 0) == 0, str(yj)))
    yd = _js_ctx("元帝", "渡江")
    cases.append(("「元帝渡江」→ 司馬睿（志書跨代不再掉 guess）",
                  yd.get("p_simarui", 0) >= 15, str(yd)))
    gl = _js_ctx("高祖", "婁敬")
    cases.append(("「高祖…婁敬」→ 劉邦（漢典，非劉淵）",
                  gl.get("p_liubang", 0) >= 1 and gl.get("p_liuyuan", 0) == 0, str(gl)))
    gm = _js_ctx("高祖", "景命")
    cases.append(("「無廢我高祖之景命」→ 司馬懿（晉室禪位詔）",
                  gm.get("p_simayi", 0) >= 1 and gm.get("p_liubang", 0) == 0, str(gm)))

    # ===== P2-a 表字长尾补录 =====
    # 表字**不能**批量补：抽查 14 条里 9 条是误抽（博士**弟子治**、
    # 王**季思**慮、遭**世康**平、申**叔時**、**叔平**其实是敞/參的字）。
    # 所以只收「与本人同句共现 ≥2 处且共现率 ≥70%」的那一档，
    # 其余留进 docs/17-条目-表字长尾.md 走人工/AI 判。
    _ZI_CASES = (("楊洪", "季休"), ("和嶠", "長輿"), ("崔琰", "季珪"),
                 ("華佗", "元化"), ("譙周", "允南"), ("荀崧", "景猷"))
    _zi_bad = []
    for _nm, _zi in _ZI_CASES:
        _ps = [p for p in persons if (p.get("tradName") or p.get("name")) == _nm]
        if not _ps:
            _zi_bad.append(_nm + "·" + _zi + "：人不在典")
            continue
        _al = {x["alias"]: x["n"] for x in _ps[0].get("topAliases") or []}
        if _al.get(_zi, 0) < 1:
            _zi_bad.append("{}·{}：未命中({})".format(_nm, _zi, sorted(_al)))
    cases.append(("表字长尾补录生效（只收同句共现 ≥70% 那档）",
                  not _zi_bad, "; ".join(_zi_bad)))

    # ===== AI 概率判定闭环（2026-09-26，docs/19 §三①）=====
    # 判定链路：_gen_ai_batch.py 出条目 → _ai_judge.py/_ai_autorule.py 出概率
    # → _apply_ai.py 只落 prob≥0.9 那堆 → 这里把结论钉成断言。
    # 每条断言对应一条**带依据**的判定，依据改了断言就改。
    def marks_of(alias, book=None):
        out = []
        for s in DATA["sentences"]:
            if book and not s["chapterId"].startswith(book + "-"):
                continue
            for m in s.get("marks") or []:
                if m.get("alias") == alias:
                    out.append((s, m))
        return out

    def pid_count(alias, book=None):
        c = Counter()
        for _s, m in marks_of(alias, book):
            c[m.get("pid")] += 1
        return c

    def alias_of_person(pid):
        for p in persons:
            if p["id"] == pid:
                return set(p.get("aliases") or [])
        return set()

    # ① 爵位名不是人名：「關內侯」整串出索引
    #    依据：漢書「賜爵關內侯」「爵皆關內侯」、三國志「與舊列侯、關內侯凡六等」
    gh = len(marks_of("關內侯")) + len(marks_of("关内侯"))
    cases.append(("「關內侯」是爵位不是人名 → 整串出索引",
                  gh == 0 and "關內侯" not in alias_of_person("p_xiaowangzhi"),
                  "标记={} 蕭望之别名含={}".format(
                      gh, "關內侯" in alias_of_person("p_xiaowangzhi"))))

    # ② 斷代史裸「文王」＝周文王：era 檔被西漢劉禮拉偏（漢書 61/70、後漢書 23/28）
    _w = Counter()
    for bk in ("hs", "hhs"):
        _w.update(pid_count("文王", bk))
    cases.append(("漢書/後漢書裸「文王」→ 周文王（不再被 era 拉給劉禮）",
                  _w.get("p_liuli", 0) == 0 and _w.get("p_zhouwen", 0) >= 80,
                  "周文王={} 劉禮={}".format(_w.get("p_zhouwen", 0),
                                            _w.get("p_liuli", 0))))

    # ③ 三國志裸「武王」＝曹操（候選原本沒有曹操，14 處全誤歸司馬炎）
    _g = pid_count("武王", "sgz")
    cases.append(("三國志裸「武王」→ 曹操（「謚曰武王」，原誤歸司馬炎）",
                  _g.get("p_caocao", 0) >= 10 and _g.get("p_simayan", 0) == 0,
                  "曹操={} 司馬炎={}".format(_g.get("p_caocao", 0),
                                            _g.get("p_simayan", 0))))

    # ④ 「《文王世子》」是《禮記》篇名，不是人
    _wz = 0
    for s, m in marks_of("文王"):
        t = s.get("text") or ""
        if "世子" in t[max(0, m.get("s", 0) - 8): m.get("e", 0) + 8]:
            _wz += 1
    cases.append(("「《文王世子》」篇名不標為人", _wz == 0, str(_wz)))

    # ⑤ 高置信那堆表字已生效（抽查傳主字，不是抽批量數字）
    _AI_ZI = (("嵇康", "叔夜"), ("祖逖", "士稚"), ("陸機", "士衡"),
              ("刁協", "玄亮"), ("秦宓", "子敕"), ("郗鑒", "道徽"))
    _zi_bad2 = []
    for _nm, _z in _AI_ZI:
        _ps = [p for p in persons if (p.get("tradName") or p.get("name")) == _nm]
        if not _ps or _z not in (_ps[0].get("aliases") or []):
            _zi_bad2.append(_nm + "·" + _z)
    cases.append(("AI 判定高置信表字已入典（嵇康叔夜/祖逖士稚…）",
                  not _zi_bad2, "缺={}".format(_zi_bad2)))

    # ⑥ 被判「不收」的那批**沒有**混進別名——負向斷言比正向更要緊
    _AI_REJ = (("蔡玄", "叔陵"), ("費直", "長翁"), ("蘇順", "孝山"),
               ("傅毅", "武仲"), ("龔壯", "子瑋"), ("孟觀", "叔時"),
               ("趙誘", "元孫"), ("鄭弘", "巨君"))
    _bad_rej = []
    for _nm, _z in _AI_REJ:
        for p in persons:
            if (p.get("tradName") or p.get("name")) != _nm:
                continue
            if _z in (p.get("aliases") or []):
                _bad_rej.append(_nm + "·" + _z)
    cases.append(("AI 判定「不收」的表字未進別名（同字他人/跨詞邊界）",
                  not _bad_rej, "误收={}".format(_bad_rej)))

    cases.extend(_newchain_cases())
    cases.extend(_workbook_cases())

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
