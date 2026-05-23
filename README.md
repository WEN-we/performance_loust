# 🚀 Locust 压力测试平台

[English](./README_EN.md) | 中文

基于 Locust 的 Windows 桌面压力测试平台，提供可视化任务管理、实时监控与报告生成功能。

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.5+-green)
![Locust](https://img.shields.io/badge/Locust-2.20+-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 📋 功能特性

### 核心功能
- **HTTP/HTTPS 压测** — 支持 GET/POST/PUT/DELETE/PATCH 等全方法
- **WebSocket 压测** — 原生 WebSocket 协议压力测试
- **JWT 认证** — 支持 Bearer Token / Basic Auth
- **参数化变量** — `${variable}` 语法，支持 CSV 数据驱动
- **自定义请求** — Header / Cookie / Token / JSON Body / Form / 文件上传
- **分布式压测** — Master/Worker 多机协同

### 界面功能
- **6 大功能页面** — 首页仪表盘、创建任务、执行任务、实时监控、历史记录、系统设置
- **暗黑模式** — 一键切换亮色/暗黑主题
- **实时监控** — 12 项核心指标 + 4 组折线图（matplotlib）
- **报告导出** — HTML / PDF / Excel / PNG 多格式
- **API 导入** — Swagger/OpenAPI/Postman Collection 一键导入

### 技术特性
- **插件扩展** — 动态加载插件，钩子系统
- **定时任务** — APScheduler Cron 定时执行
- **系统监控** — CPU/内存实时显示
- **日志系统** — 按天轮转，自动记录 traceback

---

## 📁 项目结构

```
performance_loust/
│
├── main.py                    # 应用入口
├── build.py                   # PyInstaller 打包辅助
├── requirements.txt           # 依赖清单
│
├── config/                    # 配置管理
│   └── settings.py            # 单例 Settings，JSON 配置读写
│
├── core/                      # 核心引擎
│   ├── locust_engine.py       # Locust 引擎（延迟导入，兼容 PyInstaller）
│   ├── distributed_manager.py # 分布式 Master/Worker 管理
│   └── plugin_manager.py      # 插件扩展机制
│
├── database/                  # 数据持久层
│   └── db_manager.py          # SQLite 管理器（5 表 CRUD + 连接池 + 事务）
│
├── services/                  # 业务服务层
│   ├── task_service.py        # 任务生命周期管理
│   ├── execution_service.py   # 任务执行控制（队列/暂停/恢复）
│   ├── report_service.py      # HTML/PDF/Excel/PNG 报告生成
│   ├── scheduler_service.py   # APScheduler 定时任务
│   └── api_import_service.py  # Swagger/OpenAPI/Postman 导入
│
├── ui/                        # UI 框架层
│   ├── main_window.py         # 主窗口（6 页面集成）
│   ├── navigation.py          # 左侧导航栏（程序化图标）
│   ├── status_bar.py          # 顶部 CPU/内存状态栏
│   └── styles.py              # QSS 样式管理（亮色/暗黑主题）
│
├── pages/                     # 页面组件层
│   ├── home_page.py           # 首页仪表盘
│   ├── create_task_page.py    # 创建/编辑任务
│   ├── execute_task_page.py   # 执行任务（状态徽章 + 队列）
│   ├── monitor_page.py        # 实时监控（12 指标 + 4 折线图）
│   ├── history_page.py        # 历史记录（分页 + 导出）
│   └── settings_page.py       # 系统设置
│
├── utils/                     # 工具层
│   ├── logger.py              # 日志系统（按天轮转 + traceback）
│   ├── helpers.py             # 资源路径/CSV/JSON/文件操作
│   └── system_monitor.py      # CPU/内存/磁盘/网络监控
│
├── plugins/                   # 插件目录（自动扫描加载）
├── resources/                 # 资源文件（图标等）
├── logs/                      # 日志输出目录
└── data/                      # SQLite 数据库目录
```

---

## 🗄️ 数据库设计

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `tasks` | 任务配置 | name, type, method, url, headers, cookies, token, body, users, spawn_rate, run_time |
| `task_results` | 执行结果 | task_id, status, qps, tps, rps, avg/max/min/p95_response_time, fail_rate |
| `history` | 历史记录 | task_name, execute_time, duration, result_summary, stats_json |
| `settings` | 系统设置 | key, value |
| `distributed_nodes` | 分布式节点 | task_id, node_type, host, port, status, worker_count |

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Windows 10/11
- pip

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/WEN-we/performance_loust.git
cd performance_loust

# 2. 创建虚拟环境
python -m venv .venv

# 3. 激活虚拟环境
.venv\Scripts\activate

# 4. 安装依赖
pip install -r requirements.txt

# 5. 运行应用
python main.py
```

### 直接下载

👉 前往 [Releases](https://github.com/WEN-we/performance_loust/releases) 下载 Windows 可执行程序，无需安装 Python。

---

## 📦 打包

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包（目录模式，推荐）
pyinstaller --name LocustPlatform --windowed --noconfirm main.py

# 打包（单文件模式）
pyinstaller -F -w -i icon.ico --name LocustPlatform main.py

# 使用 spec 文件打包
pyinstaller LocustPlatform.spec --noconfirm
```

打包产物位于 `dist/LocustPlatform/` 目录。

---

## 📊 实时监控指标

| 指标 | 说明 |
|------|------|
| QPS | 每秒请求数 |
| TPS | 每秒事务数 |
| RPS | 每秒响应数 |
| 平均响应时间 | 所有请求的平均响应时间 |
| 最大/最小响应时间 | 响应时间极值 |
| P95 响应时间 | 95% 请求的响应时间 |
| 失败率 | 失败请求占比 |
| 当前在线用户数 | 活跃虚拟用户数 |
| 成功/失败请求数 | 请求统计 |

---

## 🔌 插件开发

在 `plugins/` 目录下创建 Python 文件，继承 `PluginBase`：

```python
from core.plugin_manager import PluginBase, HookType

class MyPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "my_plugin"

    def on_load(self) -> None:
        self.add_hook(HookType.PRE_REQUEST, self.before_request)

    def on_unload(self) -> None:
        pass

    def before_request(self, **kwargs):
        print("请求前处理")
```

启动时自动扫描 `plugins/` 目录并加载。

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| GUI 框架 | PySide6 |
| 压测引擎 | Locust |
| 图表 | Matplotlib |
| 数据库 | SQLite |
| 定时任务 | APScheduler |
| 报告 | Jinja2 / fpdf2 / openpyxl |
| 系统监控 | psutil |
| 打包 | PyInstaller |

---

## 📄 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
