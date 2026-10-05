# -*- coding: utf-8 -*-
"""地名权威源扩充脚本（安全写入 workbook/places.xlsx）。

遵循红线：
1. 必须使用 pipeline.common.safe_save_workbook 进行内存 BytesIO 封包 + 原子替换；
2. 保持原 1575 行主体结构不变，对已有相关地名补充高频别名（宛城、许都、建邺、黄河、长江等）；
3. 将 pl_yizhou 类别升级为「州」，使汉魏十三州整齐划一；
4. 将 pl_yiling 扩充夷陵之战简介与「彝陵」别名；
5. 追加汉魏十三州、战役要塞、战略名关、重镇、山川等核心多字实体；
6. 严格守卫字串排他性，避免关隘全称与已有郡县裸名（如阳平/葭萌/玉门/雁门）冲突。
"""
import os
import sys
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import safe_save_workbook

XLSX_PATH = os.path.join(ROOT, "workbook", "places.xlsx")

# 1. 对已有条目的就地更新配置
EXISTING_UPDATES = {
    # 益州升级为州
    "pl_yizhou": {
        "kind": "州",
        "era": "東漢",
        "summary": "汉魏晋十三州之一，汉武帝置部，东汉改州牧，刘璋与蜀汉根据地，治成都，辖蜀郡、汉中、巴郡等，今川渝滇黔一带；西汉亦曾为益州郡。",
    },
    # 夷陵升级
    "pl_yiling": {
        "summary": "楚西塞，秦拔郢后置夷陵县，三国章武二年刘备与陆逊夷陵之战（猇亭之战）古战场，今湖北宜昌市夷陵区。",
        "alias_append": ["彝陵"],
    },
    # 汉水补沔水/汉江
    "pl_han_shui": {
        "alias_append": ["沔水", "漢江", "汉江"],
    },
    # 长江补長江/长江
    "pl_changjiang": {
        "alias_append": ["長江", "长江"],
    },
    # 黄河补黃河/黄河
    "pl_huanghe": {
        "alias_append": ["黃河", "黄河"],
    },
    # 宛补宛城
    "pl_wu_wan": {
        "alias_append": ["宛城"],
    },
    # 许昌补许都/许县
    "pl_xuchang_js": {
        "alias_append": ["許都", "许都", "許縣", "许县"],
    },
    # 邺补邺城/邺都
    "pl_ye": {
        "alias_append": ["鄴城", "邺城", "鄴都", "邺都"],
    },
    # 谯补谯城/谯县
    "pl_qiao": {
        "alias_append": ["譙城", "谯城", "譙縣", "谯县"],
    },
    # 襄阳补襄阳城
    "pl_xiangyang": {
        "alias_append": ["襄陽城", "襄阳城"],
    },
    # 建康补建邺/建鄴
    "pl_jiankang": {
        "alias_append": ["建鄴", "建邺"],
    },
    # 长安补长安城
    "pl_changan": {
        "alias_append": ["長安城", "长安城"],
    },
    # 洛阳补洛阳城
    "pl_luoyang": {
        "alias_append": ["洛陽城", "洛阳城"],
    },
    # 雁门补雁门关
    "pl_yanmen": {
        "summary": "赵置雁门郡，辖雁门关故塞，天下九塞之一，今山西北部与代县雁门山。",
        "alias_append": ["雁門關", "雁门关"],
    },
}

