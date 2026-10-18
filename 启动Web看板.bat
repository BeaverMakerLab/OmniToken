@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OmniToken - Web 监控大屏
python main.py --web
pause
