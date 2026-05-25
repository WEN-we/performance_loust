# 变更日志 - Locust压力测试平台

## 2026-05-25 v1.0.1

### 修改文件
- pages/monitor_page.py
- services/execution_service.py
- ui/main_window.py
- pages/execute_task_page.py
- insert_test_data.py (新增)
- main.py

### 修改原因
1. ExecutionService改为单例，修复跨页面无法感知运行中任务
2. 监控页图表改为2x2网格布局+QFrame卡片容器+渐变填充+悬浮数据提示
3. 监控页新增_update_status_label显示任务真实运行状态
4. 监控页新增_load_history_chart_data为已停止任务生成模拟趋势
5. 执行任务页_on_task_selected信号参数修复(QModelIndex vs int)
6. MainWindow连接页面navigate_requested信号
7. 新增insert_test_data.py自动插入8组测试任务+12条历史记录
8. 图表遮挡修复(最小高度280px + subplots_adjust边距)
9. 打包排除tkinter修复exe无法启动

### 影响范围
- 所有使用ExecutionService的页面(3个)
- 监控页全部功能
- 执行任务页选中功能
- 首页按钮导航功能
- 打包产物

---

## 2026-05-23 v1.0.0

### 修改文件
- ui/navigation.py
- services/execution_service.py
- pages/create_task_page.py
- services/report_service.py
- database/db_manager.py
- config/settings.py
- pages/monitor_page.py
- pages/execute_task_page.py
- pages/history_page.py
- pages/settings_page.py
- pages/__init__.py
- main.py
- core/locust_engine.py
- services/task_service.py
- utils/system_monitor.py

### 修改原因
系统修复模式5阶段执行：完整扫描→错误分析(P0-P3)→自动修复→回归测试→优化
共修复22个Bug：
- P0: 导航按钮无限递归崩溃
- P1: URL解析错误、QPS/TPS/RPS重复、PDF中文乱码、表单标签未隐藏
- P2: run_time正则、spawn_rate类型、elapsed漂移、异常吞没等
- P3: 页面导入、主题样式、清理残留状态等

### 影响范围
- 全部17个源码文件
- 数据库schema(spawn_rate INTEGER→REAL)
- 打包配置
