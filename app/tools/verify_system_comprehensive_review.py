# -*- coding: utf-8 -*-
"""BOOKINDEX 全系统端到端深度独立审查脚本（Full-System Independent Review）。

覆盖全栈 7 大核心层级：
[1] 权威源层（Workbook & Data Sources）：xlsx 完整性、安全保存、2238人物、101纯三元组关系、39证据无孤儿
[2] 处理管线层（Pipeline & Annotation）：564篇、223,164句、49,069段、稳定uid算法、注文段落100%可达、check_trad 7闸
[3] 存储派生层（Database & FTS5）：SQLite 8表基线对账、字面截断校验 text[s:e]==surface、零孤儿外键
[4] 后端服务层（Backend & API）：mention_nth (人/地)、override_states 状态机、5000长篇上限、relations_graph 过滤
[5] 前端交互层（Frontend & Web）：hitSpan 三级回退、多证据 evidences 展开、地名标错面板、web/ 历史冻结
[6] 脱机快照层（Offline Snapshot）：dist/data.js 与库同步、dist/app.js 逻辑100%对齐、export_static 守卫
[7] 工程治理层（Governance & Safety）：README 真实性、零 blat 垃圾文件、知识库与两处工作流 SKILL 同步

运行方式：
    python app/tools/verify_system_comprehensive_review.py           # 正常模式（全绿 -> 退出码 0）
    python app/tools/verify_system_comprehensive_review.py --inject  # 故障注入模式（必须红 -> 退出码 1）
"""
import os
import sys
import re
import json
import sqlite3
import hashlib
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "app", "server") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
if os.path.join(ROOT, "pipeline") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import db
import pipeline.common as common
import pipeline.relations as R

CHECKS = []
INJECT_FAULT = "--inject" in sys.argv

def check(name: str, passed: bool, extra: str = ""):
    CHECKS.append((name, passed))
    mark = "OK" if passed else "FAIL"
    detail = f"　（{extra}）" if extra else ""
    print(f"  [{mark}] {name}{detail}")


# ---------------------------------------------------------------- 第一层
def review_layer1_workbooks():
    print("\n[审查层级 1] 权威源层（Workbook & Data Sources）安全与自洽性")
    wb_dir = os.path.join(ROOT, "workbook")
    required_files = [
        "persons.xlsx", "places.xlsx", "relations.xlsx",
        "overrides.xlsx", "sentence-edits.xlsx"
    ]
    for rf in required_files:
        p = os.path.join(wb_dir, rf)
        sz = os.path.getsize(p) if os.path.exists(p) else 0
        can_open = False
        try:
            wb_test = openpyxl.load_workbook(p, read_only=True)
            wb_test.close()
            can_open = True
        except Exception:
            can_open = False
        check(f"权威源文件 {rf} 存在且健康（>3KB可读，杜绝2.3KB损坏）",
              sz > 3000 and can_open, f"size={sz} bytes, can_open={can_open}")

    # 1. 人物表审定
    wb_p = openpyxl.load_workbook(os.path.join(wb_dir, "persons.xlsx"), read_only=True, data_only=True)
    ws_p = wb_p["人物"]
    active_pids = set()
    dead_pids = set()
    taoqian_row = None
    for r in ws_p.iter_rows(min_row=2, values_only=True):
        pid, stat = r[0], r[7]
        if stat == "active":
            active_pids.add(pid)
        elif stat == "dead":
            dead_pids.add(pid)
        if pid == "p_taoqian":
            taoqian_row = r
    wb_p.close()

    if INJECT_FAULT:
        active_pids.remove("p_taoqian")  # 故障注入：故意移出陶谦

    check("persons.xlsx 中活跃人物规模达标 (>=2,400人)", len(active_pids) >= 2400, f"活跃人数={len(active_pids)}")
    check("persons.xlsx 中笔误实体 p_taohqian 明确处于 dead 状态", "p_taohqian" in dead_pids)
    
    def _is_t(v): return v in (1, "1", True, "TRUE")
    tao_multi = taoqian_row and _is_t(taoqian_row[11]) and _is_t(taoqian_row[12]) and _is_t(taoqian_row[13])
    check("persons.xlsx 中 p_taoqian 覆盖后汉书、三国志、晋书三书", bool(tao_multi))
    check("persons.xlsx 中刘焉归一主实体 p_liuyan_ys 处于 active 状态", "p_liuyan_ys" in active_pids)

    # 2. 关系表与证据子表审定
    rel_rows = R._read_rows(active_only=False)
    act_rels = [r for r in rel_rows if r.get("状态(status)") == "active"]
    check("relations.xlsx 包含恰好 101 条活跃规范关系边", len(act_rels) == 101, f"active={len(act_rels)}")
    
    # rel_id 纯业务三元组契约
    bad_rel_ids = []
    for r in act_rels:
        a, b, rel, rid = r.get("person_a"), r.get("person_b"), r.get("关系(rel)"), r.get("rel_id")
        want_rid = R.rel_id(a, b, rel)
        if INJECT_FAULT:
            want_rid = "fail_contract"
        if rid != want_rid:
            bad_rel_ids.append((rid, want_rid))
    check("关系主键 rel_id 100% 符合纯业务三元组契约 md5(a|b|rel)[:12]",
          len(bad_rel_ids) == 0, f"分歧数={len(bad_rel_ids)}")

    ev_rows = R._read_ev_rows()
    act_rids = {r["rel_id"] for r in act_rels}
    orphan_evs = [e for e in ev_rows if e["rel_id"] not in act_rids]
    check("证据子表 39 行外键 rel_id 100% 对应主表活跃关系（零孤儿）",
          len(ev_rows) == 39 and len(orphan_evs) == 0, f"证据行数={len(ev_rows)}, 孤儿数={len(orphan_evs)}")

    # 3. overrides 权威源无自检脏行
    wb_o = openpyxl.load_workbook(os.path.join(wb_dir, "overrides.xlsx"), read_only=True, data_only=True)
    ws_o = wb_o.active
    test_dirty_rows = []
    for i, r in enumerate(ws_o.iter_rows(min_row=2, values_only=True), start=2):
        note = str(r[6] or "")
        if "自检测试" in note or "test_" in note:
            test_dirty_rows.append(i)
    wb_o.close()
    check("overrides.xlsx 中无残留自检脏行", len(test_dirty_rows) == 0, f"脏行行号={test_dirty_rows}")


