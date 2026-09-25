# -*- coding: utf-8 -*-
"""P0：生成人物别名填充计划（字 + 尊称白名单 + 追尊泛称检查）。

产出 pipeline/_alias_fill_plan.json：
  zi_add:    [{pid, zi, n}]          双字「字」进 aliases
  courtesy:  [{pid, form, n, books}]  专属尊称白名单（人工表 ∩ 语料）
  generic_check: 文帝/太祖等是否已覆盖
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bd = json.loads((ROOT / "data/index/book-data.json").read_text(encoding="utf-8"))
people = json.loads((ROOT / "data/dict/people.json").read_text(encoding="utf-8"))
ZI = re.compile(r"字([一-鿿]{1,3})")
# 叙述里误抓的「字X」：公/侯/君类敬称与固定短语，不是表字
ZI_STOP = {
    "公子", "周公", "桓公", "文公", "武公", "昭公", "定公", "惠公", "孝公",
    "哀侯", "少子", "次子", "長子", "长子", "諸君", "诸君", "君長", "君长",
    "侯王", "夫人", "孺子",  # 徐孺子是号；字是季章之类——summary 若写孺子则误
    "其字", "之字", "為字", "为字", "者字",
}


def looks_like_zi(zi: str) -> bool:
    if len(zi) < 2 or zi in ZI_STOP:
        return False
    # 「X公」「X侯」结尾且非常见真表字
    if zi.endswith("公") or zi.endswith("侯") or zi.endswith("王"):
        return False
    if zi.endswith("君") and len(zi) <= 3:
        return False
    return True


# —— 全书语料（含注）表面计数 —— 按书分账更准；尊称跨书抽查用全文 ——
corpus_by_book = defaultdict(str)
for path in (ROOT / "data/corpus").glob("*.json"):
    if not path.stem.count("-"):
        continue
    code = path.stem.split("-")[0]
    if code not in ("sj", "hs", "hhs", "sgz"):
        continue
    doc = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for p in doc["paragraphs"]:
        parts.append(p.get("text") or "")
        if p.get("note"):
            parts.append(p["note"])
    corpus_by_book[code] += "\n".join(parts) + "\n"

# 统一全文（尊称频次）
ALL = "\n".join(corpus_by_book[b] for b in ("sj", "hs", "hhs", "sgz"))

# —— 专属尊称白名单：form → 期望 pid（可多书）——
# 原则：强专属、语料≥8、不是通用官名
COURTESY = [
    # 曹操系
    ("曹公", "p_caocao"),
    ("孟德", "p_caocao"),
    ("曹孟德", "p_caocao"),
    ("魏公", "p_caocao"),  # 频次低也收；魏王已在
    ("阿瞞", "p_caocao"),
    ("阿瞒", "p_caocao"),
    # 袁绍
    ("本初", "p_yuanshao"),
    ("袁公", "p_yuanshao"),
    # 董卓
    ("仲穎", "p_dongzhuo"),
    ("仲颖", "p_dongzhuo"),
    # 荀彧
    ("文若", "p_xunyu"),
    # 陶谦
    ("恭祖", "p_taohqian"),
    # 刘备
    ("玄德", "p_liubei"),
    # 诸葛亮
    ("孔明", "p_zhugegang"),
    ("臥龍", "p_zhugegang"),
    ("卧龙", "p_zhugegang"),
    # 关羽
    ("雲長", "p_guanyu"),
    ("云长", "p_guanyu"),
    # 张飞
    ("益德", "p_zhangfei"),
    # 赵云
    ("子龍", "p_zhaoyun"),
    ("子龙", "p_zhaoyun"),
    # 周瑜
    ("公瑾", "p_zhouyu_sg"),
    # 鲁肃
    ("子敬", "p_lusu"),
    # 子明：呂蒙与孫亮同字 — 冲突，宁缺勿错，不进白名单
    ("伯言", "p_luxun"),
    # 司马懿
    ("仲達", "p_simayi"),
    ("仲达", "p_simayi"),
    # 郭嘉
    ("奉孝", "p_guojia"),
    # 荀攸
    ("公達", "p_xunyou"),
    ("公达", "p_xunyou"),
    # 程昱
    ("仲德", "p_chengyu"),
    # 贾诩
    ("文和", "p_jiaxu"),
    # 张辽
    ("文遠", "p_zhangliao"),
    ("文远", "p_zhangliao"),
    # 典韦
    ("曼成", "p_lidian"),  # 李典 — 注意典韦是字不详
    # 许褚
    ("虎癡", "p_xuchu"),
    ("虎痴", "p_xuchu"),
    # 马超
    ("孟起", "p_machao"),
    # 庞统
    ("士元", "p_pangtong"),
    ("鳳雛", "p_pangtong"),
    ("凤雏", "p_pangtong"),
    # 法正
    ("孝直", "p_fazheng"),
    # 姜维
    ("伯約", "p_jiangwei"),
    ("伯约", "p_jiangwei"),
    # 孙策
    ("伯符", "p_sunce"),
    # 孙权
    ("仲謀", "p_sunquan"),
    ("仲谋", "p_sunquan"),
    # 刘表
    ("景升", "p_liubiao"),
    # 袁术
    ("公路", "p_yuanshu"),
    # 刘璋
    ("季玉", "p_liuzhang_sg"),
    # 王朗（会稽）
    ("王景興", "p_wanglang_sg"),
    ("王景兴", "p_wanglang_sg"),
    # 顾雍
    ("元嘆", "p_guyyong"),
    ("元叹", "p_guyyong"),
    # 张昭
    ("子布", "p_zhangzhao"),
    # 张纮
    ("子綱", "p_zhanghong"),
    ("子纲", "p_zhanghong"),
    # 陈群
    ("長文", "p_chenqun_sg"),
    ("长文", "p_chenqun_sg"),
    # 钟繇
    ("元常", "p_zhongyao_sg"),
    # 华歆
    ("子魚", "p_huaxin_sg"),
    ("子鱼", "p_huaxin_sg"),
    # —— 扩批：其他高频/瘦别名人物 ——
    # 董卓更多
    ("董侯", "p_dongzhuo"),
    # 荀攸已公达；补
    # 曹仁/曹洪/曹休/曹真/曹爽
    ("子孝", "p_caoren"),
    ("子廉", "p_caohong"),
    ("文烈", "p_caoxiu"),
    ("子丹", "p_caozhen"),
    ("昭伯", "p_caoshang"),
    # 夏侯
    ("元讓", "p_xiahoudun"),
    ("元让", "p_xiahoudun"),
    ("妙才", "p_xiahouyuan"),
    # 司马师/昭
    ("子元", "p_simashi"),
    ("子上", "p_simazhao"),
    # 荀彧 already 文若
    # 程昱 already 仲德
    # 刘晔
    ("子揚", "p_liuye"),
    ("子扬", "p_liuye"),
    # 蒋济
    ("子通", "p_jiangji"),
    # 董昭
    ("公仁", "p_dongzhao"),
    # 郭嘉 already
    # 贾诩 already
    # 张郃
    ("儁乂", "p_zhanghe"),
    ("俊乂", "p_zhanghe"),
    # 于禁
    ("文則", "p_yujin"),
    ("文则", "p_yujin"),
    # 徐晃
    ("公明", "p_xuhuang"),
    # 李典
    ("曼成", "p_lidian"),
    # 典韦 — 字不详，补都亭侯已在
    # 庞德
    ("令明", "p_pangde"),
    # 关羽 already
    # 马超 already
    # 黄忠
    ("漢升", "p_huangzhong"),
    ("汉升", "p_huangzhong"),
    # 赵云 already
    # 魏延
    ("文長", "p_weiyan"),
    ("文长", "p_weiyan"),
    # 杨仪
    ("威公", "p_yangyi"),
    # 费祎
    ("文偉", "p_feiyi"),
    ("文伟", "p_feiyi"),
    # 蒋琬
    ("公琰", "p_jiangwan"),
    # 姜维 already 伯约
    # 孙坚
    ("文臺", "p_sunjian"),
    ("文台", "p_sunjian"),
    # 孙权 already
    # 吕蒙
    ("子明_pt", "SKIP"),  # placeholder no-op removed below
    # 鲁肃 already
    # 陆逊 already
    # 张昭 already
    # 步骘
    ("子山", "p_buzhi"),
    # 诸葛瑾
    ("子瑜", "p_zhugejin"),
    # 诸葛恪
    ("元遜", "p_zhugeke"),
    ("元逊", "p_zhugeke"),
    # 顾雍 already
    # 张纮 already
    # 周瑜 already
    # 程普
    ("德謀", "p_chengpu"),
    ("德谋", "p_chengpu"),
    # 黄盖
    ("公覆", "p_huanggai"),
    # 甘宁
    ("興霸", "p_ganning"),
    ("兴霸", "p_ganning"),
    # 凌统
    ("公績", "p_lingtong"),
    ("公绩", "p_lingtong"),
    # 太史慈
    ("子義", "p_taishici"),
    ("子义", "p_taishici"),
    # 吕布
    ("奉先", "p_lvbu"),
    # 袁绍 already
    # 刘备 already 玄德
    # 诸葛亮 already
    # 法正 already
    # 庞统 already
    # 王粲
    ("仲宣", "p_wangcan_sg"),
    # 陈琳等不在词典则跳过
    # 荀攸 already
    # 满宠
    ("伯寧", "p_manchong_sg"),
    ("伯宁", "p_manchong_sg"),
    # 郭淮
    ("伯濟", "p_guohuai_sg"),
    ("伯济", "p_guohuai_sg"),
    # 邓艾 if exists
    ("士載", "p_dengai"),
    ("士载", "p_dengai"),
    # 钟会
    ("士季", "p_zhonghui"),
    # 司马昭 already
    # 曹丕 already 魏文帝
    # 曹植
    ("子建", "p_caozhi"),
    # 曹彰
    ("子文", "p_caizhang"),
    # 曹叡 already
    # 孙策 already
    # 孙权 already
    # 周瑜 already
    # 鲁肃 already
    # 吕蒙 — 子明 冲突已排除；补
    # 陆逊 already
    # 刘表 already
    # 董卓仲颖
    # 袁术公路 already
    # 刘璋季玉 already
    # 陶谦恭祖 already
    # 荀彧文若 already
    # 郭嘉奉孝 already
    # 程昱仲德 already
    # 贾诩文和 already
    # 司马懿 already
    # 张辽 already
    # 许褚 already
    # 关羽 already
    # 张飞 already
    # 赵云 already
    # 马超 already
    # 黄忠 already
    # 诸葛亮 already
    # 刘备 already
    # 孙权 already
    # 曹操 already
    # 董卓 already
    # 袁绍 already
]

# 清理无效占位
COURTESY = [c for c in COURTESY if c[1] not in (None, "SKIP") and not str(c[1]).startswith("SKIP")]



def count_in(text: str, form: str) -> int:
    return text.count(form) if form and text else 0


def main():
    persons = {p["id"]: p for p in bd["persons"]}

    # ===== 1) 双字「字」填充 =====
    zi_add = []
    zi_seen = set()
    for p in bd["persons"]:
        aliases = set(p.get("aliases") or [])
        aliases.add(p["name"])
        aliases.add(p["tradName"])
        m = ZI.search(p.get("summary") or "")
        if not m:
            continue
        zi = m.group(1)
        if len(zi) < 2 or zi in aliases or (p["id"], zi) in zi_seen:
            continue
        if zi in p["tradName"] or zi in p["name"]:
            continue
        if not looks_like_zi(zi):
            continue
        # 全书频次
        n = count_in(ALL, zi)
        if n < 6:
            continue
        # 避免与他人字撞车时仍收录（同字多字是常态，靠书/篇消歧）
        zi_seen.add((p["id"], zi))
        # 只写繁体字形（summary 里已是繁体为主）
        zi_add.append({
            "pid": p["id"],
            "name": p["tradName"],
            "zi": zi,
            "n": n,
            "sgz": count_in(corpus_by_book["sgz"], zi),
        })

    zi_add.sort(key=lambda x: -x["n"])

    # ===== 2) 尊称白名单 =====
    courtesy = []
    for form, pid in COURTESY:
        p = persons.get(pid)
        if not p:
            courtesy.append({"form": form, "pid": pid, "error": "missing person"})
            continue
        aliases = set(p.get("aliases") or [])
        if form in aliases:
            continue
        n_all = count_in(ALL, form)
        n_by = {b: count_in(corpus_by_book[b], form) for b in ("sj", "hs", "hhs", "sgz")}
        # 阈值：至少一本书 ≥6，或总 ≥8
        if max(n_by.values()) < 6 and n_all < 8:
            continue
        courtesy.append({
            "form": form,
            "pid": pid,
            "name": p["tradName"],
            "n": n_all,
            "byBook": n_by,
            "books": p.get("books"),
        })

    # ===== 3) 追尊/多人号检查 =====
    generic_need = []
    for label, forms in (
        ("太祖", ["太祖", "魏太祖"]),
        ("武皇帝", ["武皇帝", "魏武皇帝"]),
        ("魏武帝", ["魏武帝"]),
        ("魏公", ["魏公"]),
    ):
        # 是否已在某人 aliases 或 GENERIC_MANUAL
        in_alias = []
        for p in bd["persons"]:
            for f in forms:
                if f in (p.get("aliases") or []) or f == p.get("tradName"):
                    in_alias.append(p["id"])
        generic_need.append({
            "label": label,
            "forms": forms,
            "in_alias_pids": in_alias,
            "sgz_n": {f: count_in(corpus_by_book["sgz"], f) for f in forms},
        })

    plan = {
        "zi_add_count": len(zi_add),
        "courtesy_count": len(courtesy),
        "zi_add": zi_add,
        "courtesy": courtesy,
        "generic_check": generic_need,
    }
    out = ROOT / "pipeline" / "_alias_fill_plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print("zi_add", len(zi_add))
    print("courtesy", len(courtesy))
    print("wrote", out)
    print("\nTOP 字:")
    for r in zi_add[:15]:
        print(f"  {r['name']:8} 字 {r['zi']:4} ×{r['n']} (sgz {r['sgz']})")
    print("\n尊称:")
    for r in courtesy:
        if "error" in r:
            print("  ERR", r)
        else:
            print(f"  {r['form']:8}→{r['name']:8} n={r['n']} sgz={r['byBook']['sgz']}")


if __name__ == "__main__":
    main()
