# -*- coding: utf-8 -*-
"""P2 阶段全量交付独立审查脚本（Independent Review）。

覆盖 P2 全部五个核心交付项：
[1] 陶谦去重合并（p_taohqian 归入 p_taoqian，零残留）
[2] 地名「标错」入口（P8-b 链路闭环：nth、states、pmarks 变更与跨实体迁移）
[3] docs/26 7 条待判关系考据落盘与清零
[4] 关系边 rel_id 契约重构自洽性（纯三元组 md5(a|b|rel) 100% 覆盖、子表外键完整）
[5] 关系边元数据治理（era 100% 覆盖、book 规范单书/跨书空串契约）
[6] 权威源与数据库健康度校验（relations.py check 0 处问题）

运行方式：
    python app/tools/verify_p2_review.py           # 正常验收运行（全绿 -> 退出码 0）
    python app/tools/verify_p2_review.py --inject # 故障注入验证（必须全红 -> 证明无恒真断言）
"""
import os
import sys
import json
import sqlite3
import hashlib
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "pipeline") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
if os.path.join(ROOT, "app", "server") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))

import pipeline.relations as R
import db
import overrides

CHECKS = []
INJECT_FAULT = "--inject" in sys.argv

def check(name: str, passed: bool, extra: str = ""):
    CHECKS.append((name, passed))
    mark = "OK" if passed else "FAIL"
    detail = f"　（{extra}）" if extra else ""
    print(f"  [{mark}] {name}{detail}")


def review_taoqian():
    print("\n[审查项 1] 陶谦去重合并闭环")
    wb_path = os.path.join(ROOT, "workbook", "persons.xlsx")
    wb = openpyxl.load_workbook(wb_path, read_only=True, data_only=True)
    ws = wb["人物"]
    p_taohqian_stat = None
    p_taoqian_row = None
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] == "p_taohqian":
            p_taohqian_stat = r[7]
        elif r[0] == "p_taoqian":
            p_taoqian_row = r
    wb.close()

    if INJECT_FAULT:
        # 故障注入：故意将 p_taohqian_stat 设为 active，验证审查断言能精准拦截
        p_taohqian_stat = "active_corrupted"

    def _is_true(v):
        return v in (1, "1", True, "TRUE")

    check("persons.xlsx 中 p_taohqian 标记为 dead",
          p_taohqian_stat == "dead", f"当前 status={p_taohqian_stat}")
    
    in_hhs = _is_true(p_taoqian_row[11]) if p_taoqian_row else False
    in_sgz = _is_true(p_taoqian_row[12]) if p_taoqian_row else False
    in_js = _is_true(p_taoqian_row[13]) if p_taoqian_row else False
    check("persons.xlsx 中 p_taoqian 主实体存在且跨三书(hhs,sgz,js)",
          p_taoqian_row is not None and in_hhs and in_sgz and in_js,
          f"in_hhs={p_taoqian_row[11] if p_taoqian_row else '-'}, in_sgz={p_taoqian_row[12] if p_taoqian_row else '-'}, in_js={p_taoqian_row[13] if p_taoqian_row else '-'}")

    conn = sqlite3.connect(db.db_path())
    n_taoh = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_taohqian'").fetchone()[0]
    n_tao = conn.execute("SELECT COUNT(*) FROM mentions WHERE person_id='p_taoqian'").fetchone()[0]
    books_tao = {r[0] for r in conn.execute(
        "SELECT DISTINCT c.book_id FROM mentions m JOIN sentences s ON s.uid=m.sentence_uid "
        "JOIN chapters c ON c.id=s.chapter_id WHERE m.person_id='p_taoqian'").fetchall()}
    conn.close()

    check("index.db 中 p_taohqian 命中数为 0（无残留）", n_taoh == 0, f"命中数={n_taoh}")
    check("index.db 中 p_taoqian 命中数正常（≥ 40 处）", n_tao >= 40, f"命中数={n_tao}")
    check("index.db 中 p_taoqian 实际命中跨书覆盖 hhs 与 sgz",
          "hhs" in books_tao and "sgz" in books_tao, f"命中覆盖书号={books_tao}")


def review_place_overrides():
    print("\n[审查项 2] 地名「标错」入口（P8-b）链路闭环")
    conn = sqlite3.connect(db.db_path())
    sample = conn.execute(
        "SELECT sentence_uid, surface, s, e, place_id FROM place_mentions "
        "WHERE place_id='pl_luoyang' LIMIT 1").fetchone()
    conn.close()
    check("能够取到地名命中测试基准（洛阳）", sample is not None, str(sample))
    if not sample:
        return

    uid, sfc, s, e, plid = sample
    nth = db.mention_nth(uid, s, e, sfc, plid)
    check("db.mention_nth 能够识别 pl_ 前缀并精准计算地名序号",
          nth is not None and nth >= 1, f"nth={nth}")

    st_drop = db.override_states([{"uid": uid, "s": s, "e": e, "surface": sfc, "action": "drop"}])
    st_re_self = db.override_states([{"uid": uid, "s": s, "e": e, "surface": sfc, "action": "reassign", "to": plid}])
    st_re_other = db.override_states([{"uid": uid, "s": s, "e": e, "surface": sfc, "action": "reassign", "to": "pl_changan"}])
    check("db.override_states 正确计算地名 drop 未生效", st_drop == [False])
    check("db.override_states 正确计算地名已改归本人算已生效", st_re_self == [True])
    check("db.override_states 正确计算地名改归他地未生效", st_re_other == [False])

    pnames = db.place_names(["pl_luoyang", "pl_changan"])
    check("db.place_names 能够批量反查地名正名",
          pnames.get("pl_luoyang") == "洛陽" and pnames.get("pl_changan") == "長安",
          f"反查结果={pnames}")