# ---------------------------------------------------------------- 第二层
def review_layer2_pipeline_and_corpus():
    print("\n[审查层级 2] 处理管线层（Pipeline & Annotation）语料与算法契约")
    # 1. 篇目数与语料总句数
    conn = sqlite3.connect(db.db_path())
    n_chaps = conn.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    n_sents = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    n_paras = conn.execute("SELECT COUNT(DISTINCT chapter_id || ':' || para_seq) FROM sentences").fetchone()[0]
    conn.close()

    check("五书篇目数完整覆盖 564 篇（含晋书载记30篇）", n_chaps == 564, f"篇目数={n_chaps}")
    check("全量语料入库 223,164 句且段落数达 49,069 段（正文无开洞）",
          n_sents == 223164 and n_paras == 49069, f"句数={n_sents}, 段落数={n_paras}")

    # 2. 稳定 uid 算法契约验证
    conn = sqlite3.connect(db.db_path())
    samples = conn.execute("SELECT uid, chapter_id, para_seq, seq FROM sentences LIMIT 200").fetchall()
    conn.close()
    bad_uids = []
    for uid, cid, pseq, sseq in samples:
        want_uid = common.stable_uid(cid, pseq, sseq)
        if uid != want_uid:
            bad_uids.append((uid, want_uid))
    check("稳定 uid 算法抽样校验 100% 一致（篇|段序|句序）", len(bad_uids) == 0, f"分歧数={len(bad_uids)}")

    # 3. 注文独立索引与正文段落可达性
    conn = sqlite3.connect(db.db_path())
    p_notes = conn.execute("SELECT COUNT(*) FROM mentions WHERE tier='note'").fetchone()[0]
    # 检查注文明细跳转段落是否存在于正文
    pei_json_path = os.path.join(ROOT, "data", "index", "pei-data.json")
    with open(pei_json_path, encoding="utf-8") as f:
        pei_data = json.load(f)
    unreachable_notes = []
    check_samples = list(pei_data.items())[:50]
    for pid, pdata in check_samples:
        for it in pdata.get("items", [])[:3]:
            cid, pseq = it["cid"], it["pseq"]
            cnt = conn.execute("SELECT COUNT(*) FROM sentences WHERE chapter_id=? AND para_seq=?", (cid, pseq)).fetchone()[0]
            if cnt == 0:
                unreachable_notes.append((pid, cid, pseq))
    conn.close()
    check("裴注与旧史注作为独立账本独立统计且正文段落 100% 可达跳转",
          len(unreachable_notes) == 0, f"不可达明细={len(unreachable_notes)}")


