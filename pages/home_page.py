"""
首页模块

仪表盘风格首页，显示关键指标卡片、最近任务列表和快速操作按钮，
支持暗黑模式和定时刷新数据。
"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.db_manager import DatabaseManager
from services.task_service import TaskService
from services.execution_service import ExecutionService


class MetricCard(QFrame):
    """指标卡片组件

    在首页仪表盘中展示单个关键指标，包含标题、数值和图标区域。
    """

    def __init__(
        self,
        title: str,
        value: str = "0",
        icon_text: str = "",
        color: str = "#4a90d9",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._value = value
        self._icon_text = icon_text
        self._color = color
        self._theme = "light"

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._setup_ui()
        self._apply_card_style()

    def _setup_ui(self) -> None:
        """构建卡片内部布局"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        icon_label = QLabel(self._icon_text)
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setObjectName("cardIcon")
        icon_label.setStyleSheet(
            f"font-size: 24px; background-color: {self._color}20;"
            f"color: {self._color}; border-radius: 12px;"
        )
        layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        self._title_label = QLabel(self._title)
        self._title_label.setObjectName("cardTitle")
        self._title_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
        text_layout.addWidget(self._title_label)

        self._value_label = QLabel(self._value)
        self._value_label.setObjectName("cardValue")
        self._value_label.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {self._color};"
        )
        text_layout.addWidget(self._value_label)

        layout.addLayout(text_layout, 1)

    def _apply_card_style(self) -> None:
        """应用卡片整体样式"""
        if self._theme == "dark":
            self.setStyleSheet(
                "QFrame { background-color: #252536; border: 1px solid #3a3a55;"
                " border-radius: 12px; }"
                "QFrame:hover { border-color: #5b9bd5; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background-color: #ffffff; border: 1px solid #d0d5dd;"
                " border-radius: 12px; }"
                "QFrame:hover { border-color: #4a90d9; }"
            )

    def set_value(self, value: str) -> None:
        """更新指标数值"""
        self._value = value
        self._value_label.setText(value)

    def set_theme(self, theme: str) -> None:
        """设置暗黑/亮色主题"""
        self._theme = theme
        if theme == "dark":
            self._title_label.setStyleSheet("font-size: 12px; color: #a0a0c0;")
        else:
            self._title_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
        self._apply_card_style()


