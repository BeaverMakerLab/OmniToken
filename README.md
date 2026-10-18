# 🪙 OmniToken

<div align="center">

**一体化本地 AI Token 与成本监控平台 (Desktop HUD & Web Analytics)**

*实时监控 Google Antigravity、OpenAI Codex 与 DeepSeek 消耗，精确计算官方阶梯价格，搭配微信式托盘悬浮窗与炫酷数据大屏*

[![Release](https://img.shields.io/github/v/release/Doraawa/OmniToken?color=blue&style=flat-square)](https://github.com/Doraawa/OmniToken/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20(便携独立版)-0078D6.svg?style=flat-square&logo=windows&logoColor=white)](https://github.com/Doraawa/OmniToken/releases)

[✨ 核心功能](#-核心功能) • [🚀 快速开始](#-快速开始) • [🖥️ 界面与交互](#️-界面与交互) • [💰 定价模型](#-支持模型与计费规则) • [⚙️ 高级配置与打包](#️-高级配置与打包)

</div>

---

## 📖 简介

在日常使用各种 AI 编程助手（如 **Google Antigravity**、**OpenAI Codex CLI** 和 **DeepSeek Harness**）时，开发者常常面临无法直观掌握当天 Token 消耗速度、难以预估 API 账单金额、缺乏全局多平台汇总等痛点。

**OmniToken** 专为解决这一问题而生。它无需任何云端转发或泄露本地隐私，直接在本地解析各客户端的历史记录与数据库，实时汇总多平台 Token 流水，结合官方阶梯计费模型换算为真实人民币/美元金额，并通过**极简桌面 HUD 悬浮微件**和**交互式 Web 监控大屏**全方位呈现。

---

## ✨ 核心功能

- **🔍 多源无感扫描与隐私安全**
  - **Google Antigravity**：自动读取本地 SQLite 数据库及 WAL 缓存，通过物理文件写入与记录修改双重时间戳精确校准今日用量。
  - **OpenAI Codex CLI**：实时解析 `~/.codex/sessions` 会话元数据及 Token 流水。
  - **DeepSeek Harness**：无缝支持 DeepSeek CLI 与 Harness 会话统计。
  - **100% 本地运行**：纯本地扫描，不上传任何对话内容或私有密钥。

- **💰 精准模型官方计价引擎**
  - 内置最新阶梯计价标准（输入 Input、补全 Output、缓存读取 Cache Read、缓存写入 Cache Write）。
  - 支持 **Gemini 2.5 Pro / Flash**、**Gemini 1.5 系列**、**GPT-4o / GPT-4o-mini**、**o1 / o3 系列** 以及 **DeepSeek V3 / R1 (Reasoner)**。
  - 自动换算 USD 与 RMB（支持自定义汇率）。

- **🪟 极简桌面 HUD 悬浮微件**
  - **纯粹无打扰**：半透明磨砂设计，置顶常驻桌面边缘，随意拖拽并自动记忆坐标。
  - **任务栏静默**：不在 Windows 任务栏占据图标或标签位，保持工作区清爽。
  - **微信式系统托盘**：常驻右下角通知区域，支持双击/右键呼出菜单、一键开机自启、置顶锁定与快速刷新。

- **📊 全功能交互式 Web 大屏**
  - 内置零依赖轻量 HTTP 服务（默认端口 `8765`）。
  - 支持**今日 / 近7天 / 近30天 / 全部**时间维度切换。
  - 动态呈现**每日消耗趋势折线图**、**平台/模型消耗环形图**、**成本阶梯明细表**及**会话排行榜**。

---

## 🚀 快速开始

### 方式一：下载 Windows 免安装便携版 (推荐，小白首选)

无需配置 Python 开发环境，开箱即用：

1. 前往 [Releases 发行页面](https://github.com/Doraawa/OmniToken/releases) 下载最新版本的 `TokenMonitor-v1.0-Windows.zip`。
2. 解压到任意目录（例如 `D:\Tools\OmniToken`）。
3. 双击运行 `TokenMonitor.exe`：
   - 桌面右侧将自动出现半透明 HUD 悬浮窗；
   - 任务栏右下角出现托盘图标；
   - 双击悬浮窗或在托盘右键选择“打开 Web 看板”，即可在浏览器中进入交互大屏。

---

### 方式二：从源码运行

如果你熟悉 Python 环境，可以直接克隆本仓库：

```bash
# 1. 克隆仓库
git clone https://github.com/Doraawa/OmniToken.git
cd OmniToken

# 2. 安装必要依赖 (仅两个极简轻量库)
pip install -r requirements.txt
```

#### 启动选项：

- **启动桌面微件 + 后台 Web 服务** (推荐日常使用)：
  ```bash
  pythonw main.py
  # 或者直接双击运行 启动桌面悬浮窗.bat
  ```
- **仅启动 Web 监控大屏**：
  ```bash
  python main.py --web
  # 或者直接双击运行 启动Web看板.bat
  ```
- **在终端命令行查看报表 (CLI 模式)**：
  ```bash
  # 查看今日消耗
  python main.py --cli --today

  # 查看近 7 天报表
  python main.py --cli --days 7
  ```

---

## 🖥️ 界面与交互

### 1. 桌面 HUD 悬浮窗交互
| 操作 | 响应 |
| :--- | :--- |
| **鼠标左键拖拽** | 移动悬浮窗位置，释放后自动保存坐标并在下次启动时恢复 |
| **鼠标左键双击** | 一键呼出默认浏览器打开 Web 监控大屏 (`http://127.0.0.1:8765`) |
| **鼠标右键单击** | 弹出功能菜单：刷新数据、打开网页大屏、开机自启动开关、窗口置顶、退出程序 |

### 2. 右下角系统托盘交互
- **托盘常驻**：即使隐藏悬浮窗或最小化，系统托盘图标依然提供控制中枢。
- **开机自启动**：勾选后写入当前用户注册表启动项，开机静默常驻，不弹控制台黑框。

---

## 💰 支持模型与计费规则

OmniToken 内置了主流模型的标准官方 API 定价字典（单位：美元 / 每 1M Tokens）：

| 模型分类 | 代表模型 | 输入 / 1M | 输出 / 1M | 缓存读取 / 1M | 备注 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Gemini 2.5** | `gemini-2.5-flash` | \$0.075 | \$0.30 | \$0.01875 | 高性价比主流模型 |
| | `gemini-2.5-pro` | \$1.25 | \$5.00 | \$0.3125 | 深度推理旗舰 |
| **Gemini 1.5** | `gemini-1.5-flash` | \$0.075 | \$0.30 | \$0.01875 | 快速轻量 |
| | `gemini-1.5-pro` | \$1.25 | \$5.00 | \$0.3125 | 长上下文分析 |
| **OpenAI** | `gpt-4o` | \$2.50 | \$10.00 | \$1.25 | 多模态通用旗舰 |
| | `gpt-4o-mini` | \$0.15 | \$0.60 | \$0.075 | 极致性价比 |
| | `o1` / `o3-mini` | \$15.00 / \$1.10 | \$60.00 / \$4.40 | 支持 | 深度思维链模型 |
| **DeepSeek** | `deepseek-chat` (V3) | \$0.14 | \$0.28 | \$0.014 | 极低单价通用模型 |
| | `deepseek-reasoner` (R1) | \$0.55 | \$2.19 | \$0.14 | 强化学习思维链模型 |

> *注：程序内置美元转人民币基础汇率（默认 7.25），可在 `token_core.py` 中自由调整或扩展更多定制模型。*

---

## ⚙️ 高级配置与打包

### 项目结构

```text
OmniToken/
├── main.py                 # 统一主入口 (自动适配 GUI、Web、CLI 运行模式)
├── desktop_widget.pyw      # 桌面 HUD 悬浮微件 (Tkinter + PIL + Pystray 托盘)
├── app.py                  # 轻量 HTTP 服务及 CLI 命令行输出
├── token_core.py           # 核心扫描与计价引擎 (SQLite WAL 分析、正则解析、费用计算)
├── index.html              # 现代化 Web 数据大屏 (包含 Chart.js 图表与交互透视)
├── app.ico                 # 应用程序多分辨率高清图标
├── requirements.txt        # Python 依赖清单
├── 启动桌面悬浮窗.bat       # Windows 桌面后台无黑框快捷启动脚本
├── 启动Web看板.bat          # Windows 网页大屏快捷启动脚本
├── LICENSE                 # MIT 开源协议
└── README.md               # 项目使用说明
```

### 自行打包为单文件可执行程序 (.exe)

如果你对源码进行了修改并希望重新打包为独立单文件版：

```bash
# 安装 PyInstaller
pip install pyinstaller

# 一键打包命令 (无控制台窗口、内嵌 HTML 与图标资源)
pyinstaller --noconfirm --clean --windowed `
  --icon="app.ico" `
  --add-data "index.html;." `
  --add-data "app.ico;." `
  --name "TokenMonitor" `
  main.py
```

打包完成后，可在 `dist/` 目录下找到生成的 `TokenMonitor.exe`。

---

## 🤝 贡献与反馈

欢迎提交 PR 或创建 Issue！如果你在使用过程中遇到新客户端兼容需求或模型定价更新，欢迎贡献代码共同完善。

1. Fork 本仓库并新建分支 (`git checkout -b feature/AmazingFeature`)
2. 提交修改 (`git commit -m 'Add some AmazingFeature'`)
3. 推送分支 (`git push origin feature/AmazingFeature`)
4. 提交 Pull Request

---

## 📄 开源许可证

本项目采用 [MIT 许可证](LICENSE) 开源。
