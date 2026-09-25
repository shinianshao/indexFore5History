# -*- coding: utf-8 -*-
"""篇主补满 + 泛称收紧：批量插入 sgz 合传传主并填 CHAPTER_OWNERS_SGZ。

只改 pipeline/build_dict.py；跑完需 build_dict → annotate（或全管线）。
带 opencc 的解释器：C:\\Users\\dell\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\python.exe
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BD = ROOT / "pipeline" / "build_dict.py"

# pid, 简, 繁, title, summary, aliases(繁)
# 仅列本专项空篇主所需、词典尚缺的人；王朗/贾逵须 _sg 防撞。
NEW_PERSONS = [
    # —— 13 鍾繇華歆王朗 ——
    ("p_zhongyao_sg", "钟繇", "鍾繇", "三国", "太傅", "字元常，魏书法之祖。", ["鍾太傅"]),
    ("p_huaxin_sg", "华歆", "華歆", "三国", "太尉", "字子鱼，平原高唐人。", ["華子魚", "華獨坐"]),
    ("p_wanglang_sg", "王朗", "王朗", "三国", "司徒", "字景兴，东海郯人。", ["王景興"]),
    # —— 11 袁張涼國田王邴管 ——
    ("p_yuanhuan_sg", "袁涣", "袁渙", "三国", "郎中令", "字曜卿，陈郡扶乐人。", []),
    ("p_liangmao_sg", "凉茂", "涼茂", "三国", "魏郡太守", "字伯方，山阳昌邑人。", []),
    ("p_guoyuan_sg", "国渊", "國淵", "三国", "太仆", "字子尼，乐安盖人。", []),
    ("p_tianchou_sg", "田畴", "田疇", "三国", "议郎", "字子泰，右北平无终人。", []),
    ("p_wangxiu_sg", "王修", "王脩", "三国", "大司农", "字叔治，北海营陵人。", []),
    ("p_bingyuan_sg", "邴原", "邴原", "三国", "五官将长史", "字根矩，北海朱虚人。", ["邴根矩"]),
    ("p_guanning_sg", "管宁", "管寧", "三国", "管幼安", "字幼安，北海朱虚人，高士。", ["管幼安"]),
    # —— 15 劉司馬梁張溫賈 ——
    ("p_liufu_sg", "刘馥", "劉馥", "三国", "扬州刺史", "字元颖，沛国相人。", []),
    ("p_simalang_sg", "司马朗", "司馬朗", "三国", "兖州刺史", "字伯达，河内温人。", []),
    ("p_liangxi_sg", "梁习", "梁習", "三国", "大司农", "字子虞，沛国柘人。", []),
    ("p_zhangji_sg", "张既", "張既", "三国", "凉州刺史", "字德容，冯翊高陵人。", ["張德容"]),
    ("p_wenhui_sg", "温恢", "溫恢", "三国", "凉州刺史", "字曼基，太原祁人。", []),
    ("p_jiakui_sg", "贾逵", "賈逵", "三国", "豫州刺史", "字梁道，河东襄陵人。", ["賈梁道"]),
    # —— 16 任蘇杜鄭倉 ——
    ("p_renjun_sg", "任峻", "任峻", "三国", "典农中郎将", "字伯达，河南中牟人。", []),
    ("p_suze_sg", "苏则", "蘇則", "三国", "侍中", "字文师，扶风武功人。", []),
    ("p_duji_sg", "杜畿", "杜畿", "三国", "尚书仆射", "字伯侯，京兆杜陵人。", ["杜伯侯"]),
    ("p_zhenghun_sg", "郑浑", "鄭渾", "三国", "大将作", "字文公，河南开封人。", []),
    ("p_cangci_sg", "仓慈", "倉慈", "三国", "敦煌太守", "字孝仁，淮南人。", []),
    # —— 21 王衞二劉傅 ——
    ("p_wangcan_sg", "王粲", "王粲", "三国", "侍中", "字仲宣，山阳高平人，建安七子。", ["王仲宣"]),
    ("p_weikan_sg", "卫觊", "衛覬", "三国", "尚书", "字伯儒，河东安邑人。", []),
    ("p_liuyi_sg", "刘廙", "劉廙", "三国", "魏郡太守", "字恭嗣，南阳安众人。", []),
    ("p_liushao_sg", "刘劭", "劉劭", "三国", "骑都尉", "字孔才，广平邯郸人。", []),
    ("p_fugu_sg", "傅嘏", "傅嘏", "三国", "尚书", "字兰石，北地泥阳人。", ["傅蘭石"]),
    # —— 22 桓二陳徐衛盧 ——
    ("p_huanjie_sg", "桓阶", "桓階", "三国", "尚书令", "字伯绪，长沙临湘人。", []),
    ("p_chenqun_sg", "陈群", "陳群", "三国", "司空", "字长文，颍川许昌人。", ["陳長文"]),
    ("p_chenjiao_sg", "陈矫", "陳矯", "三国", "司徒", "字季弼，广陵东阳人。", []),
    ("p_xuxuan_sg", "徐宣", "徐宣", "三国", "左仆射", "字宝坚，广陵海西人。", []),
    ("p_weizhen_sg", "卫臻", "衛臻", "三国", "司徒", "字公振，陈留襄邑人。", []),
    ("p_luyu_sg", "卢毓", "盧毓", "三国", "司空", "字子家，涿郡涿人。", []),
    # —— 23 和常楊杜趙裴 ——
    ("p_heqia_sg", "和洽", "和洽", "三国", "太常", "字阳士，汝南西平人。", []),
    ("p_changlin_sg", "常林", "常林", "三国", "光禄勋", "字伯槐，河内温人。", []),
    ("p_yangjun_sg", "杨俊", "楊俊", "三国", "征南长史", "字季才，河内获嘉人。", []),
    ("p_duqi_sg", "杜袭", "杜襲", "三国", "大中大夫", "字子绪，颍川定陵人。", []),
    ("p_zhaoyan_sg", "赵俨", "趙儼", "三国", "骠骑将军", "字伯阳，颍川阳翟人。", []),
    ("p_peiqian_sg", "裴潜", "裴潛", "三国", "光禄勋", "字文行，河东闻喜人。", []),
    # —— 24 韓崔高孫王 ——
    ("p_hanji_sg", "韩暨", "韓曁", "三国", "司徒", "字公至，南阳堵阳人。", []),
    ("p_cuilin_sg", "崔林", "崔林", "三国", "司空", "字德儒，清河东武城人。", []),
    ("p_gaorou_sg", "高柔", "高柔", "三国", "太尉", "字文惠，陈留圉人。", []),
    ("p_sunli_sg", "孙礼", "孫禮", "三国", "司隶校尉", "字德达，涿郡容城人。", []),
    ("p_wangguan_sg", "王观", "王觀", "三国", "司空", "字伟台，东郡宛句人。", []),
    # —— 25 辛毗楊阜高堂隆 ——
    ("p_xinpi_sg", "辛毗", "辛毗", "三国", "卫尉", "字佐治，颍川阳翟人。", []),
    ("p_yangfu_sg", "杨阜", "楊阜", "三国", "少府", "字义山，天水冀人。", []),
    ("p_gaotanglong_sg", "高堂隆", "高堂隆", "三国", "光禄勋", "字升平，泰山平阳人。", []),
    # —— 26 滿田牽郭 ——
    ("p_manchong_sg", "满宠", "滿寵", "三国", "太尉", "字伯宁，山阳昌邑人。", []),
    ("p_tianyu_sg", "田豫", "田豫", "三国", "汝南太守", "字国让，渔阳雍奴人。", []),
    ("p_qianzhao_sg", "牵招", "牽招", "三国", "雁门太守", "字文经，安平观津人。", []),
    ("p_guohuai_sg", "郭淮", "郭淮", "三国", "车骑将军", "字伯济，太原阳曲人。", ["郭伯濟"]),
    # —— 27 徐胡二王 ——
    ("p_xumiao_sg", "徐邈", "徐邈", "三国", "司隶校尉", "字景山，燕国蓟人。", []),
    ("p_huzhi_sg", "胡质", "胡質", "三国", "征东将军", "字文德，楚国寿春人。", []),
    ("p_wangchang_sg", "王昶", "王昶", "三国", "司空", "字文舒，太原晋阳人。", []),
    ("p_wangji_sg", "王基", "王基", "三国", "征南将军", "字伯舆，东莱曲城人。", []),
    # —— 29 方技 ——
    ("p_zhuxuanping_sg", "朱建平", "朱建平", "三国", "太史", "善相术。", []),
    ("p_zhouxuan_fa", "周宣", "周宣", "三国", "太史", "字孔和，北海人，占梦。", []),
    ("p_guanlu_sg", "管辂", "管輅", "三国", "少府", "字公明，平原人，方技。", ["管公明"]),
    # —— 41 蜀霍王向張楊費 ——
    ("p_huojun_sg", "霍峻", "霍峻", "三国", "梓潼太守", "字仲邈，南郡枝江人。", []),
    ("p_wanglian_sg", "王连", "王連", "三国", "司盐校尉", "字文仪，南阳人。", []),
    ("p_xianglang_sg", "向朗", "向朗", "三国", "光禄勋", "字巨达，襄阳宜城人。", []),
    ("p_zhangyi_sg", "张裔", "張裔", "三国", "辅汉将军", "字君嗣，蜀郡成都人。", []),
    ("p_yanghong_sg", "杨洪", "楊洪", "三国", "蜀郡太守", "字季休，犍为武阳人。", []),
    ("p_feishi_sg", "费诗", "費詩", "三国", "谏议大夫", "字公举，犍为南安人。", []),
    # —— 42 杜周許孟來尹李譙郤 ——
    ("p_duwei_sg", "杜微", "杜微", "三国", "谏议大夫", "字国辅，梓潼涪人。", []),
    ("p_zhouqun_sg", "周群", "周羣", "三国", "儒林校尉", "字仲直，巴西阆中人。", []),
    ("p_xuci_sg", "许慈", "許慈", "三国", "太常", "字仁笃，南阳人。", []),
    ("p_menguang_sg", "孟光", "孟光", "三国", "议郎", "字孝裕，河南洛阳人。", []),
    ("p_laimin_sg", "来敏", "來敏", "三国", "光禄大夫", "字敬达，义阳新野人。", []),
    ("p_yinmo_sg", "尹默", "尹默", "三国", "谏议大夫", "字思潜，梓潼涪人。", []),
    ("p_qiaozhou_sg", "谯周", "譙周", "三国", "光禄大夫", "字允南，巴西西充国人。", ["譙允南"]),
    ("p_xizheng_sg", "郤正", "郤正", "三国", "令史", "字令先，河南偃师人。", []),
    # —— 53 吳張嚴程闞薛 ——
    ("p_yanjun_sg", "严畯", "嚴畯", "三国", "骑都尉", "字曼才，彭城人。", []),
    ("p_chengbing_sg", "程秉", "程秉", "三国", "太常", "字德枢，汝南南顿人。", []),
    ("p_kanze_sg", "阚泽", "闞澤", "三国", "太子太傅", "字德润，会稽山阴人。", ["闞德潤"]),
    ("p_xuezong_sg", "薛综", "薛綜", "三国", "选曹尚书", "字敬文，沛郡竹邑人。", []),
    # —— 63 吳範劉惇趙達 ——
    ("p_wufan_sg", "吴范", "吳範", "三国", "骑都尉", "字文则，会稽上虞人。", []),
    ("p_liudun_sg", "刘惇", "劉惇", "三国", "辅正中郎将", "字子仁，平原人。", []),
    ("p_zhaoda_sg", "赵达", "趙達", "三国", "太史丞", "河南人，善算。", []),
    # —— 05 后妃（主要几位）——
    ("p_bianshi_sg", "卞氏", "卞氏", "三国", "武宣卞皇后", "魏武帝皇后，琅邪开阳人。", ["武宣卞皇后", "卞皇后"]),
    ("p_zhenshi_sg", "甄氏", "甄氏", "三国", "文昭甄皇后", "魏文帝皇后，中山无极人。", ["文昭甄皇后", "甄皇后", "甄宓"]),
    ("p_guonvwang_sg", "郭女王", "郭女王", "三国", "文德郭皇后", "魏明帝母，广宗人。", ["文德郭皇后", "郭皇后"]),
]

# 空卷 → 篇主 pid 列表（与 volumes/sgz.json 对齐）
OWNER_FILL = {
    "05": ["p_bianshi_sg", "p_zhenshi_sg", "p_guonvwang_sg"],
    "11": ["p_yuanhuan_sg", "p_liangmao_sg", "p_guoyuan_sg", "p_tianchou_sg",
           "p_wangxiu_sg", "p_bingyuan_sg", "p_guanning_sg"],
    "13": ["p_zhongyao_sg", "p_huaxin_sg", "p_wanglang_sg"],
    "15": ["p_liufu_sg", "p_simalang_sg", "p_liangxi_sg", "p_zhangji_sg",
           "p_wenhui_sg", "p_jiakui_sg"],
    "16": ["p_renjun_sg", "p_suze_sg", "p_duji_sg", "p_zhenghun_sg", "p_cangci_sg"],
    "21": ["p_wangcan_sg", "p_weikan_sg", "p_liuyi_sg", "p_liushao_sg", "p_fugu_sg"],
    "22": ["p_huanjie_sg", "p_chenqun_sg", "p_chenjiao_sg", "p_xuxuan_sg",
           "p_weizhen_sg", "p_luyu_sg"],
    "23": ["p_heqia_sg", "p_changlin_sg", "p_yangjun_sg", "p_duqi_sg",
           "p_zhaoyan_sg", "p_peiqian_sg"],
    "24": ["p_hanji_sg", "p_cuilin_sg", "p_gaorou_sg", "p_sunli_sg", "p_wangguan_sg"],
    "25": ["p_xinpi_sg", "p_yangfu_sg", "p_gaotanglong_sg"],
    "26": ["p_manchong_sg", "p_tianyu_sg", "p_qianzhao_sg", "p_guohuai_sg"],
    "27": ["p_xumiao_sg", "p_huzhi_sg", "p_wangchang_sg", "p_wangji_sg"],
    "29": ["p_huatuo", "p_zhuxuanping_sg", "p_zhouxuan_fa", "p_guanlu_sg"],
    # 30 烏丸鮮卑東夷：民族合传，与 hhs-85–90 / sj-116 一致，保持空
    "41": ["p_huojun_sg", "p_wanglian_sg", "p_xianglang_sg", "p_zhangyi_sg",
           "p_yanghong_sg", "p_feishi_sg"],
    "42": ["p_duwei_sg", "p_zhouqun_sg", "p_xuci_sg", "p_menguang_sg",
           "p_laimin_sg", "p_yinmo_sg", "p_qiaozhou_sg", "p_xizheng_sg"],
    "53": ["p_zhanghong", "p_yanjun_sg", "p_chengbing_sg", "p_kanze_sg", "p_xuezong_sg"],
    "63": ["p_wufan_sg", "p_liudun_sg", "p_zhaoda_sg"],
}


def main() -> None:
    text = BD.read_text(encoding="utf-8")
    orig = text

    # 1) 在 PERSONS.extend([...]) 结束前插入新人
    if "p_zhongyao_sg" not in text:
        lines = ["PERSONS.extend([\n"]
        for pid, jian, fan, dy, title, summary, aliases in NEW_PERSONS:
            al = ", ".join(repr(a).replace("'", '"') for a in aliases)
            # 元组字面量用双引号统一
            al = "[" + ", ".join('"%s"' % a for a in aliases) + "]"
            lines.append(
                '    ("%s", "%s", "%s", "%s", "%s", "%s", %s),\n'
                % (pid, jian, fan, dy, title, summary, al)
            )
        lines.append("])\n\n")
        block = "".join(lines)
        marker = "PERSONS.extend([\n"
        # 插在最后一个 PERSONS.extend 块之后：找「])」结束的 extend——
        # 更稳妥：在「# ===== 《汉书》人物书作用域」前插入
        anchor = "# ===== 《汉书》人物书作用域"
        if anchor not in text:
            raise SystemExit("找不到 PERSON_BOOKS_HS 锚点")
        text = text.replace(anchor, block + anchor, 1)

    # 2) 填 CHAPTER_OWNERS_SGZ 空键
    # 匹配 "05": [],
    for slug, pids in OWNER_FILL.items():
        lit = ", ".join('"%s"' % p for p in pids)
        # 仅当该键在 CHAPTER_OWNERS_SGZ 区域且为空时替换
        pat = re.compile(
            r'("CHAPTER_OWNERS_SGZ\s*=\s*\{.*?)(?P<key>"%s":\s*\[\s*\])' % re.escape(slug),
            re.S,
        )
        if pat.search(text):
            text = pat.sub(lambda m: m.group(1) + '"%s": [%s]' % (slug, lit), text, count=1)
        else:
            # 可能已非空，跳过
            if re.search(r'"CHAPTER_OWNERS_SGZ[\s\S]*?"%s":\s*\[[^\]]' % re.escape(slug), text):
                print("skip non-empty", slug)
            else:
                print("WARN missing key", slug)

    # 3) PERSON_BOOKS_SGZ 补新人（仅 sgz）
    if "p_zhongyao_sg" not in text.split("PERSON_BOOKS_SGZ", 1)[-1][:5000]:
        scope_block = "".join(
            '    "%s": ["sgz"],\n' % pid
            for pid, *_ in NEW_PERSONS
        )
        # 插在 PERSON_BOOKS_SGZ = { 之后
        text = text.replace(
            "PERSON_BOOKS_SGZ = {",
            "PERSON_BOOKS_SGZ = {\n" + scope_block,
            1,
        )

    if text == orig:
        print("no changes")
        return
    BD.write_text(text, encoding="utf-8")
    print("updated", BD)
    print("new persons", len(NEW_PERSONS), "owner keys", len(OWNER_FILL))


if __name__ == "__main__":
    main()
