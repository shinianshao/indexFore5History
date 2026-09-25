# -*- coding: utf-8 -*-
"""抓取《史记》目录，生成「卷号 -> 篇名」映射。

维基文库主页目录结构：
    <li><a href=".../卷001" title="史記/卷001">卷一</a>　　　　　五帝本紀第一</li>
篇名在 </a> 之后的文本里，需要去掉末尾的序号（第一、第二...）。

产物：data/dict/volumes.json
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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
DICT = os.path.join(ROOT, "data", "dict")

ENTRY_RE = re.compile(r'<a\b[^>]*?href="([^"]*)"[^>]*?>([^<]*)</a>([^<]{0,40})')
VOL_RE = re.compile(r"史記/卷(\d{3})")
ORDINAL_RE = re.compile(r"第[〇零一二三四五六七八九十百千]+$")
SPACE_RE = re.compile(r"[\s\u3000]+")


def api(params):
    params = dict(params)
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    os.makedirs(DICT, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)
    res = api({"action": "parse", "page": "史記", "prop": "text", "redirects": 1})
    html = res["parse"]["text"]["*"]
    with open(os.path.join(RAW, "_main.html"), "w", encoding="utf-8") as fh:
        fh.write(html)

    mapping = {}
    matched = 0
    for match in ENTRY_RE.finditer(html):
        href = urllib.parse.unquote(match.group(1))
        found = VOL_RE.search(href)
        if not found:
            continue
        matched += 1
        volume = int(found.group(1))
        if volume in mapping:
            continue
        tail = SPACE_RE.sub("", match.group(3))
        tail = ORDINAL_RE.sub("", tail)
        if tail:
            mapping[volume] = tail

    with open(os.path.join(DICT, "volumes.json"), "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, ensure_ascii=False, indent=2)

    preview = {str(k): mapping[k] for k in sorted(mapping)[:15]}
    with open(os.path.join(ROOT, "pipeline", "_meta_preview.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "matched_entries": matched,
                "mapped": len(mapping),
                "first15": preview,
                "missing": [v for v in range(1, 131) if v not in mapping][:10],
            },
            fh, ensure_ascii=False, indent=2,
        )


if __name__ == "__main__":
    main()