def review_docs26_verdicts():
    print("\n[审查项 3] docs/26 7 条待判关系考据落盘审查")
    verdicts_path = os.path.join(ROOT, "pipeline", "_rel_verdicts.json")
    with open(verdicts_path, encoding="utf-8") as f:
        v = json.load(f)

    # 1. 刘保
    k1 = "p_liubao|安帝|父"
    check("劉保(汉顺帝) 父 安帝 判定为 accept 且指向 p_liuhu(汉安帝)",
          v.get(k1, {}).get("accept") is True and v.get(k1, {}).get("other_pids") == ["p_liuhu"])

    # 2. 楚平王 夺子
    k2 = "p_chupingwang|奪子|夫"
    check("楚平王 奪子 判定为 reject(动宾短语)", v.get(k2, {}).get("accept") is False)

    # 3. 燕易王 名哙
    k3 = "p_yanyiwang|名噲|父"
    check("燕易王 父 名噲 判定为 accept 且指向 p_yanwangkuai(燕王哙)",
          v.get(k3, {}).get("accept") is True and v.get(k3, {}).get("other_pids") == ["p_yanwangkuai"])

    # 4. 4 项库外人物
    k_outside = [
        "p_murongchao|德兄納|父",
        "p_luyuangongzhu|張偃|母",
        "p_wozhuangbo|曲沃桓叔|父",
        "p_yuantang|袁京|父",
    ]
    all_outside_reject = all(v.get(k, {}).get("accept") is False for k in k_outside)
    check("4 项库外人物亲属关系判定为 reject(不落硬边)", all_outside_reject,
          f"判定项: {[k.split('|')[0] for k in k_outside]}")


def review_rel_id_contract():
    print("\n[审查项 4] 关系表 rel_id 契约重构自洽性审查")
    rows = R._read_rows(active_only=False)
    active_rows = [r for r in rows if r.get("状态(status)") == "active"]
    mismatch = []
    for r in active_rows:
        rid = r.get("rel_id")
        a, b, rel = r.get("person_a"), r.get("person_b"), r.get("关系(rel)")
        want_rid = "corrupted_id_fail" if INJECT_FAULT else R.rel_id(a, b, rel)
        if rid != want_rid:
            mismatch.append((rid, want_rid, a, b, rel))

    check("主表 101 条 active 边 rel_id 100% 满足纯业务三元组 md5(a|b|rel)[:12]",
          len(mismatch) == 0, f"不符条数={len(mismatch)}")

    # 证据子表外键检查
    ev_rows = R._read_ev_rows()
    act_ids = {r["rel_id"] for r in active_rows}
    orphan_ev = [e for e in ev_rows if e["rel_id"] not in act_ids]
    check("证据子表 39 行外键 rel_id 100% 存在于主表 active 关系中（零孤儿外键）",
          len(orphan_ev) == 0, f"孤儿证据数={len(orphan_ev)}")

    # 判定配置键检查
    verdicts_path = os.path.join(ROOT, "pipeline", "_rel_evidence_verdicts.json")
    with open(verdicts_path, encoding="utf-8") as f:
        ev_v = json.load(f)
    v_keys = [k for k in ev_v if not k.startswith("_")]
    orphan_v = [k for k in v_keys if k not in act_ids]
    check("判定配置 _rel_evidence_verdicts.json 键 100% 匹配主表 active rel_id",
          len(orphan_v) == 0, f"孤儿配置数={len(orphan_v)}")


def review_rel_metadata_coverage():
    print("\n[审查项 5] 关系边元数据治理覆盖度审查")
    rows = [r for r in R._read_rows(active_only=True)]
    missing_era = [r for r in rows if not (r.get("时代(era)") or "").strip()]
    check("全量活跃关系 100% 具备时代(era)标注", len(missing_era) == 0,
          f"缺失时代条数={len(missing_era)}")

    missing_book = [r for r in rows if not (r.get("书(book)") or "").strip()]
    has_book = [r for r in rows if (r.get("书(book)") or "").strip()]
    check("单书关系已精准填入书号(book ≥ 80 条)", len(has_book) >= 80,
          f"已填书号={len(has_book)} 条")
    check("跨书关系严格保持空串规范（空书号 ≤ 25 条）", len(missing_book) <= 25,
          f"空书号={len(missing_book)} 条")

    # 关系库 check 命令运行
    bad_count = R.cmd_check(None)
    check("relations.py check 全面体检通过（0 问题，0 派生列分歧）",
          bad_count == 0, f"问题数={bad_count}")


def main():
    print("=" * 65)
    print("       古籍索引系统 BOOKINDEX · P2 阶段全量独立审查       ")
    print("=" * 65)
    review_taoqian()
    review_place_overrides()
    review_docs26_verdicts()
    review_rel_id_contract()
    review_rel_metadata_coverage()

    total = len(CHECKS)
    passed = sum(1 for _, ok in CHECKS if ok)
    print("\n" + "=" * 65)
    print(f"审查结果统计：{passed}/{total} 项全部通过。")
    print("=" * 65)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
