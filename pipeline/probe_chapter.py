# -*- coding: utf-8 -*-
"""抓取《史记·卷008 高祖本纪》样本，分析正文 HTML 结构。

用于确定正文提取规则，输出 _probe_chapter.json（UTF-8）。
"""
import json
import os
import re
import urllib.parse
import urllib.request

API = "https://zh.wikisource.org/w/api.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
ROOT = r"C:\Users\dell\WorkBuddy\WeChatAPP-BOOKINDEX"
RAW = os.path.join(ROOT, "data", "raw")

TAG_RE = re.compile(r"<[^>]+>")


def api(params):
    params = dict(params)
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def strip_tags(text):
    text = TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def main():
    os.makedirs(RAW, exist_ok=True)
    res = api({"action": "parse", "page": "史記/卷008", "prop": "text", "redirects": 1})
    html = res["parse"]["text"]["*"]

    html_path = os.path.join(RAW, "_probe_sj008.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    body_start = html.find('class="mw-parser-output"')
    body = html[body_start:] if body_start >= 0 else html

    report = {
        "page": res["parse"].get("title"),
        "html_len": len(html),
        "body_len": len(body),
        "counts": {
            "p": len(re.findall(r"<p[ >]", body)),
            "div": len(re.findall(r"<div[ >]", body)),
            "br": len(re.findall(r"<br", body)),
            "table": len(re.findall(r"<table[ >]", body)),
            "h2": len(re.findall(r"<h2[ >]", body)),
        },
        "p_samples": [],
        "div_samples": [],
    }

    for chunk in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)[:6]:
        report["p_samples"].append(strip_tags(chunk)[:260])

    for chunk in re.findall(r"<div class=\"[^\"]*\"[^>]*>(.*?)</div>", body, re.S)[:6]:
        report["div_samples"].append(strip_tags(chunk)[:260])

    plain = strip_tags(body)
    report["plain_len"] = len(plain)
    report["plain_head"] = plain[:600]

    with open(os.path.join(ROOT, "pipeline", "_probe_chapter.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
