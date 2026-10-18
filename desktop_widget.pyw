#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop Floating Widget for Token Monitor (v3.0 Resizable & Total-Only)
Windows 桌面常驻高清悬浮窗小程序
优化内容：
1. 【自由调大小】：右下角增加拖拽把手 ⤡，支持任意拖拽调整窗口宽和高，自动保存大小与位置
2. 【仅显示总量】：去除区分 Antigravity/Codex 的卡片，专注呈现全机总消耗量
3. 【近 7 天趋势大图】：加大画布空间，每日单柱呈现日消耗总量，柱顶标注具体数值 (如 136M, 508M)
4. 【原生高 DPI 锐利防虚】：彻底解决 Windows 高分屏模糊发虚问题
"""

import os
import sys
import json
import time
import subprocess
import threading
import datetime
import webbrowser
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as tray_item, Menu as tray_menu

def create_tray_icon_image():
    # 64x64 高清托盘图标 (圆形深色底座 + 三色能量数据柱)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 外部圆环底座
    draw.ellipse([3, 3, 61, 61], fill=(13, 17, 23, 255), outline=(56, 189, 248, 255), width=3)
    # 三根对应三引擎的明亮数据柱：青蓝 (AGY)、翠绿 (Codex)、亮蓝 (DeepSeek)
    draw.rounded_rectangle([14, 30, 24, 48], radius=2, fill=(56, 189, 248, 255))
    draw.rounded_rectangle([27, 20, 37, 48], radius=2, fill=(16, 185, 129, 255))
    draw.rounded_rectangle([40, 12, 50, 48], radius=2, fill=(77, 107, 254, 255))
    return img

# 1. 启用 Windows 原生高 DPI 缩放（解决字体模糊发虚）
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# 引入核心扫描器与 Web 服务模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import token_core

def get_config_dir():
    """获取配置文件存储目录（优先使用 exe 同级目录便携存储，无权限时回退至用户目录）"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        try:
            test_file = os.path.join(exe_dir, ".test_write")
            with open(test_file, "w") as f: f.write("ok")
            os.remove(test_file)
            return exe_dir
        except Exception:
            user_dir = os.path.join(os.path.expanduser("~"), ".token-monitor")
            os.makedirs(user_dir, exist_ok=True)
            return user_dir
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(get_config_dir(), "widget_config.json")

