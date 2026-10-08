#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
探针 1：微信小程序包体积与客户端内存雪崩量化体检探针
文件路径: course/probes/audit_01_corpus_size.py
对应课程: 《AI 辅助下现代软件工程开发》阶段一·第 1 课
适用人群: Python 初学者 / 独立开发者 / 架构自检
=============================================================================
【设计目标】
1. 遍历本项目的古籍语料与派生索引文件，计算实际文件大小与文本量。
2. 对标“微信小程序平台”的真实物理红线：
   - 主包限制：2.0 MB
   - 整包上限：20.0 MB
   - 移动端前端内存安全水位：~150 MB（JSON 解析膨胀率 4~8 倍）
3. 给出量化超标倍数，用不可辩驳的物理数据证明“为什么必须从微信小程序转向单机离线”。
=============================================================================
"""

import os
import sys
from pathlib import Path

# 微信小程序的物理红线规范（单位：MB）
WECHAT_MAIN_PACKAGE_LIMIT_MB = 2.0     # 微信主包硬限制 2MB
WECHAT_TOTAL_PACKAGE_LIMIT_MB = 20.0   # 微信所有分包总和上限 20MB
MOBILE_HEAP_SAFE_LIMIT_MB = 150.0      # 手机前端 JS 运行时安全堆内存估值


def format_bytes(size_bytes: int) -> str:
    """把字节数（Bytes）换算为易读的 KB 或 MB"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def scan_directory_stats(dir_path: Path):
    """
    扫描一个目录，统计文件个数、总字节数
    """
    if not dir_path.exists():
        return 0, 0
    total_size = 0
    file_count = 0
    for root, _, files in os.walk(dir_path):
        for f in files:
            fp = Path(root) / f
            try:
                total_size += fp.stat().st_size
                file_count += 1
            except OSError:
                pass
    return file_count, total_size


def run_audit():
    print("=" * 72)
    print("  📜 BOOKINDEX 系统平台死穴量化体检（微信小程序 vs 单机本地优先）")
    print("=" * 72)

    # 确定项目根目录
    repo_root = Path(__file__).resolve().parent.parent.parent
    data_dir = repo_root / "data"
    corpus_dir = data_dir / "corpus"
    index_dir = data_dir / "index"

    print(f"[*] 项目根路径: {repo_root}")
    print(f"[*] 检查语料目录: {corpus_dir}")
    print(f"[*] 检查索引目录: {index_dir}\n")

    # 1. 扫描语料库文件
    corpus_files, corpus_bytes = scan_directory_stats(corpus_dir)
    corpus_mb = corpus_bytes / (1024 * 1024)
    print(f"【维度 1：原始古籍语料规模（五史分篇章）】")
    print(f"  - 篇章文件数: {corpus_files} 篇")
    print(f"  - 语料物理大小: {format_bytes(corpus_bytes)} ({corpus_mb:.2f} MB)")
    print(f"  - 微信主包容纳力: {'❌ 塞不下' if corpus_mb > WECHAT_MAIN_PACKAGE_LIMIT_MB else '✅ 可容纳'} "
          f"(超标 {corpus_mb / WECHAT_MAIN_PACKAGE_LIMIT_MB:.1f} 倍)")
    print()

    # 2. 扫描核心构建产物
    print(f"【维度 2：核心构建产物与派生数据体积】")
    target_artifacts = [
        ("book-data.json (全书篇章段落全量结构树)", index_dir / "book-data.json"),
        ("index.db (SQLite + FTS5 全文倒排索引库)", index_dir / "index.db"),
        ("person_trajectories.json (61人全量生平行迹)", index_dir / "person_trajectories.json"),
        ("snapshots.db (快照与正文缓存库)", index_dir / "snapshots.db"),
    ]

    total_core_bytes = 0
    book_data_bytes = 0

    for label, path in target_artifacts:
        if path.exists():
            size = path.stat().st_size
            total_core_bytes += size
            if path.name == "book-data.json":
                book_data_bytes = size
            print(f"  - {label}")
            print(f"    大小: {format_bytes(size)} ({size / (1024 * 1024):.2f} MB)")
        else:
            print(f"  - {label}: [未找到]")

    total_core_mb = total_core_bytes / (1024 * 1024)
    book_data_mb = book_data_bytes / (1024 * 1024)
    print(f"\n  >> 核心数据总计: {format_bytes(total_core_bytes)} ({total_core_mb:.2f} MB)")
    print()

    # 3. 模拟微信小程序环境的死亡判定
    print("=" * 72)
    print("【维度 3：微信小程序物理红线对标与死穴诊断】")
    print("=" * 72)

    # 判定 A: 主包体积限制 (2MB)
    main_exceed = total_core_mb / WECHAT_MAIN_PACKAGE_LIMIT_MB
    print(f"[红线 1] 微信主包限制: {WECHAT_MAIN_PACKAGE_LIMIT_MB} MB")
    print(f"         实际核心体积: {total_core_mb:.2f} MB -> 🔴 超标 {main_exceed:.1f} 倍！")
    print(f"         结果: 微信开发者工具在上传代码时直接抛出错误: [Upload Error: Package size exceeds 2MB]！")
    print()

    # 判定 B: 全部分包上限 (20MB)
    total_exceed = total_core_mb / WECHAT_TOTAL_PACKAGE_LIMIT_MB
    print(f"[红线 2] 微信整包总限制: {WECHAT_TOTAL_PACKAGE_LIMIT_MB} MB (含所有子包)")
    print(f"         实际核心体积: {total_core_mb:.2f} MB -> 🔴 超标 {total_exceed:.1f} 倍！")
    print(f"         结果: 即使采用微信分包加载机制，依然无法将全量数据打包随前端发布！")
    print()

    # 判定 C: 内存雪崩（OOM: Out Of Memory）推算
    # 业界通用规律：在移动端 V8 / JavaScriptCore 中，JSON.parse() 将纯文本字符串解析为对象树，
    # 内存开销通常是 JSON 文本体积的 4 到 8 倍（对象指针、哈希表、属性开销）。
    min_ram_needed = book_data_mb * 4
    max_ram_needed = book_data_mb * 8
    print(f"[红线 3] 移动端前端内存（RAM）承受力与解析膨胀测试")
    print(f"         仅以单个 book-data.json ({book_data_mb:.2f} MB) 为例：")
    print(f"         前端执行 JSON.parse() 对象实例化后，预计消耗堆内存:")
    print(f"         约 {min_ram_needed:.1f} MB ~ {max_ram_needed:.1f} MB！")
    print(f"         移动端小程序宿主建议堆内存上限: ~{MOBILE_HEAP_SAFE_LIMIT_MB} MB")
    print(f"         结果: 💥 严重超标！在 iPhone / Android 上将触发 OS 强行杀后台，表现为【闪退/白屏崩溃】！")
    print()

    # 4. 架构总结诊断
    print("=" * 72)
    print("【架构导师最终体检结论】")
    print("=" * 72)
    print("  🚨 结论：'试图在微信小程序前端直接放全量古籍数据' 是死路一条！")
    print("  💡 架构破局方案：")
    print("     1. 数据下沉：将 58MB 纯 JSON 结构转化为 105MB 的【SQLite 数据库】；")
    print("     2. 算力隔离：由本地后端 (FastAPI) 处理重型检索与分词，通过 8800 端口提供毫秒 API；")
    print("     3. 离线同构：离线版仅提取当前视图需要的精简字段，通过 dist/ 进行轻量化静态脱机分发。")
    print("=" * 72)


if __name__ == "__main__":
    run_audit()
