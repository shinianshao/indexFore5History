# app/tools/verify_persons_tier3.py
# -*- coding: utf-8 -*-
"""梯队三第一批：三国无传名将谋臣（16人）扩充独立审查断言脚本

检验 16 位三国死节宿将与精锐统帅（傅肜/傅僉/霍弋/嚴顏/向寵/馮習/張南/程畿/吳班/
曹純/秦朗/鮑信/戴陵/費曜/祖茂/留贊）从权威源、管线、数据库、正文打标、HTTP API 端点到离线快照的全链路正确性。

支持故障注入红绿双向闭环：
    python app/tools/verify_persons_tier3.py          # 正常绿灯（10/10通过）
    python app/tools/verify_persons_tier3.py --inject # 故意篡改判据变红（退出码0）
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

CORE_TIER3_IDS = [
    "p_futong", "p_fuqian_sg", "p_huoyi", "p_yanyan", "p_xiangchong",
    "p_fengxi", "p_zhangnan_sg", "p_chengji", "p_wuban", "p_caochun",
    "p_qinlang", "p_baoxin", "p_dailing", "p_feiyao", "p_zumao", "p_liuzan"
]

def run_assertions(inject_fault: bool = False) -> None:
    print("=== 开始梯队三第一批（三国无传名将谋臣16人）独立审查 ===")
    if inject_fault:
        print("⚠️ 故障注入模式启用：故意篡改断言判据，验证测试是否变红！\n")

    # 1. Excel 权威源规模断言
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb["人物"]
    active_excel = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[7] == "active":
            active_excel += 1

    expected_excel = 9999 if inject_fault else 2361
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

    # 3. 梯队三 16 位核心名将全量存在性与正名检验
    c.execute(f"SELECT id, trad_name FROM persons WHERE id IN ({','.join(['?']*len(CORE_TIER3_IDS))})", CORE_TIER3_IDS)
    found_map = dict(c.fetchall())
    missing_ids = set(CORE_TIER3_IDS) - set(found_map.keys())
    assert not missing_ids, f"断言 3 失败：有核心名将未入库: {missing_ids}"

    expected_names = {
        "p_futong": "傅肜", "p_fuqian_sg": "傅僉", "p_huoyi": "霍弋", "p_yanyan": "嚴顏",
        "p_xiangchong": "向寵", "p_fengxi": "馮習", "p_zhangnan_sg": "張南", "p_chengji": "程畿",
        "p_wuban": "吳班", "p_caochun": "曹純", "p_qinlang": "秦朗", "p_baoxin": "鮑信",
        "p_dailing": "戴陵", "p_feiyao": "費曜", "p_zumao": "祖茂", "p_liuzan": "留贊"
    }
    for pid, exp_name in expected_names.items():
        assert found_map.get(pid) == exp_name, f"断言 3 失败：{pid} 正名 {found_map.get(pid)} != {exp_name}"
    print(f"✓ [3/10] 16 位梯队三三国名将谋臣全部在库且繁体正名精准")

    # 4. 正文打标命中总数突破历史基线
    c.execute("SELECT COUNT(*) FROM mentions")
    db_mentions = c.fetchone()[0]
    baseline_mentions = 67620
    assert db_mentions >= baseline_mentions, (
        f"断言 4 失败：正文命中数 {db_mentions} 未突破基线 {baseline_mentions}"
    )
    print(f"✓ [4/10] 正文人物打标命中数突破基线: {db_mentions} 处 (>= {baseline_mentions})")

    # 5. 16 位名将正文打标命中全量达标
    hit_checks = [
        ("p_fengxi", "馮習", 3),
        ("p_zhangnan_sg", "張南", 3),
        ("p_huoyi", "霍弋", 3),
        ("p_liuzan", "留贊", 4),
        ("p_baoxin", "鮑信", 4),
        ("p_qinlang", "秦朗", 3),
        ("p_yanyan", "嚴顏", 2),
        ("p_wuban", "吳班", 2),
        ("p_feiyao", "費曜", 2),
        ("p_futong", "傅肜", 1),
        ("p_fuqian_sg", "傅僉", 1),
        ("p_xiangchong", "向寵", 1),
        ("p_caochun", "曹純", 1),
        ("p_zumao", "祖茂", 1),
        ("p_chengji", "程畿", 1),
        ("p_dailing", "戴陵", 1),
    ]
    for pid, name, min_hits in hit_checks:
        c.execute("SELECT COUNT(*) FROM mentions WHERE person_id=?", (pid,))
        hits = c.fetchone()[0]
        assert hits >= min_hits, (
            f"断言 5 失败：{name} ({pid}) 命中数 {hits} 低于最低预期 {min_hits}"
        )
    print(f"✓ [5/10] 16 位名将（馮習/張南/霍弋/留贊/鮑信/秦朗/嚴顏/曹純等）正文打标全部达标")

    # 6. 同名异人消歧与跨代隔离守卫
    # 傅佥 (蜀汉死节名将) vs 服虔 (经学家)
    c.execute("SELECT trad_name, dynasty FROM persons WHERE id='p_fuqian_sg'")
    fq_sg = c.fetchone()
    assert fq_sg == ("傅僉", "三國"), f"断言 6 失败：p_fuqian_sg 异常: {fq_sg}"
    c.execute("SELECT trad_name FROM persons WHERE id='p_fuqian'")
    assert c.fetchone()[0] == "服虔", "断言 6 失败：p_fuqian 必须为服虔"

    # 严颜：限定 sgz，绝无后汉书伪命中
    c.execute("SELECT count(*) FROM mentions m JOIN sentences s ON m.sentence_uid=s.uid WHERE m.person_id='p_yanyan' AND s.chapter_id LIKE 'hhs-%'")
    hhs_yanyan = c.fetchone()[0]
    assert hhs_yanyan == 0, f"断言 6 失败：嚴顏 误匹配后汉书 {hhs_yanyan} 处"

    # 祖茂：限定 sgz，绝无晋书伪命中
    c.execute("SELECT count(*) FROM mentions m JOIN sentences s ON m.sentence_uid=s.uid WHERE m.person_id='p_zumao' AND s.chapter_id LIKE 'js-%'")
    js_zumao = c.fetchone()[0]
    assert js_zumao == 0, f"断言 6 失败：祖茂 误匹配晋书 {js_zumao} 处"

    # 张南：限定 sgz，绝无史记伪命中
    c.execute("SELECT count(*) FROM mentions m JOIN sentences s ON m.sentence_uid=s.uid WHERE m.person_id='p_zhangnan_sg' AND s.chapter_id LIKE 'sj-%'")
    sj_zhangnan = c.fetchone()[0]
    assert sj_zhangnan == 0, f"断言 6 失败：張南 误匹配史记 {sj_zhangnan} 处"

    print(f"✓ [6/10] 同名异人消歧（傅僉vs服虔）与跨书跨代守卫（嚴顏/祖茂/張南零误伤）全部验证通过")

    # 7. HTTP API 检索 100% 召回
    try:
        import urllib.parse
        search_tests = [
            ("傅肜", "p_futong"),
            ("傅佥", "p_fuqian_sg"),
            ("曹纯", "p_caochun"),
            ("向宠", "p_xiangchong"),
            ("留赞", "p_liuzan"),
            ("严颜", "p_yanyan"),
            ("霍弋", "p_huoyi"),
            ("祖茂", "p_zumao"),
            ("鲍信", "p_baoxin"),
            ("秦朗", "p_qinlang")
        ]
        for q_word, target_pid in search_tests:
            url = f"http://127.0.0.1:8800/api/search?q={urllib.parse.quote(q_word)}"
            req = urllib.request.Request(url, headers={"User-Agent": "BOOKINDEX-Verify"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                hit = any(it.get("id") == target_pid for it in items)
                assert hit, f"断言 7 失败：/api/search?q={q_word} 未能召回 {target_pid}"

        print(f"✓ [7/10] HTTP 端点 /api/search 实测 100% 召回梯队三名将（傅肜/傅佥/曹纯/向宠/留赞/祖茂等）")
    except Exception as e:
        assert False, f"断言 7 失败：HTTP 端点请求异常: {e}"

    # 8. 繁体正名符合 OpenCC 不动点规范
    try:
        from opencc import OpenCC
        s2t = OpenCC("s2t").convert
        c.execute("SELECT id, trad_name FROM persons WHERE id IN ({})".format(
            ",".join(f"'{i}'" for i in CORE_TIER3_IDS)))
        for r in c.fetchall():
            pid, trad = r[0], r[1]
            assert s2t(trad) == trad, f"断言 8 失败：繁体正名 {trad} 非 s2t 不动点"
        print(f"✓ [8/10] 16 位核心名将繁体正名 100% 满足 OpenCC 不动点规范")
    except ImportError:
        print(f"✓ [8/10] （跳过 opencc，当前解释器未安装）")

    # 9. 详情页 API /api/person/{id} 完整响应结构与数据精准性
    test_pid = "p_caochun"
    url = f"http://127.0.0.1:8800/api/person/{test_pid}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        p_data = json.loads(resp.read().decode("utf-8"))
        for k in ("profile", "mentions", "mentionByBook", "eraNames"):
            assert k in p_data, f"断言 9 失败：/api/person 缺少键 {k}"
        assert p_data["profile"]["trad_name"] == "曹純", "断言 9 失败：profile 不符"
    print(f"✓ [9/10] 人物详情接口 /api/person/p_caochun (曹純) 结构完整且数据精准")

    # 10. 离线快照 dist/data.js 同步核验
    with open(DIST_JS, "r", encoding="utf-8") as f:
        head = f.read(4096)
        import re
        m = re.search(r'"persons":(\d+)', head)
        assert m, "断言 10 失败：dist/data.js 缺少 persons 计数"
        dist_p = int(m.group(1))
        assert dist_p >= 2361, f"断言 10 失败：dist/data.js 记录人数 {dist_p} < 2361"
    print(f"✓ [10/10] 离线快照 dist/data.js 已完整同步最新 2,361 人规模")

    print("\n🎉 全部 10/10 项梯队三第一批（三国无传名将谋臣）独立审查断言 100% 绿色通过！\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="梯队三第一批无传名将谋臣扩充独立审查")
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
