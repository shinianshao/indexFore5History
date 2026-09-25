# -*- coding: utf-8 -*-
"""多书抓取：按书注册表从维基文库抓原始 HTML，并顺带产出篇名表。

为什么单独起一个脚本，而不是改 fetch.py
--------------------------------------
fetch.py 是《史记》专用且已跑完（卷号是 int、页面 = 史記/卷{:03d}）。
《汉书》的卷号形态不规则（015b / 027下之上 / 099中 / 100下），且存在
**重定向**（实测 19 个：卷001上、卷001下 → 卷001，卷027中之上 → 卷027）。
硬改 fetch.py 会同时动到两条路径，所以这里写成通用版，跑通后再决定是否合并。

两件容易踩的事（都是实测）
------------------------
1. **必须先解析重定向再抓**：不解析会把同一卷抓三遍，正文重复进语料。
   实测 131 个子页面里 19 个是重定向，去重后 108 个规范卷页。
2. **非卷页要排除**：景祐刊本校語 / 漢書敘例 是编者文字，
   韓彭英盧吳傳 / 髙惠髙后文功臣表 是与正卷重复的别本转录，均不入库。

产物
----
    data/raw/{code}-{slug}.html          原始 HTML
    data/dict/volumes/{code}.json        {slug: 篇名}
    pipeline/_fetch_{code}_log.json      抓取台账

用法
----
    python fetch_book.py --book hs                 # 抓全书（后台跑）
    python fetch_book.py --book hs --map-only      # 只解析卷表，不抓
    python fetch_book.py --book hs --limit 5       # 试跑前 5 卷
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
VOLDIR = os.path.join(ROOT, "data", "dict", "volumes")

API = "https://zh.wikisource.org/w/api.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# 书注册表。与 docs/03 的设计一致：新增书只改这里。
BOOKS = {
    "sj": {"code": "sj", "name": "史記", "prefix": "史記/卷"},
    "hs": {"code": "hs", "name": "漢書", "prefix": "漢書/卷"},
    "hhs": {"code": "hhs", "name": "後漢書", "prefix": "後漢書/卷"},
    "sgz": {"code": "sgz", "name": "三國志", "prefix": "三國志/卷"},
    "js": {"code": "js", "name": "晉書", "prefix": "晉書/卷"},
}

DEFAULT_DELAY = 2.5
RETRY_BACKOFF = (15, 30, 60, 90, 120)
MIN_BYTES = 500

TAG_RE = re.compile(r"<[^>]+>")
NUM_CN = "一二三四五六七八九十百零"
# 导航条形态：◄漢書卷一高帝紀第一►
NAV_RE = re.compile(r"◄\s*(.{1,40}?)\s*►")


def api(params, retries=6):
    params = dict(params)
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                sys.stderr.write("  {} -> 等待 {}s\n".format(exc, wait))
                time.sleep(wait)
                continue
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001
            # 实测会出 urlopen error Tunnel connection failed: 502
            last = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("API 请求失败: {}".format(last))


def list_subpages(book_name):
    """列出该书全部子页面标题。"""
    pages, cont = [], None
    while True:
        params = {"action": "query", "list": "allpages",
                  "apprefix": book_name + "/", "aplimit": "500"}
        if cont:
            params["apcontinue"] = cont
        data = api(params)
        pages += [x["title"] for x in data["query"]["allpages"]]
        if "continue" in data:
            cont = data["continue"]["apcontinue"]
        else:
            break
    return pages


def canonical_volumes(book):
    """返回 (slugs, redirects, others)。

    slugs      —— 规范卷页的 slug（去掉「書名/卷」前缀），已去重、已排序
    redirects  —— {原名: 目标名}（说明哪些页被合并掉了）
    others     —— 非卷页（不入库）
    """
    name, prefix = book["name"], book["prefix"]
    pages = list_subpages(name)
    canon, redirects = set(), {}
    for i in range(0, len(pages), 40):
        batch = pages[i:i + 40]
        data = api({"action": "query", "titles": "|".join(batch),
                    "redirects": 1, "prop": "info"})
        for r in data["query"].get("redirects", []):
            redirects[r["from"]] = r["to"]
        for page in data["query"]["pages"].values():
            if "missing" not in page:
                canon.add(page["title"])
        time.sleep(0.6)
    slugs, others = [], []
    for title in sorted(canon):
        if title.startswith(prefix):
            slugs.append(title[len(prefix):])
        else:
            others.append(title)
    return slugs, redirects, others


def sort_key(slug):
    """卷 slug 排序键：(卷号, 子序号)。

    汉书 slug 形态不规则，必须既能排 001 也能排 015b / 027下之上 / 099中：
        无后缀 0 < 上 1 < 中 2 < 下 3 < 其它 5 < b 9
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


