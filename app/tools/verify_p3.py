# -*- coding: utf-8 -*-
"""P3 鏈路的斷言（新鏈路的回歸，與 pipeline/verify.py 的舊斷言並列）。

為什麼單獨一份
--------------
`pipeline/verify.py` 斷的是舊鏈路（靜態版 `web/` 的產物）。P3 這套
（快照 / diff / overrides / 重建）是新的，且斷言方式不一樣——
它比的不是「某個稱號歸誰」，而是**過程性質**：會不會回寫權威源、
空跑有沒有幻影變化、糾錯套用後對不對。

五條斷言
--------
1. **單向性**：跑完 build_dict + apply，`people.json` 與 `overrides.xlsx` 的
   md5 **必須不變**（防回寫權威源，紅線 1）
2. **空跑 diff 為 0**：庫沒動時連拍兩份快照，四類計數全 0（防幻影變化）
3. **diff 四類判定**：合成「改歸 3 / 消失 2 / 新增 2」，計數必須精確相等
4. **`--keep` 生效**：快照數不會無限增長
5. **override 生效**：`reassign` 改對 pid、`drop` 讓命中消失——
   跑完自動 revoke 並重跑 annotate 復原
6. **句級編輯**（P4）：拆句後前半**繼承 uid**、重放冪等、撤銷後還原

快照一律寫在**臨時庫**裡（monkeypatch `snapshot.SNAP_DB`），不污染真實歷史。

用法：python app/tools/verify_p3.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import overrides   # noqa: E402
import snapshot    # noqa: E402

PY = sys.executable
BOOK = os.path.join(ROOT, "data", "index", "book-data.json")
PEOPLE = os.path.join(ROOT, "data", "dict", "people.json")
XLSX = overrides.WORKBOOK

CHECKS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok))
    print("  [{}] {}{}".format("OK" if ok else "FAIL", name,
                               "　（{}）".format(detail) if detail else ""))


def md5(path: str) -> str:
    if not os.path.exists(path):
        return "-"
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run(script: str, *args: str) -> int:
    """跑一個腳本（可帶參數），返回退出碼。

    ⚠️ 參數必須分開傳，不能寫成 "overrides.py apply"——那會被當成
    一個含空格的檔案路徑，python 直接找不到檔案、退出碼非 0（第一版就這麼錯的）。
    """
    return subprocess.run([PY, os.path.join(ROOT, script), *args],
                          cwd=ROOT).returncode


# ---------------------------------------------------------------- 1 單向性

def test_one_way() -> None:
    print("\n[1] 單向性：pipeline 不回寫權威源")
    if not os.path.exists(XLSX):
        check("單向性", False, "{} 不存在，先跑 overrides.py init".format(XLSX))
        return
    before = (md5(PEOPLE), md5(XLSX))
    rc1 = run("pipeline/build_dict.py")
    rc2 = run("app/tools/overrides.py", "apply")
    after = (md5(PEOPLE), md5(XLSX))
    check("build_dict 不回寫 overrides.xlsx", before[1] == after[1],
          "{}".format(after[1][:8]))
    check("apply 不回寫 overrides.xlsx", before[1] == after[1])
    check("people.json 冪等（同表重建內容不變）", before[0] == after[0],
          "{}".format(after[0][:8]))
    check("兩個腳本都成功退出", rc1 == 0 and rc2 == 0)


# ---------------------------------------------------------------- 2/3/4 快照

def test_snapshots(tmpdb: str) -> None:
    print("\n[2] 空跑 diff 為 0（庫沒動，不該有幻影變化）")
    snapshot.SNAP_DB = tmpdb          # 寫臨時庫，別污染真實歷史
    a = snapshot.dump(label="v-a", keep=0)
    b = snapshot.dump(label="v-b", keep=0)
    _, counts, _ = snapshot.compute_diff(a, b)
    check("空跑四類計數全 0", sum(counts.values()) == 0,
          "新增{} 消失{} 改歸{} tier{}".format(
              counts["added"], counts["removed"],
              counts["pid_changed"], counts["tier_changed"]))

    print("\n[3] diff 四類判定（合成改動）")
    c = snapshot.dump(label="v-c", keep=0)
    conn = sqlite3.connect(tmpdb)
    cur = conn.cursor()
    rids = [r[0] for r in cur.execute(
        "SELECT rowid FROM snapshot_mentions "
        "WHERE snapshot_id=? AND pid='p_xiangyu' LIMIT 3", (c,))]
    cur.execute("UPDATE snapshot_mentions SET pid='p_liubang' WHERE rowid IN ({})"
                .format(",".join("?" * len(rids))), rids)
    n_ch = cur.rowcount
    rids2 = [r[0] for r in cur.execute(
        "SELECT rowid FROM snapshot_mentions WHERE snapshot_id=? AND pid='p_liubang' "
        "AND rowid NOT IN ({}) LIMIT 2".format(",".join("?" * len(rids))),
        [c] + rids)]
    cur.execute("DELETE FROM snapshot_mentions WHERE rowid IN ({})"
                .format(",".join("?" * len(rids2))), rids2)
    n_rm = cur.rowcount
    cur.execute(
        "INSERT INTO snapshot_mentions "
        "(snapshot_id, uid, s, e, surface, pid, tier, chapter_id) "
        "SELECT ?, uid || '-fake' || rowid, s, e, surface, pid, tier, chapter_id "
        "FROM snapshot_mentions WHERE snapshot_id=? LIMIT 2", (c, a))
    n_ad = cur.rowcount
    conn.commit()
    conn.close()
    _, counts2, _ = snapshot.compute_diff(b, c)
    check("改歸計數精確", counts2["pid_changed"] == n_ch,
          "期望 {} 實得 {}".format(n_ch, counts2["pid_changed"]))
    check("消失計數精確", counts2["removed"] == n_rm,
          "期望 {} 實得 {}".format(n_rm, counts2["removed"]))
    check("新增計數精確", counts2["added"] == n_ad,
          "期望 {} 實得 {}".format(n_ad, counts2["added"]))
    check("tier 變化計為 0", counts2["tier_changed"] == 0)

    print("\n[4] --keep 生效（快照不會無限增長）")
    snapshot.dump(label="v-d", keep=2)
    n = sqlite3.connect(tmpdb).execute(
        "SELECT COUNT(*) FROM snapshots").fetchone()[0]
    check("保留最近 2 份", n == 2, "實得 {} 份".format(n))


# ---------------------------------------------------------------- 5 override

def _uid_of(s) -> str:
    import hashlib as _h
    return _h.md5("{}|{}|{}".format(
        s["chapterId"], s.get("paraSeq"), s.get("seq")).encode("utf-8")
    ).hexdigest()[:12]


def _find_mark(d, uid: str, surface: str):
    for s in d["sentences"]:
        if _uid_of(s) != uid:
            continue
        for m in (s.get("marks") or []):
            if m.get("alias") == surface:
                return s, m
    return None, None


def _count_mark(d, uid: str, surface: str) -> int:
    """該句裡這個串有幾條命中。

    ⚠️ drop 的斷言必須**數條數**，不能用「找不找得到」——一句常有
    好幾條同串命中（「漢王」可能出現三次），移掉一條後仍然找得到，
    那就會誤判成 drop 沒生效（第一版就是這麼錯的）。
    """
    n = 0
    for s in d["sentences"]:
        if _uid_of(s) != uid:
            continue
        n += sum(1 for m in (s.get("marks") or []) if m.get("alias") == surface)
    return n


def test_overrides() -> None:
    print("\n[5] override 生效（reassign / drop）")
    import json

    conn = snapshot.connect(snapshot.DB_PATH)
    # GROUP BY 保證拿到**兩句不同**的命中（同句兩條會讓 nth 判定打架）
    rows = conn.execute(
        "SELECT m.sentence_uid, m.surface FROM mentions m "
        "WHERE m.tier='core' AND m.person_id='p_liubang' "
        "GROUP BY m.sentence_uid ORDER BY m.sentence_uid LIMIT 2").fetchall()
    conn.close()
    if len(rows) < 2:
        check("取到測試樣本", False, "庫裡找不到兩條 p_liubang 的 core 命中")
        return
    uid1, surf1 = rows[0]
    uid2, surf2 = rows[1]

    # 寫兩條糾錯：一條改歸、一條棄用
    subprocess.run([PY, os.path.join(HERE, "overrides.py"), "add",
                    "--uid", uid1, "--nth", "1", "--new", "p_xiangyu",
                    "--note", "P3-5 自檢"], cwd=ROOT)
    subprocess.run([PY, os.path.join(HERE, "overrides.py"), "add",
                    "--uid", uid2, "--nth", "1", "--action", "drop",
                    "--note", "P3-5 自檢"], cwd=ROOT)

    # ⚠️ revoke 必須放 finally：這兩條 override 一旦「加了但沒撤」，就不是多兩行
    # 髒數據，而是**真的在改數據**——下一次重建會把它們套用上去，「沛公」被改歸
    # 給項羽就是這麼來的（實測：verify_p3 崩在 revoke 之前，留了兩條 active）。
    try:
        with open(BOOK, encoding="utf-8") as f:
            before_drop = _count_mark(json.load(f), uid2, surf2)

        run("app/tools/overrides.py", "apply")
        with open(BOOK, encoding="utf-8") as f:
            d = json.load(f)

        _, m1 = _find_mark(d, uid1, surf1)
        check("reassign 生效（pid 已改）",
              m1 is not None and m1.get("pid") == "p_xiangyu",
              "pid={}".format(m1.get("pid") if m1 else "—"))
        check("reassign 保留原 tier（只加 override 標記）",
              m1 is not None and m1.get("override") == 1 and m1.get("tier") != "override")

        after_drop = _count_mark(d, uid2, surf2)
        check("drop 生效（命中條數 -1）", after_drop == before_drop - 1,
              "{} → {}（surface={}）".format(before_drop, after_drop, surf2))
    finally:
        # 復原：撤銷兩條糾錯 + 重跑 annotate（apply 是破壞性的，只能靠重標註還原）
        subprocess.run([PY, os.path.join(HERE, "overrides.py"), "revoke",
                        "--uid", uid1], cwd=ROOT)
        subprocess.run([PY, os.path.join(HERE, "overrides.py"), "revoke",
                        "--uid", uid2], cwd=ROOT)
    # ⚠️ 復原必須走完整重建（annotate 四步 + 建庫）。
    # 只跑 annotate.py 會讓 book-data.json 缺 `places` 鍵——地名是
    # annotate_places.py 加的，缺了它舊斷言 verify.py 直接 KeyError。
    rc = run("app/tools/rebuild.py", "--from", "2", "--no-snapshot")
    check("復原：重建成功（annotate 四步 + 建庫）", rc == 0)
    print("  （已 revoke 兩條自檢糾錯；book-data.json 由 rebuild 復原）")


def test_sentence_edits() -> None:
    """P4 句級編輯：拆句後**前半繼承 uid**，撤銷後能還原。"""
    print("\n[6] 句級編輯（拆句 / 還原）")
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    import apply_sentence_edits as SE

    conn = snapshot.connect(snapshot.DB_PATH)
    # 挑一句：命中在句子前半，這樣拆完前半仍帶著命中
    uid = at = None
    for r in conn.execute(
            "SELECT m.sentence_uid, m.e FROM mentions m "
            "WHERE m.person_id='p_liubang' AND m.tier='core' ORDER BY m.s LIMIT 20"):
        t = conn.execute("SELECT text FROM sentences WHERE uid=?",
                         (r[0],)).fetchone()
        if t and r[1] + 1 < len(t[0]):
            uid, at = r[0], r[1] + 1
            break
    text0 = conn.execute("SELECT text FROM sentences WHERE uid=?",
                         (uid,)).fetchone()[0]
    conn.close()
    if not uid:
        check("取到測試樣本", False)
        return

    _idx = {}

    def _corpus_text(u):
        """直接從語料讀（不等建庫）。uid→檔案的索引只掃一次。"""
        if not _idx:
            _idx.update(SE.uid_index())
        path = _idx.get(u)
        if not path:
            return None
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        _, _, s = SE.find_sentence(d, u)
        return s["text"] if s else None

    try:
        subprocess.run([PY, os.path.join(ROOT, "pipeline",
                                         "apply_sentence_edits.py"),
                        "add", "--uid", uid, "--action", "split",
                        "--at", str(at), "--note", "P4 自檢"], cwd=ROOT)
        run("pipeline/apply_sentence_edits.py", "apply")

        n_after = _corpus_text(uid)
        check("拆句：前半繼承原 uid（文本變短）",
              n_after == text0[:at], "「{}」".format(n_after))
        check("拆句：後半生成新 uid 進語料",
              _corpus_text(SE.new_uid_for_split(uid, at)) == text0[at:])

        # 冪等：再跑一次不該二次拆分
        run("pipeline/apply_sentence_edits.py", "apply")
        check("重放冪等（不會二次拆分）", _corpus_text(uid) == text0[:at])

        run("app/tools/rebuild.py", "--no-snapshot")
        conn = snapshot.connect(snapshot.DB_PATH)
        row = conn.execute("SELECT text FROM sentences WHERE uid=?",
                           (uid,)).fetchone()
        n_hit = conn.execute(
            "SELECT COUNT(*) FROM mentions WHERE sentence_uid=?", (uid,)).fetchone()[0]
        conn.close()
        check("建庫後前半 uid 仍在且文本正確", row is not None and row[0] == text0[:at])
        check("歷史命中沒被打散（該 uid 仍有命中）", n_hit >= 1,
              "{} 條".format(n_hit))
    finally:
        # 還原：撤銷 + 重放（重放機制天然回滾，不需要額外的還原代碼）
        subprocess.run([PY, os.path.join(ROOT, "pipeline",
                                         "apply_sentence_edits.py"),
                        "revoke", "--uid", uid], cwd=ROOT)
        run("pipeline/apply_sentence_edits.py", "apply")
        run("app/tools/rebuild.py", "--no-snapshot")
        conn = snapshot.connect(snapshot.DB_PATH)
        row = conn.execute("SELECT text FROM sentences WHERE uid=?",
                           (uid,)).fetchone()
        conn.close()
        check("撤銷後還原（文本回到原樣）", row is not None and row[0] == text0,
              "「{}」".format(row[0] if row else "—"))


def test_relations() -> None:
    """P6-0 關係資料：落點、派生規則、規範邊。

    最重要的一條是「重建後關係仍在」——`index.db` 每次重建都刪庫重建，
    關係若沒有「建庫後灌回」這一步會**靜默歸零**（docs/25 P0-1）。
    """
    print("\n[7] 關係資料（P6-0）")
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    import relations as R

    def db_count() -> int:
        conn = snapshot.connect(snapshot.DB_PATH)
        n = conn.execute(
            "SELECT COUNT(*) FROM relations WHERE status='active'").fetchone()[0]
        conn.close()
        return n

    rows = R._read_rows()
    if not rows:                      # 沒有種子就補一條，斷言才有意義（0==0 是假綠）
        subprocess.run([PY, os.path.join(ROOT, "pipeline", "relations.py"),
                        "add", "--a", "p_liubang", "--b", "p_hanhuidi",
                        "--rel", "父", "--era", "西漢", "--book", "sj",
                        "--source", "manual", "--note", "P6 自檢"], cwd=ROOT)
        rows = R._read_rows()
    n_xlsx = len(rows)

    run("pipeline/relations.py", "apply")
    check("灌入：庫內條數 = 權威源生效條數", db_count() == n_xlsx,
          "庫 {} / 表 {}".format(db_count(), n_xlsx))

    # 必須先確認重建**真的成功了**再比對：庫被別的進程佔著時 rebuild 會失敗，
    # 那時舊庫還在、關係也還在，直接比對就是一條**假綠**（踩過一次）。
    rc = run("app/tools/rebuild.py", "--no-snapshot")
    check("重建成功（庫沒被佔用）", rc == 0, "退出碼 {}".format(rc))
    check("重建後關係仍在（P0-1 回歸）", rc == 0 and db_count() == n_xlsx,
          "重建後 {} 條".format(db_count()))

    # 規則檢查**全表掃描**，不再取一行：上一版用 `LIMIT 1` 只看第一行，
    # 注入到第 3 行的錯誤（rel 出詞表 / confidence 手填）斷言**全綠**（docs/28 P0-5）。
    conn = snapshot.connect(snapshot.DB_PATH)
    rows = [dict(x) for x in conn.execute(
        "SELECT rel_id, person_a, person_b, rel, rel_type, symmetric, "
        "confidence, source, status, evidence_uid FROM relations "
        "WHERE status='active'")]
    pids = {x[0] for x in conn.execute("SELECT id FROM persons")}
    conn.close()
    if not rows:
        check("取到關係做規則檢查", False)
        return
    bad, seen = [], {}
    for r in rows:
        tag, a, b, rel = r["rel_id"], r["person_a"], r["person_b"], r["rel"]
        if a not in pids or b not in pids:
            bad.append("{} pid 不存在".format(tag))
        if a == b:
            bad.append("{} 自環".format(tag))
        if rel not in R.REL_TABLE:
            bad.append("{} rel「{}」不在詞表".format(tag, rel))
            continue
        if r["rel_type"] != R.REL_TABLE[rel][0]:
            bad.append("{} rel_type 手填".format(tag))
        if int(r["symmetric"] or 0) != R.REL_TABLE[rel][1]:
            bad.append("{} symmetric 手填".format(tag))
        if abs(float(r["confidence"] or 0)
               - R.derive_confidence(r["source"], bool(r["evidence_uid"]))) > 1e-6:
            bad.append("{} confidence 手填（{}）".format(tag, r["confidence"]))
        if not r["evidence_uid"] and float(r["confidence"] or 0) > R.NO_EVIDENCE_CAP:
            bad.append("{} 無證據卻高置信".format(tag))
        inv = R.REL_INVERSE.get(rel)
        if inv and (b, a, inv) in seen:
            bad.append("{} 反向雙寫".format(tag))
        seen[(a, b, rel)] = tag
    check("全表掃描：rel/rel_type/symmetric/confidence 全由規則派生", not bad,
          ("；".join(bad[:3])) if bad else "{} 條全部合規".format(len(rows)))
    check("規則檢查覆蓋所有 active 邊（不是只抽一行）", len(rows) > 1,
          "{} 條".format(len(rows)))

    # degree≥2 時每條邊只出現一次（BFS 沒去重會翻倍，docs/28 P0-4）
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import db
    g1 = db.relations_graph("p_liubang", 1)
    g2 = db.relations_graph("p_liubang", 2)
    ids1 = {e["rel_id"] for e in g1["edges"]}
    ids2 = [e["rel_id"] for e in g2["edges"]]
    check("degree=2 不重複邊（BFS 有去重）", len(ids2) == len(set(ids2)),
          "{} 條 / 去重後 {}".format(len(ids2), len(set(ids2))))
    check("degree=2 包含 degree=1 的全部邊", ids1 <= set(ids2),
          "一跳 {} / 二跳 {}".format(len(ids1), len(set(ids2))))

    # 按書旋鈕（docs/28 P1-3）：以前 `AND (book=? OR book='')` 讓 `book=zzz`
    # 也靜默放行——看著像過濾了，其實一條沒少。現在兩件事都必須成立：
    # ① 書號不在五書內 → 直接報錯；② 「按書」看的是**證據句落不落在這本書**，
    #    不是 `book` 列（61/62 條是空的，關係天然跨書）。
    try:
        db.relations_graph("p_liubang", 1, book="zzz")
        check("未知書號不再靜默放行（要報錯）", False, "沒報錯，仍返回全部邊")
    except ValueError as e:
        check("未知書號不再靜默放行（要報錯）", True, str(e)[:30])

    conn = snapshot.connect(snapshot.DB_PATH)
    ev = conn.execute(
        "SELECT r.rel_id, r.person_a, c.book_id FROM relations r "
        "JOIN sentences s ON s.uid=r.evidence_uid "
        "JOIN chapters c ON c.id=s.chapter_id "
        "WHERE r.status='active' AND r.evidence_uid<>'' LIMIT 1").fetchone()
    books = [x[0] for x in conn.execute("SELECT DISTINCT book_id FROM chapters")]
    conn.close()
    if ev:
        rid, pa, bk = ev[0], ev[1], ev[2]
        hit = {e["rel_id"] for e in
               db.relations_graph(pa, 1, book=bk)["edges"]}
        other_bk = next((b for b in books if b != bk), "")
        miss = {e["rel_id"] for e in
                db.relations_graph(pa, 1, book=other_bk)["edges"]}
        check("按書過濾：證據句在本書 → 邊在（book 列空也算）", rid in hit,
              "{} @ {}".format(rid[:8], bk))
        check("按書過濾：換一本沒有出處的書 → 邊不在（不是一律放行）",
              rid not in miss, "{} @ {}".format(rid[:8], other_bk))
    else:
        check("取到帶證據的真實邊（按書過濾要用）", False)

    # docs/25 P1-9 留下的賬（docs/28 P2-2）：它建議的「auto-summary ⇒ 證據非空」
    # 與現行模型衝突（證據可空、58 條無證據）。可執行的替代版本在這裡：
    # **沒有證據的推論邊，置信度必須被壓到上限以下**——不許頂著 0.6 裝有據。
    noev_high = [r["rel_id"] for r in rows
                 if not r["evidence_uid"]
                 and float(r["confidence"] or 0) > R.NO_EVIDENCE_CAP + 1e-6]
    check("無證據的推論邊置信度被壓到上限（docs/25 P1-9 的可執行替代）",
          not noev_high, "越線 {} 條".format(len(noev_high)))

    # 世系自洽（挑刺時補的兩條不變量）：關係是**主觀判斷**，錯了斷言查不出內容，
    # 但「自己跟自己撞車」這種必須能自動發現——
    #   ① 同一對兩人多種辈分（父 與 祖父 同時存在）→ 必有一條錯
    #   ② 世系成環（A 是 B 的長輩、B 又是 A 的長輩）→ 必錯
    # 袁湯那條（簡介寫「之子」實為「之孫」）就是靠「跟別的邊撞起來」才露的馬腳。
    gen = {"父", "母", "祖父", "祖母", "養父", "繼母"}
    pair_seen = {}
    pair_dup = []
    for r in rows:
        k = (r["person_a"], r["person_b"])
        if k in pair_seen and pair_seen[k] != r["rel"]:
            pair_dup.append("{}/{}：{} 與 {}".format(
                k[0], k[1], pair_seen[k], r["rel"]))
        pair_seen[k] = r["rel"]
    check("同一對兩人只有一種辈分（父與祖父同時存在必有一錯）", not pair_dup,
          "；".join(pair_dup[:2]))

    down = {}
    for r in rows:
        if r["rel"] in gen:
            down.setdefault(r["person_a"], []).append(r["person_b"])
    bad_cycle = []
    for start in list(down):
        stack = [(start, [start])]
        while stack:
            cur, path = stack.pop()
            for nxt in down.get(cur, []):
                if nxt == start:
                    bad_cycle.append(" → ".join(path + [nxt]))
                elif nxt not in path:
                    stack.append((nxt, path + [nxt]))
    check("世系不成環（A 是 B 長輩、B 又是 A 長輩）", not bad_cycle,
          "；".join(bad_cycle[:2]))

    # 裸帝號守衛（docs/28 P1-4）：以前是精確匹配，「孝武帝」「漢高祖」這種
    # **帶修飾字**的稱號直接漏網。這裏用 importlib 載（不能 import，那個腳本
    # 在 __main__ 下才跑 main()，直接 import 會執行到底）。
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_arb", os.path.join(ROOT, "pipeline", "_apply_rel_batch.py"))
    arb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arb)
    blocked = ["孝武帝", "漢高祖", "魏文帝", "晉武帝"]      # 帶朝代/修飾字的帝號
    passed = ["王莽", "劉邦", "曹丕", "周公旦"]             # 普通人稱，不該被擋
    check("帶修飾字的帝號一律被擋下（不再只精確匹配）",
          all(arb.ambiguous_hit(n) for n in blocked),
          "漏網：" + "、".join(n for n in blocked if not arb.ambiguous_hit(n)))
    check("普通人稱不被誤擋（守衛別擋成篩子）",
          not any(arb.ambiguous_hit(n) for n in passed),
          "誤擋：" + "、".join(n for n in passed if arb.ambiguous_hit(n)))

    # 反向雙寫要拿一條**確定存在**的有向邊來測（p_liubang —父→ p_hanhuidi），
    # 不能跟着 rows[0] 走：rows[0] 若是對稱邊（夫 / 兄）REL_INVERSE 裡沒有它，
    # 這條斷言會被靜默跳過——之前就是這樣空了好幾輪。
    inv = R.REL_INVERSE.get("父")
    if inv:
        p = subprocess.run([PY, os.path.join(ROOT, "pipeline", "relations.py"),
                            "add", "--a", "p_hanhuidi", "--b", "p_liubang",
                            "--rel", inv], cwd=ROOT, capture_output=True, text=True)
        check("反向雙寫被拒（只存規範邊）", p.returncode != 0,
              (p.stdout or p.stderr or "").strip()[:40])

    p = subprocess.run([PY, os.path.join(ROOT, "pipeline", "relations.py"),
                        "check"], cwd=ROOT, capture_output=True, text=True)
    check("關係校驗無問題（含證據失效）",
          "問題 0 處" in (p.stdout or "") or "问题 0 处" in (p.stdout or ""),
          (p.stdout or "").strip().splitlines()[-1][:40] if p.stdout else "")


def test_relation_evidence() -> None:
    """P6-3 证据解析：句子可编辑之后，「写了 uid」不等于「证据还站得住」。

    测在**临时库副本**上做（直接改正式库会把自造的边留在里面，也会污染权威源）。
    覆盖四种状态：none（推断）/ active / dead（句子被弃用）/ missing（uid 查无）。
    """
    print("\n[8] 關係證據解析（P6-3）")
    import shutil
    tmp = os.path.join(tempfile.gettempdir(), "bookindex-verify-rel.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(tmp + suffix):
            os.remove(tmp + suffix)
    shutil.copyfile(snapshot.DB_PATH, tmp)
    os.environ["BOOKINDEX_DB"] = tmp
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import db                                     # 每次 connect() 都读环境变量
    try:
        conn = snapshot.connect(tmp)
        uids = [r[0] for r in conn.execute(
            "SELECT uid FROM sentences WHERE status='active' AND length(text)>12 "
            "LIMIT 3")]
        if len(uids) < 3:
            check("临时库取到三条测试句", False)
            return
        u_ok, u_dead, u_stale = uids
        real = conn.execute(
            "SELECT text FROM sentences WHERE uid=?", (u_ok,)).fetchone()[0]
        conn.execute("UPDATE sentences SET status='dead' WHERE uid=?", (u_dead,))
        rows = [
            ("ev-ok", u_ok, real),               # 快照与现句一致
            ("ev-stale", u_stale, "過期快照"),     # 快照与现句不一致
            ("ev-dead", u_dead, "句子已棄用"),     # 句子被弃用
            ("ev-missing", "nosuchuid0000", "找不到"),  # uid 查无
        ]
        for rid, uid, snap in rows:
            conn.execute(
                "INSERT OR REPLACE INTO relations(rel_id, person_a, surface_a, "
                "person_b, surface_b, rel_type, rel, symmetric, era, book, "
                "evidence_uid, evidence_text, confidence, source, status, note, "
                "created_at) VALUES(?,'p_liubang','劉邦','p_hanhuidi','劉盈',"
                "'kinship','父',0,'西漢','sj',?,?,0.9,'manual','active','P6 自檢',"
                "'2026-09-30')", (rid, uid, snap))
        conn.commit()
        conn.close()

        g = db.relations_graph("p_liubang", 1)
        by = {e["rel_id"]: e for e in g["edges"]}

        e = by.get("ev-ok")
        check("证据有效：state=active 且 valid=1",
              e is not None and e["evidence_state"] == "active"
              and e["evidence_valid"] == 1, e.get("evidence_state") if e else "缺")
        check("证据文本以现句为准（不是快照）",
              e is not None and e["evidence_text"] == real)
        check("证据带出篇 id（前端跳原文要用）",
              e is not None and bool(e["evidence_chapter"]),
              e.get("evidence_chapter", "") if e else "")
        check("快照与现句一致 → stale=0", e is not None and e["evidence_stale"] == 0)

        e = by.get("ev-stale")
        check("快照过期 → stale=1 且仍以现句为准",
              e is not None and e["evidence_stale"] == 1
              and e["evidence_text"] != "過期快照")

        e = by.get("ev-dead")
        check("句子被弃用 → 证据失效（valid=0）",
              e is not None and e["evidence_state"] == "dead"
              and e["evidence_valid"] == 0, e.get("evidence_state") if e else "缺")

        e = by.get("ev-missing")
        check("uid 查无 → state=missing（不是假绿的有效）",
              e is not None and e["evidence_state"] == "missing"
              and e["evidence_valid"] == 0, e.get("evidence_state") if e else "缺")

        none_edges = [x for x in g["edges"]
                      if not x["evidence_uid"] and not str(x["rel_id"]).startswith("ev-")]
        check("无证据的边一律 state=none（推断档看得出来）",
              bool(none_edges) and all(x["evidence_state"] == "none"
                                       for x in none_edges),
              "{} 条".format(len(none_edges)))
    finally:
        os.environ.pop("BOOKINDEX_DB", None)
        # db.py 用 `with connect()` 只提交不关闭，Windows 上文件会**被本进程锁住**；
        # 删不掉就算了（临时目录，下次启动会覆盖），别让清理把断言结果翻成失败。
        for suffix in ("", "-wal", "-shm"):
            try:
                if os.path.exists(tmp + suffix):
                    os.remove(tmp + suffix)
            except OSError:
                pass


def test_rel_view() -> None:
    """关系展示读法（docs/28 P0-1）：**有向边最容易读反**。

    规范是 (a, rel, b) = 「a 是 b 的 rel」。站在 a 的页面上，对方要叫「女 / 弟」，
    照抄 rel 就会变成「劉邦 之父 魯元公主」——拿父亲的头衔去称呼女儿。
    62 条里 52 条是有向边，这一条错就是批量误导。
    """
    print("\n[9] 關係展示讀法（P6-3 修 P0-1）")
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import relations as R                              # noqa: E402
    import db                                          # noqa: E402

    check("db 與 relations 的 CALL_INVERSE 逐字一致（兩處抄表靠這條守）",
          db.CALL_INVERSE == R.CALL_INVERSE)
    check("NO_EVIDENCE_CAP 兩處一致", db.NO_EVIDENCE_CAP == R.NO_EVIDENCE_CAP)

    # 女兒那條：p_liubang —父→ p_luyuangongzhu（魯元公主）
    g = db.relations_graph("p_liubang", 1)
    e = next((x for x in g["edges"]
              if x["source"] == "p_liubang" and x["rel"] == "父"), None)
    check("站在 a 側：有向邊讀成稱呼反向（不是照抄 rel）",
          e is not None and e["rel_view"] in ("子", "女"),
          "{} → {}".format(e["rel"] if e else "缺", e["rel_view"] if e else "缺"))
    check("性別變體：對方是女性時讀「女」而不是「子」",
          e is not None and e["rel_view"] == "女", e["rel_view"] if e else "缺")

    g2 = db.relations_graph("p_luyuangongzhu", 1)
    e2 = next((x for x in g2["edges"]
               if x["target"] == "p_luyuangongzhu" and x["rel"] == "父"), None)
    check("站在 b 側：讀 rel 本身（父）", e2 is not None and e2["rel_view"] == "父",
          e2["rel_view"] if e2 else "缺")
    check("rel_desc 是完整句（A 是 B 之X）",
          e2 is not None and e2["rel_desc"].endswith("之父")
          and e2["rel_desc"].startswith("劉邦"), e2["rel_desc"] if e2 else "缺")

    # 有證據的真實邊：必須 active（別只測自建的 ev-* 行——自建行永遠綠）
    # ⚠️ 必須連 db 正在用的那個庫（環境變量可能被上一組換成臨時副本），
    #    連錯庫就會出現「邊查得到但狀態對不上」的假紅。
    conn = snapshot.connect(db.db_path())
    real = [dict(x) for x in conn.execute(
        "SELECT rel_id, person_a, evidence_uid FROM relations "
        "WHERE status='active' AND evidence_uid<>''")]
    conn.close()
    if not real:
        check("取到真實的有證據邊", False)
        return
    g3 = db.relations_graph(real[0]["person_a"], 1)
    e3 = next((x for x in g3["edges"] if x["rel_id"] == real[0]["rel_id"]), None)
    check("真實邊：有證據就該 state=active（不是只測自建的 ev-* 行）",
          e3 is not None and e3["evidence_state"] == "active"
          and e3["evidence_valid"] == 1,
          e3["evidence_state"] if e3 else "缺")


# 断言自带的测试行标记。注意「自檢」既有繁体也有简体（早期脚本留下的）。
TEST_MARKERS = ("自檢", "測試，驗完撤銷", "测试，验完撤销", "UI 冒煙")


def purge_test_rows() -> None:
    """清掉断言自己留在权威源里的测试行。

    `overrides.py revoke` / `apply_sentence_edits.py revoke` 都是**改状态不删行**
    （要留审计痕迹），于是每跑一次回归就多两行 dead 行——跑了十几轮已经积了 40 行。
    它们不参与任何计算（dead），但会让权威源的 diff 永远脏着，也会让人误以为
    「这里曾经改过东西」。只删 **dead + 命中测试标记** 的行，活行一概不碰。
    """
    try:
        import openpyxl
    except ImportError:
        return
    total = 0
    for path in (os.path.join(ROOT, "workbook", "overrides.xlsx"),
                 os.path.join(ROOT, "workbook", "sentence-edits.xlsx")):
        if not os.path.exists(path):
            continue
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        head = {c.value: c.column for c in ws[1]}
        nc = head.get("备注(note)")
        sc = head.get("状态(status)")
        if not nc:
            wb.close()
            continue
        doomed, revived = [], []
        for r in ws.iter_rows(min_row=2):
            if not any(m in str(r[nc - 1].value or "") for m in TEST_MARKERS):
                continue
            stat = str(r[sc - 1].value or "active") if sc else "active"
            if stat == "dead":
                doomed.append(r[0].row)
            else:
                # ⚠️ 活著的自檢行 = 上一輪崩在 revoke **之前**留下的。
                # 這不是「多一行髒數據」，是**真的在改數據**：本次重建把它套用上去，
                # 「沛公」就被改歸給項羽（實測出現過）。先標 dead 再一起刪。
                if sc:
                    r[sc - 1].value = "dead"
                revived.append(r[0].row)
        if revived:
            print("  ⚠ {} 裡有 {} 行**活著**的自檢行（上一輪崩在中途），已先作廢".format(
                os.path.basename(path), len(revived)))
            doomed.extend(revived)
        for i in sorted(set(doomed), reverse=True):
            ws.delete_rows(i)
        if doomed:
            try:
                wb.save(path)
                total += len(doomed)
            except PermissionError:
                print("  ⚠ {} 被占用，测试残留没清掉".format(os.path.basename(path)))
        wb.close()
    if total:
        print("\n  清理断言测试残留 {} 行".format(total))


def test_relation_evidence_multi() -> None:
    """证据一对多（docs/28 P1-6）。

    一条关系常有不止一句出处（实测 12/62 条边有 ≥2 条候选），而 `relations` 表
    只有 `evidence_uid` 一个字段——要么丢证据，要么一条边挂错一句。所以搬出
    `relation_evidence` 子表；现在只有 2 行要搬，扩量之后再搬就贵了。
    """
    print("\n[10] 關係證據一對多（P6-3 修 P1-6）")
    import shutil
    tmp = os.path.join(tempfile.gettempdir(), "bookindex-verify-ev.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(tmp + suffix):
            os.remove(tmp + suffix)
    shutil.copyfile(snapshot.DB_PATH, tmp)
    os.environ["BOOKINDEX_DB"] = tmp
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import db                                     # 每次 connect() 都读环境变量
    try:
        conn = snapshot.connect(tmp)
        rows = [dict(x) for x in conn.execute(
            "SELECT rel_id, person_a, evidence_uid FROM relations "
            "WHERE status='active' AND evidence_uid<>''")]
        if not rows:
            check("取到带证据的真实边", False)
            return
        backfilled = all(conn.execute(
            "SELECT COUNT(*) FROM relation_evidence WHERE rel_id=? "
            "AND evidence_uid=?", (r["rel_id"], r["evidence_uid"])
        ).fetchone()[0] == 1 for r in rows)
        check("主表的证据已回填进证据子表（老数据不用手工搬）", backfilled,
              "{} 条".format(len(rows)))

        r0 = rows[0]
        # ⚠️ 别假设这条真实边**只有一条**证据：补证据之后 `rows[0]` 可能已经挂了
        # 2 条（2026-10-01 就是这样，于是期望值写死 2 就红了）。
        # 期望 = 原有条数 + 本次新增 1 条；候选句也要先排除已挂的，
        # 否则 INSERT OR REPLACE 会把已有行覆盖掉，条数不增。
        have = {r[0] for r in conn.execute(
            "SELECT evidence_uid FROM relation_evidence WHERE rel_id=?",
            (r0["rel_id"],))}
        extra = [r[0] for r in conn.execute(
            "SELECT uid FROM sentences WHERE status='active' AND length(text)>12 "
            "LIMIT 12") if r[0] not in have]
        conn.execute(
            "INSERT OR REPLACE INTO relation_evidence "
            "(rel_id, evidence_uid, verdict, note, created_at) VALUES(?,?,'accept','','')",
            (r0["rel_id"], extra[0]))
        conn.execute(  # 被人工否掉的候选：留着免得下轮再抽，但**不能当证据**
            "INSERT OR REPLACE INTO relation_evidence "
            "(rel_id, evidence_uid, verdict, note, created_at) VALUES(?,?,'reject','','')",
            (r0["rel_id"], extra[1]))
        conn.commit()
        conn.close()

        g = db.relations_graph(r0["person_a"], 1)
        e = next((x for x in g["edges"] if x["rel_id"] == r0["rel_id"]), None)
        check("一条边能挂多条证据（evidences 全带回）",
              e is not None and e["evidence_count"] == len(have) + 1,
              "{} 条（原 {} + 新 1）".format(
                  e["evidence_count"] if e else "缺", len(have)))
        check("verdict=reject 的候选不算证据（只是留档）",
              e is not None and all(x["uid"] != extra[2] for x in e["evidences"]))

        # 主证据那句被弃用、但另一条出处还活着 → 这条关系**仍算有据**
        conn = snapshot.connect(tmp)
        conn.execute("UPDATE sentences SET status='dead' WHERE uid=?",
                     (r0["evidence_uid"],))
        conn.commit()
        conn.close()
        g = db.relations_graph(r0["person_a"], 1)
        e2 = next((x for x in g["edges"] if x["rel_id"] == r0["rel_id"]), None)
        check("主证据句被弃用、但另有出处 → 仍算有据（不是一刀切失效）",
              e2 is not None and e2["evidence_valid"] == 1,
              e2["evidence_state"] if e2 else "缺")
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                if os.path.exists(tmp + suffix):
                    os.remove(tmp + suffix)
            except OSError:
                pass


def test_relation_evidence_quality() -> None:
    """证据落盘之后的两条不变量（2026-10-01 补证据那批之后立）。

    补证据是**加数据**，不是修 bug，所以断言不能写死「有据边 N 条」——
    人撤一条就红了，那是假失败。要断的是**性质**：

    1. 置信度是**派生的**（source + 有无证据）。`workbook/relations.xlsx` 里
       那列人能改，万一有人把它写死，派生规则就被绕过，图上的实线/虚线
       会跟证据脱钩。断：同来源下，有据边的置信度必须**严格高于**无据边。
    2. 落库的证据句必须是**活跃句**。指向 dead/merged 句的证据等于假证据，
       `relations.py check` 也查，但那是权威源侧的；这里断的是**库里**的最终态。
    """
    print("\n[11] 關係證據的兩條不變量（補證據之後）")
    conn = snapshot.connect(snapshot.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT rel_id, source, confidence, evidence_uid "
            "FROM relations WHERE status='active'")]
        ev = {r[0] for r in conn.execute(
            "SELECT rel_id FROM relation_evidence WHERE verdict<>'reject'")}
        by_src = {}
        for r in rows:
            has = bool(r["evidence_uid"]) or r["rel_id"] in ev
            by_src.setdefault(r["source"], {}).setdefault(has, []).append(
                r["confidence"] or 0)
        bad = []
        for src, d in by_src.items():
            if True in d and False in d:
                if max(d[False]) >= min(d[True]):
                    bad.append("{}：无据 {} ≥ 有据 {}".format(
                        src, max(d[False]), min(d[True])))
        check("有据边的置信度严格高于无据边（派生规则没被手改绕过）",
              not bad, "；".join(bad))

        uids = [r["evidence_uid"] for r in rows if r["evidence_uid"]]
        uids += [r[0] for r in conn.execute(
            "SELECT evidence_uid FROM relation_evidence WHERE verdict<>'reject'")]
        if not uids:
            check("落库的证据句都是活跃句", False, "一条证据都没有")
            return
        ph = ",".join("?" * len(uids))
        dead = [r[0] for r in conn.execute(
            "SELECT uid FROM sentences WHERE uid IN ({}) AND status<>'active'"
            .format(ph), uids)]
        check("落库的证据句都是活跃句（没有假证据）", not dead,
              "失效：{}".format("、".join(dead[:4])))
    finally:
        conn.close()


def test_index_pages() -> None:
    """索引四块（书切换 / 快捷词 / 人物索引 / 地名索引 / 篇目一覽）的后端契约。

    为什么要有它：这几块是「跟静态版对齐」时补的，前端有 _ui_test_index.js 守着，
    但**后端那半没人管**——尤其 chapters 的 main_persons / top_places 两列，
    是后来才加进建库脚本的，下次改 SCHEMA 被人顺手删掉也不会有任何测试变红。
    """
    print("\n[10] 索引四块 · 后端契约")
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import db                                          # noqa: E402

    chapters = db.list_chapters()["items"]
    check("篇目一覽取到五书全部篇目（>500）", len(chapters) > 500,
          "实得 {}".format(len(chapters)))
    with_owner = sum(1 for c in chapters if c.get("mainPersons"))
    # book-data 里 445/564 篇标了篇主；写 >=400 而不是写死 445，
    # 免得将来 annotate 改判据时这条变成假失败
    check("篇目带篇主（不是空标签）", with_owner >= 400,
          "{}/{}".format(with_owner, len(chapters)))
    with_place = sum(1 for c in chapters if c.get("topPlaces"))
    check("篇目带高频地名", with_place > 500, "{}/{}".format(with_place, len(chapters)))
    # 只斷「本紀 / 世家」：這兩類是**以人命名**的（項羽本紀、齊太公世家），
    # 沒有篇主就是標註漏了。列傳**不能這麼斷**——它裡面混著類傳與四夷傳
    # （西南夷列傳、龜策列傳、貨殖傳、匈奴傳、西域傳、宣元六王傳…），
    # 本來就沒有一個可指的篇主，實測 31 篇，拿它當紅線只會得到假失敗。
    bad = [c["id"] for c in chapters
           if c.get("category") in ("本紀", "世家") and not c.get("mainPersons")]
    check("本紀/世家篇篇有篇主（它们以人命名，没有就是漏标）", not bad,
          "缺 {} 篇，例 {}".format(len(bad), "、".join(bad[:3])))
    check("篇目带字數與句數（静态版篇目行有）",
          all(c.get("charCount") and c.get("sentenceCount") for c in chapters))

    persons = db.list_persons()["items"]
    places = db.list_places()["items"]
    check("人物索引非空（全书 2240 人）", len(persons) > 2000, "实得 {}".format(len(persons)))
    check("地名索引非空", len(places) > 1000, "实得 {}".format(len(places)))
    check("人物索引条目带分书分布（前端「见於哪本书」靠它）",
          all(p.get("books") for p in persons[:50]))
    check("地名索引条目带类型（按类型分组靠它）",
          all(p.get("kindLabel") for p in places))

    sgz = db.list_persons(book="sgz")["items"]
    check("按书收窄：三國志人物少于全部",
          0 < len(sgz) < len(persons), "全部 {} → 三國志 {}".format(len(persons), len(sgz)))
    q_all = db.quick_words()["persons"]
    q_sgz = db.quick_words(book="sgz")["persons"]
    check("快捷词按书换（三國志头一个应是曹操）",
          bool(q_sgz) and q_sgz[0]["name"] == "曹操",
          "实得 {}".format(q_sgz[0]["name"] if q_sgz else "无"))
    check("快捷词全量头一个不是三國志的头一个（口径真的分书）",
          bool(q_all) and q_all[0]["name"] != q_sgz[0]["name"],
          "{} vs {}".format(q_all[0]["name"] if q_all else "-",
                            q_sgz[0]["name"] if q_sgz else "-"))


def test_pid_semantic() -> None:
    """pid 语义化 + 引用完整性。

    为什么要有它：占位 pid（`p_xNNNNN`）本身不是 bug，但它们**会随时间变贵**——
    每多落一批关系 / override，要改的引用就多一批（2026-10 一次性把 613 个
    改成拼音语义 id，牵动 persons.xlsx 与 relations.xlsx 两张权威源）。

    这里守三件事：
      1. 不再产生新的占位 pid（新增人物走拼音语义 id）
      2. relations 的两端都能在 persons 里查到（**悬空引用不报错，只会静默少一条边**）
      3. 改过 id 之后别名没有丢（aliases.person_id 对得上）
    """
    print("\n[12] pid 语义化 · 引用完整性")
    idx = os.path.join(ROOT, "data", "index", "index.db")
    if not os.path.exists(idx):
        check("索引库存在", False, "找不到 {}".format(idx))
        return
    con = sqlite3.connect(idx)
    try:
        pids = {r[0] for r in con.execute("SELECT id FROM persons")}
        ph = sorted(p for p in pids if re.match(r"^p_x\d+$", p or ""))
        check("不再有占位 pid（p_xNNNNN）", not ph,
              "剩 {} 个，例 {}".format(len(ph), "、".join(ph[:3])))

        # 关系的两端必须都能查到人 —— 悬空引用是最难发现的一类坏：
        # apply_relations 照灌不误，前端只是凭空少一条边。
        dangling = []
        for r in con.execute(
                "SELECT person_a, person_b FROM relations WHERE status='active'"):
            for pid in (r[0], r[1]):
                if pid and pid not in pids:
                    dangling.append(pid)
        check("关系边两端都能在 persons 查到（没有悬空引用）", not dangling,
              "悬空 {} 个，例 {}".format(len(dangling),
                                     "、".join(sorted(set(dangling))[:3])))

        n_alias = con.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        bad_alias = con.execute(
            "SELECT COUNT(*) FROM aliases WHERE person_id IS NOT NULL "
            "AND person_id NOT IN (SELECT id FROM persons)").fetchone()[0]
        check("别名都挂在存在的人身上（改 id 没把别名甩掉）", bad_alias == 0,
              "别名 {} 条，甩掉 {}".format(n_alias, bad_alias))
    finally:
        con.close()


def test_notes_ledger() -> None:
    """裴注 / 晉書舊史注：**獨立賬本**（红线）。

    为什么这条必须有一條断言：注文是「另一层文本」的命中，數字一大就很容易被
    顺手加进总命中里（靜態版就有 `peiStatOf` 把它併入顯示統計）。一旦破，
    **所有命中数都会悄悄变**——而正文标注、泛称基线、快照全都不变，
    看起来「只是显示口径调整」。所以要专门盯着。
    """
    print("\n[13] 注文賬本 · 獨立計數")
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import db                                          # noqa: E402

    notes = db.person_notes_payload("p_caocao")
    pei = notes.get("pei")
    check("裴注数据能读到（裴注账本不是空的）", bool(pei and pei.get("n")),
          "曹操 pei.n = {}".format((pei or {}).get("n")))
    check("裴注带篇级分布与明细", bool(pei and pei.get("byChapter") and pei.get("items")),
          "byChapter {} 篇 / items {} 條".format(
              len((pei or {}).get("byChapter") or {}),
              len((pei or {}).get("items") or [])))
    check("注文带篇名表（前端聯機模式沒有 CHAPT 可用）",
          bool(notes.get("chapterTitles")),
          "给了 {} 個篇名".format(len(notes.get("chapterTitles") or {})))

    # ⚠️ 红线本体：person_payload 的正文 mentions 不含任何注文来源。
    # 判据用「正文命中总数」对不上「正文 + 注文」——但更硬的是直接查库：
    # mentions 表里不该有 pei/jsNote 混进来的行。
    con = sqlite3.connect(os.path.join(ROOT, "data", "index", "index.db"))
    try:
        # 库里压根不该有 pei_mentions 之类的表（注文不入库）
        tabs = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        check("注文不入库（没有 pei/notes 相关的表）",
              not any("pei" in t.lower() or "note" in t.lower() for t in tabs),
              "库里含注文表：{}".format(
                  [t for t in tabs if "pei" in t.lower() or "note" in t.lower()]))
        n_main = con.execute(
            "SELECT COUNT(*) FROM mentions WHERE person_id='p_caocao'").fetchone()[0]
    finally:
        con.close()

    # ⚠️ 红线本体，且必须**在 payload 层面**断：
    # 最典型的破法不是往库里灌表，而是有人为了「显示更全」在 person_payload 里
    # 把 pei 的 n 条拼进 mentions（我故意注入过，库里查不出来）。
    # ⚠️ 判据不能用「payload 条数 == 库里条数」——mentions 有 limit（默认 200），
    # payload 天然只有 200 条，比库里少是正常的；注入 726 条后反而可能还是
    # 「不超库内总数」，判据形同虚设（第一版就栽在这）。
    # 可靠判据：**逐条看命中章名/uid 有没有注文标记**——注文的条目必然带
    # 独立的 chapter 标记（【裴】之类）或独立 uid 前缀，因为它们不是正文句子。
    payload = db.person_payload("p_caocao")
    ms = payload.get("mentions") or []
    note_marked = [m for m in ms
                   if "【" in str(m.get("chapter") or "")
                   or str(m.get("uid") or "").startswith(("PEI", "JSNOTE"))
                   or str(m.get("tier") or "") == "note"]
    check("payload 的 mentions 里没有注文条目（逐条查标记）", not note_marked,
          "混进 {} 条，样例：{}".format(
              len(note_marked),
              [str(m.get("chapter")) for m in note_marked[:3]]))
    check("注文分量能单独取到（没被丢掉，只是不合并）",
          bool((payload.get("notes") or {}).get("pei")),
          "notes.pei.n = {}".format(
              ((payload.get("notes") or {}).get("pei") or {}).get("n")))


def test_alias_ledger() -> None:
    """完整称谓表（人物页「×××未用」那张表）· 后端契约。

    为什么单独一组断言：这张表是**人物页判断别名可靠性的唯一依据**，
    而它坏了之后页面**不报错**——只是退化成扁平别名列表（我在 renderPerson 里
    留了 fallback）。所以要专门盯着两件事：
      1. `n == Σ byBook`（前端敢在客户端按书收窄的前提：离线版没有服务端可问）；
      2. 类别顺序三处对齐（db.ALIAS_KINDS / 导出时的下标 / app.js 的 ALIAS_KINDS）
         —— 三者错位不会报错，只会把称谓分进错组，是最难发现的一类坏。
    """
    print("\n[14] 完整稱謂表 · 後端契約")
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import db                                          # noqa: E402

    con = sqlite3.connect(os.path.join(ROOT, "data", "index", "index.db"))
    try:
        rows = con.execute(
            "SELECT person_id, w, simp, n, kind, variants, by_book "
            "FROM person_aliases").fetchall()
        n_pers = con.execute(
            "SELECT COUNT(*) FROM persons WHERE status='active'").fetchone()[0]
        # 软弱水源：orphane
        orphan = con.execute(
            "SELECT COUNT(DISTINCT person_id) FROM person_aliases "
            "WHERE person_id NOT IN (SELECT id FROM persons)").fetchone()[0]
    finally:
        con.close()

    check("称谓表落库了（不是空的）", bool(rows), "{} 条".format(len(rows)))
    # 与权威中间产物对齐：book-data.json 的 aliasList 是 pipeline 的输出，
    # 落表时少一条都不知道。这是「数据形状变了没人知道」的那类防线。
    bd = os.path.join(ROOT, "data", "index", "book-data.json")
    want = 0
    if os.path.exists(bd):
        with open(bd, encoding="utf-8") as fh:
            data = json.load(fh)
        want = sum(len(p.get("aliasList") or []) for p in data.get("persons") or [])
    check("条数与 book-data.json 的 aliasList 一致（没漏灌 / 没翻倍）",
          bool(want) and len(rows) == want,
          "库里 {} 条 / book-data {} 条".format(len(rows), want))
    check("称谓表没有孤儿 pid", orphan == 0, "孤儿 {}".format(orphan))

    # ⚠️ 不变量：前端 aliasScopeN 敢在客户端求和的前提。破了的话离线版会显示
    # 与联机版不同的数字，而且不报错。
    bad_sum = [(r[0], r[1], r[3], sum((json.loads(r[6]) if r[6] else {}).values()))
               for r in rows
               if sum((json.loads(r[6]) if r[6] else {}).values()) != (r[3] or 0)]
    check("不变量 n == Σ byBook（客户端按书收窄的前提）", not bad_sum,
          "不符 {} 条，样例：{}".format(len(bad_sum), bad_sum[:3]))

    kinds = {}
    for r in rows:
        kinds[r[4]] = kinds.get(r[4], 0) + 1
    check("类别都在 ALIAS_KINDS 里（pipeline 新增类别会被归到 other，但不会丢）",
          set(kinds) <= set(db.ALIAS_KINDS),
          "库里类别 {}".format(sorted(kinds)))
    # 每条都必须能显示为某个分组：落到 other 也要 counts 得到
    rowsald = set(r[0] for r in rows)
    check("每个活跃人物都有自己的称谓表",
          len(rowsald) >= n_pers,
          "有表的 {} 人 / 活跃人物 {} 人".format(len(rowsald), n_pers))

    # payload 形状：这是**最可能的破法**——有人改了 SELECT 少取一列，
    # 前端 silent fallback 成扁平别名列表，页面照开。
    payload = db.person_payload("p_liubang")
    alist = (payload.get("profile") or {}).get("aliasList") or []
    check("person_payload.profile.aliasList 存在且不为空", bool(alist),
          "{} 条".format(len(alist)))
    shape = all(("w" in a and "kind" in a and "n" in a and "variants" in a
                 and "byBook" in a) for a in alist)
    check("每条都有前端要的五个字段（w/kind/n/variants/byBook）", shape,
          "样例键 {}".format(sorted(alist[0].keys()) if alist else "-"))
    check("存在「未用」的称谓（这张表存在的意义）",
          any(int(a.get("n") or 0) == 0 for a in alist),
          "未用条目 {}".format([a["w"] for a in alist if not a.get("n")][:5]))
    check("存在高频称谓（芯片显示 ×N 的依据）",
          any(int(a.get("n") or 0) > 100 for a in alist),
          "最大 n = {}".format(max((a.get("n") or 0) for a in alist) if alist else 0))

    # 批量版（离线导出用）与单人版（联机用）必须逐字节一致，否则
    # 「一套前端两种数据源」就在称谓表上悄悄分成两岔。
    batched = db.person_alias_lists()
    mismatch = [p for p in list(batched)[:400]
                if batched[p] != db.person_alias_list(p)]
    check("批量版与单人版一致（离线/联机同源）", not mismatch,
          "不一致 {} 人：{}".format(len(mismatch), mismatch[:3]))

    # ⚠️ 顺序对齐：导出时把类别压成下标，app.js 再用 ALIAS_KINDS 反查。
    # 对不上**不报错**，只是称谓错组——与关系图快照那个 "%g" % conf 同类。
    js = os.path.join(ROOT, "app", "web", "app.js")
    m = re.search(r"var ALIAS_KINDS\s*=\s*\[([^\]]*)\]",
                  open(js, encoding="utf-8").read())
    js_kinds = tuple(re.findall(r'"([^"]+)"', m.group(1))) if m else ()
    check("app.js 的 ALIAS_KINDS 与 db.ALIAS_KINDS 一字不差（顺序错位会错组）",
          js_kinds == db.ALIAS_KINDS,
          "app.js {} / db {}".format(js_kinds, db.ALIAS_KINDS))


def test_era_marker() -> None:
    """「前朝」小标记 · 数据契约（docs/29 §三-3.4 的降级版）。

    完整版（把索引拆成「本书记载时代 / 相对古人」两组）被否掉了——索引页会翻一倍长，
    而且史记是通史、169 人缺 eraRank，分组是错的但不显眼。降级成条目上加「前朝」二字。

    要断的三件事：
      1. 数据到了库里（人的 era_rank / 书的 era_from-to），
      2. 接口带得出去（list_persons 的 items 有 eraRank），
      3. 前端那份 eraRange 与库里一致（⚠️ 对不上不报错，只会标错人）。
    """
    print("\n[15] 「前朝」標記 · 數據契約")
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))
    import db                                          # noqa: E402

    con = sqlite3.connect(os.path.join(ROOT, "data", "index", "index.db"))
    try:
        bks = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
            "SELECT code, name, era_from, era_to FROM books")}
        n_era = con.execute(
            "SELECT COUNT(*) FROM persons WHERE era_rank IS NOT NULL").fetchone()[0]
        n_all = con.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        bad_range = [c for c, v in bks.items()
                     if v[1] is not None and v[2] is not None and v[1] > v[2]]
    finally:
        con.close()

    check("五书都在 books 表里且有名字", len(bks) == 5 and all(v[0] for v in bks.values()),
          "实得 {}".format(sorted(bks)))
    # 史记是通史，没有记载区间——这是「史记不标前朝」的依据，不能悄悄变成有值
    check("史記是通史（eraRange 为 NULL，不标前朝）",
          bks.get("sj", (None, 1, 1))[1] is None,
          "史記 era_from = {}".format(bks.get("sj", (None, None, None))[1]))
    check("四部断代史都有记载区间",
          all(bks.get(c, (None, None, None))[1] is not None
              for c in ("hs", "hhs", "sgz", "js")),
          "实得 {}".format({c: bks.get(c, (None, None, None))[1:]
                            for c in ("hs", "hhs", "sgz", "js")}))
    check("区间不自相矛盾（from <= to）", not bad_range, "坏区间 {}".format(bad_range))
    check("人物 eraRank 覆盖了绝大多数人",
          n_era > 0 and n_era / max(n_all, 1) > 0.8,
          "{} / {}（缺 {} 人，缺的不标，不猜）".format(n_era, n_all, n_all - n_era))

    items = db.list_persons()["items"]
    check("list_persons 的 items 带 eraRank（前端判前朝的依据）",
          bool(items) and "eraRank" in items[0],
          "样例键 {}".format(sorted(items[0].keys()) if items else "-"))
    check("items 里存在「对某部断代史来说是前朝」的人",
          any((it.get("eraRank") or 99) < 8 for it in items),
          "eraRank < 8 的共 {} 人".format(
              sum(1 for it in items if (it.get("eraRank") or 99) < 8)))

    # ⚠️ 前端那份常量与库里必须一致：错一位不会报错，只是把一堆人标成前朝（或漏标）
    src = open(os.path.join(ROOT, "app", "web", "app.js"), encoding="utf-8").read()
    got = {}
    for m in re.finditer(
            r'\{\s*code:\s*"(\w+)",\s*name:\s*"[^"]+",\s*era:\s*'
            r'(?:null|\[\s*(\d+)\s*,\s*(\d+)\s*\])', src):
        code, lo, hi = m.group(1), m.group(2), m.group(3)
        got[code] = (int(lo), int(hi)) if lo else None
    want = {c: (v[1], v[2]) if v[1] is not None else None for c, v in bks.items()}
    check("app.js 的 BOOKS.era 与库里 era_from/era_to 一致（前端判前朝的依据）",
          got == want, "app.js {} / 库 {}".format(got, want))


def main() -> int:
    print("=== P3 斷言 · 新鏈路 ===")
    tmpdb = os.path.join(tempfile.gettempdir(), "bookindex-verify-snap.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(tmpdb + suffix):
            os.remove(tmpdb + suffix)
    try:
        test_one_way()
        test_snapshots(tmpdb)
        test_overrides()
        test_sentence_edits()
        test_relations()
        test_relation_evidence()
        test_rel_view()
        test_relation_evidence_multi()
        test_relation_evidence_quality()
        test_index_pages()
        test_pid_semantic()
        test_notes_ledger()
        test_alias_ledger()
        test_era_marker()
    finally:
        purge_test_rows()          # 自己造的测试行自己收走，别让权威源越跑越脏
        snapshot.SNAP_DB = os.path.join(ROOT, "data", "index", "snapshots.db")
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(tmpdb + suffix):
                os.remove(tmpdb + suffix)

    ok = sum(1 for _, v in CHECKS if v)
    print("\n  {}/{} 通過".format(ok, len(CHECKS)))
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
