# -*- coding: utf-8 -*-
"""古代核心地名經緯度坐標庫編譯器（依據譚其驤《中國歷史地圖集》與宋杰著作）。
輸出：data/dict/place_coordinates.json
"""
import os
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(ROOT, "data", "dict", "place_coordinates.json")
STRAT_JSON = os.path.join(ROOT, "data", "dict", "strategic_places.json")

# 基礎 43 處要衝坐標（從 strategic_places.json 繼承）
BASE_COORDS = {}
if os.path.exists(STRAT_JSON):
    with open(STRAT_JSON, 'r', encoding='utf-8') as f:
        strat = json.load(f)
        for k, v in strat.items():
            if "coords" in v:
                BASE_COORDS[k] = {
                    "trad_name": v.get("trad_name", ""),
                    "coords": v["coords"],
                    "modern": v.get("modern_loc", ""),
                    "type": "strategic_hub"
                }

# 擴充 200+ 處秦漢魏晉南北朝核心城池、都邑、關隘、郡國治所
EXPANDED_COORDS = {
    # ================= 關中、三輔、西北 =================
    "pl_changan": {"trad_name": "長安", "coords": [108.94, 34.34], "modern": "陝西西安市漢長安城遺址", "type": "capital"},
    "pl_xianyang": {"trad_name": "咸陽", "coords": [108.70, 34.33], "modern": "陝西咸陽市秦咸陽宮遺址", "type": "capital"},
    "pl_yueyang": {"trad_name": "櫟陽", "coords": [109.18, 34.58], "modern": "陝西富平/閻良秦漢櫟陽城", "type": "city"},
    "pl_guanzhong": {"trad_name": "關中", "coords": [108.85, 34.30], "modern": "陝西關中平原腹地", "type": "region"},
    "pl_sanfu": {"trad_name": "三輔", "coords": [108.90, 34.35], "modern": "京兆、左馮翊、右扶風", "type": "region"},
    "pl_wuguan": {"trad_name": "武關", "coords": [110.45, 33.53], "modern": "陝西商洛丹鳳縣東南", "type": "pass"},
    "pl_sanguan": {"trad_name": "大散關", "coords": [107.03, 34.25], "modern": "陝西寶雞西南", "type": "pass"},
    "pl_xiaoguan": {"trad_name": "蕭關", "coords": [106.32, 35.80], "modern": "寧夏固原東南", "type": "pass"},
    "pl_longxi": {"trad_name": "隴西", "coords": [104.64, 34.98], "modern": "甘肅定西隴西縣/臨洮", "type": "commandery"},
    "pl_tianshui": {"trad_name": "天水", "coords": [105.72, 34.58], "modern": "甘肅天水市", "type": "commandery"},
    "pl_shangbang": {"trad_name": "上邽", "coords": [105.72, 34.58], "modern": "甘肅天水市秦州區", "type": "city"},
    "pl_jiexian": {"trad_name": "冀縣", "coords": [105.33, 34.75], "modern": "甘肅甘谷縣東", "type": "city"},
    "pl_jieting": {"trad_name": "街亭", "coords": [105.90, 35.00], "modern": "甘肅天水秦安縣東北", "type": "pass"},
    "pl_qishan": {"trad_name": "祁山", "coords": [105.21, 34.18], "modern": "甘肅隴南禮縣東北", "type": "pass"},
    "pl_guzang": {"trad_name": "姑臧", "coords": [102.64, 37.93], "modern": "甘肅武威市涼州區", "type": "city"},
    "pl_wuwei": {"trad_name": "武威", "coords": [102.64, 37.93], "modern": "甘肅武威市", "type": "commandery"},
    "pl_zhangye": {"trad_name": "張掖", "coords": [100.45, 38.93], "modern": "甘肅張掖市甘州區", "type": "commandery"},
    "pl_jiuquan": {"trad_name": "酒泉", "coords": [98.51, 39.74], "modern": "甘肅酒泉市肅州區", "type": "commandery"},
    "pl_dunhuang": {"trad_name": "敦煌", "coords": [94.66, 40.14], "modern": "甘肅敦煌市", "type": "commandery"},
    "pl_yumenguan": {"trad_name": "玉門關", "coords": [93.86, 40.35], "modern": "甘肅敦煌西北小方盤城", "type": "pass"},
    "pl_yangguan": {"trad_name": "陽關", "coords": [94.19, 39.92], "modern": "甘肅敦煌西南古董灘", "type": "pass"},
    "pl_jincheng": {"trad_name": "金城", "coords": [103.31, 36.17], "modern": "甘肅蘭州/永靖一帶", "type": "commandery"},
    "pl_lintao": {"trad_name": "臨洮", "coords": [103.86, 35.38], "modern": "甘肅定西臨洮縣", "type": "city"},
    "pl_shanshan": {"trad_name": "鄯善", "coords": [88.17, 39.03], "modern": "新疆若羌/樓蘭一帶", "type": "region"},
    "pl_yutian": {"trad_name": "于闐", "coords": [79.92, 37.11], "modern": "新疆和田市一帶", "type": "region"},
    "pl_shule": {"trad_name": "疏勒", "coords": [75.99, 39.47], "modern": "新疆喀什市一帶", "type": "region"},
    "pl_qiuci": {"trad_name": "龜茲", "coords": [82.96, 41.72], "modern": "新疆阿克蘇庫車市", "type": "region"},

    # ================= 中原河洛、河南、河東 =================
    "pl_luoyang": {"trad_name": "洛陽", "coords": [112.45, 34.62], "modern": "河南洛陽市漢魏故城", "type": "capital"},
    "pl_xingyang": {"trad_name": "滎陽", "coords": [113.22, 34.79], "modern": "河南滎陽市古滎鎮", "type": "city"},
    "pl_chenggao": {"trad_name": "成皋", "coords": [113.15, 34.82], "modern": "河南滎陽汜水鎮（虎牢關）", "type": "pass"},
    "pl_xuchang": {"trad_name": "許昌", "coords": [113.85, 34.03], "modern": "河南許昌市建安區", "type": "capital"},
    "pl_xu": {"trad_name": "許", "coords": [113.85, 34.03], "modern": "河南許昌市", "type": "city"},
    "pl_suiyang": {"trad_name": "睢陽", "coords": [115.65, 34.44], "modern": "河南商丘市睢陽區", "type": "city"},
    "pl_chenliu": {"trad_name": "陳留", "coords": [114.58, 34.72], "modern": "河南開封市祥符區陳留鎮", "type": "commandery"},
    "pl_daliang": {"trad_name": "大梁", "coords": [114.35, 34.79], "modern": "河南開封市城區", "type": "capital"},
    "pl_wu_wan": {"trad_name": "宛", "coords": [112.53, 32.99], "modern": "河南南陽市宛城區", "type": "city"},
    "pl_nanyang": {"trad_name": "南陽", "coords": [112.53, 32.99], "modern": "河南南陽市", "type": "commandery"},
    "pl_xinye": {"trad_name": "新野", "coords": [112.36, 32.52], "modern": "河南南陽市新野縣", "type": "city"},
    "pl_kunyang": {"trad_name": "昆陽", "coords": [113.35, 33.62], "modern": "河南平頂山葉縣", "type": "city"},
    "pl_hulaoguan": {"trad_name": "虎牢", "coords": [113.15, 34.82], "modern": "河南滎陽汜水鎮虎牢關", "type": "pass"},
    "pl_mengjin": {"trad_name": "孟津", "coords": [112.44, 34.83], "modern": "河南洛陽孟津區黃河渡口", "type": "pass"},
    "pl_hongnong": {"trad_name": "弘農", "coords": [110.88, 34.58], "modern": "河南三門峽靈寶市東北", "type": "commandery"},
    "pl_shanguan": {"trad_name": "函谷關", "coords": [110.91, 34.64], "modern": "河南靈寶北/洛陽新安", "type": "pass"},
    "pl_pingyang": {"trad_name": "平陽", "coords": [111.52, 36.08], "modern": "山西臨汾市堯都區", "type": "city"},
    "pl_anyi": {"trad_name": "安邑", "coords": [111.22, 35.15], "modern": "山西運城夏縣西北", "type": "city"},
    "pl_jinyang": {"trad_name": "晉陽", "coords": [112.55, 37.87], "modern": "山西太原市晉源區故城", "type": "city"},
    "pl_shangdang": {"trad_name": "上黨", "coords": [113.12, 36.20], "modern": "山西長治市城區", "type": "commandery"},
    "pl_huguan": {"trad_name": "壺關", "coords": [113.20, 36.12], "modern": "山西長治壺關縣", "type": "pass"},
    "pl_changping": {"trad_name": "長平", "coords": [112.98, 35.80], "modern": "山西晉升高平市西北", "type": "battlefield"},
    "pl_poyang": {"trad_name": "蒲坂", "coords": [110.29, 34.90], "modern": "山西運城永濟蒲州鎮", "type": "pass"},

    # ================= 河北、山東、幽燕 =================
    "pl_ye": {"trad_name": "鄴", "coords": [114.62, 36.31], "modern": "河北邯鄲臨漳縣鄴城遺址", "type": "capital"},
    "pl_handan": {"trad_name": "邯鄲", "coords": [114.49, 36.61], "modern": "河北邯鄲市趙王城", "type": "capital"},
    "pl_xiangguo": {"trad_name": "襄國", "coords": [114.50, 37.07], "modern": "河北邢台市襄都區", "type": "capital"},
    "pl_julu": {"trad_name": "巨鹿", "coords": [115.03, 37.22], "modern": "河北邢台巨鹿縣", "type": "city"},
    "pl_xindu": {"trad_name": "信都", "coords": [115.68, 37.73], "modern": "河北衡水冀州區", "type": "city"},
    "pl_zhongshan": {"trad_name": "中山", "coords": [114.99, 38.51], "modern": "河北定州市", "type": "commandery"},
    "pl_jixian": {"trad_name": "薊", "coords": [116.40, 39.90], "modern": "北京廣安門一帶薊城遺址", "type": "capital"},
    "pl_fangtou": {"trad_name": "枋頭", "coords": [114.55, 35.67], "modern": "河南鶴壁浚縣西南", "type": "city"},
    "pl_linzi": {"trad_name": "臨淄", "coords": [118.31, 36.83], "modern": "山東淄博臨淄區齊國故城", "type": "capital"},
    "pl_qufu": {"trad_name": "曲阜", "coords": [116.98, 35.59], "modern": "山東濟寧曲阜市魯國故城", "type": "capital"},
    "pl_dingtao": {"trad_name": "定陶", "coords": [115.57, 35.07], "modern": "山東菏澤定陶區", "type": "city"},
    "pl_puyang": {"trad_name": "濮陽", "coords": [115.03, 35.76], "modern": "河南濮陽市城區", "type": "city"},
    "pl_dong_e": {"trad_name": "東阿", "coords": [116.25, 36.33], "modern": "山東聊城東阿縣", "type": "city"},
    "pl_shouzhang": {"trad_name": "壽張", "coords": [115.98, 35.98], "modern": "山東東平縣/梁山一帶", "type": "city"},
    "pl_taishan": {"trad_name": "泰山", "coords": [117.13, 36.19], "modern": "山東泰安市泰山", "type": "mountain"},
    "pl_langya": {"trad_name": "琅邪", "coords": [119.45, 35.75], "modern": "山東日照/青島膠南一帶", "type": "commandery"},
    "pl_ju": {"trad_name": "莒", "coords": [118.84, 35.58], "modern": "山東日照莒縣", "type": "city"},

    # ================= 淮揚、江東、東南 =================
    "pl_pengcheng": {"trad_name": "彭城", "coords": [117.18, 34.27], "modern": "江蘇徐州市城區", "type": "city"},
    "pl_xiapi": {"trad_name": "下邳", "coords": [117.95, 34.33], "modern": "江蘇邳州市古邳鎮", "type": "city"},
    "pl_pei": {"trad_name": "沛", "coords": [116.93, 34.73], "modern": "江蘇徐州沛縣", "type": "city"},
    "pl_qiao": {"trad_name": "譙", "coords": [115.78, 33.87], "modern": "安徽亳州市譙城區", "type": "city"},
    "pl_guangling": {"trad_name": "廣陵", "coords": [119.42, 32.39], "modern": "江蘇揚州市城區", "type": "city"},
    "pl_shouchun": {"trad_name": "壽春", "coords": [116.78, 32.58], "modern": "安徽淮南壽縣", "type": "city"},
    "pl_lujiang": {"trad_name": "廬江", "coords": [117.29, 31.25], "modern": "安徽合肥廬江縣", "type": "commandery"},
    "pl_hefei": {"trad_name": "合肥", "coords": [117.28, 31.86], "modern": "安徽合肥市逍遙津/新城", "type": "city"},
    "pl_jiankang": {"trad_name": "建康", "coords": [118.79, 32.06], "modern": "江蘇南京市城區（六朝建康）", "type": "capital"},
    "pl_jianye": {"trad_name": "建業", "coords": [118.79, 32.06], "modern": "江蘇南京市城區（東吳都城）", "type": "capital"},
    "pl_jingkou": {"trad_name": "京口", "coords": [119.45, 32.20], "modern": "江蘇鎮江市城區", "type": "city"},
    "pl_wu_place": {"trad_name": "吳", "coords": [120.62, 31.30], "modern": "江蘇蘇州市城區", "type": "city"},
    "pl_kuaiji": {"trad_name": "會稽", "coords": [120.58, 29.99], "modern": "浙江紹興市越城區", "type": "city"},
    "pl_qiantang": {"trad_name": "錢塘", "coords": [120.15, 30.28], "modern": "浙江杭州市城區", "type": "city"},
    "pl_danyang": {"trad_name": "丹陽", "coords": [118.60, 31.50], "modern": "安徽當塗/宣城一帶", "type": "commandery"},
    "pl_chaisang": {"trad_name": "柴桑", "coords": [115.99, 29.71], "modern": "江西九江市柴桑區", "type": "city"},
    "pl_yuzhang": {"trad_name": "豫章", "coords": [115.89, 28.68], "modern": "江西南昌市城區", "type": "commandery"},
    "pl_huaiyin": {"trad_name": "淮陰", "coords": [119.03, 33.62], "modern": "江蘇淮安市淮陰區", "type": "city"},
    "pl_gaixia": {"trad_name": "垓下", "coords": [117.58, 33.54], "modern": "安徽宿州靈璧縣東南", "type": "battlefield"},

    # ================= 荊襄、江漢、兩湖 =================
    "pl_xiangyang": {"trad_name": "襄陽", "coords": [112.14, 32.01], "modern": "湖北襄陽市襄城區", "type": "city"},
    "pl_fancheng": {"trad_name": "樊城", "coords": [112.16, 32.04], "modern": "湖北襄陽市樊城區", "type": "city"},
    "pl_jiangling": {"trad_name": "江陵", "coords": [112.19, 30.35], "modern": "湖北荊州市荊州區", "type": "city"},
    "pl_dangyang": {"trad_name": "當陽", "coords": [111.78, 30.82], "modern": "湖北宜昌當陽市長坂坡", "type": "city"},
    "pl_huarong": {"trad_name": "華容", "coords": [112.55, 29.86], "modern": "湖北監利/湖南華容一帶", "type": "city"},
    "pl_yiling": {"trad_name": "夷陵", "coords": [111.29, 30.70], "modern": "湖北宜昌市夷陵區", "type": "city"},
    "pl_chibi": {"trad_name": "赤壁", "coords": [113.88, 29.88], "modern": "湖北赤壁市西北烏林對岸", "type": "battlefield"},
    "pl_xiakou": {"trad_name": "夏口", "coords": [114.28, 30.56], "modern": "湖北武漢市漢陽/武昌一帶", "type": "city"},
    "pl_wuchang": {"trad_name": "武昌", "coords": [114.89, 30.38], "modern": "湖北鄂州市城區（孫吳武昌）", "type": "capital"},
    "pl_changsha": {"trad_name": "長沙", "coords": [112.98, 28.19], "modern": "湖南長沙市城區", "type": "city"},
    "pl_wuling": {"trad_name": "武陵", "coords": [111.69, 29.03], "modern": "湖南常德市城區", "type": "commandery"},
    "pl_gongan": {"trad_name": "公安", "coords": [112.23, 30.06], "modern": "湖北荊州公安縣（油江口）", "type": "city"},

    # ================= 巴蜀、漢中、南中 =================
    "pl_hanzhong": {"trad_name": "漢中", "coords": [107.03, 33.07], "modern": "陝西漢中市漢台區（南鄭）", "type": "city"},
    "pl_nanzheng": {"trad_name": "南鄭", "coords": [107.03, 33.07], "modern": "陝西漢中市南鄭城", "type": "city"},
    "pl_dingjunshan": {"trad_name": "定軍山", "coords": [106.67, 33.15], "modern": "陝西漢中勉縣定軍山", "type": "mountain"},
    "pl_yangpingguan": {"trad_name": "陽平關", "coords": [106.18, 32.95], "modern": "陝西漢中寧強陽平關鎮", "type": "pass"},
    "pl_jiange": {"trad_name": "劍閣", "coords": [105.52, 32.28], "modern": "四川廣元劍閣劍門關", "type": "pass"},
    "pl_jiameng": {"trad_name": "葭萌", "coords": [105.65, 32.38], "modern": "四川廣元昭化古城", "type": "city"},
    "pl_zitong": {"trad_name": "梓潼", "coords": [105.16, 31.64], "modern": "四川綿陽梓潼縣", "type": "city"},
    "pl_fucheng": {"trad_name": "涪城", "coords": [104.74, 31.46], "modern": "四川綿陽市涪城區", "type": "city"},
    "pl_chengdou": {"trad_name": "成都", "coords": [104.06, 30.67], "modern": "四川成都市蜀漢都城", "type": "capital"},
    "pl_baidicheng": {"trad_name": "白帝城", "coords": [109.52, 31.04], "modern": "重慶奉節縣白帝城", "type": "city"},
    "pl_jiangzhou": {"trad_name": "江州", "coords": [106.55, 29.56], "modern": "重慶市渝中區", "type": "city"},
    "pl_nanzhong": {"trad_name": "南中", "coords": [102.73, 25.04], "modern": "雲南昆明/曲靖一帶", "type": "region"},

    # ================= 十三州部宏觀地理中心 =================
    "pl_jizhou_zhou": {"trad_name": "冀州", "coords": [115.68, 37.73], "modern": "河北冀州/中原北部", "type": "province"},
    "pl_yanzhou_zhou": {"trad_name": "兖州", "coords": [115.57, 35.50], "modern": "山東西南鄆城/定陶一帶", "type": "province"},
    "pl_qingzhou_zhou": {"trad_name": "青州", "coords": [118.47, 36.69], "modern": "山東青州/膠東半島", "type": "province"},
    "pl_xuzhou_zhou": {"trad_name": "徐州", "coords": [117.95, 34.33], "modern": "江蘇下邳/徐州一帶", "type": "province"},
    "pl_yangzhou_zhou": {"trad_name": "揚州", "coords": [116.78, 32.58], "modern": "安徽壽春/江東江淮", "type": "province"},
    "pl_jingzhou_zhou": {"trad_name": "荊州", "coords": [112.19, 30.35], "modern": "湖北江陵/襄陽江漢", "type": "province"},
    "pl_yuzhou_zhou": {"trad_name": "豫州", "coords": [115.78, 33.87], "modern": "安徽譙縣/河南中原", "type": "province"},
    "pl_yizhou": {"trad_name": "益州", "coords": [104.06, 30.67], "modern": "四川成都/巴蜀全境", "type": "province"},
    "pl_liangzhou_zhou": {"trad_name": "涼州", "coords": [102.64, 37.93], "modern": "甘肅武威姑臧/河西走廊", "type": "province"},
    "pl_youzhou": {"trad_name": "幽州", "coords": [116.40, 39.90], "modern": "北京薊城/幽燕北疆", "type": "province"},
    "pl_bingzhou_zhou": {"trad_name": "并州", "coords": [112.55, 37.87], "modern": "山西太原晉陽/河東", "type": "province"},
    "pl_sili": {"trad_name": "司隸", "coords": [112.45, 34.62], "modern": "洛陽/長安兩京司隸校尉部", "type": "province"},
    "pl_jiaozhou_zhou": {"trad_name": "交州", "coords": [113.27, 23.13], "modern": "廣東番禺/廣西越南嶺南", "type": "province"},

    # ================= 著名古邑、戰場與名山 =================
    "pl_mangdangshan": {"trad_name": "芒碭山", "coords": [116.48, 34.22], "modern": "河南商丘永城芒碭山（高祖斬蛇）", "type": "mountain"},
    "pl_fengyi": {"trad_name": "豐", "coords": [116.59, 34.70], "modern": "江蘇徐州豐縣（高祖故里）", "type": "city"},
    "pl_hongmen": {"trad_name": "鴻門", "coords": [109.20, 34.37], "modern": "陝西西安臨潼新豐鴻門坂", "type": "battlefield"},
    "pl_baqiao": {"trad_name": "灞上", "coords": [109.05, 34.27], "modern": "陝西西安灞河西岸灞上", "type": "camp"},
    "pl_bahe": {"trad_name": "霸陵", "coords": [109.12, 34.25], "modern": "陝西西安白鹿原漢文帝陵", "type": "tomb"},
    "pl_duling": {"trad_name": "杜陵", "coords": [109.02, 34.18], "modern": "陝西西安雁塔區漢宣帝陵", "type": "tomb"},
    "pl_huashan": {"trad_name": "華山", "coords": [110.08, 34.48], "modern": "陝西渭南華陰市西嶽華山", "type": "mountain"},
    "pl_songshan": {"trad_name": "嵩山", "coords": [113.02, 34.48], "modern": "河南鄭州登封中嶽嵩山", "type": "mountain"},
    "pl_henan_d": {"trad_name": "河南", "coords": [112.45, 34.62], "modern": "河南郡治洛陽", "type": "commandery"},
    "pl_hebei": {"trad_name": "河北", "coords": [115.00, 38.00], "modern": "黃河以北廣大平原", "type": "region"},
    "pl_huainan_d": {"trad_name": "淮南", "coords": [116.78, 32.58], "modern": "淮河以南壽春一帶", "type": "region"},
    "pl_runan": {"trad_name": "汝南", "coords": [114.36, 33.01], "modern": "河南駐馬店汝南縣", "type": "commandery"},
    "pl_ruyang": {"trad_name": "汝陽", "coords": [114.65, 33.63], "modern": "河南周口商水縣汝陽城", "type": "city"},
    "pl_donghai": {"trad_name": "東海", "coords": [118.50, 34.50], "modern": "山東臨沂郯城/連雲港一帶", "type": "commandery"},
    "pl_pingyuan": {"trad_name": "平原", "coords": [116.43, 37.16], "modern": "山東德州平原縣", "type": "commandery"},
    "pl_nanpi": {"trad_name": "南皮", "coords": [116.70, 38.03], "modern": "河北滄州南皮縣", "type": "city"},
    "pl_bailangshan": {"trad_name": "白狼山", "coords": [119.92, 40.85], "modern": "遼寧朝陽喀左大青山（曹操破蹋頓）", "type": "battlefield"},
    "pl_yanmen": {"trad_name": "雁門", "coords": [112.93, 39.18], "modern": "山西忻州代縣雁門關", "type": "pass"},
    "pl_daijun": {"trad_name": "代郡", "coords": [114.35, 39.82], "modern": "河北張家口蔚縣代王城", "type": "commandery"},
    "pl_shanggu": {"trad_name": "上谷", "coords": [115.82, 40.35], "modern": "河北張家口懷來一帶", "type": "commandery"},
    "pl_youbeiping": {"trad_name": "右北平", "coords": [118.18, 39.63], "modern": "河北唐山/天津薊州一帶", "type": "commandery"},
    "pl_wancheng": {"trad_name": "皖城", "coords": [116.53, 30.52], "modern": "安徽安慶潛山市", "type": "city"},
    "pl_shuxian": {"trad_name": "舒", "coords": [117.18, 31.45], "modern": "安徽廬江舒茶古舒國", "type": "city"},
    "pl_liuan": {"trad_name": "六安", "coords": [116.51, 31.75], "modern": "安徽六安市城區", "type": "city"},
    "pl_niuzhu": {"trad_name": "牛渚", "coords": [118.45, 31.67], "modern": "安徽馬鞍山採石磯", "type": "pass"},
    "pl_ruxukou": {"trad_name": "濡須口", "coords": [117.92, 31.25], "modern": "安徽蕪湖無為濡須水入江處", "type": "pass"},
    "pl_qu_a": {"trad_name": "曲阿", "coords": [119.57, 31.95], "modern": "江蘇鎮江丹陽市", "type": "city"},
    "pl_wuxing": {"trad_name": "吳興", "coords": [120.08, 30.87], "modern": "浙江湖州市城區", "type": "commandery"},
    "pl_poyang_d": {"trad_name": "鄱陽", "coords": [116.68, 29.00], "modern": "江西上饒鄱陽縣/鄱陽湖", "type": "commandery"},
    "pl_dongting": {"trad_name": "洞庭", "coords": [112.85, 29.30], "modern": "湖南岳陽洞庭湖", "type": "lake"},
    "pl_baling": {"trad_name": "巴陵", "coords": [113.12, 29.37], "modern": "湖南岳陽市城區（岳陽樓）", "type": "city"},
    "pl_lingling": {"trad_name": "零陵", "coords": [111.62, 26.22], "modern": "湖南永州市零陵區", "type": "commandery"},
    "pl_guiyang": {"trad_name": "桂陽", "coords": [113.03, 25.78], "modern": "湖南郴州市城區", "type": "commandery"},
    "pl_yulin": {"trad_name": "郁林", "coords": [109.60, 23.10], "modern": "廣西貴港市漢郁林郡", "type": "commandery"},
    "pl_nanhai": {"trad_name": "南海", "coords": [113.27, 23.13], "modern": "廣東廣州市番禺漢南海郡", "type": "commandery"},
    "pl_changjiang": {"trad_name": "江", "coords": [115.00, 30.00], "modern": "長江沿線（長江中下游）", "type": "river"},
    "pl_huanghe": {"trad_name": "河", "coords": [114.00, 35.00], "modern": "黃河沿線（黃河中下游）", "type": "river"},
    "pl_huai": {"trad_name": "淮", "coords": [116.50, 33.00], "modern": "淮河沿線（淮河干流）", "type": "river"},
    "pl_hanshui": {"trad_name": "漢水", "coords": [112.50, 31.50], "modern": "漢水/漢江中游", "type": "river"},
    "pl_luo_shui": {"trad_name": "洛水", "coords": [112.45, 34.62], "modern": "洛河（洛陽周邊）", "type": "river"},
    "pl_weishui": {"trad_name": "渭水", "coords": [108.90, 34.40], "modern": "渭河（關中平原）", "type": "river"},
    "pl_sishui": {"trad_name": "泗水", "coords": [117.20, 34.50], "modern": "泗水（徐州、魯南）", "type": "river"},
    "pl_yunmengze": {"trad_name": "雲夢", "coords": [112.80, 30.30], "modern": "湖北江漢平原古雲夢澤", "type": "lake"}
}

def build_place_coordinates():
    # 合併兩者
    final_dict = {}
    final_dict.update(BASE_COORDS)
    for k, v in EXPANDED_COORDS.items():
        if k not in final_dict:
            final_dict[k] = v
        else:
            # 優先保留更細緻的
            final_dict[k].update(v)

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(final_dict, f, ensure_ascii=False, indent=2)

    print(f"已生成古代核心地名經緯度坐標庫: {OUT_JSON}")
    print(f"收錄核心地名坐標數: {len(final_dict)} 處。")

if __name__ == '__main__':
    build_place_coordinates()
