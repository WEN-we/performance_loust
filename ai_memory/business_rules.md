# 业务规则 - Locust压力测试平台

## 状态流转

### 任务状态 (tasks表)
```
不存在 ──create_task()──▶ 已创建(无status字段)
```
注: tasks表本身无status字段，任务状态由task_results表的status字段体现。

### 任务执行结果状态 (task_results表)
```
         start_task()
不存在 ──────────────▶ running ─────┐
                                   │ stop_task()
                                   ▼
                                stopped
                                   │
                          异常中断  │  interrupted
                                   ▼
                                 error
```

**状态说明:**
- `running`: 任务正在执行中
- `stopped`: 任务正常停止完成
- `interrupted`: 程序异常退出导致的中断（启动时自动清理）
- `error`: 执行过程中发生错误

**关键规则:**
- 程序启动时自动将所有 `running` 状态改为 `interrupted`（main.py）
- 同一任务同一时刻只能有一个 `running` 实例
- ExecutionService._engines 字典维护 task_id → LocustEngine 的映射

### 引擎状态 (LocustEngine)
```
IDLE ──start()──▶ RUNNING ──stop()──▶ STOPPED
                       │
                       │ 异常
                       ▼
                     ERROR
```

## 核心业务规则

### 1. 任务创建规则
- 任务名称不可为空
- URL必须以 http:// 或 https:// 开头
- run_time 格式: 支持复合格式如 `1h30m`、`5m`、`30s`（正则: `^(\d+[smh])+$`）
- spawn_rate 为浮点数，最小值 0.1
- users 为正整数，最小值 1

### 2. 任务执行规则
- ExecutionService 为单例，全局唯一
- 同一任务不可重复启动（需先停止）
- 多任务队列按顺序执行（FIFO）
- 队列执行在独立线程中运行（_queue_thread）
- 队列停止使用 threading.Event（_queue_stop_event）

### 3. 监控数据规则
- 定时器1秒刷新一次（QTimer 1000ms）
- 运行中任务: 从 LocustEngine.get_stats() 获取实时数据
- 非运行任务: 从 DatabaseManager.get_latest_result_by_task() 回退到历史数据
- QPS = RPS（每秒请求数）
- TPS = success_count / elapsed_seconds（独立计算，不等于RPS）
- 失败率 = fail_count / total_requests

### 4. 数据库规则
- 所有连接使用 WAL 模式
- 连接池最大5个连接
- update方法必须使用 valid_columns 白名单校验列名
- 参数化查询，禁止字符串拼接SQL
- 事务使用 with self._lock 互斥

### 5. 报告生成规则
- PDF: 自动检测中文字体（msyh.ttc > simhei.ttf > simsun.ttc）
- Excel: 使用 openpyxl 生成
- 报告内容: 总览、响应时间分布、错误统计、请求详情

### 6. 导航规则
- NavigationBar 使用 QButtonGroup 管理
- idClicked 信号触发 navigation_changed
- set_current_index 有递归保护（_current_index != index）
- 页面 navigate_requested 信号连接到 MainWindow._switch_page

## 禁止事项

1. **禁止** 修改 tasks/task_results 表结构而不更新 db_manager.py 的 valid_columns
2. **禁止** 在 ExecutionService 中创建多个实例（已改为单例）
3. **禁止** 在 LocustEngine.start() 前不调用 _ensure_locust_imported()
4. **禁止** 直接操作 _engines 字典而不加 _lock
5. **禁止** 在 QButtonGroup.idClicked 回调中直接调用 button.click()（会导致无限递归）
6. **禁止** 使用 time.time() 计算运行时长（必须用 time.monotonic()）
7. **禁止** 在 except 块中使用 pass 吞掉异常（必须 logger.exception）
8. **禁止** 将 spawn_rate 声明为 INTEGER（必须是 REAL/浮点数）
9. **禁止** 在打包时包含 tkinter（--exclude-module tkinter）
10. **禁止** 删除或重构 core/__init__.py 的 __getattr__ 懒加载机制
