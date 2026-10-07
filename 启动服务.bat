@echo off
chcp 65001 >nul
title 古籍检索系统 BOOKINDEX
echo ========================================================
echo          古籍检索系统 BOOKINDEX 服务启动程序
echo ========================================================
echo.

:: 优先选用已配置完整依赖的 Python 3.12 环境
set "PY_EXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
) else if exist "C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PY_EXE=C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe"
) else (
    set "PY_EXE=python"
)

"%PY_EXE%" -c "import fastapi, uvicorn" >nul 2>nul
if %errorlevel% neq 0 (
    echo 正在检查运行依赖...
    "%PY_EXE%" -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo 【错误】依赖安装失败，请检查网络后重试。
        pause
        exit /b
    )
)

echo.
echo 服务启动中，端口: 8800...
echo 稍后将自动打开浏览器访问: http://localhost:8800
echo.
echo 提示：关闭此黑框窗口即可停止服务。
echo ========================================================

start "" "http://localhost:8800"
"%PY_EXE%" -m uvicorn app.server.main:app --host 0.0.0.0 --port 8800
pause
