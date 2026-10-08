# -*- coding: utf-8 -*-
"""人物生平行跡數據庫全量提取與初標管線。

遵循規範：
1. 嚴格遵守單向數據流，不修改 workbook/*.xlsx 權威源；
2. 存入 data/index/index.db 的 person_trajectories 表；
3. 支持同一時間多地點異說共存、無時間單色標繪；
4. 輸出結構化 JSON 供前端離線地圖與校勘界面直接消費。
"""
import os
import re
import json
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
COORDS_JSON = os.path.join(ROOT, "data", "dict", "place_coordinates.json")
STRAT_JSON = os.path.join(ROOT, "data", "dict", "strategic_places.json")
OUT_JSON = os.path.join(ROOT, "data", "index", "person_trajectories.json")

# 常見年號公元元年對照表（覆蓋西漢、東漢、三國、兩晉及十六國核心年號）
ERA_TO_AD = {
    # 先秦與秦
    "始皇帝": -221, "始皇": -221, "二世": -209, "秦二世": -209,
    # 西漢
    "漢高祖": -202, "高帝": -202, "高祖": -202, "漢王": -206,
    "惠帝": -195, "呂后": -188, "文帝": -180, "景帝": -157,
    "建元": -140, "元光": -134, "元朔": -128, "元狩": -122, "元鼎": -116, "元封": -110,
    "太初": -104, "天漢": -100, "太始": -96, "征和": -92, "後元": -88,
    "始元": -86, "元鳳": -80, "元平": -74, "本始": -73, "地節": -69, "元康": -65,
    "神爵": -61, "五鳳": -57, "甘露": -53, "黃龍": -49, "初元": -48, "永光": -43,
    "建昭": -38, "竟寧": -33, "建始": -32, "河平": -28, "陽朔": -24, "鴻嘉": -20,
    "永始": -16, "元延": -12, "綏和": -8, "建平": -6, "元壽": -2, "元始": 1,
    "居攝": 6, "初始": 8, "始建國": 9, "天鳳": 14, "地皇": 20, "更始": 23,
    # 東漢
    "建武": 25, "中元": 56, "永平": 58, "建初": 76, "元和": 84, "章和": 87,
    "永元": 89, "元興": 105, "延平": 106, "永初": 107, "元初": 114, "永寧": 120,
    "建光": 121, "延光": 122, "永建": 126, "陽嘉": 132, "永和": 136, "漢安": 142,
    "建康": 144, "永嘉": 145, "本初": 146, "建和": 147, "和平": 150, "元嘉": 151,
    "永興": 153, "永壽": 155, "延熹": 158, "永康": 167, "建寧": 168, "熹平": 172,
    "光和": 178, "中平": 184, "光熹": 189, "昭寧": 189, "永漢": 189,
    "初平": 190, "興平": 194, "建安": 196, "延康": 220,
    # 三國（曹魏、蜀漢、孫吳）
    "黃初": 220, "太和": 227, "青龍": 233, "景初": 237, "正始": 240, "嘉平": 249,
    "正元": 254, "甘露": 256, "景元": 260, "咸熙": 264,
    "章武": 221, "建興": 223, "延熙": 238, "景耀": 258, "炎興": 263,
    "黃武": 222, "黃龍": 229, "嘉禾": 232, "赤烏": 238, "太元": 251, "神鳳": 252,
    "建興": 252, "五鳳": 254, "太平": 256, "永安": 258, "元興": 264,
    "寶鼎": 266, "建衡": 269, "鳳凰": 272, "天策": 275, "天璽": 276, "天紀": 277,
    # 西晉與東晉
    "泰始": 265, "咸寧": 275, "太康": 280, "太熙": 290, "永熙": 290, "永平": 291,
    "元康": 291, "永康": 300, "永寧": 301, "太安": 302, "永安": 304,
    "永興": 304, "光熙": 306, "永嘉": 307, "建興": 313,
    "大興": 318, "永昌": 322, "太寧": 323, "咸和": 326, "咸康": 335,
    "升平": 357, "隆和": 362, "興寧": 363, "太和": 366,
    "咸安": 371, "寧康": 373, "太元": 376, "隆安": 397, "元興": 402, "大亨": 402,
    "義熙": 405, "元熙": 419,
    # 十六國
    "光極": 308, "河瑞": 309, "光興": 310, "嘉平": 311, "太寧": 349,
    "皇始": 351, "壽光": 355, "甘露": 359, "建元": 365, "太安": 385,
    "白雀": 384, "建初": 386, "皇初": 394, "弘始": 399
}

