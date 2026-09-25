# -*- coding: utf-8 -*-
"""R2：从 summary 抽双字「字」+ 安全尊称，生成并写入 build_dict 别名。

口径（docs/12 已拍板）：
  - 只补**双字**表字（孟德/仲穎/元仲…）
  - 尊称仅白名单
  - 禁止裸官名、多人同称帝号
  - 别名只写繁体
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"
PEOPLE = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
BDATA = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))

ZI = re.compile(r"字([一-鿿]{2,3})")
# summary 里误抓：不是表字
ZI_STOP = {
    "公子", "周公", "桓公", "文公", "武公", "昭公", "定公", "惠公", "孝公",
    "哀侯", "少子", "次子", "長子", "长子", "諸君", "诸君", "君長", "君长",
    "侯王", "夫人", "孺子", "其字", "之字", "為字", "为字", "者字",
    "伯始",  # 胡廣字伯始是对的，保留；下面 looks 会拦 X公
}
# 明确不要的（多人同字 / 过险）
ZI_DENY = {
    "子明",  # 呂蒙 / 孫亮
    "子龙", "子龍",  # 趙雲 / 申屠蟠
    "仲达", "仲達",  # 司馬懿 / 龐參（书作用域可分，但核心已有）
}

# 尊称白名单：form → pid（只补尚未登记的）
COURTESY = [
    ("仲穎", "p_dongzhuo"),
    ("董公", "p_dongzhuo"),
    ("仲舉", "p_chenfan"),
    ("陳仲舉", "p_chenfan"),
    ("遂高", "p_hejin"),
    ("本初", "p_yuanshao"),
    ("公路", "p_yuanshu"),
    ("奉先", "p_lvbu"),
    ("景升", "p_liubiao"),
    ("季玉", "p_liuzhang_sg"),
    ("孟起", "p_machao"),
    ("益德", "p_zhangfei"),
    ("文遠", "p_zhangliao"),
    ("妙才", "p_xiahouyuan"),
    ("元讓", "p_xiahoudun"),
    ("元仲", "p_cao_rui"),
    ("公嗣", "p_liushan"),
    ("幼常", "p_masu"),
    ("公祺", "p_zhanglu"),
    ("文烈", "p_caoxiu"),
    ("子丹", "p_caozhen"),
    ("昭伯", "p_caoshuang"),
    ("元宗", "p_sunhao"),
    ("思遠", "p_zhugezhan"),
    ("令明", "p_pangde"),
    ("公明", "p_xuhuang"),
    ("文則", "p_yujin"),
    ("曼成", "p_lidian"),
]


def looks_like_zi(zi: str) -> bool:
    if len(zi) < 2 or zi in ZI_STOP or zi in ZI_DENY:
        return False
    if zi.endswith(("公", "侯", "王")):
        return False
    if zi.endswith("君") and len(zi) <= 3:
        return False
    return True


def parse_alias_list(line: str):
    m = re.search(r"\[([^\]]*)\]", line)
    if not m:
        return None
    return re.findall(r'"([^"]+)"', m.group(1))


def format_alias_list(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return "[" + ", ".join(f'"{x}"' for x in out) + "]"


def main() -> None:
    by_id = {p["id"]: p for p in PEOPLE["persons"]}
    hit_ids = set()
    for p in BDATA["persons"]:
        bb = p.get("byBook") or {}
        if any((bb.get(c) or {}).get("mentionCount", 0) >= 5 for c in ("hhs", "sgz", "sj", "hs")):
            hit_ids.add(p["id"])

    zi_add = []
    for p in BDATA["persons"]:
        if p["id"] not in hit_ids:
            continue
        m = ZI.search(p.get("summary") or "")
        if not m:
            continue
        zi = m.group(1)[:2]  # 只取双字
        if not looks_like_zi(zi):
            continue
        aliases = set(p.get("aliases") or []) | {p.get("name"), p.get("tradName")}
        if zi in aliases or zi in "".join(aliases):
            continue
        n = max(
            ((p.get("byBook") or {}).get(c) or {}).get("mentionCount", 0)
            for c in ("sj", "hs", "hhs", "sgz")
        )
        zi_add.append({"pid": p["id"], "zi": zi, "n": n, "name": p.get("tradName")})

    courtesy_add = []
    for form, pid in COURTESY:
        p = by_id.get(pid)
        if not p:
            continue
        aliases = set(p.get("aliases") or [])
        if form in aliases:
            continue
        courtesy_add.append({"pid": pid, "form": form, "name": p.get("tradName")})

    zi_add.sort(key=lambda r: -r["n"])
    plan = {"zi_add": zi_add, "courtesy": courtesy_add}
    (ROOT / "pipeline" / "_alias_fill_plan_r2.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"zi_add {len(zi_add)}  courtesy_add {len(courtesy_add)}")
    for r in zi_add[:15]:
        print("  字", r["name"], r["zi"], "×", r["n"])
    for r in courtesy_add[:15]:
        print("  称", r["name"], r["form"])

    # —— 写入 build_dict ——
    text = BD.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    by_pid: dict[str, list[str]] = {}
    for r in zi_add:
        by_pid.setdefault(r["pid"], []).append(r["zi"])
    for r in courtesy_add:
        by_pid.setdefault(r["pid"], []).append(r["form"])

    n_line = n_add = 0
    missing = []
    for pid, forms in by_pid.items():
        hit = False
        for i, line in enumerate(lines):
            if not re.match(r'\s*\("p_', line):
                continue
            if f'"{pid}"' not in line:
                continue
            al = parse_alias_list(line)
            if al is None:
                continue
            before = len(al)
            merged = al + [f for f in forms if f not in al]
            if len(merged) == before:
                hit = True
                break
            m = re.search(r"\[([^\]]*)\]", line)
            lines[i] = line[: m.start()] + format_alias_list(merged) + line[m.end() :]
            n_line += 1
            n_add += len(merged) - before
            hit = True
            break
        if not hit:
            missing.append(pid)

    BD.write_text("".join(lines), encoding="utf-8")
    print(f"写入 {n_line} 行 / +{n_add} 别名；未命中 PERSONS 行: {missing}")


if __name__ == "__main__":
    main()
