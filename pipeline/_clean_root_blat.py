"""清理仓库根目录的 4 字节临时垃圾文件（临时目录不可用时 Python 吐出的 `blat`）。

判据（四条全中才删，宁可漏删不可误删）：
  1. 位于仓库根目录单层（不递归，不进子目录）
  2. 是普通文件（非目录、非符号链接）
  3. 内容 strip 后等于 `blat`（SQLite 临时文件的魔数）
  4. 未被 git 跟踪（跟踪中的一律不碰）

先写名单到 `_scratch/` 留证，再删；默认预演，`--apply` 才真删。
用法：
    python pipeline/_clean_root_blat.py            # 预演，只报数量
    python pipeline/_clean_root_blat.py --apply    # 真删
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = "blat"
MAX_BYTES = 16  # 4 字节魔数 + 可能的换行；比这大的一律不看


def tracked_in_git() -> set[str]:
    """返回 git 已跟踪的文件名集合（只问根目录，避免全量扫描）。"""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", "."],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[WARN] git ls-files 失败（{exc}），保守起见本轮不删任何文件")
        return {"__all__"}  # 哨兵：非空 → 全部跳过
    if out.returncode != 0:
        print(f"[WARN] git ls-files 返回 {out.returncode}，保守起见本轮不删任何文件")
        return {"__all__"}
    return {p for p in out.stdout.split("\0") if p}


def scan(tracked: set[str]) -> tuple[list[Path], list[tuple[Path, str]]]:
    """扫根目录单层，返回 (可删列表, 跳过列表)。"""
    victims: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for entry in sorted(ROOT.iterdir()):
        try:
            if not entry.is_file() or entry.is_symlink():
                continue
            if entry.stat().st_size > MAX_BYTES:
                continue
            if entry.name in tracked:
                skipped.append((entry, "被 git 跟踪"))
                continue
            try:
                content = entry.read_text(encoding="utf-8", errors="replace").strip()
            except OSError as exc:
                skipped.append((entry, f"读不了：{exc}"))
                continue
            if content == MARK:
                victims.append(entry)
            else:
                skipped.append((entry, f"内容不是 {MARK}：[{content[:20]}]"))
        except OSError as exc:
            skipped.append((entry, f"stat 失败：{exc}"))
    return victims, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="清理根目录 4 字节 blat 临时文件")
    ap.add_argument("--apply", action="store_true", help="真删（默认只预演）")
    args = ap.parse_args()

    tracked = tracked_in_git()
    if "__all__" in tracked:
        print("跳过：无法确认 git 跟踪状态，本轮不删任何文件。")
        return 2

    victims, skipped = scan(tracked)
    print(f"根目录单层小文件：可删 {len(victims)} 个，跳过 {len(skipped)} 个")

    if skipped:
        print("—— 跳过明细（最多列 10 条）——")
        for path, why in skipped[:10]:
            print(f"  {path.name}：{why}")

    if not victims:
        print("没有可删的。")
        return 0

    # 留证：名单写 _scratch/，删错了还能照单恢复
    proof = ROOT / "pipeline" / "_scratch" / "blat_removed.txt"
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text("\n".join(p.name for p in victims) + "\n", encoding="utf-8")

    if not args.apply:
        print(f"预演模式。名单已写 {proof.relative_to(ROOT)}")
        print("加 --apply 真删。")
        return 0

    failed: list[tuple[str, str]] = []
    for path in victims:
        try:
            path.unlink()
        except OSError as exc:
            failed.append((path.name, str(exc)))

    print(f"已删 {len(victims) - len(failed)} / {len(victims)} 个")
    if failed:
        print(f"失败 {len(failed)} 个：")
        for name, why in failed[:10]:
            print(f"  {name}：{why}")
        return 1
    print(f"名单留证：{proof.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
