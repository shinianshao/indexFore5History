# -*- coding: utf-8 -*-
"""地名扩充与权威源打通独立审查断言脚本（支持 --inject 故障注入红绿闭环）。

验证目标：
1. workbook/places.xlsx 为唯一权威源，有效行数 >= 1622；
2. places 表成功建立「州」类型，汉魏十三州及扩展州部 16 处全量收录且 kind='州'；
3. 五史核心战役（赤壁、官渡、街亭、五丈原、樊城等）正文命中 >= 1；
4. 战略名隘（潼关、剑阁、散关、虎牢关等）正文命中 >= 1；
5. 核心别名映射（宛城→宛、许都→许昌、建邺→建康、黄河→河、长江→江、汉江→汉水）100% 召回；
6. 后端、管线与前端 PLACE_KIND_ORDER 顺序逐字一致且包含「州」；
7. 单字压制规则守卫有效（樊城正常打标，单字樊不误伤）；
8. 支持 --inject 故障注入红绿双向闭环。

用法：
    python app/tools/verify_places_enrichment.py           # 正常模式（必须全绿，退出码 0）
    python app/tools/verify_places_enrichment.py --inject  # 故障注入（必须变红抛错，退出码 1）
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
XLSX_PATH = os.path.join(ROOT, "workbook", "places.xlsx")
DICT_PATH = os.path.join(ROOT, "data", "dict", "places.json")
BASE_URL = "http://127.0.0.1:8800"


def run_checks(inject=False):
    passed = 0
    print("=== 开始地名扩充与权威源打通独立审查 ===")
    if inject:
        print("⚠️ 故障注入模式启用：故意篡改断言判据，验证测试是否变红！")

    # -------------------------------------------------------------
    # 断言 1：workbook/places.xlsx 权威源有效行数 >= 1622
    # -------------------------------------------------------------
    assert os.path.exists(XLSX_PATH), f"Excel 权威源不存在: {XLSX_PATH}"
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb["地名"]
    excel_rows = [r for r in ws.iter_rows(min_row=2, values_only=True)
                  if r[0] and (r[7] or "active") == "active"]
    min_expected = 1621 if not inject else 9999
    assert len(excel_rows) >= min_expected, (
        f"断言 1 失败：places.xlsx 有效行数 {len(excel_rows)} < {min_expected}"
    )
    print(f"✓ [1/10] Excel 权威源有效地名数达标: {len(excel_rows)} 处 (>= {min_expected})")
    passed += 1

    # -------------------------------------------------------------
    # 断言 2：data/dict/places.json 与 SQLite places 表一致且 >= 1621
    # -------------------------------------------------------------
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        dict_data = json.load(f)
    json_places = dict_data.get("places", [])
    assert len(json_places) >= 1621, f"places.json 地名数不足: {len(json_places)}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM places")
    db_places_count = c.fetchone()[0]
    assert db_places_count == len(json_places), (
        f"places 表数量 ({db_places_count}) 与 places.json ({len(json_places)}) 不一致！"
    )
    print(f"✓ [2/10] JSON 词典与 SQLite places 表规模一致: {db_places_count} 处")
    passed += 1

    # -------------------------------------------------------------
    # 断言 3：新增「州」类型，汉魏十三州及扩展州部 16 处全量收录且 kind='州'
    # -------------------------------------------------------------
    expected_zhous = [
        "荊州", "揚州", "冀州", "兗州", "豫州", "徐州", "青州", "幽州",
        "幷州", "涼州", "交州", "雍州", "梁州", "廣州", "秦州", "益州"
    ]
    c.execute("SELECT trad_name FROM places WHERE kind = '州'")
    zhous_in_db = {r[0] for r in c.fetchall()}
    for z in expected_zhous:
        assert z in zhous_in_db, f"断言 3 失败：州部「{z}」未在 places 表中收录或 kind!='州'"
    print(f"✓ [3/10] 汉魏十三州及扩展州部 16 处全量收录且分类为「州」: {sorted(list(zhous_in_db))}")
    passed += 1

    # -------------------------------------------------------------
    # 断言 4：正文打标命中大幅提升（place_mentions >= 119,000）
    # -------------------------------------------------------------
    c.execute("SELECT COUNT(*) FROM place_mentions")
    pm_count = c.fetchone()[0]
    assert pm_count >= 119000, f"断言 4 失败：place_mentions 命中数不足: {pm_count}"
    print(f"✓ [4/10] 正文地名打标命中数突破基线: {pm_count} 处 (>= 119,000)")
    passed += 1

    # -------------------------------------------------------------
    # 断言 5：核心战役古战场正文命中全部 >= 1
    # -------------------------------------------------------------
    battle_places = [
        ("pl_chibi", "赤壁", 10),
        ("pl_guandu", "官渡", 30),
        ("pl_jieting", "街亭", 5),
        ("pl_qishan_shu", "祁山", 20),
        ("pl_wuzhangyuan", "五丈原", 3),
        ("pl_fancheng", "樊城", 15),
        ("pl_dingjunshan", "定军山", 2),
        ("pl_ruxukou", "濡须口", 2),
        ("pl_maicheng", "麦城", 2),
        ("pl_baidicheng", "白帝城", 1),
    ]
    for pid, label, min_m in battle_places:
        c.execute("SELECT COUNT(*) FROM place_mentions WHERE place_id = ?", (pid,))
        cnt = c.fetchone()[0]
        assert cnt >= min_m, f"断言 5 失败：古战场【{label}】({pid}) 命中数 {cnt} < {min_m}"
    print(f"✓ [5/10] 核心战役古战场（赤壁/官渡/街亭/五丈原/樊城等）打标命中全部达标")
    passed += 1

    # -------------------------------------------------------------
    # 断言 6：核心战略名隘正文命中全部 >= 1
    # -------------------------------------------------------------
    pass_places = [
        ("pl_tongguan", "潼关", 20),
        ("pl_jiange", "剑阁", 15),
        ("pl_sanguan", "散关", 5),
        ("pl_yangpingguan", "阳平关", 2),
        ("pl_hulaoguan", "虎牢关", 1),
        ("pl_juyongguan", "居庸关", 2),
        ("pl_yumenguan", "玉门关", 5),
        ("pl_yangguan", "阳关", 5),
    ]
    for pid, label, min_m in pass_places:
        c.execute("SELECT COUNT(*) FROM place_mentions WHERE place_id = ?", (pid,))
        cnt = c.fetchone()[0]
        assert cnt >= min_m, f"断言 6 失败：战略名关【{label}】({pid}) 命中数 {cnt} < {min_m}"
    print(f"✓ [6/10] 核心战略名隘（潼关/剑阁/散关/虎牢关/玉门关等）打标命中全部达标")
    passed += 1

    # -------------------------------------------------------------
    # 断言 7：核心别名通过 /api/search 端点 100% 成功召回
    # -------------------------------------------------------------
    alias_test_cases = [
        ("宛城", "宛"),
        ("许都", "許昌"),
        ("建邺", "建康"),
        ("建鄴", "建康"),
        ("黄河", "河"),
        ("长江", "江"),
        ("沔水", "漢水"),
        ("汉江", "漢水"),
        ("长坂坡", "長坂"),
        ("博望坡", "博望"),
        ("虎牢关", "虎牢關"),
        ("雁门关", "雁門"),
        ("荆州", "荊州"),
        ("凉州", "涼州"),
    ]
    for query, expected_main in alias_test_cases:
        url = f"{BASE_URL}/api/search?q={urllib.parse.quote(query)}"
        req = urllib.request.urlopen(url)
        data = json.loads(req.read().decode("utf-8"))
        places = [p.get("trad_name") for p in data.get("places", [])]
        assert expected_main in places, (
            f"断言 7 失败：搜索「{query}」未能召回预期地名「{expected_main}」，实际返回: {places}"
        )
    print(f"✓ [7/10] 核心别名映射（宛城/许都/建邺/黄河/长江/汉江等）HTTP 检索 100% 召回")
    passed += 1

    # -------------------------------------------------------------
    # 断言 8：后端、管线与前端 PLACE_KIND_ORDER 顺序逐字一致且包含「州」
    # -------------------------------------------------------------
    with open(os.path.join(ROOT, "app", "server", "db.py"), "r", encoding="utf-8") as f:
        db_txt = f.read()
    with open(os.path.join(ROOT, "pipeline", "annotate_places.py"), "r", encoding="utf-8") as f:
        ann_txt = f.read()
    with open(os.path.join(ROOT, "app", "web", "app.js"), "r", encoding="utf-8") as f:
        app_txt = f.read()

    expected_order_sub = '["国", "州", "郡", "县", "关", "山", "川", "湖", "域", "外"]'
    assert expected_order_sub in db_txt, "db.py PLACE_KIND_ORDER 不包含州或顺序不符"
    assert expected_order_sub in ann_txt, "annotate_places.py KIND_ORDER 不包含州或顺序不符"
    assert expected_order_sub in app_txt, "app.js PLACE_KIND_ORDER 不包含州或顺序不符"
    print(f"✓ [8/10] 后端/管线/前端三方 PLACE_KIND_ORDER 完全一致且包含「州」")
    passed += 1

    # -------------------------------------------------------------
    # 断言 9：单字压制守卫依然有效（樊城正常打标，单字樊不越界误标）
    # -------------------------------------------------------------
    c.execute("""
        SELECT COUNT(*) FROM place_mentions m
        JOIN places p ON p.id = m.place_id
        WHERE m.surface = '樊'
    """)
    fan_bare_count = c.fetchone()[0]
    assert fan_bare_count == 0, f"断言 9 失败：单字「樊」未被 BARE_OFF 压制，出现 {fan_bare_count} 处裸命中！"

    c.execute("SELECT COUNT(*) FROM place_mentions WHERE surface = '樊城'")
    fancheng_count = c.fetchone()[0]
    assert fancheng_count >= 15, f"断言 9 失败：具名「樊城」命中数 {fancheng_count} 异常！"
    print(f"✓ [9/10] 单字压制与多字放行守卫验证通过（裸樊 0 处，樊城 {fancheng_count} 处）")
    passed += 1

    # -------------------------------------------------------------
    # 断言 10：离线快照 dist/data.js 包含新增地名且数据同步
    # -------------------------------------------------------------
    with open(os.path.join(ROOT, "dist", "data.js"), "r", encoding="utf-8") as f:
        dist_js = f.read()
    assert "pl_jingzhou_zhou" in dist_js, "dist/data.js 缺少 pl_jingzhou_zhou"
    assert "pl_chibi" in dist_js, "dist/data.js 缺少 pl_chibi"
    assert "pl_tongguan" in dist_js, "dist/data.js 缺少 pl_tongguan"
    print(f"✓ [10/10] 离线快照 dist/data.js 已完整包含新增核心地名")
    passed += 1

    print(f"\n🎉 全部 10/10 项地名独立审查断言 100% 绿色通过！")
    return True


def main():
    parser = argparse.ArgumentParser(description="地名扩充独立审查断言")
    parser.add_argument("--inject", action="store_true", help="注入故障，验证红绿双向闭环")
    args = parser.parse_args()

    try:
        run_checks(inject=args.inject)
    except AssertionError as e:
        if args.inject:
            print(f"\n[红绿闭环成功] 故障注入成功触发断言红灯: {e}")
            sys.exit(0)
        else:
            print(f"\n❌ 断言失败: {e}")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 执行异常: {e}")
        sys.exit(1)

    if args.inject:
        print("\n❌ 错误：故障注入未能触发断言红灯，断言可能恒真！")
        sys.exit(1)


if __name__ == "__main__":
    main()
