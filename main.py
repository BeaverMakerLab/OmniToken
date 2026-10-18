#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Monitor Master Launcher (跨电脑即开即用独立版)
Antigravity, OpenAI Codex & DeepSeek Harness 统一 Token 监控平台

模式支持：
1. 双击运行 (无参数)：
   - 自动在后台启动 Web 监控服务 (http://127.0.0.1:8765)
   - 启动 Windows 桌面高清常驻悬浮微件 + 右下角系统托盘
   - 双击悬浮窗或右键“打开 Web 看板”，随时呼出完整交互大屏
2. 命令行参数运行：
   - TokenMonitor.exe --web [--no-browser] [--port 8765] : 仅启动网页监控服务
   - TokenMonitor.exe --cli [--today] [--days 7] : 终端命令行直接打印消耗报表
"""

import sys
import os

def attach_parent_console():
    """如果是以 GUI 无窗口模式打包，当在终端中带参数执行时自动挂载父控制台输出"""
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except Exception:
            pass

def main():
    # 检查是否为 CLI 模式
    if "--cli" in sys.argv or "-h" in sys.argv or "--help" in sys.argv:
        attach_parent_console()
        import app
        app.main()
        return

    # 检查是否为纯 Web 服务模式
    if "--web" in sys.argv or "--server" in sys.argv:
        attach_parent_console()
        import app
        app.main()
        return

    # 默认完整桌面模式：后台启动嵌入式 Web 服务 + 启动桌面悬浮窗
    import app
    app.start_server_in_thread(8765)

    import desktop_widget
    desktop_widget.main()

if __name__ == "__main__":
    main()
