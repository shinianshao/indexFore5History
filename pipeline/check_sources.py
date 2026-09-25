# -*- coding: utf-8 -*-
"""检测古籍语料源在当前网络下的可访问性。

用途：确认本地网络能否直连各公版古籍源，决定管线采用哪种抓取策略。
"""
import ssl
import urllib.request

SOURCES = [
    ("维基文库 站点", "https://zh.wikisource.org/wiki/Special:Version"),
    ("维基文库 API", "https://zh.wikisource.org/w/api.php?action=query&format=json&meta=siteinfo"),
    ("ctext.org", "https://ctext.org/"),
    ("古诗文网", "https://www.gushiwen.cn/"),
    ("百度（网络基线）", "https://www.baidu.com/"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def check(name, url, ctx):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            body = resp.read(4096)
            print("[OK]   {:<22} status={} bytes={}".format(name, resp.status, len(body)))
            return True
    except Exception as exc:
        print("[FAIL] {:<22} {}: {}".format(name, type(exc).__name__, exc))
        return False


def main():
    ctx = ssl.create_default_context()
    print("== 语料源连通性检测 ==")
    results = [check(name, url, ctx) for name, url in SOURCES]
    print("\n可用源数量: {}/{}".format(sum(results), len(results)))


if __name__ == "__main__":
    main()
