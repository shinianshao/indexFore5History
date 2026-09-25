# -*- coding: utf-8 -*-
"""从维基文库抓取《史记》指定卷，保存原始 HTML。

维基文库的 MediaWiki API 有速率限制，连续抓取会返回 429 Too Many Requests。
因此这里做三件事：
  1. 请求间隔保守（默认 2.5 秒）
  2. 遇 429/5xx 指数退避重试（15s → 30s → 60s …）
  3. 全量跑完后，对失败卷再做一轮补抓（间隔加倍）

用法：
    python fetch.py                  抓取默认范围（卷001-卷010）
    python fetch.py 1 130            抓取卷001-卷130
    python fetch.py 1 130 3.0        同上，请求间隔 3 秒
已有且大于 500 字节的会自动跳过，因此重复执行等价于「补抓缺失」。

命名：data/raw/sj-008.html
"""
import json
import os
import sys
import time
import urllib.error
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

BOOK = "史記"
BOOK_CODE = "sj"
DEFAULT_DELAY = 2.5
RETRY_BACKOFF = (15, 30, 60, 90, 120)


def api(params, retries=5):
    """带退避的 API 请求；429/5xx 会等待后重试。"""
    params = dict(params)
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                sys.stderr.write("  {} -> 等待 {}s 后重试\n".format(exc, wait))
                time.sleep(wait)
                continue
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("API 请求失败: {}".format(last))


def fetch_volume(volume):
    page = "{}/卷{:03d}".format(BOOK, volume)
    res = api({"action": "parse", "page": page, "prop": "text", "redirects": 1})
    html = res["parse"]["text"]["*"]
    path = os.path.join(RAW, "{}-{:03d}.html".format(BOOK_CODE, volume))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return page, len(html)


def main():
    args = sys.argv[1:]
    delay = float(args[2]) if len(args) >= 3 else DEFAULT_DELAY
    start, end = (int(args[0]), int(args[1])) if len(args) >= 2 else (1, 10)
    os.makedirs(RAW, exist_ok=True)

    def path_of(volume):
        return os.path.join(RAW, "{}-{:03d}.html".format(BOOK_CODE, volume))

    log = {}
    # 第一轮：跳过已有，抓取缺失
    for volume in range(start, end + 1):
        if os.path.exists(path_of(volume)) and os.path.getsize(path_of(volume)) > 500:
            log[volume] = {"volume": volume, "status": "skip"}
            continue
        try:
            page, size = fetch_volume(volume)
            log[volume] = {"volume": volume, "status": "ok", "page": page, "bytes": size}
        except Exception as exc:  # noqa: BLE001
            log[volume] = {"volume": volume, "status": "fail", "error": str(exc)}
        time.sleep(delay)

    # 第二轮：对失败卷补抓，间隔加倍
    retry = [v for v in sorted(log) if log[v]["status"] == "fail"]
    if retry:
        sys.stderr.write("补抓失败卷 {}: {}\n".format(len(retry), retry))
        time.sleep(delay * 2)
        for volume in retry:
            try:
                page, size = fetch_volume(volume)
                log[volume] = {"volume": volume, "status": "ok-retry",
                               "page": page, "bytes": size}
            except Exception as exc:  # noqa: BLE001
                log[volume] = {"volume": volume, "status": "fail-retry", "error": str(exc)}
            time.sleep(delay * 2)

    detail = [log[v] for v in sorted(log)]
    summary = {
        "ok": sum(1 for x in detail if x["status"].startswith("ok")),
        "skip": sum(1 for x in detail if x["status"] == "skip"),
        "fail": sum(1 for x in detail if x["status"].startswith("fail")),
        "failedVolumes": [x["volume"] for x in detail if x["status"].startswith("fail")],
        "detail": detail,
    }
    with open(os.path.join(ROOT, "pipeline", "_fetch_log.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