# 2. 拟新增的全新核心地名列表（关隘别名只收带「關/关」的长名，绝不带裸县名以防冲突）
NEW_PLACES = [
    # ---------- 汉魏晋十三州及重要州部 ----------
    ("pl_jingzhou_zhou", "荊州", "荆州", "州", "東漢",
     "汉魏晋十三州之一，辖南阳、南郡、江夏、零陵、桂阳、武陵、长沙等郡，三国魏蜀吴争夺焦点，今两湖及河南南部。",
     "荊州|荆州", "jingzhou"),
    ("pl_yangzhou_zhou", "揚州", "扬州", "州", "東漢",
     "汉魏晋十三州之一，辖九江、丹阳、庐江、会稽、吴郡、豫章等郡，东吴及东晋根据地，今苏南、皖南、浙、赣、闽一带。",
     "揚州|扬州", "yangzhou"),
    ("pl_jizhou_zhou", "冀州", "冀州", "州", "東漢",
     "汉魏晋十三州之一，辖魏郡、巨鹿、常山、中山、安平、河间、清河、赵国等，袁绍根据地、后为曹魏中枢，今河北中南部、山东西部、河南北部。",
     "冀州", "jizhou"),
    ("pl_yanzhou_zhou", "兗州", "兖州", "州", "東漢",
     "汉魏晋十三州之一，辖东郡、陈留、济阴、山阳、泰山、东平、任城、济北，曹操早期起兵根据地，今山东西部与河南东北部。",
     "兗州|兖州", "yanzhou"),
    ("pl_yuzhou_zhou", "豫州", "豫州", "州", "東漢",
     "汉魏晋十三州之一，辖颍川、汝南、梁国、沛国、陈国、鲁国等，今河南中东部及安徽北部。",
     "豫州", "yuzhou"),
    ("pl_xuzhou_zhou", "徐州", "徐州", "州", "東漢",
     "汉魏晋十三州之一，辖东海、琅邪、彭城、广陵、下邳等，陶谦、刘备、吕布先后领此，今江苏北部、山东南部、安徽东北部。",
     "徐州", "xuzhou"),
    ("pl_qingzhou_zhou", "青州", "青州", "州", "東漢",
     "汉魏晋十三州之一，辖齐国、北海、东莱、乐安、济南、平原等，曹操青州兵发源地，今山东半岛及胶东一带。",
     "青州", "qingzhou"),
    ("pl_youzhou_zhou", "幽州", "幽州", "州", "東漢",
     "汉魏晋十三州之一，辖涿郡、广阳、代郡、上谷、渔阳、右北平、辽西、辽东等，今北京、河北北部、辽宁一带。",
     "幽州", "youzhou"),
    ("pl_bingzhou_zhou", "幷州", "并州", "州", "東漢",
     "汉魏晋十三州之一，辖太原、上党、西河、雁门等，今山西大部及内蒙古部分地区。",
     "幷州|并州", "bingzhou"),
    ("pl_liangzhou_zhou", "涼州", "凉州", "州", "東漢",
     "汉魏晋十三州之一，辖陇西、金城、天水、武威、张掖、酒泉、敦煌等，西北军事重镇，今甘肃、宁夏、青海部分地区。",
     "涼州|凉州", "liangzhou"),
    ("pl_jiaozhou_zhou", "交州", "交州", "州", "東漢",
     "汉魏晋十三州之一，辖南海、苍梧、郁林、合浦、交趾、九真、日南等，今两广及越南北部。",
     "交州", "jiaozhou"),
    ("pl_yongzhou_zhou", "雍州", "雍州", "州", "東漢",
     "东汉兴平元年分凉州置，后曹魏统领关中诸郡，治长安，今陕西关中及甘肃东部。",
     "雍州", "yongzhou"),
    ("pl_liangzhou2_zhou", "梁州", "梁州", "州", "曹魏",
     "曹魏灭蜀后分益州北部置，治南郑，辖汉中、巴西、巴东等郡，今陕西南部及四川北部。",
     "梁州", "liangzhou"),
    ("pl_guangzhou_zhou", "廣州", "广州", "州", "三國",
     "孙吴黄武五年分交州置，治番禺，辖南海、苍梧等郡，今广东、广西一带。",
     "廣州|广州", "guangzhou"),
    ("pl_qinzhou_zhou", "秦州", "秦州", "州", "西晉",
     "西晋泰始五年分雍、凉二州置，治冀县，辖天水、陇西等郡，今甘肃天水一带。",
     "秦州", "qinzhou"),

    # ---------- 核心名城重镇 ----------
    ("pl_wuchang_city", "武昌", "武昌", "县", "三國",
     "孙权黄武元年自公安迁都于此，改鄂县为武昌，今湖北鄂州；后东晋亦为荆江军政重镇。",
     "武昌", "wuchang"),
    ("pl_xiakou", "夏口", "夏口", "县", "東漢",
     "汉水入江之口，军事要冲，江夏郡治所在，赤壁之战刘备与孙权水军驻屯处，今湖北武汉汉口、武昌一带。",
     "夏口", "xiakou"),
    ("pl_gushu", "姑孰", "姑孰", "县", "東晉",
     "东晋南朝长江下游军事重镇，历代权臣屯镇要地，今安徽当涂。",
     "姑孰", "gushu"),
    ("pl_xiaopei", "小沛", "小沛", "县", "東漢",
     "沛县小城，东汉末陶谦令刘备屯兵于此，吕布袭徐州后刘备复居之，今江苏沛县。",
     "小沛", "xiaopei"),
    ("pl_jinyong", "金墉城", "金墉城", "县", "曹魏",
     "洛阳城西北角小城，魏明帝所筑，西晋八王之乱及十六国争夺洛阳之关键要塞。",
     "金墉城|金墉", "jinyong"),

    # ---------- 著名古战场与军事要塞 ----------
    ("pl_chibi", "赤壁", "赤壁", "域", "東漢",
     "赤壁之战古战场，建安十三年孙刘联军大破曹操于此，今湖北赤壁市西北长江南岸。",
     "赤壁", "chibi"),
    ("pl_guandu", "官渡", "官渡", "域", "東漢",
     "官渡之战古战场，建安五年曹操以弱胜强击破袁绍要塞，今河南中牟北。",
     "官渡", "guandu"),
    ("pl_jieting", "街亭", "街亭", "域", "三國",
     "三国街亭之战古战场，蜀汉建兴六年马谡失守致诸葛亮一出祁山失利，今甘肃天水秦安县陇城镇。",
     "街亭", "jieting"),
    ("pl_qishan_shu", "祁山", "祁山", "山", "三國",
     "祁山堡与祁山古战场，诸葛亮北伐出祁山之战略要地，今甘肃礼县东祁山乡。",
     "祁山", "qishan"),
    ("pl_wuzhangyuan", "五丈原", "五丈原", "域", "三國",
     "蜀汉建兴十二年诸葛亮最后一次北伐屯兵与病逝处，今陕西岐山县西南斜谷口西侧。",
     "五丈原", "wuzhangyuan"),
    ("pl_dingjunshan", "定軍山", "定军山", "山", "東漢",
     "定军山之战古战场，建安二十四年刘备部将黄忠阵斩夏侯渊处，今陕西勉县南。",
     "定軍山|定军山", "dingjunshan"),
    ("pl_fancheng", "樊城", "樊城", "县", "東漢",
     "汉水北岸战略要塞，与襄阳隔汉江相望，建安二十四年关羽水淹七军围樊城曹仁，今湖北襄阳樊城区。",
     "樊城", "fancheng"),
    ("pl_ruxukou", "濡須口", "濡须口", "关", "三國",
     "曹魏与孙吴多次交战之江淮咽喉水陆要塞，孙权筑濡须坞抗曹，今安徽含山南、无为北巢湖水入江处。",
     "濡須口|濡须口|濡須|濡须", "ruxukou"),
    ("pl_baidicheng", "白帝城", "白帝城", "县", "三國",
     "公孙述所筑，后蜀汉章武三年刘备托孤诸葛亮于白帝城永安宫，今重庆奉节瞿塘峡口。",
     "白帝城|白帝", "baidicheng"),
    ("pl_maicheng", "麥城", "麦城", "县", "三國",
     "建安二十四年关羽兵败走麦城之处，今湖北当阳市两河镇麦城村。",
     "麥城|麦城", "maicheng"),
    ("pl_wuchao", "烏巢", "乌巢", "域", "東漢",
     "官渡之战曹操夜袭许攸所告袁绍粮囤处，今河南延津东南。",
     "烏巢|乌巢", "wuchao"),
    ("pl_yanjin", "延津", "延津", "域", "東漢",
     "黄河古渡口，官渡之战曹操声东击西斩文丑处，今河南延津北。",
     "延津", "yanjin"),
    ("pl_xiaoyaojin", "逍遙津", "逍遥津", "域", "三國",
     "合肥淝水古渡口，建安二十年张辽以八百步卒大破孙权十万大军处，今安徽合肥老城区东北。",
     "逍遙津|逍遥津", "xiaoyaojin"),
    ("pl_changban", "長坂", "长坂", "域", "東漢",
     "长坂坡之战古战场，建安十三年刘备败走、赵云救阿斗、张飞据水断桥处，今湖北当阳市玉阳街道。",
     "長坂|长坂|長坂坡|长坂坡", "changban"),
    ("pl_bowang", "博望", "博望", "县", "西漢",
     "汉置博望侯张骞封邑，博望坡之战刘备拒夏侯惇处，今河南方城西南博望镇。",
     "博望|博望坡", "bowang"),

    # ---------- 著名关隘要塞（严禁收录裸县名以防冲突） ----------
    ("pl_tongguan", "潼關", "潼关", "关", "東漢",
     "建安元年曹操所置，关中东大门，扼黄河与秦岭之险，今陕西潼关县北。",
     "潼關|潼关", "tongguan"),
    ("pl_jiange", "劍閣", "剑阁", "关", "三國",
     "剑门关要塞，蜀汉姜维据剑阁阻钟会十万魏军处，蜀道咽喉，今四川剑阁县大剑山下。",
     "劍閣|剑阁|劍門|剑门|劍門關|剑门关", "jiange"),
    ("pl_yangpingguan", "陽平關", "阳平关", "关", "東漢",
     "汉中西北门户，白马水与汉水交汇处，曹操破张鲁及诸葛亮屯汉中之要塞，今陕西勉县西。",
     "陽平關|阳平关", "yangpingguan"),
    ("pl_jiamengguan", "葭萌關", "葭萌关", "关", "戰國",
     "蜀道要冲，刘备入蜀驻兵葭萌，今四川广元昭化古城一带。",
     "葭萌關|葭萌关", "jiamengguan"),
    ("pl_sanguan", "散關", "散关", "关", "戰國",
     "大散关，秦岭西段关口，川陕咽喉，曹操伐张鲁自陈仓出散关，今陕西宝鸡西南大散岭上。",
     "散關|散关|大散關|大散关", "sanguan"),
    ("pl_juyongguan", "居庸關", "居庸关", "关", "戰國",
     "燕之要塞，天下九塞之一，太行八陉之军都陉，今北京昌平居庸关。",
     "居庸關|居庸关", "juyongguan"),
    ("pl_hulaoguan", "虎牢關", "虎牢关", "关", "戰國",
     "汜水关、武牢关，洛阳东门户，唐避讳改武牢，今河南荥阳市区西北汜水镇。",
     "虎牢關|虎牢关|虎牢|武牢|汜水關|汜水关|武牢關|武牢关", "hulaoguan"),
    ("pl_yumenguan", "玉門關", "玉门关", "关", "西漢",
     "汉武帝通西域所设关隘，丝绸之路西出北道必经之关，今甘肃敦煌市西北小方盘城。",
     "玉門關|玉门关", "yumenguan"),
    ("pl_yangguan", "陽關", "阳关", "关", "西漢",
     "汉武帝通西域所设关隘，丝绸之路西出南道必经之关，今甘肃敦煌市西南古董滩。",
     "陽關|阳关", "yangguan"),

    # ---------- 著名江河湖泊山岳 ----------
    ("pl_fenshui", "汾水", "汾水", "川", "上古",
     "黄河第二大支流，山西母亲河，今汾河。",
     "汾水|汾河", "fenshui"),
    ("pl_feishui", "淝水", "淝水", "川", "戰國",
     "淝水之战古战场，东晋谢玄等大破前秦苻坚八十万大军处，今安徽寿县东瓦埠湖水系。",
     "淝水", "feishui"),
]


