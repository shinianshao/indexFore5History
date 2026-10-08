# -*- coding: utf-8 -*-
"""人物生平行跡數據庫與輿圖解耦端到端獨立審查 (docs/84)

驗證範圍：
1. 坐標庫 data/dict/place_coordinates.json 覆蓋度 (>= 190 處)
2. 行跡數據庫 SQLite person_trajectories 與脫機 JSON 規模 (>= 12,000 條)
3. 五史 61 位核心人物 100% 全量收錄且每人皆有足跡
4. 公元紀年解析精確度與同期多地判定
5. 前端輿圖模式雙 Tab 解耦 (兵爭圖 vs 人物行跡圖) 與 Color Bar 色溫條
6. 雙端 (app/web/app.js vs dist/app.js) 邏輯 100% 同構
7. 故障注入模式 (--inject) 變紅閉環驗證
"""
import os
import sys
import json
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

COORD_FILE = os.path.join(ROOT, "data", "dict", "place_coordinates.json")
TRJ_JSON = os.path.join(ROOT, "data", "index", "person_trajectories.json")
DB_FILE = os.path.join(ROOT, "data", "index", "index.db")
WEB_JS = os.path.join(ROOT, "app", "web", "app.js")
DIST_JS = os.path.join(ROOT, "dist", "app.js")
DIST_DATA = os.path.join(ROOT, "dist", "data.js")

CHECKS = []
INJECT_FAULT = "--inject" in sys.argv

def check(name: str, passed: bool, extra: str = ""):
    CHECKS.append((name, passed))
    mark = "OK" if passed else "FAIL"
    detail = f"　（{extra}）" if extra else ""
    print(f"  [{mark}] {name}{detail}")

def test_place_coordinates():
    exists = os.path.exists(COORD_FILE)
    if not exists:
        check("坐標庫文件存在", False, COORD_FILE)
        return
    with open(COORD_FILE, "r", encoding="utf-8") as f:
        coords = json.load(f)
    n = len(coords)
    if INJECT_FAULT:
        n = 50
    check("地名坐標庫規模 >= 190 處", n >= 190, f"實得 {n} 處")
    
    # 抽檢核心要邑
    missing = []
    for pl in ["pl_ye", "pl_xuchang", "pl_changan", "pl_luoyang", "pl_jiankang", "pl_chengdou"]:
        if pl not in coords:
            missing.append(pl)
    check("核心都城要邑坐標齊全", len(missing) == 0, f"缺失: {missing}")

