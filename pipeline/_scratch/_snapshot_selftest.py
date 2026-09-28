# -*- coding: utf-8 -*-
"""一次性：用合成數據驗證 diff 的四類判定（不碰權威源 xlsx）。

做法：dump 一份基準快照，再造一份「被改過的」——
  · 把 5 條 p_xiangyu 的歸屬改成 p_liubang   → 期望 pid_changed = 5
  · 刪掉 3 條命中                            → 期望 removed = 3
  · 新增 2 條語料裡本來就有的命中（改 pid 偽造）→ 期望 added = 2
最後把自己造的快照與 diff 記錄清掉，不留痕。

用法：python pipeline/_scratch/_snapshot_selftest.py
"""
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = HERE                                   # pipeline/_scratch
PIPELINE = os.path.dirname(SCRATCH)              # pipeline
ROOT = os.path.dirname(PIPELINE)                 # 根目錄
sys.path.insert(0, os.path.join(ROOT, "app", "tools"))
import snapshot   # noqa: E402


def main() -> int:
    base = snapshot.dump(label="selftest-base")
    new = snapshot.dump(label="selftest-new")

    conn = sqlite3.connect(snapshot.SNAP_DB)
    cur = conn.cursor()

    # 改歸 3 條：先取明確的 rowid 再改，別用 LIMIT 子查詢（順序不可控）
    rids = [r[0] for r in cur.execute(
        "SELECT rowid FROM snapshot_mentions "
        "WHERE snapshot_id=? AND pid='p_xiangyu' LIMIT 3", (new,))]
    cur.execute("UPDATE snapshot_mentions SET pid='p_liubang' WHERE rowid IN ({})"
                .format(",".join("?" * len(rids))), rids)
    n_changed = cur.rowcount

    # 消失 2 條：挑沒被上面改過的（否則既算改歸又算消失，期望值對不上）
    rids2 = [r[0] for r in cur.execute(
        "SELECT rowid FROM snapshot_mentions WHERE snapshot_id=? AND pid='p_liubang' "
        "AND rowid NOT IN ({}) LIMIT 2".format(",".join("?" * len(rids))),
        [new] + rids)]
    cur.execute("DELETE FROM snapshot_mentions WHERE rowid IN ({})"
                .format(",".join("?" * len(rids2))), rids2)
    n_removed = cur.rowcount

    # 新增 2 條：拿基準裡沒有的 key 造兩條（改 uid 後綴偽造）
    cur.execute(
        "INSERT INTO snapshot_mentions "
        "(snapshot_id, uid, s, e, surface, pid, tier, chapter_id) "
        "SELECT ?, uid || '-fake' || rowid, s, e, surface, pid, tier, chapter_id "
        "FROM snapshot_mentions WHERE snapshot_id=? LIMIT 2", (new, base))
    n_added = cur.rowcount
    conn.commit()
    conn.close()

    did, counts, rows = snapshot.compute_diff(base, new)
    snapshot.print_diff(did, "快照 #{}".format(base), "快照 #{}".format(new),
                        counts, rows, top=2)
    print("\n合成改動：改歸 {} / 消失 {} / 新增 {}".format(
        n_changed, n_removed, n_added))

    ok = (counts["pid_changed"] == n_changed
          and counts["removed"] == n_removed
          and counts["added"] == n_added
          and counts["tier_changed"] == 0)
    print("判定：{}".format("✓ diff 四類判定正確" if ok else "✗ 與期望不符"))

    # 清理：這兩份是合成數據，別留在歷史裡
    conn = sqlite3.connect(snapshot.SNAP_DB)
    conn.execute("DELETE FROM diff_items WHERE diff_id=?", (did,))
    conn.execute("DELETE FROM diffs WHERE id=?", (did,))
    for sid in (base, new):
        conn.execute("DELETE FROM snapshot_mentions WHERE snapshot_id=?", (sid,))
        conn.execute("DELETE FROM snapshots WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    print("已清理合成快照 #{} / #{}".format(base, new))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
