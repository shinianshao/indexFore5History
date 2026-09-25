# -*- coding: utf-8 -*-
"""词典体检：找出还没被消歧覆盖的称号。

背景
----
本项目对「泛称」（称号类别名）采用运行时消歧：同一称号在不同篇目指不同人时，
按篇目上下文判定归属（见 build_dict.py 的 GENERIC_* 与 annotate.py 的
resolve_generic）。但泛称清单是人工维护的，难免有遗漏——某个称号其实对应多人，
却仍被当作专属别名全局匹配，就会在别人篇目里整片错配。

本脚本扫描语料，把「看起来像称号、却只挂在一个名下、又有大量命中落在
别人篇目里」的别名挑出来，作为下一轮补泛称的候选。

现场说明
--------
本脚本报「有其他持有者」的称号，分两类：

* ``declared`` —— 别人也把这个称号登记成了别名（如「梁王」同时挂在彭越、刘武名下）。
* ``implicit`` —— 没人声明同名，但别人的**更长称号把它整段包住**（如刘长的
  「淮南厉王」包住了「厲王」）。这一类比第一类隐蔽得多，且旧版体检完全查不到。

「漢王」「沛公」这类别名虽然大量出现在别人篇目里，但全世界只有刘邦这么叫，
不存在歧义，不报——否则体检单会淹没在几百条假警报里。
"""
import glob
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CORPUS, DICT, PIPELINE, compile_alias_pattern, corpus_paths,
                    load_json, norm, same_title_family, write_json)

# 称号后缀：以此结尾的别名才可能是「称号」
TITLE_SUFFIXES = ("王", "公", "侯", "君", "后", "太后", "相国", "将军")
# 错位达到这些阈值才值得关注
FOREIGN_MIN = 4
FOREIGN_RATIO = 0.35

# 这些称号已由 GENERIC_MANUAL / GENERIC_CORES 覆盖，不算遗漏
COVERED = {
    "梁王", "齊王", "燕王", "趙王", "韓王", "魏王", "吳王", "荊王", "代王",
    "淮南王", "衡山王", "朝鮮王", "湯", "武安君", "平王", "成王", "武王",
    "宣王", "桓公", "厲王", "幽王",
}