# 中文數字轉換
CN_NUM = {
    '元': 1, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
    '二十一': 21, '二十二': 22, '二十三': 23, '二十四': 24, '二十五': 25,
    '二十六': 26, '二十七': 27, '二十八': 28, '二十九': 29, '三十': 30,
    '三十一': 31, '三十二': 32, '三十三': 33, '三十四': 34, '三十五': 35
}

# 61 位核心人物清單（按五史分類）
TARGET_PERSONS = [
    # 史記 10 人
    'p_qihuan', 'p_jinwengong', 'p_qinshihuang', 'p_liubang', 'p_xiangyu',
    'p_hanxin', 'p_zhangliang', 'p_weiqing', 'p_liguang', 'p_huo_qubing',
    # 漢書 10 人
    'p_hanwudi', 'p_wangmang', 'p_zhangqian', 'p_suwu', 'p_liling',
    'p_liuwu', 'p_qingbu', 'p_hanxuandi', 'p_hanchengdi', 'p_hanaidi',
    # 後漢書 10 人
    'p_liuxiu', 'p_gongsunshu', 'p_mayuan', 'p_banchao', 'p_wuhan',
    'p_wangchang', 'p_mawu', 'p_dongzhuo', 'p_dengyu', 'p_fengyi',
    # 三國志 20 人
    'p_caocao', 'p_liubei', 'p_caopi', 'p_sunquan', 'p_zhugegang',
    'p_cao_rui', 'p_guanyu', 'p_yuanshao', 'p_simayi', 'p_yuanshu',
    'p_liubiao', 'p_jiangwei', 'p_lvbu', 'p_zhangliao', 'p_luxun',
    'p_sunce', 'p_zhouyu_sg', 'p_zhugeke', 'p_sunjian', 'p_zhanghe',
    # 晉書 11 人
    'p_shihu', 'p_shile', 'p_fujian2', 'p_simayan', 'p_simarui',
    'p_huanwen', 'p_liuyao', 'p_murongchui', 'p_wangdao', 'p_wangmeng_qin',
    'p_xiean'
]

