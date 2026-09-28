# -*- coding: utf-8 -*-
"""把「人名纠正」判定落到 pipeline/build_dict.py（PERSONS 的唯一来源）。

两种纠正方向不同，别混：

  drop   判定为**根本不是人名**（赵分 / 单于既 / 单门于是兴趣和DEMAND 这种
         切词噪声，仓库部 / 师 ink this 类非人实体）→ 整条从 PERSONS 摘掉。

  rename **自动补人时把名字切短了**——语料里明明写的是「公子棄疾」「公孫戎奴」
         「公子曼滿」，只是提取器只取了前两个字。这时正确做法是**把正名补长**，
         并保留补长前的短串做别名（别处若真有短写法仍旧能收），而不是删条目。

判定清单写在 pipeline/_name_plan.txt，一行一条：

    # 注释
    drop     <正名>                 # 不是人名，删条目
    rename   <正名> <补正后的正名>   # 切短了，补长
    drop-id  <pid>                  # 重名时按 pid 精确删

安全闸门
--------
- 重名（同名异人）的条目拒绝按名字批量处理，必须写 drop-id。
  铁律说不许「跨书同名合并」，这里同理：不许拿名字当唯一键。
- 删之前检查 pid 是否还被 PERSONS 之外的数据结构引用，有引用就拒绝。
- 默认只预演，写文件要显式 --apply。

用法
----
    python pipeline/_apply_names.py            # 预演
    python pipeline/_apply_names.py --apply    # 真改
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "pipeline" / "build_dict.py"
PLAN = ROOT / "pipeline" / "_name_plan.txt"
PEOPLE = ROOT / "data" / "dict" / "people.json"

try:
    from opencc import OpenCC
    _t2s = OpenCC("t2s").convert
except Exception:                                       # pragma: no cover
    def _t2s(s):
        return s


# ('pid', 简体名, 繁体名, 朝代, 头衔, 简介, [别名])
TUPLE = re.compile(
    r"^(?P<ind>\s*)\('(?P<pid>[^']+)', '(?P<nm>[^']*)', '(?P<trad>[^']*)', "
    r"'(?P<dyn>[^']*)', '(?P<title>[^']*)', '(?P<summ>[^']*)', "
    r"(?P<al>\[[^\]]*\])\),$")


def read_plan(path):
    out = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        # 支持行尾注释：证据写在同一行，判定者一眼能对照，脚本只取 # 前的部分
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        act = parts[0]
        if act == "drop" and len(parts) == 2:
            out.append(("drop", parts[1], None, i))
        elif act == "drop-id" and len(parts) == 2:
            out.append(("drop-id", parts[1], None, i))
        elif act == "rename" and len(parts) == 3:
            out.append(("rename", parts[1], parts[2], i))
        else:
            print("  计划第 {} 行：认不出的写法「{}」".format(i, line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not PLAN.exists():
        print("没有计划文件：{}".format(PLAN))
        return
    plan = read_plan(PLAN)
    if not plan:
        print("计划为空：{}".format(PLAN))
        return

    src_lines = SRC.read_text(encoding="utf-8").splitlines()
    people = json.loads(PEOPLE.read_text(encoding="utf-8"))["persons"]
    by_name, name_of = {}, {}
    for p in people:
        tn = p.get("tradName") or ""
        by_name.setdefault(tn, []).append(p["id"])
        name_of[p["id"]] = tn

    # pid 是否出现在 PERSONS 本体之外的**语义结构**里（会悬空的那种）。
    # PERSON_BOOKS_<书> 是给补人条目配的书域表，随行 generated、删人时顺手清掉即可，
    # 不算悬空引用——所以先按「当前属于哪个顶层结构」把行归类再判断。
    head = re.compile(r"^([A-Z_0-9]+)\s*=")
    referenced, owner_of_line = set(), []
    cur = None
    for ln in src_lines:
        m = head.match(ln)
        if m:
            cur = m.group(1)
        owner_of_line.append(cur)
        if cur and cur.startswith("PERSON_BOOKS"):
            continue
        for mm in re.finditer(r'"(p_[a-z0-9_]+)"', ln):
            if "('{}',".format(mm.group(1)) not in ln:
                referenced.add(mm.group(1))

    todo_drop, todo_rename, problems = [], [], []
    for act, arg, new, lineno in plan:
        if act == "drop-id":
            pid = arg
            if pid not in name_of:
                problems.append("第 {} 行：pid「{}」不在词典里".format(lineno, pid))
                continue
            if pid in referenced:
                problems.append("第 {} 行：{} 还被别的数据结构引用，先解引用".format(lineno, pid))
                continue
            todo_drop.append((pid, name_of[pid]))
            continue
        owners = by_name.get(arg, [])
        if not owners:
            problems.append("第 {} 行：「{}」在词典里找不到".format(lineno, arg))
            continue
        if len(owners) > 1:
            problems.append("第 {} 行：「{}」有 {} 个同名条目（{}）——不许按名字批量处理，"
                            "请改用 drop-id <pid>".format(
                                lineno, arg, len(owners), "/".join(owners)))
            continue
        pid = owners[0]
        if act == "drop":
            if pid in referenced:
                problems.append("第 {} 行：{}（{}）还被别的数据结构引用，先解引用".format(
                    lineno, arg, pid))
                continue
            todo_drop.append((pid, arg))
        else:
            todo_rename.append((pid, arg, new))

    if problems:
        print("拦下 {} 个问题：".format(len(problems)))
        for p in problems:
            print("  ! " + p)

    print("\n删除 {} 条 / 补名 {} 条".format(len(todo_drop), len(todo_rename)))
    for pid, nm in todo_drop:
        print("  drop   {:<8s} {}".format(nm, pid))
    for pid, nm, new in todo_rename:
        print("  rename {:<8s} -> {:<10s} ({})".format(nm, new, pid))

    if not a.apply:
        print("\n（预演：加 --apply 才写文件）")
        return
    if problems:
        print("\n有拦下的问题，不写文件。")
        return

    drop_pids = {pid for pid, _ in todo_drop}
    ren_pids = {pid: new for pid, _, new in todo_rename}
    kill, changed, missed = set(), [], []

    for idx, ln in enumerate(src_lines):
        # PERSON_BOOKS_<书>：删掉的条目在这里的尾巴也一并清掉
        if owner_of_line[idx] and owner_of_line[idx].startswith("PERSON_BOOKS"):
            mm = re.match(r'^\s*"([^"]+)":', ln)
            if mm and mm.group(1) in drop_pids:
                kill.add(idx)
            continue
        m = TUPLE.match(ln)
        if not m:
            continue
        pid = m.group("pid")
        if pid in drop_pids:
            kill.add(idx)
            changed.append("删 {}".format(pid))
            continue
        if pid in ren_pids:
            new = ren_pids[pid]
            old = m.group("trad")
            aliases = json.loads(m.group("al"))
            for x in (new, old):
                if x not in aliases:
                    aliases.append(x)
            if new in aliases and old in aliases and aliases.index(new) > 0:
                aliases.remove(new)
                aliases.insert(0, new)
            line = "{}('{}', '{}', '{}', '{}', '{}', '{}', {}),".format(
                m.group("ind"), pid, _t2s(new), new,
                m.group("dyn"), m.group("title"), m.group("summ"),
                json.dumps(aliases, ensure_ascii=False))
            src_lines[idx] = line
            changed.append("改 {} {} -> {}".format(pid, old, new))

    for pid in drop_pids | set(ren_pids):
        if not any(pid in c for c in changed):
            missed.append(pid)
    if missed:
        print("\n!! 下面这些 pid 在源码里没找到对应元组（格式可能不是单行元组）：")
        for pid in missed:
            print("   " + pid)
        print("   先不动文件。")
        return

    out = [ln for i, ln in enumerate(src_lines) if i not in kill]
    SRC.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n已写回 {}：删 {} 行，改 {} 行".format(SRC, len(kill), len(changed) - len(kill)))
    for c in changed[:20]:
        print("   · " + c)


# 有一次忘了写入口，脚本跑起来安安静静退出 0，什么都改没改——
# 这种「安静的失败」最难查，所以在末尾再加一句提示。
if __name__ == "__main__":
    main()
else:                                                   # pragma: no cover
    raise SystemExit("本脚本只能直接运行，不要 import")
