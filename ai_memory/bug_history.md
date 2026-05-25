# Bug历史记录 - Locust压力测试平台

## BUG-001: 导航按钮无限递归导致程序崩溃

- **问题**: 点击任意导航按钮，程序直接退出而非切换页面
- **原因**: `set_current_index()` 调用 `button.click()` 触发 `QButtonGroup.idClicked`，再次调用 `set_current_index()`，形成无限递归→栈溢出→崩溃
- **解决方案**: 添加 `self._current_index != index` 递归保护
- **影响范围**: ui/navigation.py
- **严重级别**: P0

## BUG-002: URL解析错误导致所有压测请求发往错误地址

- **问题**: 所有HTTP压测任务的实际请求地址与配置不符
- **原因**: `_build_engine_config` 直接将完整URL传给 Locust 的 host 参数，但 Locust 会将 host + task.path 拼接，导致路径重复
- **解决方案**: 使用 `urllib.parse.urlparse` 将 URL 拆分为 host + path
- **影响范围**: services/execution_service.py
- **严重级别**: P1

## BUG-003: QPS/TPS/RPS重复计算

- **问题**: 监控页显示的 TPS 与 RPS 完全相同，无法区分
- **原因**: TPS 直接取用 RPS 值，未独立计算
- **解决方案**: TPS = success_count / elapsed_seconds，独立于 RPS
- **影响范围**: pages/monitor_page.py, services/execution_service.py
- **严重级别**: P1

## BUG-004: PDF报告中文乱码

- **问题**: 生成的PDF报告中中文显示为乱码
- **原因**: fpdf2 默认使用 Helvetica 字体，不支持中文
- **解决方案**: 自动检测系统中文字体(msyh.ttc > simhei.ttf > simsun.ttc)，add_font 加载
- **影响范围**: services/report_service.py
- **严重级别**: P1

## BUG-005: 表单标签未随控件隐藏

- **问题**: 认证类型切换后，Token/用户名/密码的输入框隐藏了但标签还在
- **原因**: QGridLayout 中标签和控件是独立的 widget，setVisible 只隐藏了控件
- **解决方案**: 使用 Container Widget 模式，将标签+控件放入同一个 QWidget 容器
- **影响范围**: pages/create_task_page.py
- **严重级别**: P1

## BUG-006: 任务列表选中信号参数不匹配

- **问题**: 执行任务页面选中任务后，详情区域不更新，按钮功能失效
- **原因**: `_on_task_selected(self, row: int)` 签名与 `currentRowChanged(QModelIndex, QModelIndex)` 不匹配
- **解决方案**: 修改签名为 `_on_task_selected(self, current: QModelIndex, _previous=None)`，用 `current.row()` 取行号
- **影响范围**: pages/execute_task_page.py
- **严重级别**: P1

## BUG-007: ExecutionService非单例导致跨页面无法感知运行中任务

- **问题**: 执行页启动任务后，监控页看不到运行中的任务
- **原因**: 每个页面创建独立的 ExecutionService 实例，各自的 _engines 字典互不共享
- **解决方案**: ExecutionService 改为单例模式（__new__ + _init_lock + _initialized）
- **影响范围**: services/execution_service.py, 所有使用 ExecutionService 的页面
- **严重级别**: P0

## BUG-008: 监控页非运行任务时图表无数据

- **问题**: 选择已停止的任务监控，趋势图表完全空白
- **原因**: `if not stats` 对空字典返回 True 导致提前返回；非运行任务时只有最终统计数据，无时序数据
- **解决方案**: 1) 修复空字典判断逻辑 2) 新增 _load_history_chart_data 从最终统计数据生成模拟趋势
- **影响范围**: pages/monitor_page.py
- **严重级别**: P1

## BUG-009: 监控页状态误显示

- **问题**: 选择未执行的任务，状态显示为"执行中"
- **原因**: 监控页未显示任务的真实运行状态
- **解决方案**: 新增 _update_status_label 方法，根据 engine_state + db_status 显示真实状态
- **影响范围**: pages/monitor_page.py
- **严重级别**: P2

## BUG-010: PyInstaller打包后exe无法启动

- **问题**: 双击exe闪退，报错 `_tcl_data directory not found`
- **原因**: matplotlib 依赖链拉入 tkinter 运行时钩子，但打包未包含 Tcl 数据目录
- **解决方案**: 打包命令添加 `--exclude-module tkinter --exclude-module _tkinter`
- **影响范围**: 打包配置
- **严重级别**: P0

## BUG-011: 首页按钮点击无反应

- **问题**: 首页的功能按钮点击后不跳转到对应页面
- **原因**: HomePage.navigate_requested 信号未在 MainWindow._connect_signals 中连接
- **解决方案**: 遍历所有页面，将 navigate_requested 信号连接到 _switch_page
- **影响范围**: ui/main_window.py
- **严重级别**: P1

## BUG-012: spawn_rate类型错误

- **问题**: spawn_rate 在数据库中为 INTEGER，无法设置小数值
- **原因**: 建表语句中 spawn_rate 定义为 INTEGER DEFAULT 1
- **解决方案**: 改为 REAL DEFAULT 1.0，Settings 属性从 int 改为 float
- **影响范围**: database/db_manager.py, config/settings.py
- **严重级别**: P2

## BUG-013: elapsed时间漂移

- **问题**: 监控页运行时长显示不准确，随时间漂移
- **原因**: 使用 `self._elapsed_seconds += 1.0` 累加，定时器精度不足导致漂移
- **解决方案**: 改用 `time.monotonic()` 计算实际经过时间
- **影响范围**: pages/monitor_page.py
- **严重级别**: P2

## BUG-014: 图表遮挡

- **问题**: 2x2网格布局中图表太小，标题和坐标轴标签被裁切
- **原因**: 未设置图表最小高度，tight_layout 边距不足
- **解决方案**: 设置最小高度280px，使用 subplots_adjust 精确控制边距
- **影响范围**: pages/monitor_page.py
- **严重级别**: P2