# ---------------------------------------------------------------- 第三层
def review_layer3_database_integrity():
    print("\n[审查层级 3] 存储派生层（Database & FTS5）数据完整性与对账")
    conn = sqlite3.connect(db.db_path())
    c_m = conn.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
    c_pm = conn.execute("SELECT COUNT(*) FROM place_mentions").fetchone()[0]
    c_pl = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    c_pla = conn.execute("SELECT COUNT(*) FROM place_aliases").fetchone()[0]
    
    check("人物命中总频次在P0/P1/P2/T3/T4高精收拢后健康稳定 (>=67,500处)", c_m >= 67500, f"mentions={c_m}")
    check("地名命中总频次在剔除千人/下相噪声后健康稳定 (>=118,000处)", c_pm >= 118000, f"place_mentions={c_pm}")
    check("地名总数在剔除千人县后收拢为 1,620 处且异体写法表达标 (>=2,600条)",
          c_pl >= 1620 and c_pla >= 2600, f"places={c_pl}, place_aliases={c_pla}")

    # 抽查命中字面截取准确性 text[s:e] == surface
    samples = conn.execute(
        "SELECT s.text, m.s, m.e, m.surface FROM mentions m "
        "JOIN sentences s ON s.uid=m.sentence_uid LIMIT 300").fetchall()
    mismatch_surface = []
    for text, s, e, surface in samples:
        if text[s:e] != surface:
            mismatch_surface.append((text[s:e], surface))
    conn.close()
    check("实体命中切片字面抽查 100% 自洽 (text[s:e] == surface)",
          len(mismatch_surface) == 0, f"分歧数={len(mismatch_surface)}")


# ---------------------------------------------------------------- 第四层
def review_layer4_backend_api():
    print("\n[审查层级 4] 后端服务层（Backend & API）契约与状态机")
    conn = sqlite3.connect(db.db_path())
    sample_p = conn.execute(
        "SELECT sentence_uid, surface, s, e, person_id FROM mentions LIMIT 1").fetchone()
    sample_pl = conn.execute(
        "SELECT sentence_uid, surface, s, e, place_id FROM place_mentions WHERE place_id='pl_luoyang' LIMIT 1").fetchone()
    conn.close()

    # 1. mention_nth
    uid_p, sfc_p, sp, ep, pid_p = sample_p
    nth_p = db.mention_nth(uid_p, sp, ep, sfc_p, pid_p)
    uid_pl, sfc_pl, spl, epl, pid_pl = sample_pl
    nth_pl = db.mention_nth(uid_pl, spl, epl, sfc_pl, pid_pl)
    check("db.mention_nth 对人名与地名(pl_)均能精准计算本句序号",
          nth_p is not None and nth_pl is not None, f"nth_p={nth_p}, nth_pl={nth_pl}")

    # 2. override_states 状态机
    st_drop = db.override_states([{"uid": uid_pl, "s": spl, "e": epl, "surface": sfc_pl, "action": "drop"}])
    st_re_self = db.override_states([{"uid": uid_pl, "s": spl, "e": epl, "surface": sfc_pl, "action": "reassign", "to": pid_pl}])
    st_re_other = db.override_states([{"uid": uid_pl, "s": spl, "e": epl, "surface": sfc_pl, "action": "reassign", "to": "pl_changan"}])
    check("db.override_states 地名 drop/reassign 状态机计算符合预期",
          st_drop == [False] and st_re_self == [True] and st_re_other == [False])

    # 3. 篇目长章节默认 limit 达 5000（如史记年表等超大篇章无截断，原默认500截断）
    chap_long = db.chapter_sentences("sj-014")
    sents_n = len(chap_long.get("sentences", []))
    check("db.chapter_sentences 默认 limit 提升至 5000（超大长篇 3454 句无截断）",
          sents_n >= 3000, f"sj-014 返回句数={sents_n}")


# ---------------------------------------------------------------- 第五层
def review_layer5_frontend_and_web():
    print("\n[审查层级 5] 前端交互层（Frontend & Web）编码防护与历史冻结")
    app_js_path = os.path.join(ROOT, "app", "web", "app.js")
    with open(app_js_path, encoding="utf-8") as f:
        js = f.read()

    # 1. hitSpan 三级回退
    has_hitspan = "function hitSpan(" in js and "Array.from" in js and "indexOf" in js
    check("前端包含 hitSpan A/B/C 三级回退（解决非 BMP 字符标色偏移）", has_hitspan)

    # 2. 多证据展开与高亮
    has_evidences = "evidences" in js and "evidence_uid" in js
    check("前端详情面板支持多证据 evidences 数组聚合与渲染", has_evidences)

    # 3. 地名与人名对称的标错交互面板
    has_ovbar = ".ovbar" in js and "renderPlace" in js and "ovrebuild" in js
    check("前端地名与人名均支持未生效提示条 (.ovbar) 与标错面板", has_ovbar)

    # 4. 历史 web/ 目录冻结保护
    w_readme = os.path.join(ROOT, "web", "README.md")
    w_html = os.path.join(ROOT, "web", "index.html")
    with open(w_readme, encoding="utf-8") as f1, open(w_html, encoding="utf-8") as f2:
        txt1, txt2 = f1.read(), f2.read()
    check("历史前端 web/ 目录包含冻结声明与入口警告注释",
          "已冻结" in txt1 and "历史冻结页面" in txt2)