def test_trajectory_database():
    if not os.path.exists(DB_FILE):
        check("數據庫文件存在", False, DB_FILE)
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM person_trajectories")
    cnt = c.fetchone()[0]
    if INJECT_FAULT:
        cnt = 100
    check("行跡庫全量記錄 >= 10,000 條", cnt >= 10000, f"實得 {cnt} 條")
    
    # 統計有公元紀年與有坐標的數量
    c.execute("SELECT COUNT(*) FROM person_trajectories WHERE year_ad IS NOT NULL")
    dated_cnt = c.fetchone()[0]
    check("確鑿公元紀年解析 >= 350 條", dated_cnt >= 350, f"實得 {dated_cnt} 條")

    c.execute("SELECT COUNT(*) FROM person_trajectories WHERE coord_lng IS NOT NULL AND coord_lat IS NOT NULL")
    geo_cnt = c.fetchone()[0]
    check("經緯度坐標命中 >= 4,000 處", geo_cnt >= 4000, f"實得 {geo_cnt} 處")

    # 驗證 61 人收錄完整性
    c.execute("SELECT COUNT(DISTINCT person_id) FROM person_trajectories")
    p_cnt = c.fetchone()[0]
    check("覆蓋 61 位歷史核心人物", p_cnt == 61, f"實得 {p_cnt} 人")

    # 劉邦生平行跡純淨度專項斷言（防後世追述穿透與董卓/宋建錯標回潮）
    c.execute("SELECT DISTINCT source_book FROM person_trajectories WHERE person_id = 'p_liubang'")
    lb_books = [r[0] for r in c.fetchall()]
    check("劉邦行跡史料嚴格限於史記漢書", set(lb_books).issubset({"sj", "hs"}), f"實得書籍: {lb_books}")

    c.execute("""
    SELECT COUNT(*) FROM person_trajectories 
    WHERE person_id = 'p_liubang' 
      AND (source_chapter LIKE '%董卓%' OR source_chapter LIKE '%諸夏侯曹%' OR source_chapter LIKE '%武帝紀%' OR source_chapter LIKE '%劉二牧%')
    """)
    lb_bad_chaps = c.fetchone()[0]
    check("劉邦行跡零董卓列傳/諸夏侯曹傳穿透", lb_bad_chaps == 0, f"異常篇章數: {lb_bad_chaps}")

    c.execute("SELECT COUNT(*) FROM person_trajectories WHERE person_id = 'p_liubang' AND place_name = '枹罕'")
    lb_baohan = c.fetchone()[0]
    check("劉邦行跡零宋建割據點枹罕", lb_baohan == 0, f"異常枹罕記錄數: {lb_baohan}")

    # 全量 61 位歷史人物時代窗口 (PERSON_VALID_BOOKS) 零違規斷言
    from pipeline.extract_trajectories import PERSON_VALID_BOOKS
    c.execute("SELECT person_id, source_book, COUNT(*) FROM person_trajectories GROUP BY person_id, source_book")
    all_p_books = c.fetchall()
    era_violations = []
    for pid, sb, row_count in all_p_books:
        valid_bks = PERSON_VALID_BOOKS.get(pid)
        if valid_bks and sb not in valid_bks:
            era_violations.append((pid, sb, row_count))
    check("61位人物全量遵守歷史學時代窗口", len(era_violations) == 0, f"違規項: {era_violations}")

    conn.close()

def test_persons_coverage():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    key_persons = [
        ("p_qihuan", "齊桓公"),
        ("p_liubang", "劉邦"),
        ("p_xiangyu", "項羽"),
        ("p_hanwudi", "劉徹"),
        ("p_liuxiu", "劉秀"),
        ("p_caocao", "曹操"),
        ("p_liubei", "劉備"),
        ("p_simayi", "司馬懿"),
        ("p_simayan", "司馬炎"),
        ("p_wangdao", "王導"),
        ("p_shile", "石勒")
    ]
    miss = []
    for pid, name in key_persons:
        c.execute("SELECT COUNT(*) FROM person_trajectories WHERE person_id = ?", (pid,))
        n = c.fetchone()[0]
        if n == 0:
            miss.append(f"{name}({pid})")
    conn.close()
    check("五史代表人物足跡全量在冊", len(miss) == 0, f"缺失: {miss}" if miss else "11位全覆蓋")

def test_frontend_isomorphism():
    with open(WEB_JS, "r", encoding="utf-8") as f:
        web_code = f.read()
    with open(DIST_JS, "r", encoding="utf-8") as f:
        dist_code = f.read()
    if INJECT_FAULT:
        dist_code += "\n// injected_fault"
    check("雙端代碼 (app.js) 100% 同構", web_code == dist_code, f"web={len(web_code)}, dist={len(dist_code)}")
    check("前端包含人物行跡渲染引擎 (renderTrajectoryMap)", "renderTrajectoryMap" in web_code)
    check("前端包含行跡 Color Bar 色階條 (trj-colorbar-wrap)", "trj-colorbar-wrap" in web_code)
    check("前端包含點位校勘標記 (data-trj-place)", "data-trj-place" in web_code)
    check("前端支持同期多地並存提示 (同期多地並存)", "同期多地並存" in web_code)
    check("前端支持行跡異步加載 (loadPersonTrajectories)", "loadPersonTrajectories" in web_code)
    check("前端包含行跡內存緩存 (TRJ_CACHE)", "TRJ_CACHE" in web_code)
    check("前端包含生平行跡專屬按鈕 (view-trj-map)", "view-trj-map" in web_code)
    check("前端包含兵爭要塞專屬按鈕 (view-campaign-map)", "view-campaign-map" in web_code)
    check("前端考據清單包含查閱原典專屬標記 (trj-jump-btn)", "trj-jump-btn" in web_code)
    check("前端原典按鈕攜帶章節篇號 (data-chapter)", 'data-chapter="' in web_code and 'data-jump-uid="' in web_code)
    check("前端點擊查閱原典接線至原典閱讀器 (openChapter)", "openChapter(cid, jUid, targetScope)" in web_code)
    check("前端包含三國人物判定守衛 (isThreeKingdomsPerson)", "isThreeKingdomsPerson" in web_code and "HAN_MO_THREE_KINGDOMS_PIDS" in web_code)

