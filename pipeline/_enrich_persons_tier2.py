# pipeline/_enrich_persons_tier2.py
# -*- coding: utf-8 -*-
"""梯队二：类传传主与孔门七十二贤（62人）安全写入 workbook/persons.xlsx"""
import os
import sys
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

TIER2_PERSONS = [
    # --- 一、孔门七十二贤（史记·仲尼弟子列传漏网传主，共50人） ---
    {
        "id": "p_rangeng", "tradName": "冉耕", "name": "冉耕", "dynasty": "春秋",
        "title": "先賢", "summary": "字伯牛，魯人，孔門十哲德行科，以德行著稱，孔子歎曰“斯人也而有斯疾也”。",
        "aliases": "冉耕|伯牛|冉伯牛", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "rangeng"
    },
    {
        "id": "p_yuanxian_sq", "tradName": "原憲", "name": "原宪", "dynasty": "春秋",
        "title": "先賢", "summary": "字子思，宋人，清貧守道，孔子卒後隱居草澤，子貢相衛過訪，憲衣弊屣履而對。",
        "aliases": "原憲|原宪|原子思", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 1, "pinyin": "yuanxian"
    },
    {
        "id": "p_shangqu", "tradName": "商瞿", "name": "商瞿", "dynasty": "春秋",
        "title": "先賢", "summary": "字子木，魯人，少孔子二十九歲，孔子傳《易》於商瞿，為歷代易學傳承之祖。",
        "aliases": "商瞿|子木|商子木", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "shangqu"
    },
    {
        "id": "p_gaochai", "tradName": "高柴", "name": "高柴", "dynasty": "春秋",
        "title": "先賢", "summary": "字子羔，衛人，少孔子三十歲，受業孔子，仁孝守禮，為費郈二宰。",
        "aliases": "高柴|髙柴|高子羔|子羔", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "gaochai"
    },
    {
        "id": "p_qidiaokai", "tradName": "漆彫開", "name": "漆雕开", "dynasty": "春秋",
        "title": "先賢", "summary": "字子開，蔡人，史記作漆彫開，孔子使之仕，對曰“吾斯之未能信”，孔子說之。",
        "aliases": "漆彫開|漆雕開|漆雕开|漆彫开", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qidiaokai"
    },
    {
        "id": "p_gongboliao", "tradName": "公伯繚", "name": "公伯缭", "dynasty": "春秋",
        "title": "儒者", "summary": "字子周，魯人，孔子弟子，嘗愬子路於季孫。",
        "aliases": "公伯繚|公伯缭|公伯子周", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "gongboliao"
    },
    {
        "id": "p_simageng", "tradName": "司馬耕", "name": "司马耕", "dynasty": "春秋",
        "title": "先賢", "summary": "字子牛，宋人，向魋之弟，言多而躁，憂曰“人皆有兄弟我獨亡”，子夏寬之。",
        "aliases": "司馬耕|司马耕|司馬牛|司马牛", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "simageng"
    },
    {
        "id": "p_fanxu", "tradName": "樊須", "name": "樊须", "dynasty": "春秋",
        "title": "先賢", "summary": "字子遲，魯人，即樊遲，請學稼學圃，問仁問知，孔子稱“小人哉樊須也”。",
        "aliases": "樊須|樊须|樊遲|樊迟|樊子遲|樊子迟", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "fanxu"
    },
    {
        "id": "p_gongxichi", "tradName": "公西赤", "name": "公西赤", "dynasty": "春秋",
        "title": "先賢", "summary": "字子華，魯人，束帶立於朝，可使與賓客言，使齊冉有為其母請粟。",
        "aliases": "公西赤|公西華|公西华", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "gongxichi"
    },
    {
        "id": "p_wumashi", "tradName": "巫馬施", "name": "巫马施", "dynasty": "春秋",
        "title": "先賢", "summary": "字子旗，陳人，少孔子三十歲，陳司敗問昭公知禮乎，巫馬期以告孔子。",
        "aliases": "巫馬施|巫马施|巫馬期|巫马期|巫馬子旗", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "wumashi"
    },
    {
        "id": "p_yanxing_sq", "tradName": "顏幸", "name": "颜幸", "dynasty": "春秋",
        "title": "先賢", "summary": "字子柳，魯人，少孔子四十六歲，受業孔子。",
        "aliases": "顏幸|颜幸|顏子柳|颜子柳", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "yanxing"
    },
    {
        "id": "p_boqian", "tradName": "伯虔", "name": "伯虔", "dynasty": "春秋",
        "title": "先賢", "summary": "字子析，少孔子五十歲，受業孔子。",
        "aliases": "伯虔|伯子析", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "boqian"
    },
    {
        "id": "p_gongzujuzi", "tradName": "公祖句茲", "name": "公祖句兹", "dynasty": "春秋",
        "title": "先賢", "summary": "字子之，魯人，少孔子五十四歲，受業孔子。",
        "aliases": "公祖句茲|公祖句兹", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "gongzujuzi"
    },
    {
        "id": "p_qinzu", "tradName": "秦祖", "name": "秦祖", "dynasty": "春秋",
        "title": "先賢", "summary": "字子南，秦人，受業孔子。",
        "aliases": "秦祖|秦子南", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qinzu"
    },
    {
        "id": "p_qidiaoduo", "tradName": "漆雕哆", "name": "漆雕哆", "dynasty": "春秋",
        "title": "先賢", "summary": "字子斂，魯人，受業孔子。",
        "aliases": "漆雕哆|漆彫哆", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "qidiaoduo"
    },
    {
        "id": "p_rangsichi", "tradName": "壤駟赤", "name": "壤驷赤", "dynasty": "春秋",
        "title": "先賢", "summary": "字子徒，秦人，受業孔子。",
        "aliases": "壤駟赤|壤驷赤", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "rangsichi"
    },
    {
        "id": "p_gongliangru", "tradName": "公良孺", "name": "公良孺", "dynasty": "春秋",
        "title": "先賢", "summary": "字子正，陳人，賢而有勇，孔子伐木於宋，公良孺以私車五乘從。",
        "aliases": "公良孺", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "gongliangru"
    },
    {
        "id": "p_houchu", "tradName": "后處", "name": "后处", "dynasty": "春秋",
        "title": "先賢", "summary": "字子里，齊人，受業孔子。",
        "aliases": "后處|后处|後處|後处", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "houchu"
    },
    {
        "id": "p_qinran", "tradName": "秦冉", "name": "秦冉", "dynasty": "春秋",
        "title": "先賢", "summary": "字開，蔡人，受業孔子。",
        "aliases": "秦冉", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qinran"
    },
    {
        "id": "p_gongxiashou", "tradName": "公夏首", "name": "公夏首", "dynasty": "春秋",
        "title": "先賢", "summary": "字乘，魯人，受業孔子。",
        "aliases": "公夏首", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "gongxiashou"
    },
    {
        "id": "p_xirongzhen", "tradName": "奚容箴", "name": "奚容箴", "dynasty": "春秋",
        "title": "先賢", "summary": "字子皙，衛人，受業孔子。",
        "aliases": "奚容箴", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "xirongzhen"
    },
    {
        "id": "p_gongjianding", "tradName": "公肩定", "name": "公肩定", "dynasty": "春秋",
        "title": "先賢", "summary": "字子中，魯人，受業孔子。",
        "aliases": "公肩定", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "gongjianding"
    },
    {
        "id": "p_yanzu", "tradName": "顏祖", "name": "颜祖", "dynasty": "春秋",
        "title": "先賢", "summary": "字襄，魯人，受業孔子。",
        "aliases": "顏祖|颜祖", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "yanzu"
    },
    {
        "id": "p_qiaodan", "tradName": "鄡單", "name": "鄡单", "dynasty": "春秋",
        "title": "先賢", "summary": "字子家，魯人，受業孔子。",
        "aliases": "鄡單|鄡单", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qiaodan"
    },
    {
        "id": "p_hanfuhei", "tradName": "罕父黑", "name": "罕父黑", "dynasty": "春秋",
        "title": "先賢", "summary": "字子索，魯人，受業孔子。",
        "aliases": "罕父黑", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "hanfuhei"
    },
    {
        "id": "p_qinshang", "tradName": "秦商", "name": "秦商", "dynasty": "春秋",
        "title": "先賢", "summary": "字子丕，魯人，少孔子四十歲，父堇父與孔子父叔梁紇俱以勇力聞。",
        "aliases": "秦商|秦子丕", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qinshang"
    },
    {
        "id": "p_shendang", "tradName": "申黨", "name": "申党", "dynasty": "春秋",
        "title": "先賢", "summary": "字周，魯人，少孔子五十歲，受業孔子。",
        "aliases": "申黨|申党", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "shendang"
    },
    {
        "id": "p_yanzhipu", "tradName": "顏之僕", "name": "颜之仆", "dynasty": "春秋",
        "title": "先賢", "summary": "字叔，魯人，受業孔子。",
        "aliases": "顏之僕|颜之仆", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "yanzhipu"
    },
    {
        "id": "p_rongqi", "tradName": "榮旂", "name": "荣旂", "dynasty": "春秋",
        "title": "先賢", "summary": "字子祈，魯人，受業孔子。",
        "aliases": "榮旂|荣旂", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "rongqi"
    },
    {
        "id": "p_xiancheng", "tradName": "縣成", "name": "县成", "dynasty": "春秋",
        "title": "先賢", "summary": "字子祺，魯人，受業孔子。",
        "aliases": "縣成|县成", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "xiancheng"
    },
    {
        "id": "p_shizhichang", "tradName": "施之常", "name": "施之常", "dynasty": "春秋",
        "title": "先賢", "summary": "字子恒，魯人，受業孔子。",
        "aliases": "施之常", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "shizhichang"
    },
    {
        "id": "p_yankai", "tradName": "顏噲", "name": "颜噲", "dynasty": "春秋",
        "title": "先賢", "summary": "字子聲，魯人，受業孔子。",
        "aliases": "顏噲|颜噲", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "yankai"
    },
    {
        "id": "p_bushucheng", "tradName": "步叔乘", "name": "步叔乘", "dynasty": "春秋",
        "title": "先賢", "summary": "字子車，齊人，受業孔子。",
        "aliases": "步叔乘", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "bushucheng"
    },
    {
        "id": "p_yuankang_sq", "tradName": "原亢", "name": "原亢", "dynasty": "春秋",
        "title": "先賢", "summary": "字籍，魯人，受業孔子。",
        "aliases": "原亢", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "yuankang"
    },
    {
        "id": "p_lekai", "tradName": "樂欬", "name": "乐欬", "dynasty": "春秋",
        "title": "先賢", "summary": "字子聲，魯人，受業孔子。",
        "aliases": "樂欬|乐欬", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "lekai"
    },
    {
        "id": "p_lianjie", "tradName": "廉絜", "name": "廉絜", "dynasty": "春秋",
        "title": "先賢", "summary": "字庸，衛人，受業孔子。",
        "aliases": "廉絜", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "lianjie"
    },
    {
        "id": "p_shuzhonghui", "tradName": "叔仲會", "name": "叔仲会", "dynasty": "春秋",
        "title": "先賢", "summary": "字子期，魯人，少孔子五十歲，細書寫經，受業孔子。",
        "aliases": "叔仲會|叔仲会", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "shuzhonghui"
    },
    {
        "id": "p_yanhe_sq", "tradName": "顏何", "name": "颜何", "dynasty": "春秋",
        "title": "先賢", "summary": "字冉，魯人，受業孔子。",
        "aliases": "顏何|颜何", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "yanhe"
    },
    {
        "id": "p_dihei", "tradName": "狄黑", "name": "狄黑", "dynasty": "春秋",
        "title": "先賢", "summary": "字皙，魯人，受業孔子。",
        "aliases": "狄黑", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "dihei"
    },
    {
        "id": "p_bangxun", "tradName": "邦巽", "name": "邦巽", "dynasty": "春秋",
        "title": "先賢", "summary": "字子斂，魯人，受業孔子。",
        "aliases": "邦巽", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "bangxun"
    },
    {
        "id": "p_gongxiyuru", "tradName": "公西輿如", "name": "公西舆如", "dynasty": "春秋",
        "title": "先賢", "summary": "字子上，魯人，受業孔子。",
        "aliases": "公西輿如|公西舆如", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "gongxiyuru"
    },
    {
        "id": "p_gongxizhen", "tradName": "公西葴", "name": "公西葴", "dynasty": "春秋",
        "title": "先賢", "summary": "字子上，魯人，受業孔子。",
        "aliases": "公西葴", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "gongxizhen"
    },
    {
        "id": "p_chenkang", "tradName": "陳亢", "name": "陈亢", "dynasty": "春秋",
        "title": "先賢", "summary": "字子禽，陳人，問伯魚異聞，問政於子貢。",
        "aliases": "陳亢|陈亢|陳子禽|陈子禽", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "chenkang"
    },
    {
        "id": "p_dantai", "tradName": "澹臺滅明", "name": "澹台灭明", "dynasty": "春秋",
        "title": "先賢", "summary": "字子羽，武城人，少孔子三十九歲，狀貌甚惡，南遊至江，弟子三百人，行不由徑。",
        "aliases": "澹臺滅明|澹台灭明|澹臺子羽|澹台子羽", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "dantai"
    },
    {
        "id": "p_gongyechang", "tradName": "公冶長", "name": "公冶长", "dynasty": "春秋",
        "title": "先賢", "summary": "字子長，齊人，通鳥語，孔子以女妻之，曰“雖在縲紲之中，非其罪也”。",
        "aliases": "公冶長|公冶长|公冶子長", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "gongyechang"
    },
    {
        "id": "p_gongxiai", "tradName": "公皙哀", "name": "公皙哀", "dynasty": "春秋",
        "title": "先賢", "summary": "字季次，齊人，孔子曰“天下無行，多為家臣，仕於都，唯季次未嘗仕”。",
        "aliases": "公皙哀|公皙季次", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "gongxiai"
    },
    {
        "id": "p_zengdian", "tradName": "曾蒧", "name": "曾蒧", "dynasty": "春秋",
        "title": "先賢", "summary": "字皙，魯人，曾參之父，孔子問志，蒧曰“浴乎沂風乎舞雩詠而歸”，孔子曰“吾與點也”。",
        "aliases": "曾蒧|曾點|曾点|曾皙", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "zengdian"
    },
    {
        "id": "p_yanlu", "tradName": "顏無繇", "name": "颜无繇", "dynasty": "春秋",
        "title": "先賢", "summary": "字路，魯人，顏回之父，少孔子六歲，父子俱事孔子。",
        "aliases": "顏無繇|颜无繇|顏路|颜路", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "yanlu"
    },
    {
        "id": "p_yangao", "tradName": "顏高", "name": "颜高", "dynasty": "春秋",
        "title": "先賢", "summary": "字子驕，魯人，受業孔子，史記作顏髙。",
        "aliases": "顏高|颜高|顏髙|颜髙", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "yangao"
    },
    {
        "id": "p_zhengguo_sq", "tradName": "鄭國", "name": "郑国", "dynasty": "春秋",
        "title": "先賢", "summary": "字子徒，受業孔子，非水工鄭國。",
        "aliases": "鄭國|郑国|孔門鄭國", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "zhengguo"
    },
    {
        "id": "p_qinfei", "tradName": "秦非", "name": "秦非", "dynasty": "春秋",
        "title": "先賢", "summary": "字子之，受業孔子。",
        "aliases": "秦非|秦子之", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qinfei"
    },
    {
        "id": "p_kongzhong", "tradName": "孔忠", "name": "孔忠", "dynasty": "春秋",
        "title": "先賢", "summary": "字子蔑，孔子兄孟皮之子，受業孔子。",
        "aliases": "孔忠|孔子蔑", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "kongzhong"
    },
    {
        "id": "p_qinzhang", "tradName": "琴張", "name": "琴张", "dynasty": "春秋",
        "title": "先賢", "summary": "字子開，衛人，宗魯死，琴張往弔，受業孔子。",
        "aliases": "琴張|琴张", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "qinzhang"
    },
    {
        "id": "p_xiandan", "tradName": "縣亶", "name": "县亶", "dynasty": "春秋",
        "title": "先賢", "summary": "字子象，受業孔子。",
        "aliases": "縣亶|县亶", "status": "active", "note": "梯隊二孔門弟子·docs/46",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "xiandan"
    },

    # --- 二、晋代隐逸/文苑名士泰斗（6人） ---
    {
        "id": "p_taoqian_js", "tradName": "陶潛", "name": "陶潜", "dynasty": "東晉",
        "title": "靖節先生", "summary": "字元亮，一說名淵明，潯陽柴桑人，大司馬陶侃曾孫，彭澤令，不為五斗米折腰，千古田園詩人之祖。",
        "aliases": "陶潛|陶潜|陶淵明|陶渊明|陶元亮|靖節先生", "status": "active", "note": "梯隊二隱逸名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "taoqian"
    },
    {
        "id": "p_gukaizhi", "tradName": "顧愷之", "name": "顾恺之", "dynasty": "東晉",
        "title": "散騎常侍", "summary": "字長康，小字虎頭，晉陵無錫人，博學有才氣，工書法，尤精繪畫，時人稱其有三絕：才絕、畫絕、癡絕。",
        "aliases": "顧愷之|顾恺之|顧長康|顾长康|顧虎頭|顾虎头", "status": "active", "note": "梯隊二文苑名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "gukaizhi"
    },
    {
        "id": "p_yuanhong_js", "tradName": "袁宏", "name": "袁宏", "dynasty": "東晉",
        "title": "東陽太守", "summary": "字彥伯，陳郡陽夏人，少孤貧，謝尚引為參軍，著《後漢紀》三十卷及《詠史》《三國名臣序贊》。",
        "aliases": "袁宏|袁彥伯|袁彦伯", "status": "active", "note": "梯隊二文苑名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "yuanhong"
    },
    {
        "id": "p_liulinzhi", "tradName": "劉驎之", "name": "刘驎之", "dynasty": "東晉",
        "title": "高尚先生", "summary": "字子驥，南陽人，好游山澤，志存遁逸，《桃花源記》“南陽劉子驥，高尚士也，聞之欣然規往”即其人。",
        "aliases": "劉驎之|刘驎之|劉子驥|刘子骥", "status": "active", "note": "梯隊二隱逸名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 1, "pinyin": "liulinzhi"
    },
    {
        "id": "p_lubao", "tradName": "魯褒", "name": "鲁褒", "dynasty": "西晉",
        "title": "隱士", "summary": "字元道，南陽人，好學多聞，以貧素自立，痛感西晉世風貪婪腐敗，作千古名篇《錢神論》疾世。",
        "aliases": "魯褒|鲁褒|魯元道|鲁元道", "status": "active", "note": "梯隊二隱逸名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "lubao"
    },
    {
        "id": "p_chenggongsui", "tradName": "成公綏", "name": "成公绥", "dynasty": "西晉",
        "title": "中書侍郎", "summary": "字子安，東郡白馬人，少有俊才，辭賦名家，作《天地賦》《嘯賦》，張華深器之。",
        "aliases": "成公綏|成公绥|成公子安", "status": "active", "note": "梯隊二文苑名士·docs/46",
        "in_sj": 0, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 1, "pinyin": "chenggongsui"
    },

    # --- 三、两汉魏晋名媛才女（2人） ---
    {
        "id": "p_caiyan_wj", "tradName": "蔡琰", "name": "蔡琰", "dynasty": "東漢",
        "title": "女文士", "summary": "字文姬，陳留圉人，蔡邕之女，博學有才辯，通音律，陷匈奴十二年，曹操贖還，作《悲憤詩》《胡笳十八拍》。",
        "aliases": "蔡琰|蔡文姬|文姬", "status": "active", "note": "梯隊二列女名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "caiyan"
    },
    {
        "id": "p_xiedaoyun", "tradName": "謝道韞", "name": "谢道韫", "dynasty": "東晉",
        "title": "女文士", "summary": "字道韞，陳郡陽夏人，謝奕之女、謝安侄女、王羲之子王凝之妻，聰慧有才辯，“未若柳絮因風起”詠絮之才。",
        "aliases": "謝道韞|谢道韫|謝道慍|谢道愠|道韞|道韫", "status": "active", "note": "梯隊二列女名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "xiedaoyun"
    },

    # --- 四、后汉书·党锢/独行/文苑名士烈臣（4人） ---
    {
        "id": "p_heyong", "tradName": "何顒", "name": "何颙", "dynasty": "東漢",
        "title": "議郎", "summary": "字伯求，南陽襄鄉人，黨錮八俊之一，少與曹操、袁紹深交，稱操“安天下者必此人”，後與荀攸謀誅董卓。",
        "aliases": "何顒|何颙|何伯求", "status": "active", "note": "梯隊二黨錮名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "heyong"
    },
    {
        "id": "p_yuankang_dg", "tradName": "苑康", "name": "苑康", "dynasty": "東漢",
        "title": "潁川太守", "summary": "字仲真，勃海重合人，黨錮八及之一，為潁川太守，威名大震，坐黨錮廢錮。",
        "aliases": "苑康|苑仲真", "status": "active", "note": "梯隊二黨錮名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "yuankang"
    },
    {
        "id": "p_tanfu", "tradName": "檀敷", "name": "檀敷", "dynasty": "東漢",
        "title": "蒙陰令", "summary": "字文有，山陽瑕丘人，黨錮八及之一，隱居教授，立節不屈。",
        "aliases": "檀敷|檀文有", "status": "active", "note": "梯隊二黨錮名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "tanfu"
    },
    {
        "id": "p_wangyanshou", "tradName": "王延壽", "name": "王延寿", "dynasty": "東漢",
        "title": "文士", "summary": "字文考，逸之子，少遊魯國，作《魯靈光殿賦》，蔡邕見之甚奇，自愧不能及。",
        "aliases": "王延壽|王延寿|王文考", "status": "active", "note": "梯隊二文苑名士·docs/46",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "wangyanshou"
    }
]

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    xlsx_path = os.path.join(root, "workbook", "persons.xlsx")

    print(f"正在加载权威源: {xlsx_path}")
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["人物"]

    existing_ids = set()
    existing_trads = set()

    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0]:
            existing_ids.add(str(row[0]).strip())
        if row[1]:
            existing_trads.add(str(row[1]).strip())

    print(f"当前已有有效人物ID: {len(existing_ids)} 个，正名: {len(existing_trads)} 个")

    # 1. 批量追加梯队二人物
    added = 0
    for p in TIER2_PERSONS:
        pid = p["id"]
        trad = p["tradName"]
        if pid in existing_ids:
            print(f"  [跳过已存在ID] {pid} ({trad})")
            continue
        if trad in existing_trads and pid not in ["p_zhengguo_sq"]:
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

    print(f"\n成功追加梯队二新人物: {added} 人")
    print(f"新人物表总行数: {ws.max_row - 1}")

    # 2. 安全写盘
    common.safe_save_workbook(wb, xlsx_path)
    print(f"✓ 权威源 {xlsx_path} 已通过 safe_save_workbook 安全保存！")

if __name__ == "__main__":
    main()
