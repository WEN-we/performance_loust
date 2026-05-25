# AI工作规则 - Locust压力测试平台

> 本文件是AI助手在维护本项目时必须遵守的工作规则。
> 每次开始工作前，AI必须先读取 ai_memory/ 目录下的所有文件。

---

## 工作流程

### 步骤1: 读取项目记忆

每次会话开始时，必须按顺序读取以下文件：

```
1. ai_memory/AI_RULE.md          ← 本文件（工作规则）
2. ai_memory/project_map.md      ← 项目地图（技术栈、模块、流程）
3. ai_memory/business_rules.md   ← 业务规则（状态流转、禁止事项）
4. ai_memory/dependency_map.md   ← 依赖地图（调用关系、被依赖关系）
5. ai_memory/legacy_notes.md     ← 历史遗留（耦合点、禁止重构区域）
6. ai_memory/bug_history.md      ← Bug历史（避免重复犯错）
7. ai_memory/current_task.md     ← 当前任务
8. ai_memory/current_problem.md  ← 当前问题
9. ai_memory/current_solution.md ← 当前解决方案
10. ai_memory/changelog.md       ← 变更日志
```

### 步骤2: 分析影响

在修改任何代码之前，必须完成以下分析：

#### 2.1 修改文件分析
- 列出所有需要修改的文件
- 每个文件的修改内容概述
- 修改是否涉及核心模块（core/、services/、database/）

#### 2.2 依赖影响分析
- 参考 dependency_map.md，找出被修改模块的所有依赖者
- 评估修改是否会破坏下游模块
- 特别关注单例类和信号连接的变更

#### 2.3 风险评估
- **高风险**: 修改 core/__init__.py、ExecutionService单例、DatabaseManager、NavigationBar
- **中风险**: 修改 services 层、信号连接、数据库表结构
- **低风险**: 修改 pages 层UI、utils 辅助函数、新增功能

### 步骤3: 编码要求

#### 禁止事项
1. **禁止** 大规模重构 — 不改变现有项目架构
2. **禁止** 修改无关文件 — 只修改与当前任务直接相关的文件
3. **禁止** 删除历史逻辑 — 优先兼容，新增而非替换
4. **禁止** 修改 core/__init__.py 的 __getattr__ 懒加载机制
5. **禁止** 移除 NavigationBar.set_current_index 的递归保护
6. **禁止** 移除 db_manager.py 的 valid_columns 白名单校验
7. **禁止** 移除 ExecutionService 的单例模式
8. **禁止** 在 except 块中使用 pass 吞掉异常
9. **禁止** 使用 time.time() 计算运行时长
10. **禁止** 在 QButtonGroup.idClicked 回调中直接调用 button.click()

#### 必须事项
1. **必须** 参数校验 — 所有公开方法检查参数类型和范围
2. **必须** 日志记录 — 关键操作使用 logger.info/warning/error
3. **必须** 异常处理 — 所有外部调用（数据库、网络、文件）必须有 try/except
4. **必须** 线程安全 — 共享资源访问必须加锁（threading.Lock）
5. **必须** 类型标注 — 所有新增方法使用 Python 类型标注
6. **必须** 代码注释 — 关键业务逻辑添加中文注释
7. **必须** 语法检查 — 修改后运行 `python -m py_compile` 验证
8. **必须** 测试验证 — 修改后运行 `python test_all.py` 验证

### 步骤4: 自动检查清单

每次修改代码后，必须逐项检查：

| 检查项 | 检查内容 |
|--------|---------|
| 空指针 | 是否访问了可能为 None 的对象？ |
| SQL注入 | 是否使用参数化查询？是否通过 valid_columns 校验？ |
| XSS | 用户输入是否在显示前转义？（Qt中较少见） |
| 并发 | 共享资源是否加锁？是否有竞态条件？ |
| 性能 | 是否在主线程做耗时操作？是否有无限增长的数据结构？ |
| 边界条件 | 空列表、空字典、0值、负数、超大数是否处理？ |
| 信号递归 | Qt信号槽是否有循环触发风险？ |
| 资源泄漏 | 线程是否正确停止？数据库连接是否释放？ |
| 类型安全 | int/float/str 混用是否导致隐式转换错误？ |
| 打包兼容 | 新增的 import 是否需要添加 hidden-import？ |

### 步骤5: 自动更新项目记忆

每次修改完成后，必须更新以下文件：

#### changelog.md
```markdown
## YYYY-MM-DD

### 修改文件
- 文件路径列表

### 修改原因
- 具体原因

### 影响范围
- 受影响的模块和功能
```

#### current_task.md
```markdown
# 当前任务

## 任务描述
当前正在进行的任务描述

## 修改文件
- 文件路径列表

## 风险
- 风险评估
```

#### bug_history.md（如果是Bug修复）
```markdown
## BUG-XXX: Bug标题

- **问题**: 问题描述
- **原因**: 根因分析
- **解决方案**: 修复方式
- **影响范围**: 受影响的文件和功能
- **严重级别**: P0/P1/P2/P3
```

#### legacy_notes.md（如果发现新的耦合点或注意事项）
- 新增耦合点说明
- 新增注意事项

---

## 项目特定规则

### 数据库操作规则
1. 所有 SQL 使用参数化查询 `?` 占位符
2. 所有 update 方法必须使用 valid_columns 白名单
3. 修改表结构必须同步更新 valid_columns 和对应的 Model
4. 事务操作必须使用 `with self._lock` 互斥

### Qt/GUI 规则
1. 信号参数类型必须与 emit 类型严格匹配
2. 不在主线程做耗时操作，使用 QThread 或 threading.Thread
3. UI 更新必须在主线程执行（信号槽自动跨线程）
4. QButtonGroup.idClicked 回调中禁止直接调用 button.click()
5. QWidget 显示/隐藏要考虑 Container Widget 模式

### 打包规则
1. 必须排除 tkinter: `--exclude-module tkinter --exclude-module _tkinter`
2. 新增第三方库 import 必须检查是否需要 hidden-import
3. 打包后必须验证 exe 能否正常启动
4. gevent C 扩展模块必须逐个声明

### 测试规则
1. 修改后运行 `python test_all.py`
2. 修改后运行 `python -m py_compile` 检查所有修改文件
3. 源码启动验证无崩溃
4. 打包后 exe 启动验证

---

## 紧急联系点

当遇到以下情况时，需要特别谨慎：

1. **locust 导入崩溃** → 参考 legacy_notes.md "懒加载机制"
2. **导航按钮崩溃** → 参考 bug_history.md BUG-001
3. **exe 无法启动** → 参考 bug_history.md BUG-010
4. **跨页面状态丢失** → 参考 bug_history.md BUG-007
