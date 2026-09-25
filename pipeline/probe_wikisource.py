# -*- coding: utf-8 -*-
"""探测维基文库《史记》的页面组织方式，为抓取脚本确定入口。

输出写入 _probe.json（UTF-8），避免控制台编码问题。
"""
import json
import urllib.parse
import urllib.request

API = "https://zh.wikisource.org/w/api.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
OUT = r"C:\Users\dell\WorkBuddy\WeChatAPP-BOOKINDEX\pipeline\_probe.json"


def api(params):
    params = dict(params)
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    report = {}

    candidates = ["史記", "史記/卷001", "史記/卷一", "史記/卷1", "史記/五帝本紀", "史記/高祖本紀"]
    res = api({"action": "query", "titles": "|".join(candidates), "redirects": 1})
    report["candidates"] = [
        {
            "title": p.get("title"),
            "pageid": p.get("pageid"),
            "exists": "missing" not in p,
        }
        for p in res.get("query", {}).get("pages", {}).values()
    ]

    res2 = api({"action": "query", "list": "allpages", "apprefix": "史記/", "aplimit": 60})
    report["subpages"] = [p["title"] for p in res2.get("query", {}).get("allpages", [])]

    try:
        res3 = api({"action": "parse", "page": "史記", "prop": "text", "redirects": 1})
        html = res3.get("parse", {}).get("text", {}).get("*", "")
        report["main_page_html_len"] = len(html)
        report["main_page_html_head"] = html[:3000]
    except Exception as exc:
        report["main_page_error"] = "{}: {}".format(type(exc).__name__, exc)

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
