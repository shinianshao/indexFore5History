# pipeline/_enrich_persons_tier3_batch1.py
# -*- coding: utf-8 -*-
"""梯队三第一批：三国无传名将谋臣（16人）安全写入 workbook/persons.xlsx"""
import os
import sys
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

TIER3_BATCH1_PERSONS = [
    # --- 蜀汉死节名将与重臣（9人） ---
    {
        "id": "p_futong", "tradName": "傅肜", "name": "傅肜", "dynasty": "三國",
        "title": "將軍", "summary": "義陽人，蜀漢名將，章武二年隨劉備東征伐吳，軍潰為斷後大將，力戰至最後一人，吳將大呼令降，肜罵曰“吳狗！何有漢將軍降者！”遂壯烈戰死。",
        "aliases": "傅肜|傅彤", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "futong"
    },
    {
        "id": "p_fuqian_sg", "tradName": "傅僉", "name": "傅佥", "dynasty": "三國",
        "title": "關中都督", "summary": "義陽人，傅肜之子，蜀漢名將，官至關中都督。景耀六年曹魏鍾會大舉伐蜀，陽安關守將蔣舒降魏，傅僉率部死戰力竭而亡，陳壽嘉其父子奕世忠義。",
        "aliases": "傅僉|傅佥", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "fuqian"
    },
    {
        "id": "p_huoyi", "tradName": "霍弋", "name": "霍弋", "dynasty": "三國",
        "title": "南中都督", "summary": "字紹先，南郡枝江人，霍峻之子，蜀漢名將，官至安南將軍、南中都督、建寧太守，統攝南中六郡，保全一方。蜀亡後降晉，仍督南中，封列侯。",
        "aliases": "霍弋|霍紹先|霍绍先", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "huoyi"
    },
    {
        "id": "p_yanyan", "tradName": "嚴顏", "name": "严颜", "dynasty": "東漢",
        "title": "巴郡太守", "summary": "臨江人，益州名將，任巴郡太守。劉備入蜀時為張飛所生擒，飛令其降，顏瞋目叱曰“蜀中但有斷頭將軍，無降將軍也！”飛壯而釋之，引為賓客。",
        "aliases": "嚴顏|严颜", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "yanyan"
    },
    {
        "id": "p_xiangchong", "tradName": "向寵", "name": "向宠", "dynasty": "三國",
        "title": "中部督", "summary": "襄陽宜城人，向朗兄子，蜀漢名將。諸葛亮《出師表》稱“將軍向寵，性行淑均，曉暢軍事，試用於昔日，先帝稱之曰能”，延熙三年征漢嘉叛蠻戰死。",
        "aliases": "向寵|向宠", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "xiangchong"
    },
    {
        "id": "p_fengxi", "tradName": "馮習", "name": "冯习", "dynasty": "三國",
        "title": "領軍大督", "summary": "字休元，南郡人，隨劉備入蜀。章武元年劉備東征伐吳，馮習為領軍大都督，統攝諸軍，章武二年於猇亭戰敗，為吳將潘璋部所斬。",
        "aliases": "馮習|冯习|馮休元|冯休元", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "fengxi"
    },
    {
        "id": "p_zhangnan_sg", "tradName": "張南", "name": "张南", "dynasty": "三國",
        "title": "前部督", "summary": "字文進，自荊州隨劉備入蜀。章武元年東征伐吳，張南為前部督，圍攻孫桓於夷道，次年猇亭軍潰，力戰戰死。",
        "aliases": "張南|张南|張文進|张文进", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "zhangnan"
    },
    {
        "id": "p_chengji", "tradName": "程畿", "name": "程畿", "dynasty": "三國",
        "title": "從事祭酒", "summary": "字季然，巴西閬中人，初為劉璋漢昌長，後歸劉備，拜從事祭酒。隨劉備東征伐吳，軍退溯江，畿曰“吾在軍未曾前敵而逃，何況從天子而奔！”拔戟戰死。",
        "aliases": "程畿|程季然", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "chengji"
    },
    {
        "id": "p_wuban", "tradName": "吳班", "name": "吴班", "dynasty": "三國",
        "title": "驃騎將軍", "summary": "字元雄，陳留人，吳懿族弟，隨劉備入蜀，以豪俠稱。隨劉備東征為前部督，後隨諸葛亮北伐，出祁山大破司馬懿，官至驃騎將軍，封安樂亭侯。",
        "aliases": "吳班|吴班|吳元雄|吴元雄", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "wuban"
    },

    # --- 曹魏宿将与精锐统帅（5人） ---
    {
        "id": "p_caochun", "tradName": "曹純", "name": "曹纯", "dynasty": "三國",
        "title": "高陵亭侯", "summary": "字子和，沛國譙人，曹仁之弟。督率曹魏精銳“虎豹騎”，南皮斬袁譚、白狼山俘蹋頓、長坂追劉備，勇烈剛毅，官至議郎參司空軍事，封高陵亭侯。",
        "aliases": "曹純|曹纯|曹子和", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "caochun"
    },
    {
        "id": "p_qinlang", "tradName": "秦朗", "name": "秦朗", "dynasty": "三國",
        "title": "驍騎將軍", "summary": "字元明，新興雲中人，秦宜祿之子，曹操養子。魏明帝時拜驍騎將軍、給事中，青龍元年率兵大破鮮卑步度根與軻比能，威震北疆。",
        "aliases": "秦朗|秦元明", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "qinlang"
    },
    {
        "id": "p_baoxin", "tradName": "鮑信", "name": "鲍信", "dynasty": "東漢",
        "title": "濟北相", "summary": "字允誠，泰山平陽人，漢末名將，任濟北相。首倡討董卓，深知曹操雄才，迎曹操領兗州牧。初平三年與黃巾軍力戰於壽張，為救曹操力竭戰死。",
        "aliases": "鮑信|鲍信|鮑允誠|鲍允诚", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "baoxin"
    },
    {
        "id": "p_dailing", "tradName": "戴陵", "name": "戴陵", "dynasty": "三國",
        "title": "征蜀將軍", "summary": "曹魏名將。黃初年間任諫議大夫，後隨曹真、司馬懿拒蜀漢，太和五年諸葛亮出祁山，戴陵與張郃同率精騎四千為前鋒抗蜀，晉書作戴淩。",
        "aliases": "戴陵|戴淩|戴凌", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "dailing"
    },
    {
        "id": "p_feiyao", "tradName": "費曜", "name": "费曜", "dynasty": "三國",
        "title": "後將軍", "summary": "一作費耀，曹魏名將，官至後將軍。太和二年諸葛亮攻陳倉，曜奉命解圍；太和四年與魏平破蜀將吳懿；太和五年諸葛亮出祁山，曜與司馬懿同拒諸葛亮。",
        "aliases": "費曜|费曜|費耀|费耀", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "feiyao"
    },

    # --- 东吴冲锋陷阵宿将（2人） ---
    {
        "id": "p_zumao", "tradName": "祖茂", "name": "祖茂", "dynasty": "東漢",
        "title": "將軍", "summary": "字大榮，吳郡富春人，孫堅心腹驍將。初平元年討董之戰，孫堅於梁縣敗於徐榮，茂謂堅曰“明公脫赤幘以見與”，茂戴堅赤幘引賊自代，使堅從小路脫險，茂馳入塚間伏得免。",
        "aliases": "祖茂|祖大榮|祖大荣", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "zumao"
    },
    {
        "id": "p_liuzan", "tradName": "留贊", "name": "留赞", "dynasty": "三國",
        "title": "左將軍", "summary": "字正明，會稽長山人，東吳名將，官至左將軍。臨陣好引吭長嘯、高歌而進，勇冠三軍。太平元年隨孫峻出征，為魏將蔣班圍於道，力疾戰死，天下嗟惜。",
        "aliases": "留贊|留赞|留正明", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "liuzan"
    },
]

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    xlsx_path = os.path.join(root, "workbook", "persons.xlsx")

    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["人物"]

    header = [c for c in next(ws.iter_rows(values_only=True))]
    id_col = header.index("id")
    trad_col = header.index("正名(tradName)")

    existing_ids = set()
    existing_trads = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[id_col]:
            existing_ids.add(str(row[id_col]).strip())
        if row[trad_col]:
            existing_trads.add(str(row[trad_col]).strip())

    print(f"当前 persons.xlsx 现有有效人物: {len(existing_ids)} 人")

    added = 0
    for p in TIER3_BATCH1_PERSONS:
        pid = p["id"]
        trad = p["tradName"]
        if pid in existing_ids:
            print(f"  [跳过已存在ID] {pid} ({trad})")
            continue
        if trad in existing_trads and pid not in ["p_zhangnan_sg"]:
            print(f"  [跳过已存在正名] {trad} (尝试ID: {pid})")
            continue

        new_row = [
            pid,
            p["tradName"],
            p["name"],
            p["dynasty"],
            p["title"],
            p["summary"],
            p["aliases"],
            p["status"],
            p["note"],
            p["in_sj"],
            p["in_hs"],
            p["in_hhs"],
            p["in_sgz"],
            p["in_js"],
            p["pinyin"],
            0
        ]
        ws.append(new_row)
        existing_ids.add(pid)
        existing_trads.add(trad)
        added += 1

    print(f"\n成功追加梯队三第一批新人物: {added} 人")
    print(f"新人物表总行数: {ws.max_row - 1}")

    # 安全写盘
    common.safe_save_workbook(wb, xlsx_path)
    print(f"✓ 权威源 {xlsx_path} 已通过 safe_save_workbook 安全保存！")

if __name__ == "__main__":
    main()