def main():
    people = load_json(os.path.join(DICT, "people.json"), None)
    if not people:
        raise SystemExit("缺少 data/dict/people.json，先运行 build_dict.py")

    persons = people["persons"]
    owners = people["chapterOwners"]
    related = people.get("chapterRelated", {})
    name_of = {p["id"]: p["name"] for p in persons}
    generic_forms = set()
    for entry in people.get("genericAliases", []):
        for form in entry["forms"]:
            generic_forms.add(norm(form))

    # 别名 -> pid（与 annotate 的全局匹配一致：长度降序，长别名优先）
    pairs = []
    for person in persons:
        for alias in person["aliases"]:
            if norm(alias) in generic_forms:
                continue
            pairs.append((norm(alias), person["id"]))
    pairs.sort(key=lambda kv: (-len(kv[0]), kv[0], kv[1]))
    alias_to_pid = {}
    for alias, pid in pairs:
        alias_to_pid.setdefault(alias, pid)

    docs = [load_json(p) for p in corpus_paths(ready_only=True)]
    chapter_title = {}
    local_people = defaultdict(set)
    for cid, pids in owners.items():
        local_people[cid] |= set(pids)
    for cid, pids in related.items():
        local_people[cid] |= set(pids)

    # 扫描用单个正则一次过（逐别名 find 会慢一个数量级：1100 别名 × 4.6 万句）
    scan_pat, scan_map = compile_alias_pattern(
        [(a, p) for a, p in alias_to_pid.items()])

    alias_chapters = defaultdict(Counter)
    samples = {}
    for doc in docs:
        cid = doc["chapterId"]
        chapter_title[cid] = doc["fullTitle"]
        for para in doc["paragraphs"]:
            for sent in para["sentences"]:
                text = norm(sent["text"])
                for match in scan_pat.finditer(text):
                    alias_chapters[match.group(0)][cid] += 1
                    samples.setdefault((match.group(0), cid), sent["text"][:46])

    suspects = []
    for alias, dist in alias_chapters.items():
        pid = alias_to_pid[alias]
        if alias in COVERED:
            continue
        total = sum(dist.values())
        if total < FOREIGN_MIN:
            continue
        native = sum(n for cid, n in dist.items()
                     if pid in local_people.get(cid, ()))
        foreign = total - native
        if foreign < FOREIGN_MIN or foreign / total < FOREIGN_RATIO:
            continue
        # 竞争者分两类：
        #   ① declared —— 别人也把这个称号登记成了别名（「梁王」同时挂在彭越、刘武名下）
        #   ② implicit —— 没别人声明同名，但别人的**更长称号把它整段包住**。
        #      典型是「厲王」：只有周厉王声明了这个别名，可刘长的称号「淮南厉王」
        #      本就以「厲王」结尾，于是《淮南衡山列传》19 处「厲王」全被错配给周厉王，
        #      而旧版体检因为「无人竞争」而完全静默。补上这一类，盲点才堵死。
        suffix = None
        for suf in TITLE_SUFFIXES:
            if alias.endswith(suf):
                suffix = suf
                break
        declared, implicit = [], []
        if suffix:
            core = alias[:-len(suffix)]
            for other in persons:
                if other["id"] == pid:
                    continue
                for token in set(other["aliases"]) | {other["name"]}:
                    if same_title_family(token, core, suffix):
                        declared.append(other["name"])
                        break
        if suffix and not declared and len(alias) >= 2:
            for other in persons:
                if other["id"] == pid:
                    continue
                pool = set(other["aliases"]) | {other["name"], other.get("title", "")}
                if any(t and len(norm(t)) > len(alias) and norm(t).endswith(alias)
                       for t in pool):
                    implicit.append(other["name"])
        rivals = declared + implicit
        if suffix and not rivals:
            continue            # 无人可争，属专属称谓，不必消歧
        if not suffix:
            continue            # 非称号别名：在别人篇目里出现是正常提及，不是歧义
        top = []
        for cid, n in dist.most_common():
            if pid in local_people.get(cid, ()):
                continue
            alt = [name_of[p] for p in local_people.get(cid, ())]
            top.append({"chapterId": cid, "title": chapter_title.get(cid, ""),
                        "n": n, "chapterPersons": alt,
                        "sample": samples.get((alias, cid), "")})
            if len(top) >= 5:
                break
        suspects.append({
            "alias": alias,
            "owner": name_of[pid],
            "rivals": rivals,
            "rivalKind": "declared" if declared else "implicit",
            "total": total, "native": native, "foreign": foreign,
            "foreignRatio": round(foreign / total, 2),
            "titleLike": alias.endswith(TITLE_SUFFIXES),
            "foreignChapters": top,
        })

    # 称号类的问题才值得处理，排前面
    suspects.sort(key=lambda r: -r["foreign"])
    report = {
        "summary": {
            "aliasCount": len(alias_chapters),
            "totalAliasHits": sum(sum(c.values()) for c in alias_chapters.values()),
            "suspectCount": len(suspects),
            "suspectHits": sum(r["foreign"] for r in suspects),
            "coveredGeneric": sorted(COVERED),
        },
        "suspects": suspects[:60],
    }
    write_json(os.path.join(PIPELINE, "_audit_report.json"), report, indent=2)

    print("别名 {} 个 / 命中 {} 处".format(
        report["summary"]["aliasCount"], report["summary"]["totalAliasHits"]))
    print("疑似未覆盖的歧义称号 {} 个".format(report["summary"]["suspectCount"]))
    for row in suspects[:20]:
        print("  {} 归属{} 错位{}/{} 处 [{}] 竞争者:{}".format(
            row["alias"], row["owner"], row["foreign"], row["total"],
            row["rivalKind"], "/".join(row["rivals"][:4]) or "无"))


if __name__ == "__main__":
    main()
