# pipeline/_enrich_persons_tier1.py
# -*- coding: utf-8 -*-
"""梯队一：40位核心历史无传名将谋臣安全写入 workbook/persons.xlsx"""
import os
import sys
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

TIER1_PERSONS = [
    {
        "id": "p_lijue", "tradName": "李傕", "name": "李傕", "dynasty": "東漢",
        "title": "車騎將軍", "summary": "字稚然，北地泥陽人，董卓部將，卓死後與郭汜等破長安、挾獻帝，後為段煨等所殺。",
        "aliases": "李傕|稚然", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 1, "pinyin": "lijue"
    },
    {
        "id": "p_zhugedan", "tradName": "諸葛誕", "name": "诸葛诞", "dynasty": "三國",
        "title": "征東大將軍", "summary": "字公休，瑯邪陽都人，魏征東大將軍，淮南起兵反司馬昭，戰敗被斬。",
        "aliases": "諸葛誕|诸葛诞|公休", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "zhugedan"
    },
    {
        "id": "p_wangrong", "tradName": "王戎", "name": "王戎", "dynasty": "西晉",
        "title": "司徒", "summary": "字濬沖，瑯邪臨沂人，竹林七賢之一，西晉開國元勳，官至司徒，封安豐侯。",
        "aliases": "王戎|濬沖|濬冲", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "wangrong"
    },
    {
        "id": "p_wenqin", "tradName": "文欽", "name": "文钦", "dynasty": "三國",
        "title": "前將軍", "summary": "字仲若，譙郡人，魏前將軍、揚州刺史，與毌丘儉起兵反司馬師，降吳，後為諸葛誕所害。",
        "aliases": "文欽|文钦|仲若", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "wenqin"
    },
    {
        "id": "p_ranmin", "tradName": "冉閔", "name": "冉闵", "dynasty": "十六國",
        "title": "冉魏皇帝", "summary": "字永曾，魏郡內黃人，石虎養孫，後建立冉魏政權稱帝，十六國風雲人物。",
        "aliases": "冉閔|冉闵|永曾|石閔|石闵", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "ranmin"
    },
    {
        "id": "p_dongcheng", "tradName": "董承", "name": "董承", "dynasty": "東漢",
        "title": "車騎將軍", "summary": "漢靈帝母董太后之姪，獻帝妃董貴人之父，車騎將軍，受獻帝衣帶詔誅曹操，事洩被殺。",
        "aliases": "董承", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 1, "pinyin": "dongcheng"
    },
    {
        "id": "p_suihe", "tradName": "隨何", "name": "随何", "dynasty": "西漢",
        "title": "護軍中尉", "summary": "漢初著名說客，劉邦遣其說九江王英布背楚歸漢，定楚漢成敗之局。",
        "aliases": "隨何|随何", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "suihe"
    },
    {
        "id": "p_qifuren", "tradName": "戚夫人", "name": "戚夫人", "dynasty": "西漢",
        "title": "夫人", "summary": "漢高祖劉邦寵姬，生趙隱王如意，高祖崩後為呂后所害。",
        "aliases": "戚夫人|戚姬", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qifuren"
    },
    {
        "id": "p_wenyang", "tradName": "文鴦", "name": "文鸯", "dynasty": "三國",
        "title": "東夷校尉", "summary": "名俶，字次騫，小名鴦，譙郡人，文欽之子，勇力絕人，魏晉第一猛將。",
        "aliases": "文鴦|文鸯|文俶|次騫|次骞", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "wenyang"
    },
    {
        "id": "p_shenpei", "tradName": "審配", "name": "审配", "dynasty": "東漢",
        "title": "治中", "summary": "字正南，魏郡陰安人，袁紹核心謀臣，官渡敗後死守鄴城數月，城陷不屈就義。",
        "aliases": "審配|审配|正南", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "shenpei"
    },
    {
        "id": "p_lukang_sg", "tradName": "陸抗", "name": "陆抗", "dynasty": "三國",
        "title": "大司馬", "summary": "字幼節，吳郡吳縣人，陸遜次子，東吳最後名將、大司馬，羊祜之敵友。",
        "aliases": "陸抗|陆抗|幼節|幼节", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "lukang"
    },
    {
        "id": "p_furong_qq", "tradName": "苻融", "name": "苻融", "dynasty": "十六國",
        "title": "征南大將軍", "summary": "字博休，前秦宣昭帝苻堅之弟，征南大將軍、陽平公，淝水之戰前鋒主帥陣亡。",
        "aliases": "苻融|博休", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "furong"
    },
    {
        "id": "p_hanshuo_xh", "tradName": "韓說", "name": "韩说", "dynasty": "西漢",
        "title": "橫海將軍", "summary": "韓王信曾孫，按道侯、橫海將軍，巫蠱之禍中為戾太子劉據所斬。",
        "aliases": "韓說|韩说", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "hanshuo"
    },
    {
        "id": "p_shichong", "tradName": "石崇", "name": "石崇", "dynasty": "西晉",
        "title": "衛尉", "summary": "字季倫，渤海南皮人，石苞之子，西晉衛尉，巨富，金谷二十四友，八王之亂被殺。",
        "aliases": "石崇|季倫|季伦", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "shichong"
    },
    {
        "id": "p_zhuxu", "tradName": "朱序", "name": "朱序", "dynasty": "東晉",
        "title": "龍驤將軍", "summary": "字次倫，義陽平氏人，東晉將領，淝水之戰陣前大呼助晉破秦，官至豫州刺史。",
        "aliases": "朱序|次倫|次伦", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "zhuxu"
    },
    {
        "id": "p_tianfeng", "tradName": "田豐", "name": "田丰", "dynasty": "東漢",
        "title": "別駕", "summary": "字元皓，鉅鹿人，袁紹首席謀士，多謀善策，官渡戰前極諫，後為袁紹所害。",
        "aliases": "田豐|田丰|元皓", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 1, "in_hhs": 1, "in_sgz": 1, "in_js": 1, "pinyin": "tianfeng"
    },
    {
        "id": "p_jushou", "tradName": "沮授", "name": "沮授", "dynasty": "東漢",
        "title": "監軍", "summary": "廣平人，袁紹監軍，官渡戰略策劃者，官渡敗後被俘不降被殺。",
        "aliases": "沮授", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "jushou"
    },
    {
        "id": "p_yanliang", "tradName": "顏良", "name": "颜良", "dynasty": "東漢",
        "title": "將軍", "summary": "袁紹麾下頭號驍將，官渡白馬之戰為關羽所斬。",
        "aliases": "顏良|颜良", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "yanliang"
    },
    {
        "id": "p_guotu", "tradName": "郭圖", "name": "郭图", "dynasty": "東漢",
        "title": "謀士", "summary": "字公則，潁川人，袁紹重要謀臣，官渡敗後助袁譚，後為曹操所斬。",
        "aliases": "郭圖|郭图|公則|公则", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "guotu"
    },
    {
        "id": "p_fengji", "tradName": "逢紀", "name": "逢纪", "dynasty": "東漢",
        "title": "謀士", "summary": "字元圖，南陽人，袁紹創業親信謀臣，多智籌，後為袁譚所殺。",
        "aliases": "逢紀|逢纪|元圖|元图", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "fengji"
    },
    {
        "id": "p_huanghao", "tradName": "黃皓", "name": "黄皓", "dynasty": "三國",
        "title": "中常侍", "summary": "蜀漢宦官，深得後主劉禪寵信，專擅朝政，誤國害民。",
        "aliases": "黃皓|黄皓", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "huanghao"
    },
    {
        "id": "p_zhuling", "tradName": "朱靈", "name": "朱灵", "dynasty": "三國",
        "title": "後將軍", "summary": "字文博，清河鄃人，曹魏名將，封高唐侯，與于禁、張郃齊名。",
        "aliases": "朱靈|朱灵|文博", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "zhuling"
    },
    {
        "id": "p_wenchou", "tradName": "文醜", "name": "文丑", "dynasty": "東漢",
        "title": "將軍", "summary": "袁紹名將，與顏良齊名，官渡延津之戰戰死。",
        "aliases": "文醜|文丑", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "wenchou"
    },
    {
        "id": "p_dingyuan", "tradName": "丁原", "name": "丁原", "dynasty": "東漢",
        "title": "并州刺史", "summary": "字建陽，并州刺史、執金吾，呂布最初統領，進京後為董卓誘呂布所殺。",
        "aliases": "丁原|建陽|建阳", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "dingyuan"
    },
    {
        "id": "p_duanwei", "tradName": "段煨", "name": "段煨", "dynasty": "東漢",
        "title": "鎮遠將軍", "summary": "字忠明，武威姑臧人，董卓部將，鎮守華陰勤修農桑，後誅李傕，封閿鄉侯。",
        "aliases": "段煨|忠明", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 1, "pinyin": "duanwei"
    },
    {
        "id": "p_niufu", "tradName": "牛輔", "name": "牛辅", "dynasty": "東漢",
        "title": "中郎將", "summary": "董卓女婿，董卓死後屯陝縣，軍亂為左右所害。",
        "aliases": "牛輔|牛辅", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "niufu"
    },
    {
        "id": "p_huoshan", "tradName": "霍山", "name": "霍山", "dynasty": "西漢",
        "title": "奉車都尉", "summary": "霍光兄孫，樂平侯，領尚書事，霍氏謀逆事洩自殺。",
        "aliases": "霍山", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "huoshan"
    },
    {
        "id": "p_jianggan", "tradName": "蔣幹", "name": "蒋干", "dynasty": "三國",
        "title": "幕客", "summary": "字子翼，九江人，曹操幕客名士，曾往江東說周瑜。",
        "aliases": "蔣幹|蒋干|子翼", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "jianggan"
    },
    {
        "id": "p_niujin", "tradName": "牛金", "name": "牛金", "dynasty": "三國",
        "title": "後將軍", "summary": "曹仁部將，魏名將，官至後將軍，征蜀破諸葛亮、征遼東破公孫淵皆立戰功。",
        "aliases": "牛金", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "niujin"
    },
    {
        "id": "p_gaoshun", "tradName": "高順", "name": "高顺", "dynasty": "東漢",
        "title": "將軍", "summary": "呂布部將，統率「陷陣營」，每戰必克，為人清白嚴肅，下邳城破從容就義。",
        "aliases": "高順|高顺", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "gaoshun"
    },
    {
        "id": "p_quyi", "tradName": "麴義", "name": "麴义", "dynasty": "東漢",
        "title": "將軍", "summary": "袁紹部將，驍勇善戰，界橋之戰以先登死士大破公孫瓚白馬義從，後恃功自傲被殺。",
        "aliases": "麴義|麴义|曲義|曲义", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "quyi"
    },
    {
        "id": "p_guanqiujian", "tradName": "毋丘儉", "name": "毋丘俭", "dynasty": "三國",
        "title": "鎮東將軍", "summary": "字仲恭，河東聞喜人，魏名將，遠征高句麗勒石記功，後淮南起兵反司馬師敗死。",
        "aliases": "毋丘儉|毋丘俭|毌丘儉|毌丘俭|仲恭", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "guanqiujian"
    },
    {
        "id": "p_xunchen", "tradName": "荀諶", "name": "荀谌", "dynasty": "東漢",
        "title": "謀臣", "summary": "字友若，潁川潁陰人，荀彧之兄，袁紹重要謀士，曾說韓馥讓冀州。",
        "aliases": "荀諶|荀谌|友若", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "xunchen"
    },
    {
        "id": "p_fuwan", "tradName": "伏完", "name": "伏完", "dynasty": "東漢",
        "title": "屯騎校尉", "summary": "漢獻帝伏皇后之父，不其侯，官至屯騎校尉，受后密信謀誅曹操，不敢發，病卒。",
        "aliases": "伏完", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "fuwan"
    },
    {
        "id": "p_ruanxian", "tradName": "阮咸", "name": "阮咸", "dynasty": "西晉",
        "title": "散騎侍郎", "summary": "字仲容，陳留尉氏人，阮籍之姪，竹林七賢之一，精通音律，阮咸琵琶名祖。",
        "aliases": "阮咸|仲容", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "ruanxian"
    },
    {
        "id": "p_xizhicai", "tradName": "戲志才", "name": "戏志才", "dynasty": "東漢",
        "title": "謀士", "summary": "潁川人，曹操早期極其倚重之核心謀臣，早卒，荀彧薦郭嘉以代之。",
        "aliases": "戲志才|戏志才", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "xizhicai"
    },
    {
        "id": "p_haozhao", "tradName": "郝昭", "name": "郝昭", "dynasty": "三國",
        "title": "鎮西將軍", "summary": "字伯道，太原人，曹魏名將，陳倉之戰以千餘人阻諸葛亮大軍二十餘日，拜關內侯。",
        "aliases": "郝昭|伯道", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "haozhao"
    },
    {
        "id": "p_guanping", "tradName": "關平", "name": "关平", "dynasty": "三國",
        "title": "將軍", "summary": "河東解縣人，關羽長子，隨關羽鎮守荊州，兵敗臨沮與關羽一同殉難。",
        "aliases": "關平|关平", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "guanping"
    },
    {
        "id": "p_zhangbao_sg", "tradName": "張苞", "name": "张苞", "dynasty": "三國",
        "title": "將軍", "summary": "涿郡人，張飛長子，早夭，子張遵在綿竹戰死。",
        "aliases": "張苞|张苞", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "zhangbao_sg"
    },
    {
        "id": "p_huaxiong", "tradName": "華雄", "name": "华雄", "dynasty": "東漢",
        "title": "都督", "summary": "董卓部將，都督，關東軍討董時於陽人城戰役中為孫堅所斬。",
        "aliases": "華雄|华雄", "status": "active", "note": "梯隊一核心名將·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "huaxiong"
    },
]

