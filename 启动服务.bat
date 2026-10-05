@echo off
chcp 65001 >nul
title 古籍检索系统 BOOKINDEX
echo ========================================================
echo          古籍检索系统 BOOKINDEX 服务启动程序
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo 【错误】未检测到 Python 环境！
    echo 请先安装 Python 3.10+ 并勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b
)

echo 正在检查运行依赖...
python -c "import fastapi, uvicorn" >nul 2>nul
if %errorlevel% neq 0 (
    echo 正在安装必需依赖 (fastapi, uvicorn)...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo 【错误】依赖安装失败，请检查网络后重试。
        pause
        exit /b
    )
)

echo.
echo 服务正在启动中，端口: 8800...
echo 稍后将自动打开浏览器访问: http://localhost:8800
echo.
echo 提示：关闭此黑框窗口即可停止服务。
echo ========================================================

start "" "http://localhost:8800"
python -m uvicorn app.server.main:app --host 0.0.0.0 --port 8800
pause
