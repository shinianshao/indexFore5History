@echo off
rem Windows 双击入口：转调 scripts/run_all.sh（需要 Git Bash 或 WSL 的 bash）
rem 逻辑只写在 .sh 里，这里不做任何重复实现。
where bash >nul 2>nul
if errorlevel 1 (
  echo [x] 未找到 bash。请安装 Git for Windows，或直接在 Git Bash 里运行：
  echo     bash scripts/run_all.sh %*
  exit /b 2
)
bash "%~dp0run_all.sh" %*
exit /b %ERRORLEVEL%