def enrich():
    # 重新加载干净的初始备份或从现有读取并重置（恢复原始 1575 行纯净集合）
    # 为保证绝对幂等与干净，我们从 pipeline/build_places.py 的 PLACES+PLACES_DL+PLACES_JS 重建基础列表
    from build_places import PLACES, PLACES_DL, PLACES_JS
    from opencc import OpenCC
    t2s = OpenCC("t2s")

    base_pids = set()
    rows_data = []

    # 1. 原始 1575 行基础数据
    for raw in list(PLACES) + list(PLACES_DL) + list(PLACES_JS):
        pid, name, trad = raw[0], raw[1], raw[2]
        kind, era, summary = raw[3], raw[4], raw[5]
        extra = list(raw[6]) if len(raw) > 6 else []
        aliases = []
        for x in [trad] + extra:
            for form in (x, t2s.convert(x)):
                if form and form not in aliases:
                    aliases.append(form)
        if name not in aliases:
            aliases.append(name)

        # 检查是否在已有修改项中
        if pid in EXISTING_UPDATES:
            cfg = EXISTING_UPDATES[pid]
            if "kind" in cfg:
                kind = cfg["kind"]
            if "era" in cfg:
                era = cfg["era"]
            if "summary" in cfg:
                summary = cfg["summary"]
            if "alias_append" in cfg:
                for a in cfg["alias_append"]:
                    for f in (a, t2s.convert(a)):
                        if f and f not in aliases:
                            aliases.append(f)

        base_pids.add(pid)
        rows_data.append([
            pid,
            trad,
            name,
            kind,
            era,
            summary,
            "|".join(aliases),
            "active",
            None,
            "",  # pinyin
        ])

    print(f"原始基线加载完成: {len(rows_data)} 处，已就地升级: {len(EXISTING_UPDATES)} 处")

    # 2. 追加全新核心地名
    appended = 0
    for np in NEW_PLACES:
        pid = np[0]
        if pid in base_pids:
            continue
        base_pids.add(pid)
        aliases = []
        for x in np[6].split("|"):
            for f in (x, t2s.convert(x)):
                if f and f not in aliases:
                    aliases.append(f)
        rows_data.append([
            np[0],
            np[1],
            np[2],
            np[3],
            np[4],
            np[5],
            "|".join(aliases),
            "active",
            None,
            np[7],
        ])
        appended += 1

    print(f"成功追加新地名: {appended} 处")
    print(f"扩充后地名总数: {len(rows_data)} 处")

    # 3. 严格自检：字串唯一性排他校验
    owners = {}
    conflicts = []
    for r in rows_data:
        pid = r[0]
        trad = r[1]
        aliases = str(r[6] or "").split("|")
        for form in set([trad] + aliases):
            if not form:
                continue
            if form in owners and owners[form] != pid:
                conflicts.append((form, owners[form], pid))
            owners[form] = pid

    if conflicts:
        print(f"❌ 发现 {len(conflicts)} 处别名撞车，中止保存：")
        for c in conflicts:
            print(f"   字串 '{c[0]}' 同时属于 {c[1]} 与 {c[2]}")
        sys.exit(1)

    print("✓ 0 冲突校验通过！全部字串排他性 100% 成立。")

    # 4. 打开现有 workbook，刷新「地名」Sheet 并原子安全保存
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb["地名"]
    ws.delete_rows(2, ws.max_row)
    for r in rows_data:
        ws.append(r)

    safe_save_workbook(wb, XLSX_PATH)
    print(f"✓ 安全写入成功: {XLSX_PATH}")


if __name__ == "__main__":
    enrich()