# 61 位核心人物生平合法的史書範圍（排除後世追述、祭祀、借古喻今或同名封王者引發的時空穿越）
PERSON_VALID_BOOKS = {
    # 史記 10 人（先秦至楚漢、漢初名將：生平行跡嚴格限於先秦秦漢正史記載）
    'p_qihuan': ['sj'],
    'p_jinwengong': ['sj'],
    'p_qinshihuang': ['sj'],
    'p_liubang': ['sj', 'hs'],
    'p_xiangyu': ['sj', 'hs'],
    'p_hanxin': ['sj', 'hs'],
    'p_zhangliang': ['sj', 'hs'],
    'p_weiqing': ['sj', 'hs'],
    'p_liguang': ['sj', 'hs'],
    'p_huo_qubing': ['sj', 'hs'],

    # 漢書 10 人（西漢武帝至西漢末年）
    'p_hanwudi': ['sj', 'hs'],
    'p_wangmang': ['hs'],
    'p_zhangqian': ['sj', 'hs'],
    'p_suwu': ['hs'],
    'p_liling': ['sj', 'hs'],
    'p_liuwu': ['sj', 'hs'],
    'p_qingbu': ['sj', 'hs'],
    'p_hanxuandi': ['hs'],
    'p_hanchengdi': ['hs'],
    'p_hanaidi': ['hs'],

    # 後漢書 10 人（東漢開國至中後期；董卓橫跨漢末與三國正傳）
    'p_liuxiu': ['hhs'],
    'p_gongsunshu': ['hhs'],
    'p_mayuan': ['hhs'],
    'p_banchao': ['hhs'],
    'p_wuhan': ['hhs'],
    'p_wangchang': ['hhs'],
    'p_mawu': ['hhs'],
    'p_dongzhuo': ['hhs', 'sgz'],
    'p_dengyu': ['hhs'],
    'p_fengyi': ['hhs'],

    # 三國志 20 人（漢末群雄橫跨後漢書與三國志；純三國人物限三國志；司馬懿橫跨魏書與晉書宣帝紀）
    'p_caocao': ['sgz', 'hhs'],
    'p_liubei': ['sgz', 'hhs'],
    'p_caopi': ['sgz'],
    'p_sunquan': ['sgz'],
    'p_zhugegang': ['sgz'],
    'p_cao_rui': ['sgz'],
    'p_guanyu': ['sgz'],
    'p_yuanshao': ['sgz', 'hhs'],
    'p_simayi': ['sgz', 'js'],
    'p_yuanshu': ['sgz', 'hhs'],
    'p_liubiao': ['sgz', 'hhs'],
    'p_jiangwei': ['sgz'],
    'p_lvbu': ['sgz', 'hhs'],
    'p_zhangliao': ['sgz'],
    'p_luxun': ['sgz'],
    'p_sunce': ['sgz', 'hhs'],
    'p_zhouyu_sg': ['sgz'],
    'p_zhugeke': ['sgz'],
    'p_sunjian': ['sgz', 'hhs'],
    'p_zhanghe': ['sgz'],

    # 晉書 11 人（兩晉與十六國專屬）
    'p_shihu': ['js'],
    'p_shile': ['js'],
    'p_fujian2': ['js'],
    'p_simayan': ['js'],
    'p_simarui': ['js'],
    'p_huanwen': ['js'],
    'p_liuyao': ['js'],
    'p_murongchui': ['js'],
    'p_wangdao': ['js'],
    'p_wangmeng_qin': ['js'],
    'p_xiean': ['js']
}

def parse_time_str(text):
    """從文本中嘗試識別年號紀年並計算估算公元紀年。"""
    pattern = r'([^\s，。；]{2,5}?)(元|[一二三四五六七八九十]{1,3})年'
    match = re.search(pattern, text)
    if match:
        era_name = match.group(1)
        year_num_str = match.group(2)
        era_clean = re.sub(r'^(是歲|是年|及|至|時|秋|冬|春|夏|後)', '', era_name)
        if era_clean in ERA_TO_AD:
            base_ad = ERA_TO_AD[era_clean]
            offset = CN_NUM.get(year_num_str, 1) - 1
            calc_ad = base_ad + offset
            month_match = re.search(r'([春夏秋冬])?(?:([正二三四五六七八九十][一二]?月))?', text[match.end():match.end()+10])
            detail_time = match.group(0)
            if month_match and (month_match.group(1) or month_match.group(2)):
                detail_time += month_match.group(0)
            return detail_time, calc_ad
        else:
            return match.group(0), None
    return None, None

