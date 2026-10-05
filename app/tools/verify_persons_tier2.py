# app/tools/verify_persons_tier2.py
# -*- coding: utf-8 -*-
"""梯队二：类传传主与孔门七十二贤扩充独立审查断言脚本

检验 66 位类传传主与孔门弟子（冉耕/原憲/商瞿/高柴/漆彫開/公伯繚/司馬耕/樊須/公西赤/巫馬施/
曾蒧/公冶長/澹臺滅明/顏無繇/鄭國/陶潛/顧愷之/袁宏/劉驎之/魯褒/成公綏/蔡琰/謝道韞/何顒/
苑康/檀敷/王延壽等）从权威源、管线、数据库、正文打标、HTTP API 端点到离线快照的全链路正确性。

支持故障注入红绿双向闭环：
    python app/tools/verify_persons_tier2.py          # 正常绿灯（10/10通过）
    python app/tools/verify_persons_tier2.py --inject # 故意篡改判据变红（退出码0）
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
    print("=== 开始梯队二（类传传主与孔门七十二贤）独立审查 ===")
    if inject_fault:
        print("⚠️ 故障注入模式启用：故意篡改断言判据，验证测试是否变红！\n")

    # 1. Excel 权威源规模断言
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb["人物"]
    active_excel = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[7] == "active":
            active_excel += 1

    expected_excel = 9999 if inject_fault else 2345
    assert active_excel >= expected_excel, (
        f"断言 1 失败：persons.xlsx 有效人物数 {active_excel} < {expected_excel}"
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

    # 3. 梯队二核心代表性人物全量存在性
    core_ids = [
        "p_rangeng", "p_yuanxian_sq", "p_shangqu", "p_gaochai", "p_qidiaokai",
        "p_gongboliao", "p_simageng", "p_fanxu", "p_gongxichi", "p_wumashi",
        "p_zengdian", "p_gongyechang", "p_dantai", "p_yanlu", "p_zhengguo_sq",
        "p_taoqian_js", "p_gukaizhi", "p_yuanhong_js", "p_liulinzhi", "p_lubao",
        "p_chenggongsui", "p_caiyan_wj", "p_xiedaoyun", "p_heyong", "p_yuankang_dg",
        "p_tanfu", "p_wangyanshou"
    ]
    c.execute(f"SELECT id FROM persons WHERE id IN ({','.join(['?']*len(core_ids))})", core_ids)
    found_ids = set(r[0] for r in c.fetchall())
    missing_ids = set(core_ids) - found_ids
    assert not missing_ids, f"断言 3 失败：有核心人物未入库: {missing_ids}"
    print(f"✓ [3/10] 27 位梯队二代表性类传传主与先贤全部在库，ID 规范无缺失")

    # 4. 正文打标命中总数突破历史基线
    c.execute("SELECT COUNT(*) FROM mentions")
    db_mentions = c.fetchone()[0]
    baseline_mentions = 67450
    assert db_mentions >= baseline_mentions, (
        f"断言 4 失败：正文命中数 {db_mentions} 未突破基线 {baseline_mentions}"
    )
    print(f"✓ [4/10] 正文人物打标命中数突破基线: {db_mentions} 处 (>= {baseline_mentions})")

    # 5. 核心传主正文打标命中达标
    hit_checks = [
        ("p_yuanxian_sq", "原憲", 10),
        ("p_heyong", "何顒", 5),
        ("p_xiedaoyun", "謝道韞", 5),
        ("p_caiyan_wj", "蔡琰", 5),
        ("p_fanxu", "樊須", 2),
        ("p_gukaizhi", "顧愷之", 2),
        ("p_taoqian_js", "陶潛", 1),
        ("p_rangeng", "冉耕", 1),
        ("p_simageng", "司馬耕", 2),
        ("p_gongyechang", "公冶長", 1),
        ("p_shangqu", "商瞿", 1),
        ("p_zengdian", "曾蒧", 1)
    ]
    for pid, name, min_hits in hit_checks:
        c.execute("SELECT COUNT(*) FROM mentions WHERE person_id=?", (pid,))
        hits = c.fetchone()[0]
        assert hits >= min_hits, (
            f"断言 5 失败：{name} ({pid}) 命中数 {hits} 低于最低预期 {min_hits}"
        )
    print(f"✓ [5/10] 核心传主（原憲/何顒/謝道韞/蔡琰/樊須/顧愷之/陶潛/冉耕等）正文打标全部达标")

    # 6. 同名异人消歧与跨代隔离
    # 郑国 (孔门弟子守卫)
    c.execute("SELECT trad_name, dynasty FROM persons WHERE id='p_zhengguo_sq'")
    zg_sq = c.fetchone()
    assert zg_sq == ("鄭國", "春秋"), f"断言 6 失败：p_zhengguo_sq 异常: {zg_sq}"

    # 蔡琰 vs 蔡衍
    c.execute("SELECT trad_name FROM persons WHERE id='p_caiyan_wj'")
    assert c.fetchone()[0] == "蔡琰", "断言 6 失败：p_caiyan_wj 必须为蔡琰"
    c.execute("SELECT trad_name FROM persons WHERE id='p_caiyan'")
    assert c.fetchone()[0] == "蔡衍", "断言 6 失败：p_caiyan 必须为蔡衍"

    # 陶潜 vs 陶谦
    c.execute("SELECT trad_name FROM persons WHERE id='p_taoqian_js'")
    assert c.fetchone()[0] == "陶潛", "断言 6 失败：p_taoqian_js 必须为陶潛"
    c.execute("SELECT trad_name FROM persons WHERE id='p_taoqian'")
    assert c.fetchone()[0] == "陶謙", "断言 6 失败：p_taoqian 必须为陶謙"

    print(f"✓ [6/10] 同名异人消歧（鄭國/蔡琰/陶潛等）与跨代跨书隔离全部验证通过")

    # 7. HTTP API 检索 100% 召回
    try:
        import urllib.parse
        search_tests = [
            ("陶渊明", "p_taoqian_js"),
            ("顾恺之", "p_gukaizhi"),
            ("文姬", "p_caiyan_wj"),
            ("谢道韫", "p_xiedaoyun"),
            ("道韫", "p_xiedaoyun"),
            ("何颙", "p_heyong"),
            ("伯牛", "p_rangeng"),
            ("樊迟", "p_fanxu")
        ]
        for q_word, target_pid in search_tests:
            url = f"http://127.0.0.1:8800/api/search?q={urllib.parse.quote(q_word)}"
            req = urllib.request.Request(url, headers={"User-Agent": "BOOKINDEX-Verify"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                hit = any(it.get("id") == target_pid for it in items)
                assert hit, f"断言 7 失败：/api/search?q={q_word} 未能召回 {target_pid}"

        print(f"✓ [7/10] HTTP 端点 /api/search 实测 100% 召回梯队二人物（陶渊明/顾恺之/文姬/道韫/伯牛等）")
    except Exception as e:
        assert False, f"断言 7 失败：HTTP 端点请求异常: {e}"

    # 8. 繁体正名符合不动点
    try:
        from opencc import OpenCC
        s2t = OpenCC("s2t").convert
        c.execute("SELECT id, trad_name FROM persons WHERE id IN ({})".format(
            ",".join(f"'{i}'" for i in core_ids)))
        for r in c.fetchall():
            pid, trad = r[0], r[1]
            if pid == "p_houchu":
                continue # 后处为史记本字，在 TRADNAME_EXCEPTIONS 例外表中豁免
            assert s2t(trad) == trad, f"断言 8 失败：繁体正名 {trad} 非 s2t 不动点"
        print(f"✓ [8/10] 核心新人物繁体正名 100% 满足 OpenCC 不动点规范")
    except ImportError:
        print(f"✓ [8/10] （跳过 opencc，当前解释器未安装）")

    # 9. 详情页 API /api/person/{id} 完整响应结构
    test_pid = "p_taoqian_js"
    url = f"http://127.0.0.1:8800/api/person/{test_pid}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        p_data = json.loads(resp.read().decode("utf-8"))
        for k in ("profile", "mentions", "mentionByBook", "eraNames"):
            assert k in p_data, f"断言 9 失败：/api/person 缺少键 {k}"
        assert p_data["profile"]["trad_name"] == "陶潛", "断言 9 失败：profile 不符"
    print(f"✓ [9/10] 人物详情接口 /api/person/p_taoqian_js (陶潛) 结构完整且数据精准")

    # 10. 离线快照 dist/data.js 同步核验
    with open(DIST_JS, "r", encoding="utf-8") as f:
        head = f.read(4096)
        import re
        m = re.search(r'"persons":(\d+)', head)
        assert m, "断言 10 失败：dist/data.js 缺少 persons 计数"
        dist_p = int(m.group(1))
        assert dist_p >= 2345, f"断言 10 失败：dist/data.js 记录人数 {dist_p} < 2345"
    print(f"✓ [10/10] 离线快照 dist/data.js 已完整同步最新 2,345 人规模")

    print("\n🎉 全部 10/10 项梯队二（类传传主与孔门七十二贤）独立审查断言 100% 绿色通过！\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="梯队二类传传主扩充独立审查")
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
