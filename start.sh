#!/usr/bin/env bash
# 古籍检索系统 BOOKINDEX 服务启动脚本 (macOS / Linux)

echo "========================================================"
echo "         古籍检索系统 BOOKINDEX 服务启动程序"
echo "========================================================"

if ! command -v python3 &> /dev/null; then
    echo "【错误】未检测到 Python3 环境，请先安装 Python 3.10+。"
    exit 1
fi

echo "正在检查运行依赖..."
if ! python3 -c "import fastapi, uvicorn" &> /dev/null; then
    echo "正在安装必需依赖..."
    pip3 install -r requirements.txt
fi

echo "服务启动中: http://localhost:8800"
echo "按 Ctrl+C 可停止服务。"
echo "========================================================"

if command -v open &> /dev/null; then
    open "http://localhost:8800"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8800"
fi

python3 -m uvicorn app.server.main:app --host 0.0.0.0 --port 8800