def cn_number(n):
    """整数 → 中文数字（1..999）。用于「按卷号精确剥掉卷号」。

    为什么需要它：篇名本身也可能以数字开头（「十二諸侯年表」「三代世表」），
    用 lstrip(数字集) 或「解析中文数字」都会误吃篇名首字。
    但**卷号是已知的**（来自 slug），所以反过来——
    先算出该卷号对应的中文数字，再精确剥掉它，篇名就不会被误伤。
    """
    digits = "零一二三四五六七八九"
    if n <= 0:
        return ""
    out = ""
    wrote_hundred = False
    if n >= 100:
        out += digits[n // 100] + "百"
        n %= 100
        wrote_hundred = True
        if 0 < n < 10:
            out += "零"
    if n >= 20:
        out += digits[n // 10] + "十"
        n %= 10
    elif n >= 10:
        # 百位之后「一十」要带「一」：维基文库写「卷一百一十」，不是「卷一百十」。
        # 实测这条让 110–130 那 21 卷从全错变全对。
        out += "一十" if wrote_hundred else "十"
        n -= 10
    if n:
        out += digits[n]
    return out


def parse_title(html, book_name, volume_num):
    """从导航条抽出篇名；抽不到返回空串（由调用方兜底为「卷XXX」）。

    导航条形如「◄漢書卷一高帝紀第一►」。处理顺序刻意如此：
        书名（含异写 太史公書） → 「卷/巻」 → **卷号**（按已知卷号精确剥）
        → 夹注〈第十八〉 → 末尾「第N」

    用《史记》130 卷的既有篇名表对账：与人工审定值一致 122/130（93.8%），
    其余 8 条是**辑录取名差异**（维基作「呂太后本紀」，本工程作「呂后本紀」；
    「衞康叔世家」的 衞/衛 异写等），不是抽取错误——
    与本项目「挖掘器只负责召回，精确性由人审读」的规矩一致。
    """
    text = re.sub(r"\s+", "", TAG_RE.sub("", html))
    m = NAV_RE.search(text)
    if not m:
        return ""
    seg = m.group(1)
    if book_name in seg:
        seg = seg.split(book_name, 1)[1]
    if seg[:1] in ("卷", "巻"):          # 「巻」是「卷」的异写，语料里两种都有
        seg = seg[1:]
    cn = cn_number(volume_num)
    if cn and seg.startswith(cn):
        seg = seg[len(cn):]
    for alias in ("太史公書", "太史公书"):
        if seg.startswith(alias):
            seg = seg[len(alias):]
    seg = re.sub(r"〈[^〉]*〉", "", seg)
    # 晋书导航只给「帝紀第一」「列傳第十三」——剥掉「第N」后只剩体例词，
    # 无法区分卷，故体例词+序号整段保留（如 帝紀第一 / 載記第一）。
    m_ord = re.search(r"(第[" + NUM_CN + r"]+)$", seg)
    if m_ord:
        body = seg[: m_ord.start()]
        if body in ("帝紀", "列傳", "志", "載記", "傳", "紀"):
            return seg
        seg = body
    return seg


def slug_number(slug):
    """slug → 卷号整数。「015b」→ 15、「027下之上」→ 27。"""
    m = re.match(r"^(\d+)", slug)
    return int(m.group(1)) if m else 0


def main():
    args = sys.argv[1:]
    code = "hs"
    if "--book" in args:
        code = args[args.index("--book") + 1]
    if code not in BOOKS:
        raise SystemExit("未知书代码 {}，已知：{}".format(code, ",".join(BOOKS)))
    book = BOOKS[code]
    delay = float(args[args.index("--delay") + 1]) if "--delay" in args else DEFAULT_DELAY
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 0
    map_only = "--map-only" in args

    os.makedirs(RAW, exist_ok=True)
    os.makedirs(VOLDIR, exist_ok=True)

    print("解析《{}》卷表 …".format(book["name"]))
    slugs, redirects, others = canonical_volumes(book)
    slugs.sort(key=sort_key)
    if limit:
        slugs = slugs[:limit]
    print("  规范卷页 {} 个；重定向 {} 个；非卷页 {}（不入库）".format(
        len(slugs), len(redirects), len(others)))
    for t in others:
        print("    · 排除非卷页：{}".format(t))

    if map_only:
        print("  --map-only，不抓正文")
        return

    titles, log = {}, {}
    for idx, slug in enumerate(slugs, 1):
        out_path = os.path.join(RAW, "{}-{}.html".format(code, slug))
        page = "{}/卷{}".format(book["name"], slug)
        if os.path.exists(out_path) and os.path.getsize(out_path) > MIN_BYTES:
            log[slug] = {"slug": slug, "status": "skip"}
            try:
                with open(out_path, encoding="utf-8") as fh:
                    titles[slug] = parse_title(fh.read(), book["name"],
                                               slug_number(slug))
            except Exception:  # noqa: BLE001
                titles[slug] = ""
            continue
        try:
            data = api({"action": "parse", "page": page, "prop": "text",
                        "redirects": 1})
            html = data["parse"]["text"]["*"]
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            titles[slug] = parse_title(html, book["name"], slug_number(slug))
            log[slug] = {"slug": slug, "status": "ok", "bytes": len(html),
                         "title": titles[slug]}
            print("  [{:3d}/{}] {} ok {} bytes  {}".format(
                idx, len(slugs), slug, len(html), titles[slug]))
        except Exception as exc:  # noqa: BLE001
            titles[slug] = ""
            log[slug] = {"slug": slug, "status": "fail", "error": str(exc)}
            print("  [{:3d}/{}] {} FAIL {}".format(idx, len(slugs), slug, exc))
        time.sleep(delay)

    retry = [s for s in slugs if log.get(s, {}).get("status") == "fail"]
    if retry:
        print("补抓失败卷 {} 个".format(len(retry)))
        time.sleep(delay * 2)
        for slug in retry:
            out_path = os.path.join(RAW, "{}-{}.html".format(code, slug))
            try:
                data = api({"action": "parse",
                            "page": "{}/卷{}".format(book["name"], slug),
                            "prop": "text", "redirects": 1})
                html = data["parse"]["text"]["*"]
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(html)
                titles[slug] = parse_title(html, book["name"], slug_number(slug))
                log[slug] = {"slug": slug, "status": "ok-retry", "bytes": len(html),
                             "title": titles[slug]}
            except Exception as exc:  # noqa: BLE001
                log[slug] = {"slug": slug, "status": "fail-retry", "error": str(exc)}
            time.sleep(delay * 2)

    ok = sum(1 for v in log.values() if str(v["status"]).startswith("ok"))
    fail = sum(1 for v in log.values() if str(v["status"]).startswith("fail"))
    skip = sum(1 for v in log.values() if v["status"] == "skip")

    map_path = os.path.join(VOLDIR, "{}.json".format(code))
    with open(map_path, "w", encoding="utf-8") as fh:
        json.dump(titles, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "pipeline", "_fetch_{}_log.json".format(code)),
              "w", encoding="utf-8") as fh:
        json.dump({"ok": ok, "skip": skip, "fail": fail,
                   "redirects": redirects, "others": others,
                   "failedSlugs": [s for s, v in log.items()
                                   if str(v["status"]).startswith("fail")],
                   "detail": [log[s] for s in slugs]},
                  fh, ensure_ascii=False, indent=2)

    empty = [s for s in slugs if not titles.get(s)]
    print("\n抓取完成：ok {} / skip {} / fail {}".format(ok, skip, fail))
    print("篇名表 → {}（{} 条，缺篇名 {}）".format(map_path, len(titles), len(empty)))
    if empty:
        print("  缺篇名的卷：{}".format(", ".join(empty[:20])))


if __name__ == "__main__":
    main()
