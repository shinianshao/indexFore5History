# pipeline/_enrich_persons_tier3_batches23.py
# -*- coding: utf-8 -*-
"""梯队三剩余批次（批次二与批次三，共41人）安全写入 workbook/persons.xlsx"""
import os
import sys
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

TIER3_BATCHES23_PERSONS = [
    # =========================================================================
    # 批次二：三国宿将谋臣 + 两晋十六国名将名士（23人）
    # =========================================================================
    # --- 两晋十六国（9人） ---
    {
        "id": "p_dengqiang", "tradName": "鄧羌", "name": "邓羌", "dynasty": "十六國",
        "title": "御史中丞", "summary": "前秦名將，勇冠三軍，與張蚝並稱“萬人敵”。輔佐王猛討平前燕慕容評、拔壺關、克潞川，滅仇池，平蜀漢叛亂，屢立奇功。",
        "aliases": "鄧羌|邓羌", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "dengqiang"
    },
    {
        "id": "p_gouxi", "tradName": "苟晞", "name": "苟晞", "dynasty": "西晉",
        "title": "撫軍大將軍", "summary": "字道將，河內山陽人，西晉末期名將，號“屠伯”。少有智謀，屢破汲桑、石勒，威震中原，官至大將軍、太子太保，後為石勒所擒害。",
        "aliases": "苟晞|苟道將|苟道将", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "gouxi"
    },
    {
        "id": "p_zuyue", "tradName": "祖約", "name": "祖约", "dynasty": "東晉",
        "title": "平西將軍", "summary": "字士少，范陽遒縣人，祖逖之弟。祖逖死後代領其部曲，為平西將軍、豫州刺史。因朝廷薄待與蘇峻合謀起兵叛亂，事敗投奔後趙，後為石勒所殺。",
        "aliases": "祖約|祖约|祖士少", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "zuyue"
    },
    {
        "id": "p_huanchong", "tradName": "桓沖", "name": "桓冲", "dynasty": "東晉",
        "title": "車騎將軍", "summary": "字幼子，譙國龍亢人，桓溫之弟。溫死後統攝桓氏部曲，都督七州諸軍事、荊州刺史，鎮守荊襄十餘載，力拒前秦苻堅，與謝安協和朝野。",
        "aliases": "桓沖|桓冲|桓幼子", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "huanchong"
    },
    {
        "id": "p_xieshi", "tradName": "謝石", "name": "谢石", "dynasty": "東晉",
        "title": "征討大都督", "summary": "字石奴，陳郡陽夏人，謝安之弟。太元八年淝水之戰，謝石拜征討大都督，為東晉全軍最高統帥，統率謝玄、謝琰大破前秦八十萬大軍，封南康公。",
        "aliases": "謝石|谢石|謝石奴|谢石奴", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "xieshi"
    },
    {
        "id": "p_xieyan", "tradName": "謝琰", "name": "谢琰", "dynasty": "東晉",
        "title": "望蔡公", "summary": "字瑗度，陳郡陽夏人，謝安次子。太元八年淝水之戰，謝琰拜輔國將軍，統率精銳大破苻融並陣斬苻融，封望蔡公，後討孫恩力戰殉國。",
        "aliases": "謝琰|谢琰|謝瑗度|谢瑗度", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "xieyan"
    },
    {
        "id": "p_xichao", "tradName": "郗超", "name": "郗超", "dynasty": "東晉",
        "title": "中書侍郎", "summary": "字景興，高平金鄉人，郗鑒之孫。桓溫首席謀主，典故“入幕之賓”主角，才冠江左，時稱“郗嘉賓”，助桓溫廢立政變。",
        "aliases": "郗超|郗景興|郗景兴|郗嘉賓|郗嘉宾", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "xichao"
    },
    {
        "id": "p_weijie", "tradName": "衛玠", "name": "卫玠", "dynasty": "西晉",
        "title": "太子洗馬", "summary": "字叔寶，河東安邑人，衛瓘之孫。風神秀異，名冠天下，時人謂之玉人，典故“看殺衛玠”主角，官至太子洗馬。",
        "aliases": "衛玠|卫玠|衛叔寶|卫叔宝", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "weijie"
    },
    {
        "id": "p_lvzhu", "tradName": "綠珠", "name": "绿珠", "dynasty": "西晉",
        "title": "石崇愛妾", "summary": "白州博白人，西晉石崇愛妾，美而豔，善吹笛。趙王倫黨羽孫秀遣人索求綠珠，石崇不與，孫秀收崇，綠珠遂墜樓自盡以殉節。",
        "aliases": "綠珠|绿珠", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 1, "pinyin": "lvzhu"
    },
    # --- 蜀汉/曹魏/东汉三国名将谋臣（14人） ---
    {
        "id": "p_yanyu", "tradName": "閻宇", "name": "阎宇", "dynasty": "三國",
        "title": "右大將軍", "summary": "字文平，南郡人，蜀漢右大將軍。宿有功幹，於事精勤，繼羅憲出鎮永安，蜀亡前夕奉詔入衛成都。",
        "aliases": "閻宇|阎宇|閻文平|阎文平", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "yanyu"
    },
    {
        "id": "p_fukuang", "tradName": "輔匡", "name": "辅匡", "dynasty": "三國",
        "title": "鎮南將軍", "summary": "字元弼，襄陽人，隨劉備入蜀。歷任巴郡太守、鎮南將軍，封中鄉侯，名位亞李嚴，夷陵之役任別督。",
        "aliases": "輔匡|辅匡|輔元弼|辅元弼", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "fukuang"
    },
    {
        "id": "p_yaozhou", "tradName": "姚伷", "name": "姚伷", "dynasty": "三國",
        "title": "尚書僕射", "summary": "字子緒，巴西閬中人，蜀漢尚書僕射。諸葛亮贊其剛柔並存、廣文武之用，深得州黨歸信。",
        "aliases": "姚伷|姚子緒|姚子绪", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "yaozhou"
    },
    {
        "id": "p_leitong", "tradName": "雷銅", "name": "雷铜", "dynasty": "三國",
        "title": "將軍", "summary": "益州名將，隨劉備爭奪漢中，同張飛入武都、屯下辯抗曹軍，為曹洪所破戰死。",
        "aliases": "雷銅|雷铜", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "leitong"
    },
    {
        "id": "p_wulan", "tradName": "吳蘭", "name": "吴兰", "dynasty": "三國",
        "title": "將軍", "summary": "蜀漢將軍，隨劉備爭奪漢中，與馬超、張飛屯下辯，為曹洪、曹休所破戰死。",
        "aliases": "吳蘭|吴兰", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "wulan"
    },
    {
        "id": "p_huangzu", "tradName": "黃祖", "name": "黄祖", "dynasty": "東漢",
        "title": "江夏太守", "summary": "劉表部將，任江夏太守十餘載，阻遏孫氏江東大軍，初平三年部將射殺孫堅。建安十三年為孫權大軍所破被殺。",
        "aliases": "黃祖|黄祖", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "huangzu"
    },
    {
        "id": "p_caimao_sg", "tradName": "蔡瑁", "name": "蔡瑁", "dynasty": "東漢",
        "title": "從事中郎", "summary": "字德珪，襄陽豪族，劉表妻弟。善水軍謀略，劉表死後迎曹操，曹操待以故舊，拜從事中郎、司馬、長水校尉，封漢陽亭侯。",
        "aliases": "蔡瑁|蔡德珪", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "caimao"
    },
    {
        "id": "p_panghui", "tradName": "龐會", "name": "庞会", "dynasty": "三國",
        "title": "臨渭亭侯", "summary": "龐德之子，勇烈有父風。隨諸葛誕討叛突圍立功，後隨鍾會鄧艾大軍伐蜀，官至中尉將軍，封列侯。",
        "aliases": "龐會|庞会", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "panghui"
    },
    {
        "id": "p_xuyou", "tradName": "許攸", "name": "许攸", "dynasty": "東漢",
        "title": "謀士", "summary": "字子遠，南陽人，漢末謀士。初隨袁紹為謀主，官渡之戰奔投曹操，奇策火燒烏巢大破袁紹，克冀州後恃舊傲慢，為曹操所收誅。",
        "aliases": "許攸|许攸|許子遠|许子远", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "xuyou"
    },
    {
        "id": "p_gaolan", "tradName": "高覽", "name": "高览", "dynasty": "東漢",
        "title": "偏將軍", "summary": "河北名將，與張郃齊名。官渡之戰受郭圖構陷，遂與張郃率眾投降曹操，拜偏將軍，封東萊侯。",
        "aliases": "高覽|高览", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "gaolan"
    },
    {
        "id": "p_zhangren", "tradName": "張任", "name": "张任", "dynasty": "東漢",
        "title": "益州名將", "summary": "蜀郡人，劉璋心腹驍將，勇毅有謀。劉備入蜀時率軍拒戰於涪城、雒城，戰敗被擒，厲聲叱曰“老臣終不事二主”，遂被斬，劉備嘆惜之。",
        "aliases": "張任|张任", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "zhangren"
    },
    {
        "id": "p_jufu", "tradName": "句扶", "name": "句扶", "dynasty": "三國",
        "title": "左將軍", "summary": "字孝興，巴西漢昌人，蜀漢名將，官至左將軍，封宕渠侯。忠勇寬厚，功名亞王平，蜀人稱“前有王句，後有張廖”。",
        "aliases": "句扶|句孝興|句孝兴", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "jufu"
    },
    {
        "id": "p_liuyin_sh", "tradName": "柳隱", "name": "柳隐", "dynasty": "三國",
        "title": "漢中都督", "summary": "字休然，成都人，蜀漢名將。隨姜維北伐屢立戰功，年逾八旬守黃金城拒鍾會魏軍大軍，蜀亡降魏，官至西平太守。",
        "aliases": "柳隱|柳隐|柳休然", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "liuyin"
    },
    {
        "id": "p_yanxing", "tradName": "閻行", "name": "阎行", "dynasty": "東漢",
        "title": "犍為太守", "summary": "字彥明，金城人，韓遂部將，少有健名。早年與馬超交戰幾刺死馬超，後勸韓遂歸曹操，拜中郎將封列侯。",
        "aliases": "閻行|阎行|閻彥明|阎彦明", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "yanxing"
    },

    # =========================================================================
    # 批次三：三国宗室名臣与江东宿将 + 先秦两汉名臣先贤名媛（18人）
    # =========================================================================
    # --- 三国宗室江东名臣（11人） ---
    {
        "id": "p_feiguan", "tradName": "費觀", "name": "费观", "dynasty": "三國",
        "title": "巴郡太守", "summary": "字賓伯，江夏鄳縣人，劉璋姻親。綿竹降劉備，拜裨將軍，後領巴郡太守、江州都督，封都亭侯，有才幹。",
        "aliases": "費觀|费观|費賓伯|费宾伯", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "feiguan"
    },
    {
        "id": "p_chenshi_sg", "tradName": "陳式", "name": "陈式", "dynasty": "三國",
        "title": "將軍", "summary": "蜀漢將軍。隨諸葛亮北伐，建興七年率兵拔武都、陰平二郡，功名著於史冊。",
        "aliases": "陳式|陈式", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "chenshi"
    },
    {
        "id": "p_guoyouzhi", "tradName": "郭攸之", "name": "郭攸之", "dynasty": "三國",
        "title": "侍中", "summary": "字演長，南陽人，蜀漢侍中。諸葛亮《出師表》稱“郭攸之、費禕、董允等，此皆良實，志慮忠純，是以先帝簡拔以遺陛下”。",
        "aliases": "郭攸之|郭演長|郭演长", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "guoyouzhi"
    },
    {
        "id": "p_shendan", "tradName": "申耽", "name": "申耽", "dynasty": "東漢",
        "title": "征北將軍", "summary": "字義舉，魏興錫縣人，上庸豪強。降劉備拜征北將軍，領上庸太守、封員鄉侯，後隨孟達降曹魏，徙居南陽。",
        "aliases": "申耽|申義舉|申义举", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "shendan"
    },
    {
        "id": "p_shenyi", "tradName": "申儀", "name": "申仪", "dynasty": "三國",
        "title": "魏興太守", "summary": "魏興錫縣人，申耽之弟。初歸劉備，後隨兄降魏，拜魏興太守、封真鄉侯。孟達欲反，儀密告司馬懿，助平新城。",
        "aliases": "申儀|申仪", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "shenyi"
    },
    {
        "id": "p_caoyu", "tradName": "曹宇", "name": "曹宇", "dynasty": "三國",
        "title": "燕王", "summary": "字彭祖，沛國譙人，曹操之子，封燕王。魏明帝病危臨終首選曹宇為大將軍托孤輔政，宇深自推讓乃換曹爽司馬懿。",
        "aliases": "曹宇", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "caoyu"
    },
    {
        "id": "p_sunjing", "tradName": "孫靜", "name": "孙静", "dynasty": "東漢",
        "title": "昭義將軍", "summary": "字幼臺，吳郡富春人，孫堅幼弟。助孫策平定江東，奇襲查瀆破王朗，性謙和保全宗室，封昭義將軍。",
        "aliases": "孫靜|孙静|孫幼臺|孙幼台", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "sunjing"
    },
    {
        "id": "p_sunben", "tradName": "孫賁", "name": "孙贲", "dynasty": "東漢",
        "title": "征虜將軍", "summary": "字伯陽，吳郡富春人，孫堅兄子。隨孫堅討董、隨孫策平江東，領豫章太守，拜征虜將軍，封都亭侯。",
        "aliases": "孫賁|孙贲|孫伯陽|孙伯阳", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 1, "in_sgz": 1, "in_js": 0, "pinyin": "sunben"
    },
    {
        "id": "p_zhonglimu", "tradName": "鍾離牧", "name": "钟离牧", "dynasty": "三國",
        "title": "左將軍", "summary": "字子幹，會稽山陰人，東吳名將。任濡須都督、左將軍，率部討平交趾叛亂，封都鄉侯，以清平廉正稱。",
        "aliases": "鍾離牧|钟离牧|鍾離子幹|钟离子干", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "zhonglimu"
    },
    {
        "id": "p_wuyan", "tradName": "吾彥", "name": "吾彦", "dynasty": "三國",
        "title": "交州刺史", "summary": "字士則，吳郡吳縣人，陸抗部將。吳末任建平太守，以浮木測晉軍動向，堅守抗晉，吳亡方降，入晉官至交州刺史。",
        "aliases": "吾彥|吾彦|吾士則|吾士则", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 1, "pinyin": "wuyan"
    },
    {
        "id": "p_yanbaihu", "tradName": "嚴白虎", "name": "严白虎", "dynasty": "東漢",
        "title": "吳郡豪強", "summary": "吳郡烏程豪強，自號東吳德王，聚眾萬人據吳抗衡孫策，兵敗逃奔餘杭，終為孫策所破。",
        "aliases": "嚴白虎|严白虎", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 0, "in_hhs": 0, "in_sgz": 1, "in_js": 0, "pinyin": "yanbaihu"
    },
    # --- 先秦两汉名臣先贤名媛（7人） ---
    {
        "id": "p_liling", "tradName": "李陵", "name": "李陵", "dynasty": "西漢",
        "title": "騎都尉", "summary": "字少卿，隴西成紀人，李廣之孫。率五千步卒深入匈奴浚稽山力戰八萬騎，矢盡無援受降，司馬遷因言李陵受宮刑。",
        "aliases": "李陵|李少卿", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "liling"
    },
    {
        "id": "p_jianshu", "tradName": "蹇叔", "name": "蹇叔", "dynasty": "春秋",
        "title": "秦國大夫", "summary": "春秋秦穆公賢相謀臣。“蹇叔哭師”料定秦軍襲鄭必敗於殽之戰，果然全軍覆沒，為千古名諫。",
        "aliases": "蹇叔", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "jianshu"
    },
    {
        "id": "p_xiangao", "tradName": "弦高", "name": "弦高", "dynasty": "春秋",
        "title": "鄭國商人", "summary": "春秋鄭國愛國商人。行商途中遇秦軍襲鄭，“弦高犒師”以十二牛偽託國命犒勞秦師，遣人急報鄭國備戰，智退秦師保全鄭國。",
        "aliases": "弦高", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 1, "in_hs": 0, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "xiangao"
    },
    {
        "id": "p_wangzhaojun", "tradName": "王昭君", "name": "王昭君", "dynasty": "西漢",
        "title": "寧胡閼氏", "summary": "名嬙，字昭君，南郡秭歸人，漢元帝宮人。竟寧元年自請和親匈奴呼韓邪單于，封寧胡閼氏，邊境晏然數十年。",
        "aliases": "王昭君|王嬙|王樯", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 0, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "wangzhaojun"
    },
    {
        "id": "p_chulong", "tradName": "觸龍", "name": "触龙", "dynasty": "戰國",
        "title": "左師", "summary": "戰國趙國左師老臣。秦攻趙急，趙太后不肯以長安君為質，“觸龍說趙太后”以柔克剛，勸太后遣質立奇功。",
        "aliases": "觸龍|触龙|觸讋|触讋", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "chulong"
    },
    {
        "id": "p_xishi", "tradName": "西施", "name": "西施", "dynasty": "春秋",
        "title": "越國名姝", "summary": "施夷光，春秋四大美女之首，越國名姝。勾踐被困會稽，范蠡獻西施於吳王夫差，沈溺其志，助越滅吳。",
        "aliases": "西施|施夷光", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 1, "in_hs": 1, "in_hhs": 1, "in_sgz": 0, "in_js": 0, "pinyin": "xishi"
    },
    {
        "id": "p_daji", "tradName": "妲己", "name": "妲己", "dynasty": "商代",
        "title": "商王妃", "summary": "有蘇氏之女，商紂王帝辛之妃，傾國名媛，周武王伐紂克商被戮。",
        "aliases": "妲己", "status": "active", "note": "梯隊三無傳名將·docs/48",
        "in_sj": 1, "in_hs": 1, "in_hhs": 0, "in_sgz": 0, "in_js": 0, "pinyin": "daji"
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
    for p in TIER3_BATCHES23_PERSONS:
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

    print(f"\n成功追加梯队三批次二与批次三新人物: {added} 人")
    print(f"新人物表总行数: {ws.max_row - 1}")

    # 安全写盘
    common.safe_save_workbook(wb, xlsx_path)
    print(f"✓ 权威源 {xlsx_path} 已通过 safe_save_workbook 安全保存！")

if __name__ == "__main__":
    main()
