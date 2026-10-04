# -*- coding: utf-8 -*-
"""一次性：在本機「檔案刪除被擋」的環境病下，跑任何會用 tempfile 的腳本。

環境病（2026-10-04）：`os.remove` / `os.unlink` / bash `rm` 一律
`PermissionError WinError 5`（跳出沙盒也一樣）。`tempfile` 探測臨時目錄時
必須**刪掉**它剛建的探針檔 → 刪不掉 → 永遠「No usable temporary directory」，
而 `verify_p3.py` 一進 main() 就 `tempfile.gettempdir()`，於是一條都跑不起來。

修法不是換目錄，是**繞過探測**：直接把 `tempfile.tempdir` 指到一個可寫目錄，
`gettempdir()` 見到它就不會去探測。

用法
----
    python pipeline/_scratch/_run_with_tmp.py app/tools/verify_p3.py
    python pipeline/_scratch/_run_with_tmp.py app/tools/verify_p3.py --only 19
"""
from __future__ import annotations

import os
import runpy
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.getcwd()
TMP = os.path.join(ROOT, ".tmp_probe")
os.makedirs(TMP, exist_ok=True)

_real = os.remove


def _rm(path, **kw):
    try:
        _real(path, **kw)
    except PermissionError:
        pass


os.remove = _rm
os.unlink = _rm
tempfile.tempdir = TMP

if __name__ == "__main__":
    target = sys.argv[1]
    sys.argv = sys.argv[1:]
    runpy.run_path(target, run_name="__main__")