def load_config():
    default_config = {
        "x": None,
        "y": None,
        "width": 420,
        "height": 340,
        "topmost": True,
        "alpha": 0.95,
        "refresh_interval": 30,
        "show_taskbar": False,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_config.update(cfg)
        except Exception:
            pass
    return default_config

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def fmt_short(n):
    if not n: return "0"
    if n >= 1e8: return f"{n / 1e8:.2f} 亿"
    if n >= 1e6: return f"{n / 1e6:.1f} M"
    if n >= 1e3: return f"{n / 1e3:.1f} K"
    return str(n)

class DesktopTokenWidget:
    def __init__(self):
        self.config = load_config()
        self.root = tk.Tk()
        self.root.title("Token Monitor Widget")

        # 窗口标题与置顶
        self.root.title("Token 监控悬浮窗")
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", self.config.get("alpha", 0.96))
        self.root.attributes("-topmost", True)

        # 调优暗黑配色 (高对比度、清晰、不晕色)
        self.c_bg = "#0d1117"        # 底色
        self.c_card = "#161b22"      # 卡片底色
        self.c_subcard = "#21262d"   # 小标签底色
        self.c_border = "#38bdf8"    # 亮青蓝高亮边框，确保在任何壁纸上都清晰可辨
        self.c_text = "#f0f6fc"      # 主文字
        self.c_muted = "#8b949e"     # 次要文字
        self.c_primary = "#38bdf8"   # 亮青蓝
        self.c_today_bar = "#60a5fa" # 今日柱子亮色
        self.c_bar = "#38bdf8"       # 历史日柱子
        self.c_green = "#10b981"     # 绿色

        # 高清字体 (微软雅黑 UI)
        self.font_title = ("Microsoft YaHei UI", 9, "bold")
        self.font_hero = ("Microsoft YaHei UI", 22, "bold")
        self.font_badge = ("Microsoft YaHei UI", 8, "bold")
        self.font_bold8 = ("Microsoft YaHei UI", 8, "bold")
        self.font_sub = ("Microsoft YaHei UI", 8)
        self.font_info = ("Microsoft YaHei UI", 8)
        self.font_micro = ("Microsoft YaHei UI", 7)
        self.font_bar_val = ("Segoe UI", 7, "bold")
        self.font_bar_date = ("Segoe UI", 7)

        self.root.configure(bg=self.c_border)

        # 尺寸
        self.width = max(320, self.config.get("width", 420))
        self.height = max(240, self.config.get("height", 340))

        # 初始化位置 (严密防越界智能校准)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_x = max(30, screen_w - self.width - 50)
        default_y = 60

        x = self.config.get("x")
        y = self.config.get("y")
        # 只要窗口超出当前屏幕任一侧可视范围，自动回归右上角可视安全区
        if x is None or x < 0 or (x + self.width) > screen_w:
            x = default_x
        if y is None or y < 0 or (y + self.height) > screen_h:
            y = default_y

        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # 任务栏图标显隐设置 (默认隐藏不占任务栏和 Alt+Tab，悬浮窗常驻桌面 + 右下角系统托盘)
        self._apply_taskbar_visibility()

        self.root.lift()
        self.root.attributes("-topmost", True)

        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {"x": 0, "y": 0, "w": 0, "h": 0}

        # 内部主容器（留 1px 细边框）
        self.main_frame = tk.Frame(self.root, bg=self.c_bg, padx=12, pady=10)
        self.main_frame.place(x=1, y=1, relwidth=1.0, relheight=1.0, width=-2, height=-2)

        self.timeline_data = []

        self._build_ui()
        self._bind_events()

        # 状态标志与系统托盘初始化 (类似微信常驻右下角)
        self.is_window_visible = True
        self._hide_notified = False
        self.tray_icon = None
        self._init_system_tray()

        # 启动后台自动刷新
        self.is_running = True
        self.refresh_thread = threading.Thread(target=self._auto_refresh_worker, daemon=True)
        self.refresh_thread.start()

        # 确保后台嵌入式 Web 服务就绪（随时供双击呼出完整看板）
        try:
            import app
            app.start_server_in_thread(8765)
        except Exception:
            pass

    def _build_ui(self):
        # 1. 顶部标题栏
        top_bar = tk.Frame(self.main_frame, bg=self.c_bg)
        top_bar.pack(fill="x", side="top", pady=(0, 6))

        lbl_title = tk.Label(top_bar, text="⚡ Token 实时监视器", font=self.font_title, fg=self.c_text, bg=self.c_bg)
        lbl_title.pack(side="left")

        # 类似微信：点击右上角关闭按钮，默认最小化收纳到右下角托盘
        btn_close = tk.Label(top_bar, text="✕", font=("Segoe UI", 10, "bold"), fg=self.c_muted, bg=self.c_bg, cursor="hand2")
        btn_close.pack(side="right")
        btn_close.bind("<Button-1>", lambda e: self.hide_to_tray())
        btn_close.bind("<Enter>", lambda e: btn_close.configure(fg="#f85149"))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(fg=self.c_muted))

        # 最小化到系统托盘按钮
        btn_min = tk.Label(top_bar, text="—", font=("Segoe UI", 9, "bold"), fg=self.c_muted, bg=self.c_bg, cursor="hand2")
        btn_min.pack(side="right", padx=(0, 6))
        btn_min.bind("<Button-1>", lambda e: self.hide_to_tray())
        btn_min.bind("<Enter>", lambda e: btn_min.configure(fg=self.c_primary))
        btn_min.bind("<Leave>", lambda e: btn_min.configure(fg=self.c_muted))

        self.lbl_status = tk.Label(top_bar, text="● 实时", font=self.font_micro, fg="#10b981", bg=self.c_bg)
        self.lbl_status.pack(side="right", padx=6)

        # 2. 今日实时消耗板块 (只展示总量)
        today_frame = tk.Frame(self.main_frame, bg=self.c_card, padx=12, pady=10, highlightthickness=1, highlightbackground=self.c_border)
        today_frame.pack(fill="x", pady=(0, 8))

        # 首行：大号总消耗 + 缓存率药丸标签
        hero_row = tk.Frame(today_frame, bg=self.c_card)
        hero_row.pack(fill="x")

        self.val_today_total = tk.Label(hero_row, text="-- M", font=self.font_hero, fg=self.c_primary, bg=self.c_card)
        self.val_today_total.pack(side="left")

        self.val_today_badge = tk.Label(hero_row, text="缓存率: --%", font=self.font_badge, fg="#38bdf8", bg=self.c_subcard, padx=8, pady=2)
        self.val_today_badge.pack(side="right")

        # 次行：说明与请求数
        sub_row = tk.Frame(today_frame, bg=self.c_card)
        sub_row.pack(fill="x", pady=(2, 6))
        self.val_today_sub = tk.Label(sub_row, text="今日全机实时总消耗", font=self.font_sub, fg=self.c_muted, bg=self.c_card)
        self.val_today_sub.pack(side="left")
        self.lbl_today_calls = tk.Label(sub_row, text="-- 次调用", font=self.font_bold8, fg=self.c_text, bg=self.c_card)
        self.lbl_today_calls.pack(side="right")

        # 第三行：输入与输出细节小标签
        detail_chips = tk.Frame(today_frame, bg=self.c_subcard, padx=8, pady=4)
        detail_chips.pack(fill="x")
        self.lbl_detail_in = tk.Label(detail_chips, text="输入: -- M", font=self.font_micro, fg=self.c_muted, bg=self.c_subcard)
        self.lbl_detail_in.pack(side="left")
        self.lbl_detail_out = tk.Label(detail_chips, text="输出: -- M (含思考: -- M)", font=self.font_micro, fg=self.c_muted, bg=self.c_subcard)
        self.lbl_detail_out.pack(side="right")

        # 3. 近 7 天消耗趋势对比 (占满剩余纵向空间)
        trend_header = tk.Frame(self.main_frame, bg=self.c_bg)
        trend_header.pack(fill="x", pady=(2, 4))
        tk.Label(trend_header, text="📈 近 7 天消耗趋势 (日总量)", font=self.font_bold8, fg=self.c_text, bg=self.c_bg).pack(side="left")
        self.lbl_trend_peak = tk.Label(trend_header, text="7日最高: --", font=self.font_micro, fg=self.c_muted, bg=self.c_bg)
        self.lbl_trend_peak.pack(side="right")

        # 趋势画布 (自适应宽高)
        self.chart_frame = tk.Frame(self.main_frame, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        self.chart_frame.pack(fill="both", expand=True, pady=(0, 6))

        self.canvas = tk.Canvas(self.chart_frame, bg=self.c_card, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas.bind("<Configure>", lambda e: self._draw_trend_chart(self.timeline_data))

        # 4. 底部状态栏 + 右下角拉伸把手
        bot_bar = tk.Frame(self.main_frame, bg=self.c_bg)
        bot_bar.pack(fill="x", side="bottom")

        self.lbl_update_time = tk.Label(bot_bar, text="正在读取数据...", font=self.font_micro, fg=self.c_muted, bg=self.c_bg)
        self.lbl_update_time.pack(side="left")

        # 右下角拖拽缩放把手
        self.resize_grip = tk.Label(
            bot_bar,
            text="⤡",
            font=("Segoe UI", 12, "bold"),
            fg=self.c_muted,
            bg=self.c_bg,
            cursor="size_nw_se"
        )
        self.resize_grip.pack(side="right", padx=(4, 0))

        lbl_hint = tk.Label(bot_bar, text="拖拽 ⤡ 调大小 | 双击开大屏", font=self.font_micro, fg=self.c_muted, bg=self.c_bg)
        lbl_hint.pack(side="right")

    def _bind_events(self):
        # 拖拽移动窗口绑定
        drag_widgets = [
            self.root, self.main_frame, self.val_today_total,
            self.val_today_sub, self.canvas
        ]
        for w in drag_widgets:
            w.bind("<Button-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_motion)
            w.bind("<ButtonRelease-1>", self._on_drag_end)
            w.bind("<Double-Button-1>", self._on_double_click)
            w.bind("<Button-3>", self._show_context_menu)

        # 拖拽调整大小绑定
        self.resize_grip.bind("<Button-1>", self._on_resize_start)
        self.resize_grip.bind("<B1-Motion>", self._on_resize_motion)
        self.resize_grip.bind("<ButtonRelease-1>", self._on_resize_end)
        self.resize_grip.bind("<Enter>", lambda e: self.resize_grip.configure(fg=self.c_primary))
        self.resize_grip.bind("<Leave>", lambda e: self.resize_grip.configure(fg=self.c_muted))

    # --- 拖拽移动逻辑 ---
    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()

    def _on_drag_motion(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def _on_drag_end(self, event):
        self.config["x"] = self.root.winfo_x()
        self.config["y"] = self.root.winfo_y()
        save_config(self.config)

    # --- 拖拽调整大小逻辑 ---
    def _on_resize_start(self, event):
        self._resize_data["w"] = self.root.winfo_width()
        self._resize_data["h"] = self.root.winfo_height()
        self._resize_data["x"] = event.x_root
        self._resize_data["y"] = event.y_root

    def _on_resize_motion(self, event):
        dx = event.x_root - self._resize_data["x"]
        dy = event.y_root - self._resize_data["y"]
        new_w = max(320, self._resize_data["w"] + dx)
        new_h = max(240, self._resize_data["h"] + dy)
        self.root.geometry(f"{new_w}x{new_h}")
        self.root.update_idletasks()

    def _on_resize_end(self, event):
        self.config["width"] = self.root.winfo_width()
        self.config["height"] = self.root.winfo_height()
        save_config(self.config)

    def _on_double_click(self, event):
        self._open_web_dashboard()

    # --- 系统托盘收纳与呼出逻辑 (类似微信) ---
    def toggle_window(self):
        if self.is_window_visible:
            self.hide_to_tray()
        else:
            self.show_from_tray()

    def hide_to_tray(self):
        self.root.withdraw()
        self.is_window_visible = False
        if not self._hide_notified:
            self._hide_notified = True
            if self.tray_icon:
                try:
                    self.tray_icon.notify("悬浮窗已收纳至右下角系统托盘，双击或右键托盘图标随时重新呼出！", "Token 实时监视器")
                except Exception:
                    pass

    def show_from_tray(self):
        self.root.deiconify()
        self.root.overrideredirect(True)
        self._apply_taskbar_visibility()
        self.root.lift()
        if self.config.get("topmost", True):
            self.root.attributes("-topmost", True)
        self.root.focus_force()
        self.is_window_visible = True

    def _init_system_tray(self):
        icon_img = create_tray_icon_image()

        def on_toggle(icon, item):
            self.root.after(0, self.toggle_window)

        def on_open_web(icon, item):
            self.root.after(0, self._open_web_dashboard)

        def on_refresh(icon, item):
            self.trigger_refresh()

        def on_toggle_topmost(icon, item):
            self.root.after(0, self._toggle_topmost)

        def is_topmost_checked(item):
            return self.config.get("topmost", True)

        def on_toggle_taskbar(icon, item):
            self.root.after(0, self._toggle_taskbar)

        def is_taskbar_checked(item):
            return self.config.get("show_taskbar", False)

        def make_alpha_action(val):
            return lambda icon, item: self.root.after(0, lambda: self._set_alpha(val))

        def make_alpha_checked(val):
            return lambda item: abs(self.config.get("alpha", 0.96) - val) < 0.03

        def make_size_action(w, h):
            return lambda icon, item: self.root.after(0, lambda: self._set_preset_size(w, h))

        def make_size_checked(w, h):
            return lambda item: (self.config.get("width") == w and self.config.get("height") == h)

        def on_autostart(icon, item):
            self.root.after(0, self._setup_autostart_dialog)

        def on_exit(icon, item):
            self.root.after(0, self.quit_application)

        tray_menu_obj = tray_menu(
            tray_item("👁️ 显示 / 隐藏悬浮窗", on_toggle, default=True),
            tray_item("🌐 打开 Web 监控看板", on_open_web),
            tray_item("🔄 立即刷新数据", on_refresh),
            tray_menu.SEPARATOR,
            tray_item("📌 保持窗口置顶", on_toggle_topmost, checked=is_topmost_checked),
            tray_item("🗂️ 在任务栏显示图标", on_toggle_taskbar, checked=is_taskbar_checked),
            tray_item("🌓 调整透明度", tray_menu(
                tray_item("100% (完全不透明)", make_alpha_action(1.0), checked=make_alpha_checked(1.0), radio=True),
                tray_item("95% (推荐半透)", make_alpha_action(0.95), checked=make_alpha_checked(0.95), radio=True),
                tray_item("85% (高透明度)", make_alpha_action(0.85), checked=make_alpha_checked(0.85), radio=True),
                tray_item("70% (极度透明)", make_alpha_action(0.70), checked=make_alpha_checked(0.70), radio=True),
            )),
            tray_item("📐 快捷调整尺寸", tray_menu(
                tray_item("紧凑尺寸 (350 × 270)", make_size_action(350, 270), checked=make_size_checked(350, 270), radio=True),
                tray_item("标准尺寸 (420 × 340)", make_size_action(420, 340), checked=make_size_checked(420, 340), radio=True),
                tray_item("大号尺寸 (500 × 400)", make_size_action(500, 400), checked=make_size_checked(500, 400), radio=True),
            )),
            tray_menu.SEPARATOR,
            tray_item("🚀 开机自启动设置...", on_autostart),
            tray_item("❌ 彻底退出程序", on_exit),
        )

        self.tray_icon = pystray.Icon(
            "TokenMonitorWidget",
            icon_img,
            "Token 实时监视器 (双击显示/隐藏)",
            tray_menu_obj
        )

        def run_tray():
            try:
                self.tray_icon.run()
            except Exception:
                pass

        self.tray_thread = threading.Thread(target=run_tray, daemon=True)
        self.tray_thread.start()

    def _show_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0, bg="#161b22", fg="#f0f6fc", activebackground="#38bdf8", activeforeground="#000", font=self.font_sub)
        menu.add_command(label="📥 最小化到系统托盘", command=self.hide_to_tray)
        menu.add_command(label="🔄 立即刷新数据", command=self.trigger_refresh)
        menu.add_command(label="📊 打开网页完整大屏", command=self._open_web_dashboard)
        menu.add_separator()

        topmost_label = "📌 取消始终置顶" if self.config.get("topmost", True) else "📌 开启始终置顶"
        menu.add_command(label=topmost_label, command=self._toggle_topmost)

        taskbar_label = "🗂️ 隐藏任务栏图标" if self.config.get("show_taskbar", False) else "🗂️ 在任务栏显示图标"
        menu.add_command(label=taskbar_label, command=self._toggle_taskbar)

        alpha_menu = tk.Menu(menu, tearoff=0, bg="#161b22", fg="#f0f6fc", font=self.font_sub)
        alpha_menu.add_command(label="100% (完全不透明 - 极度清晰)", command=lambda: self._set_alpha(1.0))
        alpha_menu.add_command(label="95% (推荐半透)", command=lambda: self._set_alpha(0.95))
        alpha_menu.add_command(label="85% (高透明度)", command=lambda: self._set_alpha(0.85))
        alpha_menu.add_command(label="70% (极透)", command=lambda: self._set_alpha(0.70))
        menu.add_cascade(label="🌓 调整透明度", menu=alpha_menu)

        size_menu = tk.Menu(menu, tearoff=0, bg="#161b22", fg="#f0f6fc", font=self.font_sub)
        size_menu.add_command(label="紧凑尺寸 (350 × 270)", command=lambda: self._set_preset_size(350, 270))
        size_menu.add_command(label="标准尺寸 (420 × 340)", command=lambda: self._set_preset_size(420, 340))
        size_menu.add_command(label="大号尺寸 (500 × 400)", command=lambda: self._set_preset_size(500, 400))
        menu.add_cascade(label="📐 快捷调整尺寸", menu=size_menu)

        menu.add_separator()
        menu.add_command(label="🚀 开机自启动开关...", command=self._setup_autostart_dialog)
        menu.add_command(label="❌ 彻底退出程序", command=self.quit_application)

        menu.tk_popup(event.x_root, event.y_root)

    def _set_preset_size(self, w, h):
        self.root.geometry(f"{w}x{h}")
        self.config["width"] = w
        self.config["height"] = h
        save_config(self.config)

    def _toggle_topmost(self):
        new_state = not self.config.get("topmost", True)
        self.config["topmost"] = new_state
        self.root.attributes("-topmost", new_state)
        save_config(self.config)

    def _apply_taskbar_visibility(self):
        if sys.platform == "win32":
            try:
                import ctypes
                self.root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                if not hwnd:
                    hwnd = self.root.winfo_id()
                GWL_EXSTYLE = -20
                WS_EX_APPWINDOW = 0x00040000
                WS_EX_TOOLWINDOW = 0x00000080
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if self.config.get("show_taskbar", False):
                    style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                else:
                    style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            except Exception:
                pass

    def _toggle_taskbar(self):
        new_state = not self.config.get("show_taskbar", False)
        self.config["show_taskbar"] = new_state
        self._apply_taskbar_visibility()
        save_config(self.config)

    def _set_alpha(self, alpha_val):
        self.config["alpha"] = alpha_val
        self.root.attributes("-alpha", alpha_val)
        save_config(self.config)

    def _open_web_dashboard(self):
        try:
            import app
            app.start_server_in_thread(8765)
        except Exception:
            pass
        time.sleep(0.3)
        webbrowser.open("http://127.0.0.1:8765")

    def _setup_autostart_dialog(self):
        startup_folder = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
        bat_shortcut = os.path.join(startup_folder, "TokenMonitorWidget.bat")
        curr_pyw = os.path.abspath(__file__)
        is_enabled = os.path.exists(bat_shortcut)

        if not is_enabled:
            try:
                with open(bat_shortcut, "w", encoding="ascii") as f:
                    if getattr(sys, 'frozen', False):
                        target_exe = os.path.abspath(sys.executable)
                        f.write(f'@echo off\nstart "" "{target_exe}"\n')
                    else:
                        f.write(f'@echo off\nstart "" pythonw "{curr_pyw}"\n')
                messagebox.showinfo("开机自启", "已开启【开机自动启动】！\n快捷方式已写入 Windows 启动目录。")
            except Exception as e:
                messagebox.showerror("错误", f"设置开机自启失败: {e}")
        else:
            try:
                os.remove(bat_shortcut)
                messagebox.showinfo("开机自启", "已取消【开机自动启动】。")
            except Exception as e:
                messagebox.showerror("错误", f"取消失败: {e}")

    def trigger_refresh(self):
        threading.Thread(target=self._update_data_worker, daemon=True).start()

    def _auto_refresh_worker(self):
        while self.is_running:
            self._update_data_worker()
            interval = self.config.get("refresh_interval", 30)
            for _ in range(interval):
                if not self.is_running: break
                time.sleep(1)

    def _update_data_worker(self):
        now = datetime.datetime.now()
        start_7d = now - datetime.timedelta(days=7)
        try:
            data = token_core.get_combined_stats(start_dt=start_7d, end_dt=now)

            today_str = now.strftime("%Y-%m-%d")
            agy_today = data["antigravity"]["by_day"].get(today_str, {"total": 0, "calls": 0, "cached": 0, "in": 0, "out": 0, "thinking": 0})
            codex_today = data["codex"]["by_day"].get(today_str, {"total": 0, "calls": 0, "cached": 0, "in": 0, "out": 0, "thinking": 0})
            dsh_today = data.get("deepseek", {}).get("by_day", {}).get(today_str, {"total": 0, "calls": 0, "cached": 0, "in": 0, "out": 0, "thinking": 0, "cost_usd": 0.0})

            today_tot = agy_today["total"] + codex_today["total"] + dsh_today["total"]
            today_cached = agy_today["cached"] + codex_today["cached"] + dsh_today["cached"]
            today_in = agy_today["in"] + codex_today["in"] + dsh_today["in"]
            today_out = agy_today["out"] + codex_today["out"] + dsh_today["out"]
            today_thinking = agy_today["thinking"] + codex_today["thinking"] + dsh_today["thinking"]
            today_calls = agy_today["calls"] + codex_today["calls"] + dsh_today["calls"]
            today_cost = agy_today.get("cost_usd", 0.0) + codex_today.get("cost_usd", 0.0) + dsh_today.get("cost_usd", 0.0)

            today_ratio = round(today_cached / today_in * 100, 1) if today_in > 0 else 0.0

            time_str = now.strftime("%H:%M:%S")

            timeline = data.get("daily_timeline", [])
            if len(timeline) > 7:
                timeline = timeline[-7:]

            self.timeline_data = timeline

            self.root.after(0, lambda: self._apply_ui_update(
                today_tot, today_ratio, today_calls, today_in, today_out, today_thinking, today_cost, time_str, timeline
            ))
        except Exception:
            pass

    def _apply_ui_update(self, tot, ratio, calls, in_tok, out_tok, thinking_tok, cost_usd, time_str, timeline):
        self.val_today_total.configure(text=f"{fmt_short(tot)}")
        self.val_today_badge.configure(text=f"缓存 {ratio}%")
        cost_str = f"${cost_usd:.2f} (￥{cost_usd*7.2:.1f})"
        self.val_today_sub.configure(text=f"全机实时 · 预估费用: {cost_str}")
        self.lbl_today_calls.configure(text=f"{calls:,} 次调用")
        self.lbl_detail_in.configure(text=f"输入: {fmt_short(in_tok)}")
        self.lbl_detail_out.configure(text=f"输出: {fmt_short(out_tok)} (含思考: {fmt_short(thinking_tok)})")
        self.lbl_update_time.configure(text=f"{time_str} 自动更新")

        # 动态同步更新 Windows 任务栏系统托盘悬停提示
        if self.tray_icon:
            try:
                tip = f"Token 实时监视器\n今日: {fmt_short(tot)} | {cost_str}\n双击或右键托盘图标呼出菜单"
                self.tray_icon.title = tip[:127]
            except Exception:
                pass

        if timeline:
            peak = max(d.get("total", 0) for d in timeline)
            self.lbl_trend_peak.configure(text=f"7日最高: {fmt_short(peak)}")

        self._draw_trend_chart(timeline)

    def _draw_trend_chart(self, timeline):
        self.canvas.delete("all")
        if not timeline:
            w = self.canvas.winfo_width() or 300
            h = self.canvas.winfo_height() or 80
            self.canvas.create_text(w // 2, h // 2, text="暂无趋势数据", fill=self.c_muted, font=self.font_micro)
            return

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 10 or h <= 10:
            return

        pad_top = 18    # 留出柱顶数字空间
        pad_bot = 20    # 留出底部日期标签空间
        pad_left = 10
        pad_right = 10

        chart_w = w - pad_left - pad_right
        chart_h = h - pad_top - pad_bot

        # 最大值计算
        max_val = max([d.get("total", 0) for d in timeline] + [1000])
        max_val *= 1.15

        n = len(timeline)
        slot_w = chart_w / max(1, n)
        bar_w = max(6, min(28, int(slot_w * 0.6)))

        now_str = datetime.datetime.now().strftime("%Y-%m-%d")

        # 背景参考虚线与底线
        y_mid = pad_top + chart_h / 2
        self.canvas.create_line(pad_left, y_mid, w - pad_right, y_mid, fill="#21262d", dash=(2, 2))
        y_base = pad_top + chart_h
        self.canvas.create_line(pad_left, y_base, w - pad_right, y_base, fill=self.c_border)

        for idx, d in enumerate(timeline):
            center_x = pad_left + idx * slot_w + slot_w / 2
            tot_v = d.get("total", 0)
            d_str = d.get("date", "")
            is_today = (d_str == now_str)

            # 柱子高度
            bar_h = int((tot_v / max_val) * chart_h) if max_val > 0 else 0
            x1 = center_x - bar_w / 2
            x2 = center_x + bar_w / 2
            y2 = y_base
            y1 = y2 - max(2, bar_h) if tot_v > 0 else y2

            # 柱子填充颜色：今日高亮突出
            fill_color = self.c_today_bar if is_today else self.c_bar
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline="")

            # 柱顶总量数值标签 (例如 508M, 136M)
            val_label = fmt_short(tot_v)
            label_y = max(8, y1 - 8)
            label_fg = "#ffffff" if is_today else self.c_muted
            self.canvas.create_text(center_x, label_y, text=val_label, fill=label_fg, font=self.font_bar_val)

            # 底部日期标签 (例如 08-29, 今天)
            date_label = "今天" if is_today else d_str[5:]
            date_fg = self.c_primary if is_today else self.c_muted
            self.canvas.create_text(center_x, h - 9, text=date_label, fill=date_fg, font=self.font_bar_date)

    def quit_application(self):
        self.is_running = False
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()

    def close(self):
        # 兼容旧调用或关闭按钮，默认行为是收纳至托盘（类似微信）
        self.hide_to_tray()

    def run(self):
        self.root.mainloop()

def main():
    app = DesktopTokenWidget()
    app.run()

if __name__ == "__main__":
    main()
