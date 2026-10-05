# -*- coding: utf-8 -*-
"""P0 与 P1 故障注入与独立审查验证脚本。
严格执行「故障注入 → 断言变红（红）→ 还原 → 断言变绿（绿）」闭环。

覆盖范围：
1. [P0 护栏] safe_save_workbook 异常隔离性：写入过程发生异常时，原文件绝不被 0 字节截断。
2. [P1 段落] 句数缺失检测：句数不为 223,164 时断言必红。
3. [P1 注文] 注文跳转悬空检测：若存在悬空段号，断言必红。
4. [P1 长篇] 500 句截断检测：若篇目被 500 截断，断言必红。
5. [P1 重复] 重复 pid 判定：若 p_liuyan_sg 残留命中，断言必红。

用法：
    python app/tools/verify_p1_fault_injection.py
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "app", "server"))
from common import safe_save_workbook
import db

PY = sys.executable


def run_injection_test(name: str, inject_fn, test_fn, restore_fn):
    print(f"\n--- [测试] {name} ---")
    # 1. 注入故障
    inject_fn()
    red_ok = False
    try:
        test_fn()
        print(f"  ❌ 故障注入后未变红！断言失效！")
    except Exception as e:
        red_ok = True
        print(f"  🔴 [变红成功] 捕获预期异常：{e}")

    # 2. 还原
    restore_fn()
    green_ok = False
    try:
        test_fn()
        green_ok = True
        print(f"  🟢 [变绿成功] 还原后断言正常通过")
    except Exception as e:
        print(f"  ❌ 还原后未能变绿：{e}")

    assert red_ok and green_ok, f"{name} 故障注入闭环失败！"
    print(f"  ✅ {name} 红/绿双向验证闭环！")


def test_p0_openpyxl_safety():
    """验证 safe_save_workbook 在写入异常时保护磁盘原文件。"""
    print("\n--- [测试] P0 openpyxl 异常防截断护栏 ---")
    tmp_dir = tempfile.mkdtemp()
    test_file = os.path.join(tmp_dir, "test_target.xlsx")
    original_content = b"ORIGINAL_VALID_XLSX_DATA_" * 100
    with open(test_file, "wb") as f:
        f.write(original_content)

    original_size = os.path.getsize(test_file)

    class BrokenWorkbook:
        def save(self, stream):
            # 模拟在写入 zip 过程中抛出异常
            stream.write(b"PARTIAL_JUNK")
            raise IOError("Simulated disk error or permissions crash during save")

    broken_wb = BrokenWorkbook()

    # 执行保存，预期抛出异常
    failed = False
    try:
        safe_save_workbook(broken_wb, test_file)
    except IOError as e:
        failed = True
        print(f"  🔴 [变红成功] 保存过程抛出预期异常: {e}")

    assert failed, "BrokenWorkbook 应该抛出异常"

    # 核心检验：目标文件是否依然完整、字节数是否未被截断为 0
    current_size = os.path.getsize(test_file)
    current_content = open(test_file, "rb").read()
    assert current_size == original_size, f"原文件尺寸被破坏！{current_size} != {original_size}"
    assert current_content == original_content, "原文件内容被篡改或损坏！"
    print(f"  🟢 [变绿成功] 发生崩溃时，目标文件尺寸依然为 {current_size} 字节，完全毫发无损！")

    shutil.rmtree(tmp_dir)
    print("  ✅ P0 openpyxl 安全保存护栏红/绿闭环通过！")


def main():
    print("==================================================================")
    print("        P0 & P1 独立审查：故障注入 (Fault Injection) 验证          ")
    print("==================================================================")

    # 1. P0 护栏验证
    test_p0_openpyxl_safety()

    # 2. P1 句数检查注入
    # 模拟句数少 1 句或不符合预期
    expected_sent = [223164]

    def inject_sent():
        expected_sent[0] = 223163  # 注入错误期望值，断言应敏锐变红

    def restore_sent():
        expected_sent[0] = 223164  # 恢复正常期望值，断言应变绿

    def test_sent():
        conn = db.connect()
        n = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        conn.close()
        if n != expected_sent[0]:
            raise AssertionError(f"句数不符合预期：{n} != {expected_sent[0]}")

    run_injection_test(
        "P1 全量句数敏感性",
        inject_sent,
        test_sent,
        restore_sent,
    )

    # 3. P1 注文跳转悬空敏感性
    bad_jump_flag = [False]

    def inject_pei():
        bad_jump_flag[0] = True

    def restore_pei():
        bad_jump_flag[0] = False

    def test_pei_jump():
        pei_path = os.path.join(ROOT, "data", "index", "pei-data.json")
        pei = json.load(open(pei_path, encoding="utf-8"))
        conn = db.connect()
        db_paras = {(r[0], r[1]) for r in conn.execute("SELECT chapter_id, para_seq FROM sentences").fetchall()}
        conn.close()
        miss = []
        for pid, pdata in pei.get("persons", {}).items():
            for item in pdata.get("items", []):
                cid = item.get("cid")
                pseq = item.get("pseq")
                if bad_jump_flag[0] and pseq == 8:
                    pseq = 999999  # 注入悬空段
                if (cid, pseq) not in db_paras:
                    miss.append((cid, pseq))
        if miss:
            raise AssertionError(f"发现悬空跳转 {len(miss)} 条：样例 {miss[:2]}")

    run_injection_test(
        "P1 裴注跳转悬空敏感性",
        inject_pei,
        test_pei_jump,
        restore_pei,
    )

    # 4. P1 长篇 500 截断敏感性
    limit_state = [5000]

    def inject_limit():
        limit_state[0] = 500

    def restore_limit():
        limit_state[0] = 5000

    def test_long_chap():
        data = db.chapter_sentences("sj-014", limit=limit_state[0])
        n = len(data.get("sentences", []))
        if n < 3454:
            raise AssertionError(f"长篇被截断：实得 {n} 句 < 3454 句")

    run_injection_test(
        "P1 长篇截断敏感性",
        inject_limit,
        test_long_chap,
        restore_limit,
    )

    # 5. P1 刘焉去重敏感性
    mock_sg_hits = [0]

    def inject_liuyan():
        mock_sg_hits[0] = 9

    def restore_liuyan():
        mock_sg_hits[0] = 0

    def test_liuyan_dup():
        conn = db.connect()
        n_sg = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_liuyan_sg'").fetchone()[0]
        n_ys = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_liuyan_ys'").fetchone()[0]
        conn.close()
        total_sg = n_sg + mock_sg_hits[0]
        if total_sg > 0:
            raise AssertionError(f"检测到残留重复 pid p_liuyan_sg 命中数={total_sg}")
        if n_ys == 0:
            raise AssertionError(f"主 pid p_liuyan_ys 命中数为 0")

    run_injection_test(
        "P1 刘焉重复 PID 残留敏感性",
        inject_liuyan,
        test_liuyan_dup,
        restore_liuyan,
    )

    print("\n==================================================================")
    print("   [独立审查结论] 全部 5 大核心注入测试 100% 通过红/绿闭环！        ")
    print("==================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
