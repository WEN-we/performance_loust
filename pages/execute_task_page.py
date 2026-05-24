"""
执行任务页面模块

提供任务列表展示、任务选择、执行控制（开始/暂停/恢复/停止）、
运行状态实时刷新、多任务队列执行等功能，支持暗黑模式。
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.db_manager import DatabaseManager
from services.execution_service import ExecutionService
from services.task_service import TaskService


class StatusBadge(QFrame):
    """运行状态徽章组件

    根据任务运行状态显示不同颜色的状态标签，
    支持的状态：等待/运行中/已暂停/已停止/异常
    """

    STATUS_CONFIG = {
        "waiting": {"text": "等待", "bg": "#e6f7ff", "fg": "#1890ff", "border": "#91d5ff"},
        "running": {"text": "运行中", "bg": "#f6ffed", "fg": "#52c41a", "border": "#b7eb8f"},
        "paused": {"text": "已暂停", "bg": "#fffbe6", "fg": "#faad14", "border": "#ffe58f"},
        "stopped": {"text": "已停止", "bg": "#f5f5f5", "fg": "#8c8c8c", "border": "#d9d9d9"},
        "error": {"text": "异常", "bg": "#fff1f0", "fg": "#f5222d", "border": "#ffa39e"},
        "never_run": {"text": "未执行", "bg": "#f5f5f5", "fg": "#8c8c8c", "border": "#d9d9d9"},
    }

    DARK_STATUS_CONFIG = {
        "waiting": {"text": "等待", "bg": "#1a2a4a", "fg": "#5b9bd5", "border": "#2a4a7a"},
        "running": {"text": "运行中", "bg": "#1a3a1a", "fg": "#73d13d", "border": "#2a5a2a"},
        "paused": {"text": "已暂停", "bg": "#3a3a1a", "fg": "#ffc53d", "border": "#5a5a2a"},
        "stopped": {"text": "已停止", "bg": "#2a2a2a", "fg": "#a0a0a0", "border": "#3a3a3a"},
        "error": {"text": "异常", "bg": "#3a1a1a", "fg": "#ff4d4f", "border": "#5a2a2a"},
        "never_run": {"text": "未执行", "bg": "#2a2a2a", "fg": "#a0a0a0", "border": "#3a3a3a"},
    }

    def __init__(self, status: str = "never_run", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = status
        self._theme = "light"
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        """构建状态徽章内部布局"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(0)

        self._dot_label = QLabel("●")
        self._dot_label.setFixedWidth(12)
        layout.addWidget(self._dot_label)

        self._text_label = QLabel()
        layout.addWidget(self._text_label)

    def _apply_style(self) -> None:
        """根据状态和主题应用样式"""
        config_map = self.DARK_STATUS_CONFIG if self._theme == "dark" else self.STATUS_CONFIG
        config = config_map.get(self._status, config_map["never_run"])

        self.setStyleSheet(
            f"QFrame {{ background-color: {config['bg']}; "
            f"border: 1px solid {config['border']}; "
            f"border-radius: 6px; }}"
        )
        self._dot_label.setStyleSheet(f"color: {config['fg']}; font-size: 10px;")
        self._text_label.setStyleSheet(f"color: {config['fg']}; font-size: 12px; font-weight: 500;")
        self._text_label.setText(config["text"])

    def set_status(self, status: str) -> None:
        """更新状态

        Args:
            status: 新的运行状态
        """
        self._status = status
        self._apply_style()

    def set_theme(self, theme: str) -> None:
        """设置暗黑/亮色主题

        Args:
            theme: 主题名称，"light" 或 "dark"
        """
        self._theme = theme
        self._apply_style()


