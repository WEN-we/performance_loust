# 历史遗留笔记 - Locust压力测试平台

## 历史遗留问题

### 1. core/__init__.py 懒加载机制
- **问题**: locust 导入时会 monkey-patch 标准库，导致 "bad file descriptor" 崩溃
- **方案**: 使用 `__getattr__` 模块级懒加载，延迟到实际使用时才 import
- **状态**: 已修复，但机制脆弱
- **注意**: 任何修改 core/__init__.py 的行为都可能导致崩溃回归

### 2. LocustEngine._ensure_locust_imported()
- **问题**: LocustEngine 的 stop() 方法在引擎未初始化时调用会失败
- **方案**: stop() 中先检查 IDLE/STOPPED 状态，再调用 _ensure_locust_imported()
- **注意**: 顺序不能颠倒，否则空转时也会触发 locust 导入

### 3. PyInstaller 打包兼容性
- **问题**: tkinter 被 matplotlib 依赖链拉入，但打包时不包含 Tcl 数据目录
- **方案**: 打包命令添加 `--exclude-module tkinter --exclude-module _tkinter`
- **注意**: 每次修改打包配置都必须验证 exe 能否启动

### 4. gevent C扩展模块
- **问题**: gevent 的 C 扩展模块需要逐个声明 hidden-import
- **方案**: 在 PyInstaller 命令中列出所有 `_gevent_c_*` 模块
- **注意**: 升级 gevent 版本后需检查是否有新的 C 扩展模块

## 耦合点

### 高耦合: ExecutionService ↔ LocustEngine
- ExecutionService 直接持有 LocustEngine 实例字典
- 引擎状态通过 Python 字典传递，无类型约束
- **风险**: 修改 LocustEngine 接口会直接影响 ExecutionService

### 高耦合: MonitorPage ↔ ExecutionService
- 监控页直接调用 get_task_status() 获取引擎状态
- stats 字典的键名是隐式约定，无 Schema 定义
- **风险**: 修改 stats 返回格式会导致监控页数据错乱

### 中耦合: DatabaseManager ↔ 所有 services/pages
- 7个模块直接依赖 DatabaseManager
- SQL 列名通过 valid_columns 白名单硬编码
- **风险**: 修改表结构必须同步更新所有 valid_columns

### 中耦合: Settings ↔ 多个模块
- 4个模块直接读取 Settings 属性
- 属性名变更会导致运行时 AttributeError
- **风险**: 重命名配置项需全局搜索替换

## 注意事项

1. **QButtonGroup.idClicked 递归**: set_current_index 中必须有 `_current_index != index` 保护，否则无限递归→栈溢出→崩溃
2. **空字典 falsy 判断**: `if not stats` 对空字典 `{}` 返回 True，必须用 `if not stats or not isinstance(stats, dict)` 或显式检查
3. **QItemSelectionModel.currentRowChanged**: 信号参数是 `(QModelIndex, QModelIndex)`，不是 `(int, int)`
4. **threading.Lock 不可重入**: 同一线程重复 acquire 会死锁，如需重入用 threading.RLock
5. **SQLite WAL 模式**: 多进程写入时仍需注意锁，WAL 只解决读写并发
6. **matplotlib 嵌入 Qt**: 必须使用 `FigureCanvasQTAgg`，不能用 `FigureCanvasAgg`
7. **fpdf2 中文字体**: 必须显式 add_font，Helvetica 不支持中文
8. **time.monotonic() vs time.time()**: 计算运行时长必须用 monotonic，time() 会受系统时钟调整影响

## 禁止重构区域

1. **core/__init__.py 的 __getattr__**: 懒加载机制是解决 bad file descriptor 的唯一方案，不可重构
2. **ExecutionService.__new__ 单例**: 改为单例是为了跨页面共享引擎状态，不可回退
3. **NavigationBar.set_current_index 的递归保护**: 删除保护会导致程序崩溃
4. **db_manager.py 的 valid_columns 白名单**: 删除会导致 SQL 注入风险
5. **main.py 启动时的 running→interrupted 清理**: 删除会导致重启后任务状态永久卡在 running