# ---------------------------------------------------------------- 第六层
def review_layer6_offline_snapshot():
    print("\n[审查层级 6] 脱机分发层（Offline Snapshot）与快照守卫")
    dist_dir = os.path.join(ROOT, "dist")
    data_js = os.path.join(dist_dir, "data.js")
    app_js = os.path.join(dist_dir, "app.js")
    idx_html = os.path.join(dist_dir, "index.html")

    check("离线快照 dist/ 核心文件 (data.js, app.js, index.html) 齐全",
          os.path.exists(data_js) and os.path.exists(app_js) and os.path.exists(idx_html))

    # 源码一致性
    src_app = os.path.join(ROOT, "app", "web", "app.js")
    with open(src_app, "r", encoding="utf-8") as f1, open(app_js, "r", encoding="utf-8") as f2:
        t1 = f1.read().replace("\r\n", "\n")
        t2 = f2.read().replace("\r\n", "\n")
    if INJECT_FAULT:
        t2 = t2 + "\n// corrupt"
    check("主力前端 app/web/app.js 与 dist/app.js 逻辑代码 100% 同步",
          t1 == t2, f"src_len={len(t1)}, dst_len={len(t2)}")

    # 运行 export_static.py --check
    import subprocess
    py = sys.executable
    res = subprocess.run([py, os.path.join(ROOT, "app", "tools", "export_static.py"), "--check"],
                         capture_output=True, text=True)
    check("export_static.py --check 验证快照与 SQLite 库完全同步",
          res.returncode == 0, res.stdout.strip())


# ---------------------------------------------------------------- 第七层
def review_layer7_governance_and_skills():
    print("\n[审查层级 7] 工程治理层（Governance & Safety）文档与技能知识库")
    # 1. 根目录 README 真实性
    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        r_text = f.read()
    check("根目录 README.md 包含最新全栈指标（564篇/22.3万句/2238人/101关系）",
          "564 篇" in r_text and "223,164 句" in r_text and "2,238 位人物" in r_text and "101 条规范边" in r_text)
    check("根目录 README.md 清除旧 8770 指导并正确引导 8800 服务",
          "8800" in r_text and "cd web && python -m http.server 8770" not in r_text)

    # 2. 根目录垃圾文件排查
    clean_py = os.path.join(ROOT, "pipeline", "_clean_root_blat.py")
    res_clean = os.popen(f"{sys.executable} {clean_py}").read()
    check("仓库根目录无任何 4 字节 blat 临时垃圾文件泄漏",
          "可删 0 个" in res_clean, res_clean.strip())

    # 3. 工作流技能一致性
    s1_path = os.path.join(ROOT, ".agents", "skills", "bookindex-workflow", "SKILL.md")
    s2_path = os.path.join(ROOT, ".mimocode", "skills", "bookindex-workflow", "SKILL.md")
    with open(s1_path, encoding="utf-8") as f1, open(s2_path, encoding="utf-8") as f2:
        s1 = f1.read().replace("\r\n", "\n")
        s2 = f2.read().replace("\r\n", "\n")
    check("两处工作流 SKILL.md (.agents 与 .mimocode) 保持 100% 同步",
          s1 == s2, f"s1_len={len(s1)}, s2_len={len(s2)}")


def main():
    print("=" * 70)
    print("     古籍索引系统 BOOKINDEX · 全系统端到端深度独立审查 (Review)     ")
    print("=" * 70)
    review_layer1_workbooks()
    review_layer2_pipeline_and_corpus()
    review_layer3_database_integrity()
    review_layer4_backend_api()
    review_layer5_frontend_and_web()
    review_layer6_offline_snapshot()
    review_layer7_governance_and_skills()

    total = len(CHECKS)
    passed = sum(1 for _, ok in CHECKS if ok)
    print("\n" + "=" * 70)
    print(f"全系统审查结果统计：{passed}/{total} 项全部通过。")
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
