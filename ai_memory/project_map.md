# 项目地图 - Locust压力测试平台

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| GUI框架 | PySide6 (Qt6) | ≥6.5 |
| 压测引擎 | Locust (程序化API) | ≥2.20 |
| 图表 | Matplotlib (Agg/Qt5Agg) | ≥3.7 |
| 数据库 | SQLite3 (WAL模式) | 内置 |
| 协程 | gevent | ≥23.0 |
| 定时任务 | APScheduler | ≥3.10 |
| PDF报告 | fpdf2 | ≥2.7 |
| Excel导出 | openpyxl | ≥3.1 |
| 系统监控 | psutil | ≥5.9 |
| 打包 | PyInstaller | ≥6.0 |

## 项目目录结构

```
performance_loust/
├── main.py                    # 应用入口
├── build.py                   # 打包脚本
├── insert_test_data.py        # 测试数据填充脚本
├── test_all.py                # 自动化测试套件
├── requirements.txt           # 依赖声明
├── LocustPlatform.spec        # PyInstaller打包规格
│
├── config/
│   ├── __init__.py
│   └── settings.py            # Settings单例 - 全局配置管理
│
├── core/
│   ├── __init__.py            # 懒加载入口(__getattr__)
│   ├── locust_engine.py       # LocustEngine - Locust引擎封装
│   ├── distributed_manager.py # DistributedManager - 分布式节点管理
│   └── plugin_manager.py      # PluginManager - 插件系统
│
├── database/
│   ├── __init__.py
│   └── db_manager.py          # DatabaseManager单例 - SQLite连接池+CRUD
│
├── services/
│   ├── __init__.py            # 服务导出
│   ├── task_service.py        # TaskService - 任务CRUD+校验
│   ├── execution_service.py   # ExecutionService单例 - 引擎生命周期管理
│   ├── report_service.py      # ReportService - PDF/Excel报告生成
│   ├── scheduler_service.py   # SchedulerService - 定时任务调度
│   └── api_import_service.py  # ApiImportService - API导入
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py         # MainWindow - 主窗口(页面注册+信号路由)
│   ├── navigation.py          # NavigationBar - 侧边导航栏
│   ├── status_bar.py          # StatusBar - 底部状态栏
│   └── styles.py              # StyleManager单例 - QSS主题管理
│
├── pages/
│   ├── __init__.py            # 页面导出
│   ├── home_page.py           # HomePage - 首页仪表盘
│   ├── create_task_page.py    # CreateTaskPage - 创建/编辑任务
│   ├── execute_task_page.py   # ExecuteTaskPage - 执行任务+队列管理
│   ├── monitor_page.py        # MonitorPage - 实时监控+图表
│   ├── history_page.py        # HistoryPage - 历史记录查询
│   └── settings_page.py       # SettingsPage - 设置中心
│
├── utils/
│   ├── __init__.py
│   ├── logger.py              # get_logger() - 日志工厂
│   ├── helpers.py             # 通用辅助函数
│   └── system_monitor.py      # SystemMonitor - 系统资源监控线程
│
├── ai_memory/                 # AI工程维护记忆
└── docs/                      # 项目文档
```

## 模块说明

| 模块 | 职责 | 关键类 |
|------|------|--------|
| config | 全局配置读写、持久化 | Settings(单例) |
| core | Locust引擎封装、分布式管理、插件系统 | LocustEngine, DistributedManager, PluginManager |
| database | SQLite连接池、5张表CRUD、列名白名单校验 | DatabaseManager(单例) |
| services | 业务逻辑层：任务管理、执行控制、报告生成、调度 | ExecutionService(单例), TaskService, ReportService |
| ui | 主窗口框架、导航栏、状态栏、主题管理 | MainWindow, NavigationBar, StyleManager(单例) |
| pages | 6个功能页面（MVC中的View+Controller） | HomePage, CreateTaskPage, ExecuteTaskPage, MonitorPage, HistoryPage, SettingsPage |
| utils | 日志、辅助函数、系统监控 | get_logger(), SystemMonitor |

## 核心业务流程

```
用户操作流程:
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 创建任务  │───▶│ 执行任务  │───▶│ 实时监控  │───▶│ 历史记录  │───▶│ 生成报告  │
│CreateTask│    │ExecuteTask│   │ Monitor  │    │ History  │    │ Report   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
  TaskService    ExecutionService  LocustEngine   DatabaseManager  ReportService
     │               │                                               │
     ▼               ▼                                               ▼
 DatabaseManager  LocustEngine                                   fpdf2/openpyxl
```

### 详细流程:

1. **创建任务**: CreateTaskPage → TaskService.create_task() → DatabaseManager → tasks表
2. **执行任务**: ExecuteTaskPage → ExecutionService.start_task() → LocustEngine.start() → gevent协程运行
3. **实时监控**: MonitorPage定时器(1s) → ExecutionService.get_task_status() → LocustEngine.get_stats() → 更新卡片+图表
4. **停止任务**: ExecutionService.stop_task() → LocustEngine.stop() → _save_final_results() → task_results表 + history表
5. **历史查询**: HistoryPage → DatabaseManager.get_history_list() → history表
6. **生成报告**: ReportService.generate_report() → task_results + history → PDF/Excel文件

## 系统地图 - 单例与信号流

```
┌─────────────────────────────────────────────────────────┐
│                      MainWindow                          │
│  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │ NavigationBar│  │         QStackedWidget            │ │
│  │              │  │ ┌────┬────┬────┬────┬────┬────┐  │ │
│  │ ▸ 首页       │  │ │Home│Create│Exec│Moni│Hist│Sett│  │ │
│  │ ▸ 创建任务   │  │ │    │Task │Task│tor │ory │ings│  │ │
│  │ ▸ 执行任务   │  │ └────┴────┴────┴────┴────┴────┘  │ │
│  │ ▸ 实时监控   │  │                                    │ │
│  │ ▸ 历史记录   │  └──────────────────────────────────┘ │
│  │ ▸ 设置中心   │                                      │
│  └──────┬───────┘                                      │
│         │ navigation_changed(int)                       │
│         ▼                                               │
│  _on_navigation_changed → stackedWidget.setCurrentIndex │
│                                                         │
│  页面.navigate_requested ──▶ _switch_page(int)         │
└─────────────────────────────────────────────────────────┘

单例实例:
  Settings ←── config/settings.py
  DatabaseManager ←── database/db_manager.py
  ExecutionService ←── services/execution_service.py
  StyleManager ←── ui/styles.py
```
