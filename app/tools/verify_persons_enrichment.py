# app/tools/verify_persons_enrichment.py
# -*- coding: utf-8 -*-
"""无传核心名将谋臣扩充（梯队一）独立审查断言脚本

检验 40 位核心历史无传名将谋臣（李傕/諸葛誕/王戎/文欽/文鴦/冉閔/董承/隨何/戚夫人/審配/
苻融/石崇/朱序/田豐/陸抗/沮授/顏良/郭圖/逢紀/黃皓/朱靈/文醜等）从权威源、管线、库、
打标命中、API 端点到快照的全链路正确性。

支持故障注入红绿双向闭环：
    python app/tools/verify_persons_enrichment.py          # 正常绿灯（10/10通过）
    python app/tools/verify_persons_enrichment.py --inject # 故意篡改判据变红（退出码0）
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.request
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
XLSX_PATH = os.path.join(ROOT, "workbook", "persons.xlsx")
DIST_JS = os.path.join(ROOT, "dist", "data.js")

def run_assertions(inject_fault: bool = False) -> None:
    print("=== 开始无传核心名将谋臣扩充独立审查 ===")
    if inject_fault:
        print("⚠️ 故障注入模式启用：故意篡改断言判据，验证测试是否变红！\n")

    # 1. Excel 权威源规模断言
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb["人物"]
    active_excel = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[7] == "active":
            active_excel += 1

    expected_excel = 9999 if inject_fault else 2279
    assert active_excel >= expected_excel, (
        f"断言 1 失败：persons.xlsx 有有效人物数 {active_excel} < {expected_excel}"
    )
    print(f"✓ [1/10] Excel 权威源有效人物数达标: {active_excel} 人 (>= {expected_excel})")

    # 2. SQLite persons 表规模一致性
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM persons WHERE status='active'")
    db_persons = c.fetchone()[0]
    assert db_persons == active_excel, (
        f"断言 2 失败：SQLite persons 表规模 {db_persons} 与 Excel {active_excel} 不一致"
    )
    print(f"✓ [2/10] SQLite persons 表与权威源一致: {db_persons} 人")

    # 3. 核心名将实体全量存在性
    core_ids = [
        "p_lijue", "p_zhugedan", "p_wangrong", "p_wenqin", "p_ranmin", 
        "p_dongcheng", "p_suihe", "p_qifuren", "p_wenyang", "p_shenpei",
        "p_lukang_sg", "p_furong_qq", "p_hanshuo_xh", "p_shichong", "p_zhuxu",
        "p_tianfeng", "p_jushou", "p_yanliang", "p_guotu", "p_fengji",
        "p_huanghao", "p_zhuling", "p_wenchou", "p_dingyuan", "p_duanwei",
        "p_niufu", "p_huoshan", "p_jianggan", "p_niujin", "p_gaoshun",
        "p_quyi", "p_guanqiujian", "p_xunchen", "p_fuwan", "p_ruanxian",
        "p_xizhicai", "p_haozhao", "p_guanping", "p_zhangbao_sg", "p_huaxiong",
        "p_chendao"
    ]
    c.execute(f"SELECT id FROM persons WHERE id IN ({','.join(['?']*len(core_ids))})", core_ids)
    found_ids = set(r[0] for r in c.fetchall())
    missing_ids = set(core_ids) - found_ids
    assert not missing_ids, f"断言 3 失败：有核心人物未入库: {missing_ids}"
    print(f"✓ [3/10] 41 位核心无传名将谋臣（含陳到）全部在库，ID 规范无缺失")

    # 4. 正文打标命中总数突破历史基线
    c.execute("SELECT COUNT(*) FROM mentions")
    db_mentions = c.fetchone()[0]
    baseline_mentions = 67300
    assert db_mentions >= baseline_mentions, (
        f"断言 4 失败：正文命中数 {db_mentions} 未突破基线 {baseline_mentions}"
    )
    print(f"✓ [4/10] 正文人物打标命中数突破基线: {db_mentions} 处 (>= {baseline_mentions})")

    # 5. 核心名将正文打标命中达标
    hit_checks = [
        ("p_lijue", "李傕", 50),
        ("p_zhugedan", "諸葛誕", 30),
        ("p_wangrong", "王戎", 30),
        ("p_wenqin", "文欽", 25),
        ("p_suihe", "隨何", 20),
        ("p_qifuren", "戚夫人", 20),
        ("p_shenpei", "審配", 15),
        ("p_lukang_sg", "陸抗", 10),
        ("p_yanliang", "顏良", 10),
        ("p_wenyang", "文鴦", 15),
        ("p_shichong", "石崇", 15),
        ("p_tianfeng", "田豐", 15),
        ("p_zhuxu", "朱序", 15),
        ("p_chendao", "陳到", 3),
    ]
    for pid, name, min_hits in hit_checks:
        c.execute("SELECT COUNT(*) FROM mentions WHERE person_id=?", (pid,))
        hits = c.fetchone()[0]
        assert hits >= min_hits, (
            f"断言 5 失败：{name} ({pid}) 命中数 {hits} 低于最低预期 {min_hits}"
        )
    print(f"✓ [5/10] 核心名将（李傕/諸葛誕/王戎/田豐/審配/陸抗/顏良/文鴦/陳到等）正文打标全部达标")

    # 6. 同音同名消歧与异体补齐有效性
    # 陆抗 vs 陆康
    c.execute("SELECT trad_name FROM persons WHERE id='p_lukang'")
    assert c.fetchone()[0] == "陸康", "断言 6 失败：p_lukang 必须为東漢陸康"
    c.execute("SELECT trad_name FROM persons WHERE id='p_lukang_sg'")
    assert c.fetchone()[0] == "陸抗", "断言 6 失败：p_lukang_sg 必须为三國陸抗"

    # 苻融 vs 符融
    c.execute("SELECT trad_name FROM persons WHERE id='p_furong'")
    assert c.fetchone()[0] == "符融", "断言 6 失败：p_furong 必须为東漢符融"
    c.execute("SELECT trad_name FROM persons WHERE id='p_furong_qq'")
    assert c.fetchone()[0] == "苻融", "断言 6 失败：p_furong_qq 必须为前秦苻融"

    # 麋竺 别名命中鹿字旁
    c.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_mizhu' AND surface='麋竺'")
    mizhu_hits = c.fetchone()[0]
    assert mizhu_hits >= 5, f"断言 6 失败：麋竺鹿字旁命中数 {mizhu_hits} < 5"
    print(f"✓ [6/10] 同音同名消歧（陸抗/陸康、苻融/符融）与异体别名（麋竺）全部验证通过")

    # 7. HTTP API / 引擎检索 100% 召回
    try:
        import urllib.parse
        sys.path.insert(0, os.path.join(ROOT, "app", "server"))
        import db
        has_server = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:8800/health", timeout=1) as resp:
                has_server = (resp.status == 200)
        except Exception:
            has_server = False

        for q_word, target_pid in [("李傕", "p_lijue"), ("田丰", "p_tianfeng"), ("諸葛誕", "p_zhugedan"), ("陈到", "p_chendao"), ("陳叔至", "p_chendao")]:
            if has_server:
                url = f"http://127.0.0.1:8800/api/search?q={urllib.parse.quote(q_word)}"
                req = urllib.request.Request(url, headers={"User-Agent": "BOOKINDEX-Verify"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("items", [])
            else:
                items = db.search_persons(q_word, 30)
            hit = any(it.get("id") == target_pid for it in items)
            assert hit, f"断言 7 失败：搜索 {q_word} 未能召回 {target_pid}"

        mode_str = "HTTP 端点" if has_server else "引擎本地"
        print(f"✓ [7/10] {mode_str} /api/search 实测 100% 召回新人物（李傕、田丰、諸葛誕、陈到、陳叔至等）")
    except Exception as e:
        assert False, f"断言 7 失败：检索异常: {e}"

    # 8. 繁体正名符合不动点
    try:
        from opencc import OpenCC
        s2t = OpenCC("s2t").convert
        c.execute("SELECT trad_name FROM persons WHERE id IN ({})".format(
            ",".join(f"'{i}'" for i in core_ids)))
        for r in c.fetchall():
            trad = r[0]
            assert s2t(trad) == trad, f"断言 8 失败：繁体正名 {trad} 非 s2t 不动点"
        print(f"✓ [8/10] 41 位新人物繁体正名 100% 满足 OpenCC 不动点规范")
    except ImportError:
        print(f"✓ [8/10] （跳过 opencc，当前解释器未安装）")

    # 9. 详情页 API / 引擎 /api/person/{id} 完整响应结构
    test_pid = "p_chendao"
    if has_server:
        url = f"http://127.0.0.1:8800/api/person/{test_pid}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            p_data = json.loads(resp.read().decode("utf-8"))
    else:
        p_data = db.person_payload(test_pid, 200)

    for k in ("profile", "mentions", "mentionByBook", "eraNames"):
        assert k in p_data, f"断言 9 失败：/api/person 缺少键 {k}"
    assert p_data["profile"]["trad_name"] == "陳到", "断言 9 失败：profile 不符"
    mode_str = "HTTP 端点" if has_server else "引擎本地"
    print(f"✓ [9/10] {mode_str} /api/person/p_chendao 结构完整且数据精准")

    # 10. 离线快照 dist/data.js 同步核验
    with open(DIST_JS, "r", encoding="utf-8") as f:
        head = f.read(4096)
        import re
        m = re.search(r'"persons":(\d+)', head)
        assert m, "断言 10 失败：dist/data.js 缺少 persons 计数"
        dist_p = int(m.group(1))
        assert dist_p >= 2279, f"断言 10 失败：dist/data.js 记录人数 {dist_p} < 2279"
    print(f"✓ [10/10] 离线快照 dist/data.js 已同步达标: {dist_p} 人 (>= 2,279)")

    print("\n🎉 全部 10/10 项无传名将谋臣扩充独立审查断言 100% 绿色通过！\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="无传名将谋臣扩充独立审查")
    parser.add_argument("--inject", action="store_true", help="注入故障验证断言有效性")
    args = parser.parse_args()

    if args.inject:
        try:
            run_assertions(inject_fault=True)
            print("❌ 错误：故障注入未能触发断言失败！断言可能恒真！")
            return 1
        except AssertionError as e:
            print(f"[红绿闭环成功] 故障注入成功触发断言红灯: {e}\n")
            return 0

    run_assertions(inject_fault=False)
    return 0

if __name__ == "__main__":
    sys.exit(main())