def init_trajectory_schema(conn):
    """初始化人物生平行跡表。"""
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS person_trajectories")
    c.execute("""
    CREATE TABLE person_trajectories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        person_name TEXT NOT NULL,
        place_id TEXT NOT NULL,
        place_name TEXT NOT NULL,
        time_raw TEXT,
        year_ad INTEGER,
        time_order INTEGER,
        event_summary TEXT,
        sentence_uid TEXT NOT NULL,
        source_book TEXT NOT NULL,
        source_chapter TEXT,
        chapter_id TEXT,
        source_text TEXT,
        tier INTEGER DEFAULT 1,
        confidence TEXT DEFAULT 'verified',
        coord_lng REAL,
        coord_lat REAL,
        is_disputed INTEGER DEFAULT 0
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_trj_person ON person_trajectories(person_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_trj_place ON person_trajectories(place_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_trj_year ON person_trajectories(year_ad)")
    conn.commit()

def load_all_coords():
    """加載 190+ 處古代地名經緯度。"""
    coords_dict = {}
    if os.path.exists(COORDS_JSON):
        with open(COORDS_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for k, v in data.items():
                if "coords" in v:
                    coords_dict[k] = v["coords"]
    # 兜底補充 strategic_places
    if os.path.exists(STRAT_JSON):
        with open(STRAT_JSON, 'r', encoding='utf-8') as f:
            strat = json.load(f)
            for k, v in strat.items():
                if "coords" in v and k not in coords_dict:
                    coords_dict[k] = v["coords"]
    return coords_dict

def extract_for_person(conn, person_id, coords_map, max_records=None):
    """提取指定人物的全量同句人地共現及時空行跡。"""
    c = conn.cursor()
    c.execute("SELECT trad_name FROM persons WHERE id = ?", (person_id,))
    p_row = c.fetchone()
    if not p_row:
        return []
    p_name = p_row[0]

    valid_books = PERSON_VALID_BOOKS.get(person_id)
    if valid_books:
        placeholders = ','.join('?' for _ in valid_books)
        query = f"""
        SELECT s.uid, s.text, pl.id, pl.trad_name, ch.book_id, ch.title, s.para_seq, s.seq, s.chapter_id
        FROM mentions m
        JOIN place_mentions pm ON m.sentence_uid = pm.sentence_uid
        JOIN sentences s ON m.sentence_uid = s.uid
        JOIN chapters ch ON s.chapter_id = ch.id
        JOIN places pl ON pm.place_id = pl.id
        WHERE m.person_id = ? AND ch.book_id IN ({placeholders})
        ORDER BY ch.book_id, s.chapter_id, s.para_seq, s.seq
        """
        c.execute(query, [person_id] + list(valid_books))
    else:
        query = """
        SELECT s.uid, s.text, pl.id, pl.trad_name, ch.book_id, ch.title, s.para_seq, s.seq, s.chapter_id
        FROM mentions m
        JOIN place_mentions pm ON m.sentence_uid = pm.sentence_uid
        JOIN sentences s ON m.sentence_uid = s.uid
        JOIN chapters ch ON s.chapter_id = ch.id
        JOIN places pl ON pm.place_id = pl.id
        WHERE m.person_id = ?
        ORDER BY ch.book_id, s.chapter_id, s.para_seq, s.seq
        """
        c.execute(query, (person_id,))
    rows = c.fetchall()

    trajectories = []
    context_time_cache = {}

    for r in rows:
        uid, text, place_id, place_name, book_id, ch_title, para_seq, seq, ch_id = r
        time_raw, year_ad = parse_time_str(text)
        
        cache_key = (ch_id, para_seq)
        if time_raw:
            context_time_cache[cache_key] = (time_raw, year_ad)
        else:
            if cache_key in context_time_cache:
                time_raw, year_ad = context_time_cache[cache_key]
                time_raw = f"{time_raw}(上下文推定)"

        lng, lat = None, None
        if place_id in coords_map:
            lng, lat = coords_map[place_id]

        event_summary = text.strip()
        if len(event_summary) > 40:
            event_summary = event_summary[:38] + "…"

        trj = {
            "person_id": person_id,
            "person_name": p_name,
            "place_id": place_id,
            "place_name": place_name,
            "time_raw": time_raw if time_raw else "無明確時間",
            "year_ad": year_ad,
            "time_order": None,
            "event_summary": event_summary,
            "sentence_uid": uid,
            "source_book": book_id,
            "source_chapter": ch_title,
            "chapter_id": ch_id,
            "source_text": text,
            "tier": 1,
            "confidence": "verified" if year_ad else "co_occur",
            "coord_lng": lng,
            "coord_lat": lat,
            "is_disputed": 0
        }
        trajectories.append(trj)

    unique_trjs = []
    seen = set()
    for t in trajectories:
        key = (t["sentence_uid"], t["place_id"])
        if key not in seen:
            seen.add(key)
            unique_trjs.append(t)

    dated_items = [t for t in unique_trjs if t["year_ad"] is not None]
    undated_items = [t for t in unique_trjs if t["year_ad"] is None]
    dated_items.sort(key=lambda x: x["year_ad"])

    for idx, t in enumerate(dated_items, 1):
        t["time_order"] = idx
    for t in undated_items:
        t["time_order"] = 0

    final_list = dated_items + undated_items
    if max_records:
        final_list = final_list[:max_records]
    return final_list

def save_trajectories_to_db(conn, trj_list):
    """批量寫入 SQLite。"""
    c = conn.cursor()
    for t in trj_list:
        c.execute("""
        INSERT INTO person_trajectories (
            person_id, person_name, place_id, place_name,
            time_raw, year_ad, time_order, event_summary,
            sentence_uid, source_book, source_chapter, chapter_id, source_text,
            tier, confidence, coord_lng, coord_lat, is_disputed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t["person_id"], t["person_name"], t["place_id"], t["place_name"],
            t["time_raw"], t["year_ad"], t["time_order"], t["event_summary"],
            t["sentence_uid"], t["source_book"], t["source_chapter"], t.get("chapter_id", ""), t["source_text"],
            t["tier"], t["confidence"], t["coord_lng"], t["coord_lat"], t["is_disputed"]
        ))
    conn.commit()

