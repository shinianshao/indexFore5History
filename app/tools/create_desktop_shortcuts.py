# -*- coding: utf-8 -*-
"""在 Windows 桌面创建或刷新 BOOKINDEX 快捷方式"""

import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESKTOP = os.path.expanduser("~/Desktop")

ICO_WEB = os.path.join(ROOT, "app", "web", "bookindex.ico")
ICO_DIST = os.path.join(ROOT, "dist", "bookindex.ico")
BAT_PATH = os.path.join(ROOT, "启动服务.bat")
HTML_PATH = os.path.join(ROOT, "dist", "index.html")

ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')

# 1. 本地服务版快捷方式
$s1 = $ws.CreateShortcut((Join-Path $desktop "古籍检索系统 BOOKINDEX.lnk"))
$s1.TargetPath = "{BAT_PATH}"
$s1.WorkingDirectory = "{ROOT}"
$s1.Description = "古籍检索系统 BOOKINDEX 本地服务版"
if (Test-Path "{ICO_WEB}") {{
    $s1.IconLocation = "{ICO_WEB},0"
}}
$s1.Save()
Write-Host "✓ 已刷新桌面快捷方式: 古籍检索系统 BOOKINDEX.lnk"

# 2. 纯静态脱机版快捷方式
$s2 = $ws.CreateShortcut((Join-Path $desktop "古籍检索系统 (免服务脱机版).lnk"))
$s2.TargetPath = "{HTML_PATH}"
$s2.WorkingDirectory = "{os.path.join(ROOT, 'dist')}"
$s2.Description = "古籍检索系统 BOOKINDEX 免服务脱机版"
if (Test-Path "{ICO_DIST}") {{
    $s2.IconLocation = "{ICO_DIST},0"
}}
$s2.Save()
Write-Host "✓ 已刷新桌面快捷方式: 古籍检索系统 (免服务脱机版).lnk"
"""

def main():
    print(f"正在为桌面 ({DESKTOP}) 刷新快捷方式...")
    tmp_ps = os.path.join(ROOT, "scratch", "_create_shortcuts.ps1")
    os.makedirs(os.path.dirname(tmp_ps), exist_ok=True)
    with open(tmp_ps, "w", encoding="utf-8") as f:
        f.write(ps_script)
    
    ret = subprocess.call(["powershell", "-ExecutionPolicy", "Bypass", "-File", tmp_ps])
    if os.path.exists(tmp_ps):
        try:
            os.remove(tmp_ps)
        except Exception:
            pass
    if ret == 0:
        print("所有桌面快捷方式创建与校验完成！")
    else:
        print(f"快捷方式创建失败，退出码: {ret}")

if __name__ == "__main__":
    main()
