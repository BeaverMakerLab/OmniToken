@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OmniToken - 桌面悬浮窗
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*desktop_widget.pyw*' -or $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
start "" pythonw main.py