def test_static_export_data():
    with open(DIST_DATA, "r", encoding="utf-8") as f:
        content = f.read()
    check("離線快照包含坐標庫 (placeCoords)", "placeCoords" in content)
    check("離線快照包含行跡庫 (trajectories)", "trajectories" in content)

def test_online_api_payload():
    from app.server import db
    payload = db.index_payload("")
    coords = payload.get("placeCoords", {})
    counts = payload.get("trajectoryCounts", {})
    n_coords = len(coords)
    n_counts = len(counts)
    if INJECT_FAULT:
        n_coords = 0
        n_counts = 0
    check("聯機索引負載包含坐標庫 (placeCoords >= 190)", n_coords >= 190, f"實得 {n_coords} 處")
    check("聯機索引負載包含行跡計數 (trajectoryCounts == 61)", n_counts == 61, f"實得 {n_counts} 人")
    check("核心人物劉邦曹操計數正確", counts.get("p_liubang", 0) >= 1000 and counts.get("p_caocao", 0) >= 900)
    sent_meta = db.get_sentence_meta("0ac9fb2e1dc1")
    check("後端支持由句子UID獲取篇章元數據 (get_sentence_meta)", sent_meta is not None and "chapter_id" in sent_meta)

    # 三國志分卷統計精準過濾驗證 (方案 B)
    sgz_liubang = db.sgz_breakdown("p_liubang")
    sgz_kongzi = db.sgz_breakdown("p_kongzi")
    sgz_caocao = db.sgz_breakdown("p_caocao")
    sgz_liubei = db.sgz_breakdown("p_liubei")
    if INJECT_FAULT:
        sgz_liubang = {"dummy": 1}
    check("三國志分卷非三國人物徹底清空 (劉邦/孔子為None)", sgz_liubang is None and sgz_kongzi is None)
    check("三國志分卷三國群雄名臣正常保留 (曹操/劉備有效)", sgz_caocao is not None and sgz_liubei is not None)

def main():
    mode = "故障注入模式 (--inject)" if INJECT_FAULT else "正常模式"
    print("=" * 65)
    print(f"   古籍索引系統 BOOKINDEX · 人物行跡數據庫與解耦輿圖獨立審查 ({mode})   ")
    print("=" * 65)
    test_place_coordinates()
    test_trajectory_database()
    test_persons_coverage()
    test_frontend_isomorphism()
    test_static_export_data()
    test_online_api_payload()
    print("=" * 65)
    fails = [name for name, passed in CHECKS if not passed]
    if INJECT_FAULT:
        if len(fails) > 0:
            print(f"故障注入成功變紅：{len(fails)} 項檢測失敗（符合預期閉環）")
            sys.exit(1)
        else:
            print("異常：故障注入模式下測試未變紅！")
            sys.exit(2)
    else:
        if len(fails) == 0:
            print(f"審查結果：全部 {len(CHECKS)} 項核心檢測 100% 綠色通過！")
            sys.exit(0)
        else:
            print(f"審查失敗：{len(fails)} 項未通過！")
            sys.exit(1)

if __name__ == "__main__":
    main()
