# -*- coding: utf-8 -*-
"""R3c：列传传主批量写入 build_dict（人物 + 篇主）。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BD = ROOT / "pipeline" / "build_dict.py"

# slug: [(pid, simp, trad, zi_alias...)]
# 只收卷首第一传主/合传主干；附传 R3d 滚补
BIOS = [
    ("032", "p_yumengmu", "虞孟母", "元敬虞皇后", ["虞皇后", "元敬虞皇后"]),
    ("033", "p_wangxiang", "王祥", "王祥", ["王休徵", "休徵", "休征"]),
    ("034", "p_yanghu", "羊祜", "羊祜", ["羊叔子", "叔子"]),
    ("035", "p_chenqian", "陈骞", "陳騫", []),
    ("036", "p_weiguan", "卫瓘", "衛瓘", ["衞瓘", "衛伯玉", "伯玉"]),
    ("037", "p_sima_fu", "司马孚", "司馬孚", ["安平獻王", "安平献王", "司馬叔達", "叔達", "叔达"]),
    ("038", "p_simagan", "司马幹", "司馬幹", ["平原王幹", "平原王干"]),
    ("039", "p_wangshen", "王沈", "王沈", ["王處道", "處道", "处道"]),
    ("040", "p_jiachong", "贾充", "賈充", ["賈公閭", "公閭", "公闾"]),
    ("041", "p_weishu", "魏舒", "魏舒", ["魏陽元", "陽元", "阳元"]),
    ("042", "p_wanghun", "王浑", "王渾", ["王玄沖", "玄沖", "玄冲"]),
    ("043", "p_shantao", "山涛", "山濤", ["山巨源", "巨源"]),
    ("044", "p_zhengmao", "郑袤", "鄭袤", ["鄭林叔", "林叔"]),
    ("045", "p_liuyi_jin", "刘毅", "劉毅", ["劉仲雄", "仲雄"]),
    ("046", "p_liusong", "刘颂", "劉頌", ["劉子雅", "子雅"]),
    ("047", "p_fuxuan", "傅玄", "傅玄", ["傅休奕", "休奕"]),
    ("048", "p_xiangxiong", "向雄", "向雄", ["向茂伯", "茂伯"]),
    ("049", "p_ruanji", "阮籍", "阮籍", ["阮嗣宗", "嗣宗"]),
    ("050", "p_caozhi_jin", "曹志", "曹志", ["曹允恭", "允恭"]),
    ("051", "p_huangfumi", "皇甫谧", "皇甫謐", ["皇甫士安", "士安"]),
    ("052", "p_xishen", "郤诜", "郤詵", ["郤廣基", "廣基", "广基"]),
    ("053", "p_sima_yu2", "司马遹", "司馬遹", ["湣懷太子", "愍怀太子", "太子遹"]),
    ("054", "p_luji", "陆机", "陸機", ["陸士衡", "士衡"]),
    ("055", "p_xiahouzhan", "夏侯湛", "夏侯湛", ["夏侯孝若", "孝若"]),
    ("056", "p_jiangtong", "江统", "江統", ["江應元", "應元", "应元"]),
    ("057", "p_luoxian", "罗宪", "羅憲", ["羅令則", "令則", "令则"]),
    ("058", "p_zhouchu", "周处", "周處", ["周子隱", "子隱", "子隐"]),
    ("060", "p_xiexi", "解系", "解系", ["解少連", "少連", "少连"]),
    ("061", "p_zhoujun", "周浚", "周浚", ["周開林", "開林", "开林"]),
    ("062", "p_liukun", "刘琨", "劉琨", ["劉越石", "越石"]),
    ("063", "p_shaoxu", "邵续", "邵續", ["邵嗣祖", "嗣祖"]),
    ("065", "p_wangdao2", "王导", "王導", []),  # 已有 p_wangdao，跳过重复则脚本忽略
    ("066", "p_liuhong", "刘弘", "劉弘", ["劉和季", "和季"]),
    ("067", "p_wenqiao", "温峤", "溫嶠", ["溫太真", "太真"]),
    ("068", "p_gurong", "顾荣", "顧榮", ["顧彥先", "彥先", "彦先"]),
    ("069", "p_liuwei", "刘隗", "劉隗", ["劉大連", "大連", "大连"]),
    ("070", "p_yingzhan", "应詹", "應詹", ["應思遠", "思遠", "思远"]),
    ("071", "p_sunhui", "孙惠", "孫惠", ["孫德施", "德施"]),
    ("072", "p_guopu", "郭璞", "郭璞", ["郭景純", "景純", "景纯"]),
    ("074", "p_huanyi", "桓彝", "桓彝", ["桓茂倫", "茂倫", "茂伦"]),
    ("078", "p_kongyu", "孔愉", "孔愉", ["孔敬康", "敬康"]),
    ("079", "p_xieshang", "谢尚", "謝尚", ["謝仁祖", "仁祖"]),
    ("080", "p_wangxizhi", "王羲之", "王羲之", ["王逸少", "逸少"]),
    ("081", "p_wangxun", "王逊", "王遜", ["王邵伯", "邵伯"]),
    ("082", "p_chenshou", "陈寿", "陳壽", ["陳承祚", "承祚"]),
    ("083", "p_guhe", "顾和", "顧和", ["顧君孝", "君孝"]),
    ("084", "p_wanggong", "王恭", "王恭", ["王孝伯", "孝伯"]),
    ("085", "p_liuyi_xile", "刘毅2", "劉毅", ["劉希樂", "希樂", "希乐"]),  # 与仲雄同名异人
    ("087", "p_lihao", "李暠", "李暠", ["武昭王", "李玄盛", "玄盛"]),
    ("093", "p_yangxiu", "羊琇", "羊琇", ["羊稚舒", "稚舒"]),
    ("094", "p_sundeng", "孙登", "孫登", ["孫公和", "公和"]),
    ("095", "p_chenxun", "陈训", "陳訓", ["陳道元", "道元"]),
    ("098", "p_wangdun2", "王敦", "王敦", []),  # 已有
    ("099", "p_huanxuan", "桓玄", "桓玄", ["桓敬道", "敬道", "靈寶", "灵宝"]),
    ("100", "p_wangmi", "王弥", "王彌", []),
]


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    existing = set(re.findall(r'\("(p_[^"]+)"', text))
    lines = ["\n# ===== R3c 《晋书》列传传主 =====\nPERSONS.extend([\n"]
    n_new = 0
    used_pids = set()
    for slug, pid, simp, trad, extras in BIOS:
        if pid in existing or pid == "p_wangdao2" or pid == "p_wangdun2":
            continue
        aliases = [trad] + [a for a in extras if a != trad]
        # 去重保序
        seen, al = set(), []
        for a in aliases:
            if a not in seen:
                seen.add(a)
                al.append(a)
        al_s = ", ".join('"%s"' % a for a in al)
        lines.append(
            '    ("%s", "%s", "%s", "东晋", "晋书列传", "《晋书》列传。", [%s]),\n'
            % (pid, simp if any("一" <= ch <= "鿿" for ch in simp) else trad, trad, al_s)
        )
        used_pids.add(pid)
        n_new += 1
    lines.append("])\n")

    # 篇主：在 CHAPTER_OWNERS_JS 字典里补
    owner_lines = ["\n# R3c 列传篇主\n"]
    for slug, pid, simp, trad, extras in BIOS:
        if pid in ("p_wangdao2", "p_wangdun2"):
            continue
        if pid not in existing and pid not in used_pids:
            continue
        use = pid if pid in used_pids or pid in existing else None
        if not use:
            continue
        # 同名异人：p_wangdao 已有王导 → 065 用 p_wangdao
        if slug == "065":
            use = "p_wangdao"
        if slug == "098":
            use = "p_wangdun"
        owner_lines.append('CHAPTER_OWNERS_JS.setdefault("%s", [])\n' % slug)
        owner_lines.append(
            'if "%s" not in CHAPTER_OWNERS_JS["%s"]:\n    CHAPTER_OWNERS_JS["%s"].append("%s")\n'
            % (use, slug, slug, use)
        )

    # books
    book_lines = ["\n# R3c 列传 books\nfor _pid in (%s,):\n    PERSON_BOOKS_JS.setdefault(_pid, [\"js\"])\n"
                  % ", ".join('"%s"' % p for p in sorted(used_pids))]

    # 插入位置：CHAPTER_OWNERS_JS 结束后
    marker = "# ===== 《晋书》篇目主人公 结束 ====="
    if marker not in text:
        raise SystemExit("marker not found")
    block = "".join(lines) + "".join(owner_lines) + "".join(book_lines) + "\n"
    text = text.replace(marker, marker + "\n" + block, 1)
    BD.write_text(text, encoding="utf-8")
    print("new persons", n_new)


if __name__ == "__main__":
    main()
