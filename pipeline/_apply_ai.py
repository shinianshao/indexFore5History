# -*- coding: utf-8 -*-
"""AI 概率判定闭环 · 第 4 段：把判定**落地**到 build_dict.py。

只对 **高置信堆（prob ≥ 0.9）** 动手，且每种 action 的落点写死：

| action   | 落点 |
|----------|------|
| `alias`  | 表字补进 `PERSONS` 该人的别名表（繁体＋OpenCC 简体） |
| `drop`   | 从 `GENERIC_MANUAL`、`GENERIC_DEFAULT` 摘掉，并从所有人别名表里摘掉 |
| `bookcand` | `GENERIC_BOOK_CANDIDATES["称号"]["书"] = [pid]`（必要时先补进 `GENERIC_MANUAL`） |
| `ctxrule` | `GENERIC_CONTEXT_RULES["称号"]` 追加一条 |
| `keep` / `reject` / `unknown` | **不动**（unknown 走人工复核清单） |

为什么只动高置信堆：中堆要人看，低堆是「判不了」，硬归就是伪称。
这是 docs/17 §一「能修 / 仍歧义 / 难判断」三层里第一层的机械执行。

安全网
------
- 改前先写 `build_dict.py.bak`；
- 改完立刻 `ast.parse` 校验语法——**语法不过就直接报错退出**，
  绝不留一个半坏的词典文件给下一轮；
- 幂等：已存在的别名/规则跳过，重复跑不会叠加。

用法
----
    python pipeline/_apply_ai.py            # 预演（默认不写盘）
    python pipeline/_apply_ai.py --apply    # 真写
    python pipeline/_apply_ai.py --min 0.85 # 放宽阈值（谨慎）
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"
BATCH = ROOT / "pipeline" / "_ai_batch.json"

try:
    from opencc import OpenCC
    _t2s = OpenCC("t2s").convert
except Exception:                                    # pragma: no cover
    def _t2s(s):
        return s


# ---------------------------------------------------------------------------
# PERSONS 行级编辑（沿用 _apply_zi_fill.py 的写法：两种引号都要认）
# ---------------------------------------------------------------------------
def add_person_alias(lines, pid, forms):
    pat = re.compile(r"\s*\(['\"]p_")
    qpid = "'{}'".format(pid), '"{}"'.format(pid)
    for i, line in enumerate(lines):
        if not pat.match(line):
            continue
        if qpid[0] not in line and qpid[1] not in line:
            continue
        m = re.search(r"\[([^\]]*)\]", line)
        if not m:
            continue
        cur = re.findall(r'["\']([^"\']+)["\']', m.group(1))
        added = [f for f in forms if f not in cur]
        if not added:
            return False, "已在"
        new_list = "[" + ", ".join('"{}"'.format(x) for x in cur + added) + "]"
        lines[i] = line[: m.start()] + new_list + line[m.end():]
        return True, "+{}".format("/".join(added))
    return False, "找不到 PERSONS 行"


# ---------------------------------------------------------------------------
# 字典块级编辑：在 `NAME = {` 里定位 `    "key": ...` 到它的闭合
# ---------------------------------------------------------------------------
def block_span(text, name):
    m = re.search(r"^{} = \{{$".format(name), text, re.M)
    if not m:
        return None
    i = text.index("{", m.start())
    depth, j = 0, i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return (m.start(), i, j)
        j += 1
    return None


def entry_span(text, start, end, key):
    """在 [start,end) 内找 `    "key": <...>` 的起止行下标。"""
    # re.M 必须有：^ 要匹配**行首**，不是整个文件开头（漏了它这函数永远找不到项）
    pat = re.compile(r'^\s{4}"' + re.escape(key) + r'":\s*', re.M)
    m = pat.search(text, start, end)
    if not m:
        return None
    # 从值开头起做括号配平，找到这一项的结尾（逗号或换行）
    k = m.end()
    if text[k] == "[":
        depth = 0
        while k < end:
            if text[k] == "[":
                depth += 1
            elif text[k] == "]":
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
    elif text[k] == "{":
        depth = 0
        while k < end:
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
    else:                                   # 标量：吃到行尾
        k = text.index("\n", k)
    return (m.start(), k)


def remove_entry(text, block, key):
    start, _i, end = block
    sp = entry_span(text, start, end, key)
    if not sp:
        return text, False
    a, b = sp
    # 连同行尾换行一起删
    b = text.index("\n", b) + 1 if "\n" in text[b:b + 2] else b
    # 若上一行是注释行，一并保留（注释不动，宁可留着也不删错）
    return text[:a] + text[b:], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min", type=float, default=0.9)
    ap.add_argument("--batch", default=str(BATCH))
    a = ap.parse_args()

    b = json.loads(Path(a.batch).read_text(encoding="utf-8"))
    hi = [it for it in b["items"]
          if it.get("ai") and (it["ai"].get("prob") or 0) >= a.min
          and it["ai"].get("action") in ("alias", "drop", "bookcand", "ctxrule")]
    print("高置信待落地 {} 条（阈值 {}）".format(len(hi), a.min))

    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    done, skipped = [], []

    # ---- alias：表字补进 PERSONS ----
    for it in hi:
        if it["ai"]["action"] != "alias":
            continue
        pid = it["ai"].get("target") or it["person"]["pid"]
        zi = it["ai"].get("form") or it["surface"]
        forms = [zi]
        s = _t2s(zi)
        if s != zi:
            forms.append(s)
        ok, why = add_person_alias(lines, pid, forms)
        (done if ok else skipped).append(
            "{}「{}」{}".format(pid, zi, why if ok else "——" + why))

    text = "".join(lines)

    # ---- drop：从泛称表与人的别名里摘掉 ----
    drops = [it for it in hi if it["ai"]["action"] == "drop"]
    for it in drops:
        alias = it["surface"]
        for block_name in ("GENERIC_MANUAL", "GENERIC_DEFAULT"):
            blk = block_span(text, block_name)
            if blk:
                text, ok = remove_entry(text, blk, alias)
                if ok:
                    done.append("{} 摘掉 {}".format(block_name, alias))
        # 从所有人别名表里摘
        n = 0
        for pat in ('"' + alias + '", ', ', "' + alias + '"',
                    '"' + alias + '"', "'" + alias + "'"):
            n += text.count(pat)
        text = re.sub(r'(?<=[\[,])\s*"' + re.escape(alias) + r'"\s*,\s*', "", text)
        text = re.sub(r',\s*"' + re.escape(alias) + r'"(?=\])', "", text)
        text = re.sub(r'(?<=[\[,])\s*\'' + re.escape(alias) + r'\'\s*,\s*', "", text)
        text = re.sub(r',\s*\'' + re.escape(alias) + r'\'(?=\])', "", text)
        done.append("别名表摘掉「{}」（原文出现 {} 次子串）".format(alias, n))

    # ---- bookcand：分书收束 ----
    for it in hi:
        if it["ai"]["action"] != "bookcand":
            continue
        alias, book = it["surface"], it["book"]
        pid = it["ai"]["target"]
        # ① 目标必须在 GENERIC_MANUAL 候选里，否则收束不生效
        blk = block_span(text, "GENERIC_MANUAL")
        if blk:
            sp = entry_span(text, blk[0], blk[2], alias)
            if sp and pid not in text[sp[0]:sp[1]]:
                seg = text[sp[0]:sp[1]]
                new = re.sub(r"\]$", ', "{}"]'.format(pid), seg.rstrip())
                text = text[:sp[0]] + new + text[sp[1]:]
                done.append("GENERIC_MANUAL[{}] += {}".format(alias, pid))
        # ② 写 GENERIC_BOOK_CANDIDATES
        blk = block_span(text, "GENERIC_BOOK_CANDIDATES")
        if not blk:
            skipped.append("找不到 GENERIC_BOOK_CANDIDATES")
            continue
        sp = entry_span(text, blk[0], blk[2], alias)
        if sp:
            seg = text[sp[0]:sp[1]]
            m = re.search(r'"' + re.escape(book) + r'":\s*\[[^\]]*\]', seg)
            if m:
                new = seg[:m.start()] + '"{}": ["{}"]'.format(book, pid) + seg[m.end():]
            else:
                # 插到该称号 dict 闭合前
                k = seg.rstrip().rfind("}")
                new = (seg[:k] + '        "{}": ["{}"],\n    '.format(book, pid)
                       + seg[k:])
            text = text[:sp[0]] + new + text[sp[1]:]
        else:
            k = blk[2]
            ins = '\n    "{}": {{\n        "{}": ["{}"],\n    }},'.format(
                alias, book, pid)
            text = text[:k] + ins + text[k:]
        done.append("GENERIC_BOOK_CANDIDATES[{}][{}] = [{}]".format(alias, book, pid))

    # ---- ctxrule ----
    for it in hi:
        if it["ai"]["action"] != "ctxrule":
            continue
        alias = it["surface"]
        ev = it["ai"].get("evidence", "")
        # 依据里形如「加 window 規則「世子」→ none」：抓出关键词与目标
        m = re.search(r"[「\[]([^」\]]+)[」\]]\s*→\s*(\w+|none)", ev)
        if not m:
            skipped.append("ctxrule 依据里读不出 (关键词, 目标)：{}".format(alias))
            continue
        key, tgt = m.group(1), m.group(2)
        tgt = "None" if tgt.lower() == "none" else '"{}"'.format(tgt)
        blk = block_span(text, "GENERIC_CONTEXT_RULES")
        if not blk:
            skipped.append("找不到 GENERIC_CONTEXT_RULES")
            continue
        sp = entry_span(text, blk[0], blk[2], alias)
        rule = '        ("window", "{}", {}),\n'.format(key, tgt)
        if sp:
            seg = text[sp[0]:sp[1]]
            if key in seg:
                skipped.append("ctxrule {}/{} 已存在".format(alias, key))
                continue
            k = seg.rstrip().rfind("]")
            text = text[:sp[0]] + seg[:k] + rule + "    " + seg[k:] + text[sp[1]:]
        else:
            k = blk[2]
            text = (text[:k] + '\n    "{}": [\n{}    ],'.format(alias, rule)
                    + text[k:])
        done.append("GENERIC_CONTEXT_RULES[{}] += window/{}->{}".format(alias, key, tgt))

    # ---- 校验 + 写盘 ----
    try:
        ast.parse(text)
    except SyntaxError as e:                        # 语法不过就别写
        print("\n✗ 改完语法不过，未写盘：line {} {}".format(e.lineno, e.msg))
        print("  ", (text.splitlines()[e.lineno - 1] if e.lineno else "")[:120])
        sys.exit(1)

    print("\n落地 {} 项：".format(len(done)))
    # 泛称类的改动影响面大，先打出来；别名是大批量的，只报条数
    for d in done:
        if d.startswith("p_"):
            continue
        print("  ★", d)
    n_alias = sum(1 for d in done if d.startswith("p_"))
    print("  · 表字补录 {} 条（明细见 --verbose）".format(n_alias))
    if "-v" in sys.argv or "--verbose" in sys.argv:
        for d in done:
            if d.startswith("p_"):
                print("    ", d)
    if skipped:
        print("\n跳过 {} 项：".format(len(skipped)))
        for s in skipped[:20]:
            print("  !", s)

    if a.apply:
        shutil.copyfile(BD, str(BD) + ".bak")
        BD.write_text(text, encoding="utf-8")
        print("\n已写入 {}（备份 build_dict.py.bak）".format(BD))
    else:
        print("\n（预演，未写盘；加 --apply 真写）")


if __name__ == "__main__":
    main()
