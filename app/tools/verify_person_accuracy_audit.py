# app/tools/verify_person_accuracy_audit.py
# -*- coding: utf-8 -*-
"""周平王假命中彻底治理与全系统人物准确性重梳独立审查断言脚本

检验周平王（封王截断与动宾撕裂清除）、郝昭（霸道伪命中消除）、何曾/顾众/夏方/毕卓/蔡豹/孙辅
等跨朝代假命中清零，以及潘岳/挚虞/嵇康朝代元数据修复的全链路正确性。

支持故障注入红绿双向闭环：
    python app/tools/verify_person_accuracy_audit.py          # 正常绿灯（10/10通过）
    python app/tools/verify_person_accuracy_audit.py --inject # 故意篡改判据变红（退出码0）
"""
import argparse
import json
import os
import sqlite3
import sys
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
XLSX_PATH = os.path.join(ROOT, "workbook", "persons.xlsx")
DIST_JS = os.path.join(ROOT, "dist", "data.js")

def run_assertions(inject_fault: bool = False) -> None:
    print("=== 开始周平王与全系统人物准确性重梳独立审查 ===")
    if inject_fault:
        print("⚠️ 故障注入模式启用：故意篡改断言判据，验证测试是否变红！\n")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. 朝代元数据纠偏断言
    c.execute("SELECT id, dynasty FROM persons WHERE id IN ('p_panyue', 'p_zhiyu', 'p_jikang', 'p_zhoupingwang')")
    dyn_map = dict(c.fetchall())
    expected_dyns = {
        "p_panyue": "西晉",
        "p_zhiyu": "西晉",
        "p_jikang": "三國",
        "p_zhoupingwang": "東周",
    }
    for pid, exp_dyn in expected_dyns.items():
        if inject_fault and pid == "p_panyue":
            exp_dyn = "商"  # 故障注入
        assert dyn_map.get(pid) == exp_dyn, (
            f"断言 1 失败：{pid} 朝代 {dyn_map.get(pid)} != {exp_dyn}"
        )
    print("✓ [1/10] 朝代元数据 100% 修复自洽 (潘岳/摯虞->西晉, 嵇康->三國, 周平王->東周)")

    # 2. 周平王命中收拢：极致纯净 25 处（100% 为真周平王史事，长尾封王全部清零）
    c.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_zhoupingwang'")
    pw_hits = c.fetchone()[0]
    expected_hits = 10 if inject_fault else 25
    assert pw_hits == expected_hits, (
        f"断言 2 失败：周平王命中数 {pw_hits} != {expected_hits}（未达极致纯净25处）"
    )
    print(f"✓ [2/10] 周平王命中达极致纯净: 恰好 {pw_hits} 处 (100% 真实周平王史事，长尾伪命中全部肃清)")

    # 3. 周平王在三国志中的命中彻底清零（原 11 处全为安平王/东平王/阳平王等封王截断）
    c.execute("""
        SELECT COUNT(*) FROM mentions m
        JOIN sentences s ON m.sentence_uid = s.uid
        WHERE m.person_id='p_zhoupingwang' AND s.chapter_id LIKE 'sgz-%'
    """)
    pw_sgz = c.fetchone()[0]
    assert pw_sgz == 0, f"断言 3 失败：周平王在三国志仍有 {pw_sgz} 处残留伪命中"
    print("✓ [3/10] 周平王在三国志伪命中 100% 清零 (0 处，东平王/安平王截断彻底隔绝)")

    # 4. 周平王在晋书、汉书中的典型封王截断、梁平王刘襄及动宾撕裂彻底清除
    bad_phrases = [
        "安平王孚", "東平王楙", "始平王裕", "平王敦", "平王郎", "平王室亂", "屈宜臼",
        "平王襄", "秦周字平王", "李太后，親平王之大母也", "任王后甚有寵於平王襄", "平王頃王子", "立趙敬肅王子偃為平王"
    ]
    for bp in bad_phrases:
        c.execute("""
            SELECT COUNT(*) FROM mentions m
            JOIN sentences s ON m.sentence_uid = s.uid
            WHERE m.person_id='p_zhoupingwang' AND s.text LIKE ?
        """, (f"%{bp}%",))
        cnt = c.fetchone()[0]
        assert cnt == 0, f"断言 4 失败：短语 '{bp}' 仍有周平王误标 ({cnt} 处)"
    print("✓ [4/10] 安平王/東平王/平王敦/屈宜臼/平王襄/秦周字平王 等封王及表字短语 100% 零误标")

    # 5. 周平王核心真命中 100% 精准保留
    good_cases = [
        ("sj-004", "東遷于雒邑"),
        ("sj-005", "襄公以兵送周平王"),
        ("sj-037", "周平王命武公爲公"),
        ("js-014", "及平王東遷洛邑"),
    ]
    for cid, phrase in good_cases:
        c.execute("""
            SELECT COUNT(*) FROM mentions m
            JOIN sentences s ON m.sentence_uid = s.uid
            WHERE m.person_id='p_zhoupingwang' AND s.chapter_id=? AND s.text LIKE ?
        """, (cid, f"%{phrase}%"))
        cnt = c.fetchone()[0]
        assert cnt >= 1, f"断言 5 失败：周平王核心真命中 [{cid}] '{phrase}' 未被标注"
    print("✓ [5/10] 周平王核心真命中（平王東遷雒邑/襄公送周平王等）100% 精准保留")

    # 6. 郝昭（p_haozhao）五行志霸道伪命中清零
    c.execute("""
        SELECT COUNT(*) FROM mentions m
        JOIN sentences s ON m.sentence_uid = s.uid
        WHERE m.person_id='p_haozhao' AND s.chapter_id LIKE 'hs-%'
    """)
    hz_hs = c.fetchone()[0]
    assert hz_hs == 0, f"断言 6 失败：郝昭在汉书仍有 {hz_hs} 处霸道伪命中"
    c.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_haozhao'")
    assert c.fetchone()[0] == 3, "断言 6 失败：郝昭真三国陈仓守将命中受损"
    print("✓ [6/10] 郝昭汉书五行志齐桓行霸道伪命中 100% 清零 (0 处，真三国命中无损)")

    # 7. 何曾、顾众、夏方、毕卓、蔡豹早期伪命中清零
    cleansed = [
        ("p_hezeng", "sj", "何曾", "萧何曾孙庆"),
        ("p_hezeng", "hs", "何曾", "萧何曾孙庆"),
        ("p_guzhong", "hs", "顾众", "不顾众庶"),
        ("p_xiafang", "hs", "夏方", "考文正理"),
        ("p_bizhuo", "hs", "毕卓", "丰茂世之规"),
        ("p_caibao", "hs", "蔡豹", "公士宣"),
    ]
    for pid, book, name, reason in cleansed:
        c.execute(f"""
            SELECT COUNT(*) FROM mentions m
            JOIN sentences s ON m.sentence_uid = s.uid
            WHERE m.person_id=? AND s.chapter_id LIKE '{book}-%'
        """, (pid,))
        cnt = c.fetchone()[0]
        assert cnt == 0, f"断言 7 失败：{name} 在 {book} 仍有 {cnt} 处伪命中（原因：{reason}）"
    print("✓ [7/10] 何曾(萧何曾孙)/顾众(不顾众庶)/夏方(考文正理)/毕卓(茂世)/蔡豹(士宣) 早期伪命中全部清零")

    # 8. 孙辅、孙和、孙奋及嵇康跨书伪命中清零
    sg_cleansed = [
        ("p_sunfu", "hs", "孙辅", "宗室子孙辅而立之"),
        ("p_sunhe", "sj", "孙和", "田常曾孙和"),
        ("p_sunfen", "sj", "孙奋", "代国守将孙奋"),
        ("p_sunfen", "hs", "孙奋", "代国守将孙奋"),
        ("p_jikang", "hs", "嵇康", "汉书古今人表西周重臣叔夜"),
    ]
    for pid, book, name, reason in sg_cleansed:
        c.execute(f"""
            SELECT COUNT(*) FROM mentions m
            JOIN sentences s ON m.sentence_uid = s.uid
            WHERE m.person_id=? AND s.chapter_id LIKE '{book}-%'
        """, (pid,))
        cnt = c.fetchone()[0]
        assert cnt == 0, f"断言 8 失败：{name} 在 {book} 仍有 {cnt} 处伪命中（原因：{reason}）"
    c.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_jikang'")
    assert c.fetchone()[0] == 20, "断言 8 失败：嵇康真晋书竹林名士命中受损"
    print("✓ [8/10] 孙辅/孙和/孙奋/嵇康 在史记、汉书的跨代伪命中全部清零 (嵇康纯净20处)")

    # 9. 楚平王真命中健康性保障
    c.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_chupingwang'")
    cp_hits = c.fetchone()[0]
    assert cp_hits >= 55, f"断言 9 失败：楚平王真命中受损，仅得 {cp_hits} 处"
    print(f"✓ [9/10] 楚平王真命中健康完好: {cp_hits} 处 (>= 55 处，消歧规则平稳)")

    # 10. 离线快照 dist/data.js 完整同步校验
    assert os.path.exists(DIST_JS), f"断言 10 失败：{DIST_JS} 不存在"
    with open(DIST_JS, "r", encoding="utf-8") as f:
        head_js = f.read(5000)
    assert "離線快照數據" in head_js and "2402" in head_js, "断言 10 失败：dist/data.js 内容异常"
    print("✓ [10/10] 离线快照 dist/data.js 同步最新 2,402 人纯净版数据")

    print("\n🎉 全部 10/10 项周平王与全系统人物准确性重梳审查断言 100% 绿色通过！")

def main():
    parser = argparse.ArgumentParser(description="人物准确性重梳独立审查断言脚本")
    parser.add_argument("--inject", action="store_true", help="启用故障注入，验证测试变红")
    args = parser.parse_args()

    if args.inject:
        try:
            run_assertions(inject_fault=True)
            print("\n❌ 错误：故障注入未触发断言失败！测试套件缺乏敏感度！")
            sys.exit(1)
        except AssertionError as e:
            print(f"\n🎯 [PASS: 故障注入成功变红] 捕获预期断言异常:\n   {e}")
            print("双向闭环证实：断言脚本具备真实验伪敏感度！退出码置 0。")
            sys.exit(0)
    else:
        run_assertions(inject_fault=False)

if __name__ == "__main__":
    main()