class HomePage(QWidget):
    """首页仪表盘页面

    展示系统关键指标卡片、最近任务列表和快速操作按钮，
    支持定时刷新数据（10秒间隔）和暗黑模式切换。
    """

    navigate_requested = Signal(int)

    REFRESH_INTERVAL_MS = 10000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = "light"
        self._db = DatabaseManager()
        self._task_service = TaskService(self._db)
        self._execution_service = ExecutionService(self._db)

        self._setup_ui()
        self._setup_timer()
        self.refresh_data()

    def _setup_ui(self) -> None:
        """构建首页整体布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(24)

        header_layout = QHBoxLayout()
        self._title_label = QLabel("仪表盘")
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1a1a2e;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._refresh_time_label = QLabel("")
        self._refresh_time_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
        header_layout.addWidget(self._refresh_time_label)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setProperty("secondary", True)
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(self._refresh_btn)

        main_layout.addLayout(header_layout)

        self._setup_metric_cards(main_layout)
        self._setup_recent_tasks(main_layout)
        self._setup_quick_actions(main_layout)

    def _setup_metric_cards(self, parent_layout: QVBoxLayout) -> None:
        """创建四个关键指标卡片"""
        cards_layout = QGridLayout()
        cards_layout.setSpacing(16)

        self._card_today_tasks = MetricCard(
            title="今日任务数",
            value="0",
            icon_text="📋",
            color="#4a90d9",
        )
        cards_layout.addWidget(self._card_today_tasks, 0, 0)

        self._card_running_tasks = MetricCard(
            title="运行中任务",
            value="0",
            icon_text="▶️",
            color="#52c41a",
        )
        cards_layout.addWidget(self._card_running_tasks, 0, 1)

        self._card_total_requests = MetricCard(
            title="总请求数",
            value="0",
            icon_text="📊",
            color="#faad14",
        )
        cards_layout.addWidget(self._card_total_requests, 0, 2)

        self._card_avg_response = MetricCard(
            title="平均响应时间",
            value="0ms",
            icon_text="⏱️",
            color="#f5222d",
        )
        cards_layout.addWidget(self._card_avg_response, 0, 3)

        parent_layout.addLayout(cards_layout)

    def _setup_recent_tasks(self, parent_layout: QVBoxLayout) -> None:
        """创建最近任务列表区域"""
        task_header_layout = QHBoxLayout()
        task_title = QLabel("最近任务")
        task_title.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #1a1a2e;"
        )
        task_header_layout.addWidget(task_title)
        task_header_layout.addStretch()
        parent_layout.addLayout(task_header_layout)

        self._task_table = QTableWidget()
        self._task_table.setColumnCount(6)
        self._task_table.setHorizontalHeaderLabels(
            ["ID", "任务名称", "类型", "请求方法", "状态", "创建时间"]
        )
        self._task_table.horizontalHeader().setStretchLastSection(True)
        self._task_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._task_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._task_table.setAlternatingRowColors(True)
        self._task_table.verticalHeader().setVisible(False)
        self._task_table.setMinimumHeight(200)

        column_widths = [60, 200, 100, 100, 100, 180]
        for i, width in enumerate(column_widths):
            self._task_table.setColumnWidth(i, width)

        parent_layout.addWidget(self._task_table, 1)

    def _setup_quick_actions(self, parent_layout: QVBoxLayout) -> None:
        """创建快速操作按钮区域"""
        actions_header_layout = QHBoxLayout()
        actions_title = QLabel("快速操作")
        actions_title.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #1a1a2e;"
        )
        actions_header_layout.addWidget(actions_title)
        actions_header_layout.addStretch()
        parent_layout.addLayout(actions_header_layout)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)

        self._btn_create_task = QPushButton("创建任务")
        self._btn_create_task.setFixedHeight(44)
        self._btn_create_task.setMinimumWidth(140)
        self._btn_create_task.clicked.connect(
            lambda: self.navigate_requested.emit(1)
        )
        actions_layout.addWidget(self._btn_create_task)

        self._btn_view_history = QPushButton("查看历史")
        self._btn_view_history.setProperty("secondary", True)
        self._btn_view_history.setFixedHeight(44)
        self._btn_view_history.setMinimumWidth(140)
        self._btn_view_history.clicked.connect(
            lambda: self.navigate_requested.emit(4)
        )
        actions_layout.addWidget(self._btn_view_history)

        self._btn_system_settings = QPushButton("系统设置")
        self._btn_system_settings.setProperty("secondary", True)
        self._btn_system_settings.setFixedHeight(44)
        self._btn_system_settings.setMinimumWidth(140)
        self._btn_system_settings.clicked.connect(
            lambda: self.navigate_requested.emit(5)
        )
        actions_layout.addWidget(self._btn_system_settings)

        actions_layout.addStretch()
        parent_layout.addLayout(actions_layout)

    def _setup_timer(self) -> None:
        """初始化定时刷新定时器"""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_data)
        self._refresh_timer.start(self.REFRESH_INTERVAL_MS)

    def refresh_data(self) -> None:
        """从数据库刷新仪表盘数据"""
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            all_tasks = self._task_service.list_tasks()
            today_count = sum(
                1
                for t in all_tasks
                if t.get("created_at", "").startswith(today_str)
            )
            self._card_today_tasks.set_value(str(today_count))

            running_count = self._db.get_running_task_count()
            self._card_running_tasks.set_value(str(running_count))

            total_requests = 0
            avg_response = 0.0
            avg_count = 0
            for task in all_tasks:
                stats = self._db.get_task_statistics(task.get("id", 0))
                total_requests += stats.get("total_requests", 0)
                if stats.get("avg_response_time", 0) > 0:
                    avg_response += stats["avg_response_time"]
                    avg_count += 1

            self._card_total_requests.set_value(str(total_requests))

            if avg_count > 0:
                avg_ms = round(avg_response / avg_count, 2)
                self._card_avg_response.set_value(f"{avg_ms}ms")
            else:
                self._card_avg_response.set_value("0ms")

            self._refresh_task_table(all_tasks)

            now_str = datetime.now().strftime("%H:%M:%S")
            self._refresh_time_label.setText(f"最后刷新: {now_str}")

        except Exception as e:
            self._refresh_time_label.setText(f"刷新失败: {e}")

    def _refresh_task_table(self, tasks: list[dict]) -> None:
        """刷新最近任务列表表格"""
        recent_tasks = tasks[:20]
        self._task_table.setRowCount(len(recent_tasks))

        for row, task in enumerate(recent_tasks):
            id_item = QTableWidgetItem(str(task.get("id", "")))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._task_table.setItem(row, 0, id_item)

            name_item = QTableWidgetItem(task.get("name", ""))
            self._task_table.setItem(row, 1, name_item)

            type_item = QTableWidgetItem(task.get("type", "HTTP"))
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._task_table.setItem(row, 2, type_item)

            method_item = QTableWidgetItem(task.get("method", "GET"))
            method_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._task_table.setItem(row, 3, method_item)

            latest_result = self._db.get_latest_result_by_task(task.get("id", 0))
            status = latest_result.get("status", "未执行") if latest_result else "未执行"
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "running":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif status == "error":
                status_item.setForeground(Qt.GlobalColor.red)
            self._task_table.setItem(row, 4, status_item)

            created_item = QTableWidgetItem(task.get("created_at", ""))
            created_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._task_table.setItem(row, 5, created_item)

    def set_theme(self, theme: str) -> None:
        """设置暗黑/亮色主题

        Args:
            theme: 主题名称，"light" 或 "dark"
        """
        self._theme = theme
        if theme == "dark":
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #e0e0f0;"
            )
            self._refresh_time_label.setStyleSheet(
                "font-size: 12px; color: #a0a0c0;"
            )
        else:
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #1a1a2e;"
            )
            self._refresh_time_label.setStyleSheet(
                "font-size: 12px; color: #5a5a7a;"
            )

        self._card_today_tasks.set_theme(theme)
        self._card_running_tasks.set_theme(theme)
        self._card_total_requests.set_theme(theme)
        self._card_avg_response.set_theme(theme)

        for i in range(self._task_table.rowCount()):
            for j in range(self._task_table.columnCount()):
                item = self._task_table.item(i, j)
                if item:
                    if theme == "dark":
                        item.setForeground(Qt.GlobalColor.white)
                    else:
                        item.setForeground(Qt.GlobalColor.black)

        header_labels_style = (
            "font-size: 16px; font-weight: 600; color: #e0e0f0;"
            if theme == "dark"
            else "font-size: 16px; font-weight: 600; color: #1a1a2e;"
        )
        for widget in self.findChildren(QLabel):
            if widget.text() in ("最近任务", "快速操作"):
                widget.setStyleSheet(header_labels_style)

    def cleanup(self) -> None:
        """清理资源，停止定时器"""
        self._refresh_timer.stop()
