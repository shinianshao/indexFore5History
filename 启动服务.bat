@echo off
cd /d "%~dp0"
title BOOKINDEX Launcher

set "PY_EXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
) else if exist "C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PY_EXE=C:\Users\dell\AppData\Local\Programs\Python\Python312\python.exe"
) else (
    set "PY_EXE=python"
)

"%PY_EXE%" app\tools\launcher.py
if %errorlevel% neq 0 (
    echo [ERROR] Launcher exited with code %errorlevel%.
    pause
)