def run_extraction():
    conn = sqlite3.connect(DB_PATH)
    init_trajectory_schema(conn)
    coords_map = load_all_coords()

    all_extracted = {}
    print(f"=== 開始全量抽取 61 位核心人物行跡數據 (地名坐標庫: {len(coords_map)} 處) ===")
    total_count = 0
    total_dated = 0
    total_with_coords = 0

    for idx, pid in enumerate(TARGET_PERSONS, 1):
        trjs = extract_for_person(conn, pid, coords_map)
        all_extracted[pid] = trjs
        cnt = len(trjs)
        dated_cnt = sum(1 for t in trjs if t["year_ad"] is not None)
        coord_cnt = sum(1 for t in trjs if t["coord_lng"] is not None)
        
        total_count += cnt
        total_dated += dated_cnt
        total_with_coords += coord_cnt
        
        pname = trjs[0]["person_name"] if trjs else pid
        print(f"[{idx:02d}/61] {pname:<6} ({pid:<16}) -> 總行跡: {cnt:<4} | 有紀年: {dated_cnt:<3} | 命中經緯度: {coord_cnt:<3}")

    # 清空原有試點數據後全量寫入
    c = conn.cursor()
    c.execute("DELETE FROM person_trajectories")
    for pid, trjs in all_extracted.items():
        save_trajectories_to_db(conn, trjs)

    # 輸出脫機 JSON 全量快照
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(all_extracted, f, ensure_ascii=False, indent=2)

    print(f"\n=======================================================")
    print(f"全量抽取完成！成功寫入 SQLite person_trajectories 表。")
    print(f"導出脫機快照: {OUT_JSON}")
    print(f"總覆蓋人物: {len(all_extracted)} 人")
    print(f"總行跡記錄: {total_count} 條")
    print(f"有明確公元紀年: {total_dated} 條")
    print(f"命中經緯度坐標: {total_with_coords} 條")
    print(f"=======================================================")

if __name__ == '__main__':
    run_extraction()