# 需要就地补齐别名的已有实体
PATCH_ALIASES = {
    "p_mizhu": "麋竺",   # 补鹿字旁麋竺
    "p_mifang": "麋芳",  # 补鹿字旁麋芳
}

def main():
    xlsx_path = os.path.join(common.ROOT, "workbook", "persons.xlsx")
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["人物"]
    
    # 建立现有 ID 与 行 映射
    id_to_row = {}
    existing_ids = set()
    existing_trads = set()
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
        pid = row[0].value
        trad = row[1].value
        if pid:
            id_to_row[pid] = row_idx
            existing_ids.add(pid)
        if trad:
            existing_trads.add(trad)

    print(f"原人物表行数: {ws.max_row - 1}")

    # 1. 补齐已有实体别名
    for pid, extra_alias in PATCH_ALIASES.items():
        if pid in id_to_row:
            r_idx = id_to_row[pid]
            cell = ws.cell(row=r_idx, column=7)  # column 7: 别名
            cur_val = cell.value or ""
            parts = [p.strip() for p in cur_val.split("|") if p.strip()]
            if extra_alias not in parts:
                parts.append(extra_alias)
                cell.value = "|".join(parts)
                print(f"  [补齐别名] {pid} -> {cell.value}")

    # 2. 追加新人物
    added = 0
    for p in TIER1_PERSONS:
        pid = p["id"]
        trad = p["tradName"]
        if pid in existing_ids:
            print(f"  [跳过已存在ID] {pid} ({trad})")
            continue
        if trad in existing_trads:
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

    print(f"成功追加新人物: {added} 人")
    print(f"新人物表总行数: {ws.max_row - 1}")

    # 安全写盘
    common.safe_save_workbook(wb, xlsx_path)
    print(f"✓ 权威源 {xlsx_path} 已通过 safe_save_workbook 安全保存！")

if __name__ == "__main__":
    main()
