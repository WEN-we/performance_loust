"""
页面模块

提供应用程序的所有页面组件，包括：
- HomePage: 首页仪表盘
- CreateTaskPage: 创建/编辑任务页面
- HistoryPage: 历史记录页面
- SettingsPage: 系统设置页面
"""

from pages.home_page import HomePage
from pages.create_task_page import CreateTaskPage
from pages.history_page import HistoryPage
from pages.settings_page import SettingsPage

__all__ = [
    "HomePage",
    "CreateTaskPage",
    "HistoryPage",
    "SettingsPage",
]
