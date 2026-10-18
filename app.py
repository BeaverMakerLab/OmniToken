#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Monitor Application (Web Dashboard + CLI Runner)
Unified Token Monitor for Antigravity (AGY) and OpenAI Codex.
Pure Python standard library (no pip install required).
"""

import os
import sys
import json
import socket
import argparse
import datetime
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 自动处理 Windows 控制台输出编码与 pythonw 无输出流问题
if sys.platform == "win32":
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    else:
        try:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    else:
        try:
            import io
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

# Import scanner core
import token_core

def get_base_dir():
    """获取静态资源根目录（兼容 PyInstaller 打包与源码运行）"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.exists(os.path.join(exe_dir, "index.html")):
            return exe_dir
        return getattr(sys, '_MEIPASS', exe_dir)
    return os.path.dirname(os.path.abspath(__file__))

_server_thread = None
_httpd = None

def is_port_in_use(port, host="127.0.0.1"):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False

def start_server_in_thread(port=8765):
    global _server_thread, _httpd
    if is_port_in_use(port):
        return port
    try:
        import threading
        server_address = ("127.0.0.1", port)
        base_dir = get_base_dir()
        def handler_factory(*h_args, **h_kwargs):
            return TokenDashboardHandler(*h_args, directory=base_dir, **h_kwargs)
        _httpd = ThreadingHTTPServer(server_address, handler_factory)
        _server_thread = threading.Thread(target=_httpd.serve_forever, daemon=True)
        _server_thread.start()
        return port
    except Exception:
        return None

class TokenDashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        if directory is None:
            directory = get_base_dir()
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/stats":
            qs = parse_qs(parsed_url.query)
            days = qs.get("days", [None])[0]
            today = qs.get("today", [None])[0]
            is_all = qs.get("all", [None])[0]
            start_str = qs.get("start", [None])[0]
            end_str = qs.get("end", [None])[0]
            granularity = qs.get("granularity", [None])[0]

            now = datetime.datetime.now()
            if is_all:
                start_dt = datetime.datetime(2020, 1, 1)
                end_dt = now
            elif today:
                start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_dt = now
            elif days is not None:
                try:
                    d_float = float(days)
                    start_dt = now - datetime.timedelta(days=d_float)
                    end_dt = now
                except ValueError:
                    start_dt = now - datetime.timedelta(days=7)
                    end_dt = now
            elif start_str:
                try:
                    start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d")
                    end_dt = datetime.datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59) if end_str else now
                except ValueError:
                    start_dt = now - datetime.timedelta(days=7)
                    end_dt = now
            else:
                start_dt = now - datetime.timedelta(days=7)
                end_dt = now

            data = token_core.get_combined_stats(
                start_dt=start_dt,
                end_dt=end_dt,
                granularity=granularity or "auto"
            )
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/":
            self.path = "/index.html"

        super().do_GET()

    def log_message(self, format, *args):
        pass

def find_available_port(preferred_port=8765):
    for p in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return preferred_port