class ExecuteTaskPage(QWidget):
    """执行任务页面

    展示所有任务列表，支持选择任务后查看详情，
    提供开始/暂停/恢复/停止操作按钮，
    支持多任务队列顺序执行，实时刷新运行状态（2秒间隔）。
    """

    REFRESH_INTERVAL_MS = 2000

    navigate_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = "light"
        self._db = DatabaseManager()
        self._task_service = TaskService(self._db)
        self._execution_service = ExecutionService(self._db)
        self._selected_task_id: int | None = None
        self._queue_task_ids: list[int] = []

        self._setup_ui()
        self._setup_timer()
        self._refresh_task_list()

    def _setup_ui(self) -> None:
        """构建执行任务页面整体布局"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(32, 24, 32, 16)

        self._title_label = QLabel("执行任务")
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1a1a2e;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._queue_status_label = QLabel("")
        self._queue_status_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
        header_layout.addWidget(self._queue_status_label)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setProperty("secondary", True)
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self._refresh_task_list)
        header_layout.addWidget(self._refresh_btn)

        outer_layout.addLayout(header_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setContentsMargins(32, 0, 32, 0)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        self._setup_task_table(left_layout)
        self._setup_queue_section(left_layout)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        self._setup_detail_section(right_layout)
        self._setup_action_buttons(right_layout)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        outer_layout.addWidget(splitter, 1)

    def _setup_task_table(self, parent_layout: QVBoxLayout) -> None:
        """创建任务列表表格区域

        Args:
            parent_layout: 父级布局
        """
        table_header_layout = QHBoxLayout()
        table_title = QLabel("任务列表")
        table_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #1a1a2e;")
        table_header_layout.addWidget(table_title)
        table_header_layout.addStretch()
        parent_layout.addLayout(table_header_layout)

        self._task_table = QTableWidget()
        self._task_table.setColumnCount(6)
        self._task_table.setHorizontalHeaderLabels(
            ["ID", "任务名称", "类型", "方法", "状态", "创建时间"]
        )
        self._task_table.horizontalHeader().setStretchLastSection(True)
        self._task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._task_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._task_table.setAlternatingRowColors(True)
        self._task_table.verticalHeader().setVisible(False)
        self._task_table.selectionModel().currentRowChanged.connect(self._on_task_selected)

        column_widths = [50, 180, 80, 80, 100, 160]
        for i, width in enumerate(column_widths):
            self._task_table.setColumnWidth(i, width)

        parent_layout.addWidget(self._task_table, 1)

    def _setup_queue_section(self, parent_layout: QVBoxLayout) -> None:
        """创建多任务队列区域

        Args:
            parent_layout: 父级布局
        """
        queue_frame = QFrame()
        queue_frame.setFrameShape(QFrame.Shape.StyledPanel)
        queue_layout = QVBoxLayout(queue_frame)
        queue_layout.setContentsMargins(12, 12, 12, 12)
        queue_layout.setSpacing(8)

        queue_header = QHBoxLayout()
        queue_title = QLabel("多任务队列")
        queue_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        queue_header.addWidget(queue_title)
        queue_header.addStretch()

        self._add_to_queue_btn = QPushButton("加入队列")
        self._add_to_queue_btn.setProperty("secondary", True)
        self._add_to_queue_btn.setFixedWidth(90)
        self._add_to_queue_btn.clicked.connect(self._add_selected_to_queue)
        queue_header.addWidget(self._add_to_queue_btn)

        self._remove_from_queue_btn = QPushButton("移除")
        self._remove_from_queue_btn.setProperty("secondary", True)
        self._remove_from_queue_btn.setFixedWidth(60)
        self._remove_from_queue_btn.clicked.connect(self._remove_from_queue)
        queue_header.addWidget(self._remove_from_queue_btn)

        queue_layout.addLayout(queue_header)

        self._queue_label = QLabel("队列：空")
        self._queue_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
        self._queue_label.setWordWrap(True)
        queue_layout.addWidget(self._queue_label)

        queue_btn_layout = QHBoxLayout()
        queue_btn_layout.setSpacing(8)

        self._start_queue_btn = QPushButton("开始队列执行")
        self._start_queue_btn.setFixedHeight(36)
        self._start_queue_btn.clicked.connect(self._start_queue)
        queue_btn_layout.addWidget(self._start_queue_btn)

        self._stop_queue_btn = QPushButton("停止队列")
        self._stop_queue_btn.setProperty("danger", True)
        self._stop_queue_btn.setFixedHeight(36)
        self._stop_queue_btn.setEnabled(False)
        self._stop_queue_btn.clicked.connect(self._stop_queue)
        queue_btn_layout.addWidget(self._stop_queue_btn)

        queue_layout.addLayout(queue_btn_layout)

        self._queue_frame = queue_frame
        parent_layout.addWidget(queue_frame)

    def _setup_detail_section(self, parent_layout: QVBoxLayout) -> None:
        """创建任务详情区域

        Args:
            parent_layout: 父级布局
        """
        detail_header = QHBoxLayout()
        detail_title = QLabel("任务详情")
        detail_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #1a1a2e;")
        detail_header.addWidget(detail_title)
        detail_header.addStretch()
        parent_layout.addLayout(detail_header)

        self._detail_frame = QFrame()
        self._detail_frame.setFrameShape(QFrame.Shape.StyledPanel)
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(8)

        self._detail_name_label = QLabel("请选择一个任务")
        self._detail_name_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        detail_layout.addWidget(self._detail_name_label)

        self._detail_status_badge = StatusBadge("never_run")
        detail_layout.addWidget(self._detail_status_badge)

        self._detail_info = QTextEdit()
        self._detail_info.setReadOnly(True)
        self._detail_info.setMinimumHeight(200)
        self._detail_info.setPlaceholderText("选中任务后，此处将显示任务详情和运行状态信息")
        detail_layout.addWidget(self._detail_info, 1)

        parent_layout.addWidget(self._detail_frame, 1)

    def _setup_action_buttons(self, parent_layout: QVBoxLayout) -> None:
        """创建操作按钮区域

        Args:
            parent_layout: 父级布局
        """
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._start_btn = QPushButton("▶ 开始")
        self._start_btn.setFixedHeight(40)
        self._start_btn.setMinimumWidth(100)
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start_task)
        btn_layout.addWidget(self._start_btn)

        self._pause_btn = QPushButton("⏸ 暂停")
        self._pause_btn.setProperty("secondary", True)
        self._pause_btn.setFixedHeight(40)
        self._pause_btn.setMinimumWidth(100)
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self._pause_task)
        btn_layout.addWidget(self._pause_btn)

        self._resume_btn = QPushButton("⏵ 恢复")
        self._resume_btn.setProperty("secondary", True)
        self._resume_btn.setFixedHeight(40)
        self._resume_btn.setMinimumWidth(100)
        self._resume_btn.setEnabled(False)
        self._resume_btn.clicked.connect(self._resume_task)
        btn_layout.addWidget(self._resume_btn)

        self._stop_btn = QPushButton("⏹ 停止")
        self._stop_btn.setProperty("danger", True)
        self._stop_btn.setFixedHeight(40)
        self._stop_btn.setMinimumWidth(100)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_task)
        btn_layout.addWidget(self._stop_btn)

        parent_layout.addLayout(btn_layout)

    def _setup_timer(self) -> None:
        """初始化定时刷新定时器，每2秒刷新一次运行状态"""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_running_status)
        self._refresh_timer.start(self.REFRESH_INTERVAL_MS)

    def _refresh_task_list(self) -> None:
        """从数据库刷新任务列表"""
        try:
            tasks = self._task_service.list_tasks()
            self._task_table.setRowCount(len(tasks))

            for row, task in enumerate(tasks):
                task_id = task.get("id", 0)

                id_item = QTableWidgetItem(str(task_id))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                id_item.setData(Qt.ItemDataRole.UserRole, task_id)
                self._task_table.setItem(row, 0, id_item)

                name_item = QTableWidgetItem(task.get("name", ""))
                self._task_table.setItem(row, 1, name_item)

                type_item = QTableWidgetItem(task.get("type", "HTTP"))
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._task_table.setItem(row, 2, type_item)

                method_item = QTableWidgetItem(task.get("method", "GET"))
                method_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._task_table.setItem(row, 3, method_item)

                status = self._get_task_display_status(task_id)
                status_item = QTableWidgetItem(status)
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status_item.setForeground(self._status_color(status))
                self._task_table.setItem(row, 4, status_item)

                created_item = QTableWidgetItem(task.get("created_at", ""))
                created_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._task_table.setItem(row, 5, created_item)

            self._refresh_running_status()

        except Exception as e:
            QMessageBox.warning(self, "刷新失败", f"刷新任务列表时出错:\n{e}")

    def _get_task_display_status(self, task_id: int) -> str:
        """获取任务的显示状态文本

        Args:
            task_id: 任务ID

        Returns:
            状态显示文本
        """
        try:
            status_info = self._execution_service.get_task_status(task_id)
            engine_state = status_info.get("engine_state", "idle")
            status = status_info.get("status", "never_run")

            if engine_state == "running":
                return "running"
            elif engine_state == "paused":
                return "paused"
            elif status == "never_run":
                return "never_run"
            elif status == "error":
                return "error"
            else:
                return status
        except Exception:
            return "never_run"

    def _status_color(self, status: str) -> QColor:
        """根据状态返回对应的颜色

        Args:
            status: 运行状态

        Returns:
            QColor 颜色对象
        """
        if self._theme == "dark":
            color_map = {
                "running": QColor("#73d13d"),
                "paused": QColor("#ffc53d"),
                "stopped": QColor("#a0a0a0"),
                "error": QColor("#ff4d4f"),
                "waiting": QColor("#5b9bd5"),
                "never_run": QColor("#a0a0a0"),
            }
        else:
            color_map = {
                "running": QColor("#52c41a"),
                "paused": QColor("#faad14"),
                "stopped": QColor("#8c8c8c"),
                "error": QColor("#f5222d"),
                "waiting": QColor("#1890ff"),
                "never_run": QColor("#8c8c8c"),
            }
        return color_map.get(status, QColor("#8c8c8c"))

    def _refresh_running_status(self) -> None:
        """刷新所有任务的运行状态（定时器回调）"""
        try:
            for row in range(self._task_table.rowCount()):
                id_item = self._task_table.item(row, 0)
                if id_item is None:
                    continue
                task_id = id_item.data(Qt.ItemDataRole.UserRole)
                if task_id is None:
                    continue

                status = self._get_task_display_status(task_id)
                status_item = self._task_table.item(row, 4)
                if status_item:
                    status_item.setText(status)
                    status_item.setForeground(self._status_color(status))

            if self._selected_task_id is not None:
                self._update_detail_info(self._selected_task_id)

            self._refresh_queue_status()

        except Exception:
            from utils.logger import get_logger
            get_logger("execute_task_page").exception("刷新运行状态失败")

    def _refresh_queue_status(self) -> None:
        """刷新队列执行状态"""
        try:
            queue_info = self._execution_service.get_queue_status()
            is_running = queue_info.get("running", False)
            remaining = queue_info.get("remaining", 0)
            queue_list = queue_info.get("queue", [])

            if is_running:
                self._queue_status_label.setText(f"队列执行中，剩余 {remaining} 个任务")
                self._queue_status_label.setStyleSheet("font-size: 12px; color: #52c41a;")
                self._start_queue_btn.setEnabled(False)
                self._stop_queue_btn.setEnabled(True)
            else:
                self._queue_status_label.setText("")
                self._start_queue_btn.setEnabled(len(self._queue_task_ids) > 0)
                self._stop_queue_btn.setEnabled(False)

            if self._queue_task_ids:
                task_names = []
                for tid in self._queue_task_ids:
                    task = self._db.get_task(tid)
                    if task:
                        task_names.append(f"{tid}:{task.get('name', '')}")
                    else:
                        task_names.append(str(tid))
                self._queue_label.setText(f"队列（{len(self._queue_task_ids)}个）：{' → '.join(task_names)}")
            else:
                self._queue_label.setText("队列：空")

        except Exception:
            from utils.logger import get_logger
            get_logger("execute_task_page").exception("刷新队列状态失败")

    def _on_task_selected(self, current: QModelIndex, _previous: QModelIndex = None) -> None:
        row = current.row() if current.isValid() else -1
        """任务列表选中行变更回调

        Args:
            row: 选中的行号
        """
        if row < 0:
            self._selected_task_id = None
            self._update_button_states()
            return

        id_item = self._task_table.item(row, 0)
        if id_item is None:
            self._selected_task_id = None
            self._update_button_states()
            return

        task_id = id_item.data(Qt.ItemDataRole.UserRole)
        self._selected_task_id = task_id
        self._update_detail_info(task_id)
        self._update_button_states()

    def _update_detail_info(self, task_id: int) -> None:
        """更新任务详情区域

        Args:
            task_id: 任务ID
        """
        task = self._db.get_task(task_id)
        if task is None:
            self._detail_name_label.setText("任务不存在")
            self._detail_info.clear()
            return

        self._detail_name_label.setText(task.get("name", "未命名任务"))

        status_info = self._execution_service.get_task_status(task_id)
        status = status_info.get("status", "never_run")
        engine_state = status_info.get("engine_state", "idle")

        if engine_state == "running":
            display_status = "running"
        elif engine_state == "paused":
            display_status = "paused"
        elif status == "error":
            display_status = "error"
        elif status == "never_run":
            display_status = "never_run"
        else:
            display_status = status

        self._detail_status_badge.set_status(display_status)

        info_lines = []
        info_lines.append(f"任务ID: {task_id}")
        info_lines.append(f"类型: {task.get('type', 'HTTP')}")
        info_lines.append(f"请求方法: {task.get('method', 'GET')}")
        info_lines.append(f"请求地址: {task.get('url', '')}")
        info_lines.append(f"并发用户数: {task.get('users', 10)}")
        info_lines.append(f"启动速率: {task.get('spawn_rate', 1)} 用户/秒")
        info_lines.append(f"持续时间: {task.get('run_time', '5m')}")
        info_lines.append(f"超时时间: {task.get('timeout', 30)} 秒")
        info_lines.append("")

        stats = status_info.get("stats", {})
        if stats and isinstance(stats, dict):
            info_lines.append("── 实时统计 ──")
            info_lines.append(f"运行时长: {stats.get('elapsed_seconds', 0):.1f} 秒")
            info_lines.append(f"当前在线用户: {stats.get('user_count', 0)}")
            info_lines.append(f"QPS: {stats.get('rps', 0):.2f}")
            info_lines.append(f"总请求数: {stats.get('total_requests', 0)}")
            info_lines.append(f"失败数: {stats.get('total_failures', 0)}")
            fail_rate = stats.get('failure_rate', 0)
            info_lines.append(f"失败率: {fail_rate:.2%}")
            info_lines.append(f"平均响应时间: {stats.get('avg_response_time', 0):.2f} ms")
            info_lines.append(f"最大响应时间: {stats.get('max_response_time', 0):.2f} ms")
            info_lines.append(f"最小响应时间: {stats.get('min_response_time', 0):.2f} ms")
            info_lines.append(f"95%响应时间: {stats.get('p95_response_time', 0):.2f} ms")
        else:
            latest_result = self._db.get_latest_result_by_task(task_id)
            if latest_result:
                info_lines.append("── 最近执行结果 ──")
                info_lines.append(f"状态: {latest_result.get('status', 'unknown')}")
                info_lines.append(f"开始时间: {latest_result.get('start_time', '-')}")
                info_lines.append(f"结束时间: {latest_result.get('end_time', '-')}")
                info_lines.append(f"总请求数: {latest_result.get('total_requests', 0)}")
                info_lines.append(f"成功数: {latest_result.get('success_count', 0)}")
                info_lines.append(f"失败数: {latest_result.get('fail_count', 0)}")
                info_lines.append(f"QPS: {latest_result.get('qps', 0):.2f}")
                info_lines.append(f"平均响应时间: {latest_result.get('avg_response_time', 0):.2f} ms")
                info_lines.append(f"95%响应时间: {latest_result.get('p95_response_time', 0):.2f} ms")
                info_lines.append(f"失败率: {latest_result.get('fail_rate', 0):.2%}")

        self._detail_info.setPlainText("\n".join(info_lines))

    def _update_button_states(self) -> None:
        """根据选中任务的状态更新操作按钮的启用/禁用状态"""
        if self._selected_task_id is None:
            self._start_btn.setEnabled(False)
            self._pause_btn.setEnabled(False)
            self._resume_btn.setEnabled(False)
            self._stop_btn.setEnabled(False)
            return

        status_info = self._execution_service.get_task_status(self._selected_task_id)
        engine_state = status_info.get("engine_state", "idle")

        is_running = engine_state == "running"
        is_paused = engine_state == "paused"
        is_idle = engine_state in ("idle", "stopped")

        self._start_btn.setEnabled(is_idle)
        self._pause_btn.setEnabled(is_running)
        self._resume_btn.setEnabled(is_paused)
        self._stop_btn.setEnabled(is_running or is_paused)

    def _start_task(self) -> None:
        """启动选中的任务"""
        if self._selected_task_id is None:
            return

        try:
            success = self._execution_service.start_task(self._selected_task_id)
            if success:
                self._update_button_states()
                self._update_detail_info(self._selected_task_id)
            else:
                QMessageBox.warning(self, "启动失败", "任务启动失败，请检查任务配置")
        except ValueError as e:
            QMessageBox.warning(self, "启动失败", str(e))
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"启动任务时发生错误:\n{e}")

    def _pause_task(self) -> None:
        """暂停选中的任务"""
        if self._selected_task_id is None:
            return

        try:
            success = self._execution_service.pause_task(self._selected_task_id)
            if success:
                self._update_button_states()
                self._update_detail_info(self._selected_task_id)
            else:
                QMessageBox.warning(self, "暂停失败", "任务暂停失败")
        except Exception as e:
            QMessageBox.critical(self, "暂停失败", f"暂停任务时发生错误:\n{e}")

    def _resume_task(self) -> None:
        """恢复选中的任务"""
        if self._selected_task_id is None:
            return

        try:
            success = self._execution_service.resume_task(self._selected_task_id)
            if success:
                self._update_button_states()
                self._update_detail_info(self._selected_task_id)
            else:
                QMessageBox.warning(self, "恢复失败", "任务恢复失败")
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", f"恢复任务时发生错误:\n{e}")

    def _stop_task(self) -> None:
        """停止选中的任务"""
        if self._selected_task_id is None:
            return

        reply = QMessageBox.question(
            self,
            "确认停止",
            "确定要停止该任务吗？停止后将保存当前执行结果。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            success = self._execution_service.stop_task(self._selected_task_id)
            if success:
                self._update_button_states()
                self._update_detail_info(self._selected_task_id)
            else:
                QMessageBox.warning(self, "停止失败", "任务停止失败")
        except Exception as e:
            QMessageBox.critical(self, "停止失败", f"停止任务时发生错误:\n{e}")

    def _add_selected_to_queue(self) -> None:
        """将选中的任务添加到执行队列"""
        if self._selected_task_id is None:
            QMessageBox.information(self, "提示", "请先在任务列表中选择一个任务")
            return

        if self._selected_task_id in self._queue_task_ids:
            QMessageBox.information(self, "提示", "该任务已在队列中")
            return

        self._queue_task_ids.append(self._selected_task_id)
        self._refresh_queue_status()

    def _remove_from_queue(self) -> None:
        """从队列中移除选中的任务"""
        if self._selected_task_id is None:
            return

        if self._selected_task_id in self._queue_task_ids:
            self._queue_task_ids.remove(self._selected_task_id)
            self._refresh_queue_status()

    def _start_queue(self) -> None:
        """开始执行任务队列"""
        if not self._queue_task_ids:
            QMessageBox.information(self, "提示", "队列为空，请先添加任务到队列")
            return

        task_names = []
        for tid in self._queue_task_ids:
            task = self._db.get_task(tid)
            task_names.append(task.get("name", str(tid)) if task else str(tid))

        reply = QMessageBox.question(
            self,
            "确认执行队列",
            f"将按顺序执行以下 {len(self._queue_task_ids)} 个任务：\n"
            + "\n".join(f"  {i + 1}. {name}" for i, name in enumerate(task_names))
            + "\n\n确定开始吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            success = self._execution_service.execute_queue(self._queue_task_ids)
            if success:
                self._queue_task_ids.clear()
                self._refresh_queue_status()
            else:
                QMessageBox.warning(self, "启动失败", "队列启动失败，可能已有队列在执行中")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"启动队列时发生错误:\n{e}")

    def _stop_queue(self) -> None:
        """停止队列执行"""
        reply = QMessageBox.question(
            self,
            "确认停止队列",
            "确定要停止队列执行吗？当前正在运行的任务也将被停止。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._execution_service.stop_queue()
            self._refresh_queue_status()
            self._update_button_states()
        except Exception as e:
            QMessageBox.critical(self, "停止失败", f"停止队列时发生错误:\n{e}")

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
            self._queue_status_label.setStyleSheet("font-size: 12px; color: #a0a0c0;")
            self._queue_label.setStyleSheet("font-size: 12px; color: #a0a0c0;")
            self._detail_name_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #e0e0f0;")

            self._queue_frame.setStyleSheet(
                "QFrame { background-color: #252536; border: 1px solid #3a3a55; border-radius: 8px; }"
            )
            self._detail_frame.setStyleSheet(
                "QFrame { background-color: #252536; border: 1px solid #3a3a55; border-radius: 8px; }"
            )
            self._detail_info.setStyleSheet(
                "QTextEdit { background-color: #1e1e2e; color: #e0e0f0; border: 1px solid #3a3a55; border-radius: 6px; }"
            )
        else:
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #1a1a2e;"
            )
            self._queue_status_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
            self._queue_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
            self._detail_name_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #1a1a2e;")

            self._queue_frame.setStyleSheet(
                "QFrame { background-color: #ffffff; border: 1px solid #d0d5dd; border-radius: 8px; }"
            )
            self._detail_frame.setStyleSheet(
                "QFrame { background-color: #ffffff; border: 1px solid #d0d5dd; border-radius: 8px; }"
            )
            self._detail_info.setStyleSheet(
                "QTextEdit { background-color: #ffffff; color: #1a1a2e; border: 1px solid #d0d5dd; border-radius: 6px; }"
            )

        self._detail_status_badge.set_theme(theme)

        for i in range(self._task_table.rowCount()):
            for j in range(self._task_table.columnCount()):
                item = self._task_table.item(i, j)
                if item:
                    if j == 4:
                        status_text = item.text()
                        item.setForeground(self._status_color(status_text))
                    else:
                        if theme == "dark":
                            item.setForeground(Qt.GlobalColor.white)
                        else:
                            item.setForeground(Qt.GlobalColor.black)

        section_title_style = (
            "font-size: 16px; font-weight: 600; color: #e0e0f0;"
            if theme == "dark"
            else "font-size: 16px; font-weight: 600; color: #1a1a2e;"
        )
        for widget in self.findChildren(QLabel):
            if widget.text() in ("任务列表", "任务详情"):
                widget.setStyleSheet(section_title_style)

    def cleanup(self) -> None:
        """清理资源，停止定时器"""
        self._refresh_timer.stop()
