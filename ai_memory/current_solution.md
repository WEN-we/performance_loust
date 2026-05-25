# 当前解决方案

## 状态: 无活跃解决方案

## 最近解决方案摘要

### 图表悬浮数据提示 (2026-05-25)
- 使用 matplotlib mpl_connect 监听 motion_notify_event
- 找到最近数据点，显示 tooltip annotation + 垂直参考线 + 高亮圆点
- 提示框根据鼠标位置自动调整方向
- 暗色/亮色主题自动适配

### ExecutionService 单例改造 (2026-05-25)
- __new__ + _init_lock + _initialized 标志
- 所有页面共享同一实例
- reset_instance() 方法用于测试清理

### 图表2x2布局 (2026-05-25)
- QGridLayout 替代纵向堆叠
- 移除 NavigationToolbar
- QFrame 卡片容器 + 圆角边框
- fill_between 渐变填充
