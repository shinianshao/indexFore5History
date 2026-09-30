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

    with open(BOOK, encoding="utf-8") as f:
        before_drop = _count_mark(json.load(f), uid2, surf2)

    run("app/tools/overrides.py", "apply")
    with open(BOOK, encoding="utf-8") as f:
        d = json.load(f)

    _, m1 = _find_mark(d, uid1, surf1)
    check("reassign 生效（pid 已改）", m1 is not None and m1.get("pid") == "p_xiangyu",
          "pid={}".format(m1.get("pid") if m1 else "—"))
    check("reassign 保留原 tier（只加 override 標記）",
          m1 is not None and m1.get("override") == 1 and m1.get("tier") != "override")

    after_drop = _count_mark(d, uid2, surf2)
    check("drop 生效（命中條數 -1）", after_drop == before_drop - 1,
          "{} → {}（surface={}）".format(before_drop, after_drop, surf2))

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

    conn = snapshot.connect(snapshot.DB_PATH)
    r = conn.execute(
        "SELECT rel, rel_type, confidence, source, status, evidence_uid "
        "FROM relations WHERE status='active' LIMIT 1").fetchone()
    conn.close()
    if not r:
        check("取到一條關係做規則檢查", False)
        return
    rel, rt, conf, src, st, euid = r
    check("rel 在規範詞表內", rel in R.REL_TABLE, rel)
    check("rel_type 由 rel 派生（不手填）", rt == R.REL_TABLE[rel][0],
          "{} → {}".format(rel, rt))
    # 注意：無證據的關係會被壓到推斷檔，所以期望值要帶 evidence 一起算
    check("confidence 由 source + 有無證據派生（不手填）",
          conf == R.derive_confidence(src, bool(euid)),
          "{}（證據 {}） → {}".format(src, "有" if euid else "無", conf))
    check("無證據的關係置信度已壓低", (not euid) and conf <= R.NO_EVIDENCE_CAP,
          "conf={}".format(conf))
    check("status 為 active", st == "active")

    inv = R.REL_INVERSE.get(rel)
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
    finally:
        snapshot.SNAP_DB = os.path.join(ROOT, "data", "index", "snapshots.db")
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(tmpdb + suffix):
                os.remove(tmpdb + suffix)

    ok = sum(1 for _, v in CHECKS if v)
    print("\n  {}/{} 通過".format(ok, len(CHECKS)))
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
