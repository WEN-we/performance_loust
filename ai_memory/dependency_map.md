# 依赖地图 - Locust压力测试平台

## 模块依赖关系

### 层级架构
```
┌─────────────────────────────────────────┐
│              main.py (入口)              │
├─────────────────────────────────────────┤
│                 ui 层                    │
│  MainWindow / NavigationBar / StatusBar │
├─────────────────────────────────────────┤
│               pages 层                  │
│  HomePage / CreateTaskPage / ...        │
├─────────────────────────────────────────┤
│              services 层                │
│  TaskService / ExecutionService / ...   │
├─────────────────────────────────────────┤
│               core 层                   │
│  LocustEngine / DistributedManager / ...│
├─────────────────────────────────────────┤
│             database 层                 │
│           DatabaseManager               │
├─────────────────────────────────────────┤
│              config 层                  │
│             Settings                    │
├─────────────────────────────────────────┤
│              utils 层                   │
│       logger / helpers / system_monitor │
└─────────────────────────────────────────┘
```

## 调用关系（谁依赖谁）

### main.py
- → config.settings (Settings)
- → database.db_manager (DatabaseManager)
- → ui.main_window (MainWindow)
- → ui.styles (StyleManager)
- → core (PluginManager)
- → utils.logger (get_logger)
- → insert_test_data (insert_test_data)

### ui/main_window.py
- → pages.* (所有6个页面类)
- → config.settings (Settings)
- → ui.navigation (NavigationBar)
- → ui.status_bar (StatusBar)
- → ui.styles (StyleManager)

### pages/home_page.py
- → services.execution_service (ExecutionService)
- → services.task_service (TaskService)
- → database.db_manager (DatabaseManager)
- → utils.system_monitor (SystemMonitor)

### pages/create_task_page.py
- → services.task_service (TaskService)
- → database.db_manager (DatabaseManager)
- → config.settings (Settings)

### pages/execute_task_page.py
- → services.execution_service (ExecutionService)
- → services.task_service (TaskService)
- → database.db_manager (DatabaseManager)

### pages/monitor_page.py
- → services.execution_service (ExecutionService)
- → database.db_manager (DatabaseManager)
- → matplotlib (FigureCanvas, Figure)

### pages/history_page.py
- → database.db_manager (DatabaseManager)
- → services.report_service (ReportService)

### pages/settings_page.py
- → config.settings (Settings)
- → ui.styles (StyleManager)

### services/execution_service.py
- → database.db_manager (DatabaseManager)
- → core.locust_engine (LocustEngine)
- → utils.logger (get_logger)

### services/task_service.py
- → database.db_manager (DatabaseManager)
- → utils.logger (get_logger)

### services/report_service.py
- → database.db_manager (DatabaseManager)
- → fpdf (FPDF)
- → openpyxl (Workbook)
- → utils.logger (get_logger)

### core/locust_engine.py
- → locust.* (HttpUser, Environment, LocalRunner, gevent)
- → utils.logger (get_logger)

### database/db_manager.py
- → utils.logger (get_logger)

## 被依赖关系（谁被谁依赖）

| 被依赖模块 | 依赖者数量 | 依赖者列表 |
|-----------|-----------|-----------|
| database.db_manager | 7 | main, home_page, create_task_page, execute_task_page, monitor_page, history_page, execution_service |
| utils.logger | 6 | main, execution_service, task_service, report_service, locust_engine, db_manager |
| config.settings | 4 | main, main_window, create_task_page, settings_page |
| services.execution_service | 3 | home_page, execute_task_page, monitor_page |
| ui.styles | 2 | main_window, settings_page |

## 循环依赖

**当前无循环依赖。** core/__init__.py 使用 __getattr__ 懒加载避免了 core ↔ services 的循环导入。

## 关键依赖链

### 执行任务链
```
ExecuteTaskPage → ExecutionService(单例) → LocustEngine → locust.HttpUser + gevent
                                          → DatabaseManager → SQLite
```

### 监控数据链
```
MonitorPage → ExecutionService(单例) → LocustEngine.get_stats()
           → DatabaseManager.get_latest_result_by_task() (回退)
           → matplotlib.FigureCanvas (图表渲染)
```

### 报告生成链
```
HistoryPage → ReportService → DatabaseManager → SQLite
                               → fpdf2/openpyxl → 文件系统
```
