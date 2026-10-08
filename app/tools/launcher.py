# -*- coding: utf-8 -*-
"""BOOKINDEX 本地服务优雅启动器 (Launcher)

特性：
1. 编码安全：原生 Python 跨平台 UTF-8 输出，杜绝 Windows CMD 中文字节撕裂与乱码；
2. 端口探测与秒级直达：
   - 若 8800 端口已在运行（如后台服务已开启），直接唤起默认浏览器打开网页，无需重复拉起；
   - 若 8800 未运行，在后台轮询检测就绪状态，确认服务 HTTP 就绪后精确唤起浏览器，彻底杜绝 ERR_CONNECTION_REFUSED；
3. 优雅终端交互：提供清晰的运行状态指示与退出指引。
"""
import os
import sys
import time
import socket
import urllib.request
import webbrowser
import threading

# 修正工作目录至项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

PORT = 8800
HOST = "127.0.0.1"
URL = f"http://{HOST}:{PORT}"

def is_service_ready(timeout=0.3):
    """检测 8800 端口服务是否已响应 HTTP 200"""
    try:
        req = urllib.request.Request(f"{URL}/health")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def open_browser_when_ready():
    """在服务真正就绪后唤起浏览器"""
    start_time = time.time()
    while time.time() - start_time < 20:  # 最多等待 20 秒
        if is_service_ready():
            time.sleep(0.15)
            print(f"\n[OK] 服务已就绪！正在自动为您打开浏览器: {URL}")
            try:
                webbrowser.open(URL)
            except Exception as e:
                print(f"[提示] 请手动在浏览器中打开: {URL} ({e})")
            return
        time.sleep(0.15)
    print(f"\n[提示] 服务启动耗时较长，请稍后手动访问: {URL}")

def check_dependencies():
    """依赖检查"""
    try:
        import fastapi
        import uvicorn
        return True
    except ImportError:
        print("[提示] 正在安装运行依赖 (FastAPI, Uvicorn)...")
        import subprocess
        cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        ret = subprocess.call(cmd)
        return ret == 0

def main():
    print("=" * 64)
    print("         古籍检索系统 BOOKINDEX · 服务启动程序")
    print("=" * 64)
    print(f" 工作目录: {ROOT}")
    print(f" 解释器:   {sys.executable}")
    print("=" * 64)

    if not check_dependencies():
        print("[错误] 依赖安装失败，请检查网络后重试。")
        input("\n按回车键退出...")
        return

    # 若已有服务在运行，直接打开浏览器
    if is_service_ready():
        print(f"\n[提示] 检测到 BOOKINDEX 服务已在后台运行中！")
        print(f"正在为您直接打开浏览器: {URL}\n")
        webbrowser.open(URL)
        print("提示：您可直接使用此服务。按回车键可关闭此窗口。")
        input()
        return

    # 启动等待线程
    watcher = threading.Thread(target=open_browser_when_ready, daemon=True)
    watcher.start()

    print(f"\n正在启动后台服务，监听: {URL} ...")
    print("提示：服务运行期间请保持此窗口开启；关闭此窗口即可停止服务。\n")

    import uvicorn
    from app.server.main import app

    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
    except KeyboardInterrupt:
        print("\n服务已由用户停止。")
    except Exception as ex:
        print(f"\n[错误] 服务启动异常: {ex}")
        input("\n按回车键退出...")

if __name__ == "__main__":
    main()
