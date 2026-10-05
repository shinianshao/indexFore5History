# -*- coding: utf-8 -*-
"""
古籍索引系统（BOOKINDEX）分发打包工具
自动构建两套解压即用的便携发布压缩包：
  1. BOOKINDEX_Static_v1.0.zip - 纯静态脱机版（零依赖、双击直接打开，跨平台，约 7~8MB）
  2. BOOKINDEX_Full_v1.0.zip   - 全功能服务版（含 FastAPI + SQLite + 一键启动脚本，约 35MB）
"""
import os
import sys
import zipfile
import shutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(ROOT_DIR, "release")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def zip_folder(source_dir, output_zip, rel_prefix=""):
    """将整个目录打成 zip 包"""
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, source_dir)
                archive_name = os.path.join(rel_prefix, rel_path) if rel_prefix else rel_path
                zf.write(abs_path, archive_name)

def build_static_bundle():
    print("\n[1/2] 正在打包【纯静态脱机版】(BOOKINDEX_Static_v1.0.zip)...")
    dist_dir = os.path.join(ROOT_DIR, "dist")
    out_zip = os.path.join(OUTPUT_DIR, "BOOKINDEX_Static_v1.0.zip")
    
    # 检查 dist 文件齐全
    for f in ["index.html", "app.js", "data.js"]:
        f_path = os.path.join(dist_dir, f)
        if not os.path.exists(f_path):
            raise FileNotFoundError(f"缺少必要静态文件: {f_path}，请先运行 export_static.py")
            
    # 额外在包里放一个简要说明
    readme_content = """===============================================================
  古籍检索系统（BOOKINDEX）纯静态离线版使用说明
===============================================================

【核心特点】
1. 零环境依赖：不需要安装 Python、不需要配置数据库、不需要 Node.js！
2. 跨平台支持：Windows、Mac、Linux、iPad、手机均可直接打开。
3. 数据完整性：内嵌五书 564 篇、22.3 万句、6.7 万人物命中、11.9 万地名命中与关系谱系。

【使用方法】
解压本压缩包后：
👉 直接用浏览器双击打开 "index.html" 即可立即使用！
（推荐使用 Chrome、Edge、Safari 或 Firefox 浏览器）

祝使用愉快！
"""
    readme_path = os.path.join(dist_dir, "使用说明.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
        
    zip_folder(dist_dir, out_zip, rel_prefix="BOOKINDEX_Static")
    os.remove(readme_path)
    
    size_mb = os.path.getsize(out_zip) / (1024 * 1024)
    print(f"✓ 纯静态脱机版打包完成: {out_zip} ({size_mb:.2f} MB)")
    return out_zip

def build_full_bundle():
    print("\n[2/2] 正在打包【全功能服务版】(BOOKINDEX_Full_v1.0.zip)...")
    out_zip = os.path.join(OUTPUT_DIR, "BOOKINDEX_Full_v1.0.zip")
    
    # 白名单打包：严格只打包运行所需文件，排除所有 .git, 临时文件, scratch 等
    include_paths = [
        ("app", True),
        ("data/dict", True),
        ("data/index/index.db", False),
        ("workbook", True),
        ("requirements.txt", False),
        ("启动服务.bat", False),
        ("start.sh", False),
    ]
    
    readme_full = """===============================================================
  古籍检索系统（BOOKINDEX）全功能本地服务版使用说明
===============================================================

【运行环境要求】
- 操作系统：Windows 10/11 或 macOS / Linux
- Python：Python 3.10 或更高版本

【一键启动方法】
▶ Windows 用户：
   直接双击文件夹内的【启动服务.bat】即可！
   程序会自动检查依赖、启动后台服务，并在浏览器自动打开 http://localhost:8800

▶ macOS / Linux 用户：
   在终端进入本目录，执行：
   chmod +x start.sh && ./start.sh
   随后浏览器访问 http://localhost:8800

【包含内容】
- FastAPI 高性能异步后端
- SQLite + FTS5 毫秒级全文检索与关系图谱接口
- 包含 Excel 权威源与标错/覆盖操作支持
===============================================================
"""
    readme_path = os.path.join(ROOT_DIR, "使用说明.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_full)
    
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.write(readme_path, "BOOKINDEX/使用说明.txt")
        
        for item, is_dir in include_paths:
            full_item_path = os.path.join(ROOT_DIR, item)
            if not os.path.exists(full_item_path):
                print(f"  ⚠ 警告：未找到路径 {full_item_path}")
                continue
            if is_dir:
                for root, dirs, files in os.walk(full_item_path):
                    # 排除 __pycache__ 等
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for file in files:
                        if file.endswith((".pyc", ".pyo")):
                            continue
                        f_path = os.path.join(root, file)
                        rel_path = os.path.relpath(f_path, ROOT_DIR)
                        zf.write(f_path, os.path.join("BOOKINDEX", rel_path))
            else:
                zf.write(full_item_path, os.path.join("BOOKINDEX", item))
                
    if os.path.exists(readme_path):
        os.remove(readme_path)
        
    size_mb = os.path.getsize(out_zip) / (1024 * 1024)
    print(f"✓ 全功能服务版打包完成: {out_zip} ({size_mb:.2f} MB)")
    return out_zip

if __name__ == "__main__":
    static_pkg = build_static_bundle()
    full_pkg = build_full_bundle()
    print("\n=======================================================")
    print("发布包制作完成！已输出至 release/ 目录：")
    print(f"1. 纯静态版: {static_pkg}")
    print(f"2. 全功能版: {full_pkg}")
    print("=======================================================")