def run_cli(start_dt, end_dt, granularity="auto"):
    data = token_core.get_combined_stats(start_dt=start_dt, end_dt=end_dt, granularity=granularity)
    comb = data["combined_summary"]
    agy = data["antigravity"]["summary"]
    codex = data["codex"]["summary"]
    dsh = data.get("deepseek", {}).get("summary", {"total_tokens": 0, "cache_ratio": 0.0, "total_calls": 0})

    print("=" * 86)
    print(" 本机 Antigravity, OpenAI Codex & DeepSeek Harness Token 消耗综合统计")
    print(f" 时间范围: {data['range']['start']}  至  {data['range']['end']}")
    print(f" 统计粒度: {'逐小时 (Hourly)' if data['granularity'] == 'hourly' else '按天 (Daily)'}")
    print("=" * 86)
    print("[全机消耗总览]")
    print(f"  * 全机总消耗 Token    : {comb['total_tokens']:>15,} tokens (约 {comb['total_tokens']/1e6:.2f} M / {comb['total_tokens']/1e8:.2f} 亿)")
    print(f"  * 预估产生总费用      : ${comb.get('cost_usd', 0.0):>14.2f} (约 ¥{comb.get('cost_cny', 0.0):>10.2f} RMB)")
    print(f"  * 缓存命中总量 (Cache): {comb['cached_tokens']:>15,} tokens (缓存率: {comb['cache_ratio']}%)")
    print(f"  * 思考推理总量 (Think): {comb['thinking_tokens']:>15,} tokens")
    print(f"  * 交互调用总次数      : {comb['total_calls']:>15,} 次")
    print("-" * 86)
    print("[三客户端对比]")
    print(f"  * Antigravity : {agy['total_tokens']:>14,} tokens ({agy['total_tokens']/max(1,comb['total_tokens'])*100:>5.1f}%) | 费用: ${agy.get('cost_usd', 0.0):>7.2f} (¥{agy.get('cost_cny', 0.0):>7.2f}) | 缓存率: {agy['cache_ratio']:>5.1f}% | 调用: {agy['total_calls']:>5} 次")
    print(f"  * OpenAI Codex: {codex['total_tokens']:>14,} tokens ({codex['total_tokens']/max(1,comb['total_tokens'])*100:>5.1f}%) | 费用: ${codex.get('cost_usd', 0.0):>7.2f} (¥{codex.get('cost_cny', 0.0):>7.2f}) | 缓存率: {codex['cache_ratio']:>5.1f}% | 调用: {codex['total_calls']:>5} 次")
    print(f"  * DeepSeek DSH: {dsh['total_tokens']:>14,} tokens ({dsh['total_tokens']/max(1,comb['total_tokens'])*100:>5.1f}%) | 费用: ${dsh.get('cost_usd', 0.0):>7.2f} (¥{dsh.get('cost_cny', 0.0):>7.2f}) | 缓存率: {dsh['cache_ratio']:>5.1f}% | 调用: {dsh['total_calls']:>5} 次")
    print("-" * 86)

    if data["granularity"] == "hourly":
        print("[逐小时消耗明细 (仅展示有活跃调用的时段)]")
        print(f"  {'时间段':<18} | {'全机总 Token':>14} | {'Antigravity':>12} | {'Codex':>12} | {'DeepSeek':>12} | {'总调用数':>8}")
        print("  " + "-" * 88)
        active_hours = [h for h in data["hourly_timeline"] if (h.get("agy_calls", 0) + h.get("codex_calls", 0) + h.get("dsh_calls", 0)) > 0]
        if not active_hours:
            print("  (所选时间范围内暂无活跃 Token 消耗)")
        else:
            for h in active_hours:
                calls = h.get("agy_calls", 0) + h.get("codex_calls", 0) + h.get("dsh_calls", 0)
                print(f"  {h['timestamp']:<18} | {h['total']:>14,} | {h.get('agy_total', 0):>12,} | {h.get('codex_total', 0):>12,} | {h.get('dsh_total', 0):>12,} | {calls:>8}")
        print("-" * 86)

    print("[每日消耗趋势]")
    print(f"  {'日期':<12} | {'全机总 Token':>14} | {'Antigravity':>12} | {'Codex':>12} | {'DeepSeek':>12} | {'总调用数':>8}")
    print("  " + "-" * 82)
    for d in data["daily_timeline"]:
        calls = d.get("agy_calls", 0) + d.get("codex_calls", 0) + d.get("dsh_calls", 0)
        print(f"  {d['date']:<12} | {d['total']:>14,} | {d.get('agy_total', 0):>12,} | {d.get('codex_total', 0):>12,} | {d.get('dsh_total', 0):>12,} | {calls:>8}")
    print("=" * 86)

def main():
    parser = argparse.ArgumentParser(description="本机 Antigravity, Codex 与 DeepSeek Harness Token 消耗统计小程序")
    parser.add_argument("--cli", action="store_true", help="仅在终端中输出统计表格，不启动 Web 界面")
    parser.add_argument("-d", "--days", type=float, default=7, help="查询过去 N 天内的消耗 (默认: 7)")
    parser.add_argument("--today", action="store_true", help="快捷参数：查询今天")
    parser.add_argument("--hourly", action="store_true", help="强制逐小时粒度显示")
    parser.add_argument("--daily", action="store_true", help="强制按天粒度显示")
    parser.add_argument("--port", type=int, default=8765, help="Web 看板服务器端口 (默认: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="启动 Web 服务但不自动打开浏览器")

    args = parser.parse_args()

    granularity = "hourly" if args.hourly else ("daily" if args.daily else "auto")

    now = datetime.datetime.now()
    if args.today:
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_dt = now - datetime.timedelta(days=args.days)
    end_dt = now

    if args.cli:
        run_cli(start_dt, end_dt, granularity=granularity)
        return

    port = find_available_port(args.port)
    server_address = ("127.0.0.1", port)
    app_dir = get_base_dir()

    def handler_factory(*h_args, **h_kwargs):
        return TokenDashboardHandler(*h_args, directory=app_dir, **h_kwargs)

    httpd = ThreadingHTTPServer(server_address, handler_factory)
    url = f"http://127.0.0.1:{port}"

    print("=" * 70)
    print(" [*] 本机 Token 消耗监控看板 (Antigravity & Codex) 已启动！")
    print(f" [+] 本地访问地址: {url}")
    print(" [-] 按 Ctrl + C 可退出服务。")
    print("=" * 70)

    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n看板服务已停止。")
        httpd.server_close()

if __name__ == "__main__":
    main()
