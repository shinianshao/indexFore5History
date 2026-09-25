# -*- coding: utf-8 -*-
"""R3：扫描 build_dict / people.json 里挂在单人 aliases 上的官职串。只读。"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ppl = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))

# 官职/军号/散号核心词（含用户点名的骑都尉）
OFFICE = re.compile(
    r"("
    r"丞相|相國|相国|太尉|司徒|司空|司馬|司马$|太傅|太保|太師|太师|太常|光祿勳|光禄勋|"
    r"衛尉|卫尉|太僕|太仆|廷尉|大鴻臚|大鸿胪|宗正|大司農|大农|少府|執金吾|执金吾|"
    r"尚書|尚书|侍中|中常侍|黃門侍郎|黄门侍郎|議郎|议郎|郎中|謁者|谒者|"
    r"御史|刺史|太守|郡守|縣令|县令|長史|长史|主簿|參軍|参军|從事|从事|掾|"
    r"都尉|騎都尉|骑都尉|校尉|中郎將|中郎将|"
    r"大將軍|大将军|驃騎將軍|骠骑将军|車騎將軍|车骑将军|衛將軍|卫将军|"
    r"前將軍|前将军|後將軍|后将军|左將軍|左将军|右將軍|右将军|"
    r"征東|征东|征西|征南|征北|安東|安东|安西|安南|安北|"
    r"鎮東|镇东|鎮西|镇西|鎮南|镇南|鎮北|镇北|"
    r"平東|平东|平西|平南|平北|"
    r"建威|奮威|奋威|揚威|扬威|昭武|昭文|振威|"
    r"折衝|折冲|蕩寇|荡寇|討逆|讨逆|破虜|破虏|討虜|讨虏|"
    r"橫江|横江|鎮軍|镇军|安漢|安汉|秉忠|輔國|辅国|"
    r"軍師|军师|祭酒|中領軍|中领军|領軍|领军|護軍|护军|都護|都护|"
    r"西域都護|西域都护|典農|典农|度遼|度辽|"
    r"將軍|将军|將|军$"
    r")"
)

# 只要整串「像官职」就剥：短串且命中官职词，或以 將軍/都尉/校尉/太守/刺史/丞相 等结尾
SUFFIX = re.compile(
    r"(將軍|将军|都尉|校尉|太守|刺史|丞相|相國|相国|太尉|太傅|太保|司徒|司空|"
    r"尚書|尚书|侍中|長史|长史|參軍|参军|主簿|從事|从事|祭酒|都護|都护|"
    r"大司農|大农|光祿勳|光禄勋|衛尉|卫尉|太僕|太仆|廷尉|大鴻臚|大鸿胪|"
    r"執金吾|执金吾|中常侍|議郎|议郎|郎中|謁者|谒者|牧$|尹$)"
)

# 明确保留：已是人名/封号且不与官职撞的不动；表字不在本表
KEEP = set()


def is_office_alias(a: str) -> bool:
    if not a or len(a) < 2:
        return False
    if a in KEEP:
        return False
    # 纯官职 / 官职+简短后缀
    if SUFFIX.search(a) and len(a) <= 8:
        # 排除「司馬懿」「司馬遷」等人名（司馬+名）
        if re.match(r"司馬[一-鿿]{1,2}$", a) and a not in (
            "司馬懿", "司馬師", "司馬昭", "司馬炎", "司馬朗", "司馬遷", "司馬談",
            "司馬相如", "司馬穰苴", "司馬欣", "司馬尚", "司馬錯", "司馬季主",
            "司馬宣王", "司馬宣帝", "司馬仲達",
        ):
            # 司馬當官職（太尉司馬）時整串才是官；「司馬」二字单独是官
            pass
        if a in ("司馬", "司马", "左司馬", "左司马", "右司馬", "右司马", "大司馬", "大司马"):
            return True
        # 人名型：司馬X 保留
        if re.fullmatch(r"司馬[一-鿿]{1,2}", a) and a not in ("司馬",):
            return False
        return True
    if a in ("丞相", "太尉", "太傅", "太保", "司徒", "司空", "侍中", "尚書", "尚书",
             "大將軍", "大将军", "將軍", "将军", "太守", "刺史", "騎都尉", "骑都尉",
             "都尉", "校尉", "大司馬", "大司马", "相國", "相国", "牧"):
        return True
    return False


rows = []
by_alias = defaultdict(list)
for p in ppl["persons"]:
    for a in p.get("aliases") or []:
        if is_office_alias(a):
            rows.append((p["id"], p.get("tradName"), a, p.get("title")))
            by_alias[a].append(p["tradName"])

print(f"官职串挂在单人 aliases: {len(rows)} 条 / {len(by_alias)} 种写法")
for a, names in sorted(by_alias.items(), key=lambda x: (-len(x[1]), x[0])):
    print(f"  {a!r} → {names}")

# 骑都尉专项
print("\n=== 骑都尉/都尉 专项 ===")
for p in ppl["persons"]:
    for a in p.get("aliases") or []:
        if "都尉" in a or "騎都" in a or "骑都" in a:
            print(p["id"], p.get("tradName"), a, "title=", p.get("title"))
