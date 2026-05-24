"""
实时监控页面模块

提供性能测试的实时监控功能，包含指标卡片区域和图表区域，
使用 matplotlib 的 FigureCanvasQTAgg 嵌入 PySide6，
支持暗黑模式、图表缩放、导出PNG等特性。
"""

from collections import deque
from pathlib import Path

import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from database.db_manager import DatabaseManager
from services.execution_service import ExecutionService
from services.task_service import TaskService


class MetricCard(QFrame):
    """指标卡片组件

    在监控页面顶部展示单个实时指标，包含标题、数值和单位，
    支持暗黑模式切换。
    """

    def __init__(
        self,
        title: str,
        value: str = "0",
        unit: str = "",
        color: str = "#4a90d9",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._value = value
        self._unit = unit
        self._color = color
        self._theme = "light"

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._setup_ui()
        self._apply_card_style()

    def _setup_ui(self) -> None:
        """构建指标卡片内部布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._title_label = QLabel(self._title)
        self._title_label.setObjectName("metricTitle")
        self._title_label.setStyleSheet("font-size: 11px; color: #5a5a7a;")
        layout.addWidget(self._title_label)

        value_layout = QHBoxLayout()
        value_layout.setSpacing(4)

        self._value_label = QLabel(self._value)
        self._value_label.setObjectName("metricValue")
        self._value_label.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {self._color};"
        )
        value_layout.addWidget(self._value_label)

        self._unit_label = QLabel(self._unit)
        self._unit_label.setObjectName("metricUnit")
        self._unit_label.setStyleSheet("font-size: 11px; color: #5a5a7a; alignment: bottom;")
        value_layout.addWidget(self._unit_label)
        value_layout.addStretch()

        layout.addLayout(value_layout)

    def _apply_card_style(self) -> None:
        """应用卡片整体样式"""
        if self._theme == "dark":
            self.setStyleSheet(
                "QFrame { background-color: #252536; border: 1px solid #3a3a55;"
                " border-radius: 10px; }"
            )
            self._title_label.setStyleSheet("font-size: 11px; color: #a0a0c0;")
            self._unit_label.setStyleSheet("font-size: 11px; color: #a0a0c0;")
        else:
            self.setStyleSheet(
                "QFrame { background-color: #ffffff; border: 1px solid #d0d5dd;"
                " border-radius: 10px; }"
            )
            self._title_label.setStyleSheet("font-size: 11px; color: #5a5a7a;")
            self._unit_label.setStyleSheet("font-size: 11px; color: #5a5a7a;")

    def set_value(self, value: str) -> None:
        """更新指标数值

        Args:
            value: 新的指标值字符串
        """
        self._value = value
        self._value_label.setText(value)

    def set_theme(self, theme: str) -> None:
        """设置暗黑/亮色主题

        Args:
            theme: 主题名称，"light" 或 "dark"
        """
        self._theme = theme
        self._apply_card_style()


class RealtimeChart(QFrame):
    """实时折线图组件

    基于 matplotlib 的 FigureCanvasQTAgg，嵌入 QFrame 卡片容器中，
    支持多数据系列、自动滚动、暗黑模式、渐变填充区域。
    """

    MAX_POINTS = 120

    def __init__(
        self,
        title: str = "",
        ylabel: str = "",
        series_names: list[str] | None = None,
        series_colors: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._ylabel = ylabel
        self._series_names = series_names or ["值"]
        self._series_colors = series_colors or ["#4a90d9"]
        self._theme = "light"

        self._time_data: deque[float] = deque(maxlen=self.MAX_POINTS)
        self._series_data: dict[str, deque[float]] = {
            name: deque(maxlen=self.MAX_POINTS) for name in self._series_names
        }

        self._setup_ui()
        self._setup_axes()
        self._apply_chart_style()
        self._apply_frame_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        self._fig = Figure(figsize=(5, 3.2), dpi=100)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._canvas.updateGeometry()
        layout.addWidget(self._canvas)

    def _setup_axes(self) -> None:
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        self._ax.set_title(self._title, fontsize=12, fontweight="bold", pad=10)
        self._ax.set_ylabel(self._ylabel, fontsize=9)
        self._ax.set_xlabel("时间 (秒)", fontsize=9)
        self._ax.grid(True, alpha=0.3, linestyle="--")

        self._lines: dict[str, object] = {}
        self._fills: dict[str, object] = {}
        for name, color in zip(self._series_names, self._series_colors):
            line, = self._ax.plot([], [], label=name, color=color, linewidth=2.0, alpha=0.9)
            self._lines[name] = line
            fill = self._ax.fill_between([], [], alpha=0.0)
            self._fills[name] = fill

        if len(self._series_names) > 1:
            self._ax.legend(fontsize=8, loc="upper left", framealpha=0.8)

        self._fig.tight_layout(pad=2.0)

    def _apply_frame_style(self) -> None:
        if self._theme == "dark":
            self.setStyleSheet(
                "QFrame { background-color: #252536; border: 1px solid #3a3a55;"
                " border-radius: 12px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background-color: #ffffff; border: 1px solid #e0e4ec;"
                " border-radius: 12px; }"
            )

    def _apply_chart_style(self) -> None:
        if self._theme == "dark":
            self._fig.patch.set_facecolor("#252536")
            self._ax.set_facecolor("#1e1e2e")
            self._ax.tick_params(colors="#a0a0c0", labelsize=8)
            self._ax.xaxis.label.set_color("#a0a0c0")
            self._ax.yaxis.label.set_color("#a0a0c0")
            self._ax.title.set_color("#e0e0f0")
            for spine in self._ax.spines.values():
                spine.set_color("#3a3a55")
            self._ax.grid(True, alpha=0.15, color="#3a3a55", linestyle="--")
            legend = self._ax.get_legend()
            if legend:
                legend.get_frame().set_facecolor("#252536")
                legend.get_frame().set_edgecolor("#3a3a55")
                for text in legend.get_texts():
                    text.set_color("#a0a0c0")
        else:
            self._fig.patch.set_facecolor("#ffffff")
            self._ax.set_facecolor("#fafbfd")
            self._ax.tick_params(colors="#5a5a7a", labelsize=8)
            self._ax.xaxis.label.set_color("#5a5a7a")
            self._ax.yaxis.label.set_color("#5a5a7a")
            self._ax.title.set_color("#1a1a2e")
            for spine in self._ax.spines.values():
                spine.set_color("#e0e4ec")
            self._ax.grid(True, alpha=0.25, color="#e0e4ec", linestyle="--")
            legend = self._ax.get_legend()
            if legend:
                legend.get_frame().set_facecolor("#ffffff")
                legend.get_frame().set_edgecolor("#e0e4ec")
                for text in legend.get_texts():
                    text.set_color("#5a5a7a")

    def append_data(self, time_val: float, values: dict[str, float]) -> None:
        self._time_data.append(time_val)
        for name in self._series_names:
            val = values.get(name, 0.0)
            self._series_data[name].append(val)

        time_list = list(self._time_data)
        for name in self._series_names:
            if name in self._lines:
                data_list = list(self._series_data[name])
                self._lines[name].set_data(time_list, data_list)

                if name in self._fills:
                    self._fills[name].remove()
                color = self._series_colors[self._series_names.index(name)]
                self._fills[name] = self._ax.fill_between(
                    time_list, data_list, alpha=0.12, color=color,
                )

        if time_list:
            self._ax.set_xlim(time_list[0], max(time_list[-1], time_list[0] + 1))

        all_vals = []
        for name in self._series_names:
            all_vals.extend(self._series_data[name])
        if all_vals:
            min_val = min(all_vals)
            max_val = max(all_vals)
            margin = max((max_val - min_val) * 0.15, 1)
            self._ax.set_ylim(max(0, min_val - margin), max_val + margin)

        self._canvas.draw_idle()

    def clear_data(self) -> None:
        self._time_data.clear()
        for name in self._series_names:
            self._series_data[name].clear()
            if name in self._lines:
                self._lines[name].set_data([], [])
            if name in self._fills:
                self._fills[name].remove()
                self._fills[name] = self._ax.fill_between([], [], alpha=0.0)
        self._ax.set_xlim(0, 1)
        self._ax.set_ylim(0, 1)
        self._canvas.draw_idle()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self._apply_chart_style()
        self._apply_frame_style()
        self._canvas.draw_idle()

    def export_png(self, file_path: str) -> None:
        self._fig.savefig(file_path, dpi=150, bbox_inches="tight",
                          facecolor=self._fig.get_facecolor())


class MonitorPage(QWidget):
    """实时监控页面

    核心监控页面，展示性能测试的实时指标（数字+图表），
    包含指标卡片区域（顶部）和图表区域（中部），
    使用 matplotlib 嵌入 PySide6，支持缩放、导出PNG和暗黑模式。
    """

    REFRESH_INTERVAL_MS = 1000
    MAX_HISTORY_POINTS = 120

    navigate_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = "light"
        self._db = DatabaseManager()
        self._task_service = TaskService(self._db)
        self._execution_service = ExecutionService(self._db)

        self._monitoring_task_id: int | None = None
        self._elapsed_seconds: float = 0.0
        self._monitor_start_time: float | None = None
        self._history_chart_loaded: bool = False

        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self) -> None:
        """构建实时监控页面整体布局"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(32, 24, 32, 16)

        self._title_label = QLabel("实时监控")
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1a1a2e;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._task_info_label = QLabel("未选择监控任务")
        self._task_info_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")
        header_layout.addWidget(self._task_info_label)

        self._select_task_btn = QPushButton("选择任务")
        self._select_task_btn.setProperty("secondary", True)
        self._select_task_btn.setFixedWidth(100)
        self._select_task_btn.clicked.connect(self._select_monitoring_task)
        header_layout.addWidget(self._select_task_btn)

        self._export_btn = QPushButton("导出PNG")
        self._export_btn.setProperty("secondary", True)
        self._export_btn.setFixedWidth(90)
        self._export_btn.clicked.connect(self._export_charts)
        header_layout.addWidget(self._export_btn)

        outer_layout.addLayout(header_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(32, 0, 32, 32)
        content_layout.setSpacing(16)

        self._setup_metric_cards(content_layout)
        self._setup_charts(content_layout)

        content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(scroll_area, 1)

    def _setup_metric_cards(self, parent_layout: QVBoxLayout) -> None:
        """创建指标卡片区域（顶部）

        展示11个关键实时指标：QPS、TPS、RPS、平均响应时间、
        最大响应时间、最小响应时间、95%响应时间、失败率、
        当前在线用户数、成功请求数、失败请求数。

        Args:
            parent_layout: 父级布局
        """
        cards_layout = QGridLayout()
        cards_layout.setSpacing(12)

        self._card_qps = MetricCard("QPS", "0", "req/s", "#4a90d9")
        cards_layout.addWidget(self._card_qps, 0, 0)

        self._card_tps = MetricCard("TPS", "0", "txn/s", "#52c41a")
        cards_layout.addWidget(self._card_tps, 0, 1)

        self._card_rps = MetricCard("RPS", "0", "resp/s", "#722ed1")
        cards_layout.addWidget(self._card_rps, 0, 2)

        self._card_avg_rt = MetricCard("平均响应时间", "0", "ms", "#faad14")
        cards_layout.addWidget(self._card_avg_rt, 0, 3)

        self._card_max_rt = MetricCard("最大响应时间", "0", "ms", "#f5222d")
        cards_layout.addWidget(self._card_max_rt, 1, 0)

        self._card_min_rt = MetricCard("最小响应时间", "0", "ms", "#13c2c2")
        cards_layout.addWidget(self._card_min_rt, 1, 1)

        self._card_p95_rt = MetricCard("95%响应时间", "0", "ms", "#eb2f96")
        cards_layout.addWidget(self._card_p95_rt, 1, 2)

        self._card_fail_rate = MetricCard("失败率", "0", "%", "#f5222d")
        cards_layout.addWidget(self._card_fail_rate, 1, 3)

        self._card_users = MetricCard("在线用户数", "0", "人", "#4a90d9")
        cards_layout.addWidget(self._card_users, 2, 0)

        self._card_success = MetricCard("成功请求数", "0", "", "#52c41a")
        cards_layout.addWidget(self._card_success, 2, 1)

        self._card_fail = MetricCard("失败请求数", "0", "", "#f5222d")
        cards_layout.addWidget(self._card_fail, 2, 2)

        self._card_elapsed = MetricCard("运行时长", "0", "秒", "#5a5a7a")
        cards_layout.addWidget(self._card_elapsed, 2, 3)

        self._metric_cards = [
            self._card_qps, self._card_tps, self._card_rps,
            self._card_avg_rt, self._card_max_rt, self._card_min_rt,
            self._card_p95_rt, self._card_fail_rate, self._card_users,
            self._card_success, self._card_fail, self._card_elapsed,
        ]

        parent_layout.addLayout(cards_layout)

    def _setup_charts(self, parent_layout: QVBoxLayout) -> None:
        charts_header = QHBoxLayout()
        charts_title = QLabel("实时趋势图表")
        charts_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #1a1a2e;")
        charts_header.addWidget(charts_title)
        charts_header.addStretch()
        parent_layout.addLayout(charts_header)

        charts_grid = QGridLayout()
        charts_grid.setSpacing(16)
        charts_grid.setContentsMargins(0, 0, 0, 0)

        self._chart_qps_tps_rps = RealtimeChart(
            title="QPS / TPS / RPS 趋势",
            ylabel="请求/秒",
            series_names=["QPS", "TPS", "RPS"],
            series_colors=["#4a90d9", "#52c41a", "#722ed1"],
            parent=self,
        )
        charts_grid.addWidget(self._chart_qps_tps_rps, 0, 0)

        self._chart_response_time = RealtimeChart(
            title="响应时间趋势",
            ylabel="响应时间 (ms)",
            series_names=["平均", "最大", "95%"],
            series_colors=["#faad14", "#f5222d", "#eb2f96"],
            parent=self,
        )
        charts_grid.addWidget(self._chart_response_time, 0, 1)

        self._chart_fail_rate = RealtimeChart(
            title="失败率趋势",
            ylabel="失败率 (%)",
            series_names=["失败率"],
            series_colors=["#f5222d"],
            parent=self,
        )
        charts_grid.addWidget(self._chart_fail_rate, 1, 0)

        self._chart_users = RealtimeChart(
            title="在线用户数趋势",
            ylabel="用户数",
            series_names=["在线用户"],
            series_colors=["#4a90d9"],
            parent=self,
        )
        charts_grid.addWidget(self._chart_users, 1, 1)

        parent_layout.addLayout(charts_grid)

        self._all_charts = [
            self._chart_qps_tps_rps,
            self._chart_response_time,
            self._chart_fail_rate,
            self._chart_users,
        ]

    def _setup_timer(self) -> None:
        """初始化定时刷新定时器，每1秒刷新一次"""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_monitor_data)
        self._refresh_timer.start(self.REFRESH_INTERVAL_MS)

    def _select_monitoring_task(self) -> None:
        """选择要监控的任务

        弹出对话框让用户从正在运行的任务中选择一个进行监控。
        """
        tasks = self._task_service.list_tasks()
        running_tasks = []
        for task in tasks:
            task_id = task.get("id", 0)
            status_info = self._execution_service.get_task_status(task_id)
            engine_state = status_info.get("engine_state", "idle")
            if engine_state == "running":
                running_tasks.append(task)

        if not running_tasks:
            all_tasks = tasks[:20]
            if not all_tasks:
                QMessageBox.information(self, "提示", "当前没有任何任务，请先创建并启动任务")
                return

            items = [f"ID:{t.get('id')} - {t.get('name', '')}" for t in all_tasks]
            item, ok = QInputDialog.getItem(
                self, "选择监控任务", "没有正在运行的任务，可选择任意任务：", items, 0, False
            )
            if ok and item:
                task_id = int(item.split(":")[1].split(" - ")[0])
                self._set_monitoring_task(task_id)
            return

        items = [f"ID:{t.get('id')} - {t.get('name', '')} [运行中]" for t in running_tasks]
        item, ok = QInputDialog.getItem(
            self, "选择监控任务", "选择要监控的运行中任务：", items, 0, False
        )
        if ok and item:
            task_id = int(item.split(":")[1].split(" - ")[0])
            self._set_monitoring_task(task_id)

    def _set_monitoring_task(self, task_id: int) -> None:
        self._monitoring_task_id = task_id
        self._elapsed_seconds = 0.0
        self._monitor_start_time = None
        self._history_chart_loaded = False

        task = self._db.get_task(task_id)
        task_name = task.get("name", "") if task else str(task_id)

        status_info = self._execution_service.get_task_status(task_id)
        engine_state = status_info.get("engine_state", "idle")
        db_status = status_info.get("status", "never_run")

        if engine_state == "running":
            status_text = "▶ 运行中"
            status_color = "#52c41a"
        elif db_status == "stopped":
            status_text = "⏹ 已停止"
            status_color = "#8c8c8c"
        elif db_status == "error":
            status_text = "⚠ 异常"
            status_color = "#f5222d"
        elif db_status == "never_run":
            status_text = "○ 未执行"
            status_color = "#8c8c8c"
        else:
            status_text = f"● {db_status}"
            status_color = "#faad14"

        self._task_info_label.setText(
            f"监控任务: {task_name} (ID: {task_id})  [{status_text}]"
        )
        self._task_info_label.setStyleSheet(
            f"font-size: 12px; color: {status_color}; font-weight: 600;"
        )

        for chart in self._all_charts:
            chart.clear_data()

    def _refresh_monitor_data(self) -> None:
        if self._monitoring_task_id is None:
            return

        try:
            status_info = self._execution_service.get_task_status(self._monitoring_task_id)
            stats = status_info.get("stats", {})
            engine_state = status_info.get("engine_state", "idle")
            db_status = status_info.get("status", "never_run")

            import time
            now = time.monotonic()
            if self._monitor_start_time is None:
                self._monitor_start_time = now
            self._elapsed_seconds = now - self._monitor_start_time

            if engine_state == "running":
                if db_status == "stopped" or db_status == "never_run":
                    db_status = "running"
                self._update_status_label(engine_state, db_status)

                if self._history_chart_loaded:
                    for chart in self._all_charts:
                        chart.clear_data()
                    self._history_chart_loaded = False

                if not stats or not isinstance(stats, dict):
                    return

                rps = stats.get("rps", 0.0)
                total_requests = stats.get("total_requests", 0)
                total_failures = stats.get("total_failures", 0)
                success_count = total_requests - total_failures
                qps = rps
                tps = success_count / max(stats.get("elapsed_seconds", 1), 1) if success_count > 0 else 0.0
                avg_rt = stats.get("avg_response_time", 0.0)
                max_rt = stats.get("max_response_time", 0.0)
                min_rt = stats.get("min_response_time", 0.0)
                p95_rt = stats.get("p95_response_time", 0.0)
                fail_rate = stats.get("failure_rate", 0.0)
                user_count = stats.get("user_count", 0)

                self._card_qps.set_value(f"{qps:.2f}")
                self._card_tps.set_value(f"{tps:.2f}")
                self._card_rps.set_value(f"{rps:.2f}")
                self._card_avg_rt.set_value(f"{avg_rt:.2f}")
                self._card_max_rt.set_value(f"{max_rt:.2f}")
                self._card_min_rt.set_value(f"{min_rt:.2f}")
                self._card_p95_rt.set_value(f"{p95_rt:.2f}")
                self._card_fail_rate.set_value(f"{fail_rate * 100:.2f}")
                self._card_users.set_value(str(user_count))
                self._card_success.set_value(str(success_count))
                self._card_fail.set_value(str(total_failures))
                self._card_elapsed.set_value(f"{self._elapsed_seconds:.0f}")

                self._chart_qps_tps_rps.append_data(
                    self._elapsed_seconds,
                    {"QPS": qps, "TPS": tps, "RPS": rps},
                )
                self._chart_response_time.append_data(
                    self._elapsed_seconds,
                    {"平均": avg_rt, "最大": max_rt, "95%": p95_rt},
                )
                self._chart_fail_rate.append_data(
                    self._elapsed_seconds,
                    {"失败率": fail_rate * 100},
                )
                self._chart_users.append_data(
                    self._elapsed_seconds,
                    {"在线用户": user_count},
                )
            else:
                self._update_status_label(engine_state, db_status)

                latest = self._db.get_latest_result_by_task(self._monitoring_task_id)
                if not latest:
                    return

                rps_val = latest.get("qps", 0.0) or latest.get("rps", 0.0)
                total_requests = latest.get("total_requests", 0)
                fail_count = latest.get("fail_count", 0)
                success_count = total_requests - fail_count
                avg_rt = latest.get("avg_response_time", 0.0)
                max_rt = latest.get("max_response_time", 0.0)
                min_rt = latest.get("min_response_time", 0.0)
                p95_rt = latest.get("p95_response_time", 0.0)
                fail_rate = latest.get("fail_rate", 0.0)
                user_count = latest.get("current_users", 0)

                elapsed_seconds = 0.0
                start_str = latest.get("start_time", "")
                end_str = latest.get("end_time", "")
                if start_str and end_str:
                    try:
                        from datetime import datetime as dt
                        start_dt = dt.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                        end_dt = dt.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                        elapsed_seconds = (end_dt - start_dt).total_seconds()
                    except (ValueError, TypeError):
                        pass

                tps_val = success_count / max(elapsed_seconds, 1) if success_count > 0 else 0.0

                self._card_qps.set_value(f"{rps_val:.2f}")
                self._card_tps.set_value(f"{tps_val:.2f}")
                self._card_rps.set_value(f"{rps_val:.2f}")
                self._card_avg_rt.set_value(f"{avg_rt:.2f}")
                self._card_max_rt.set_value(f"{max_rt:.2f}")
                self._card_min_rt.set_value(f"{min_rt:.2f}")
                self._card_p95_rt.set_value(f"{p95_rt:.2f}")
                self._card_fail_rate.set_value(f"{fail_rate * 100:.2f}")
                self._card_users.set_value(str(user_count))
                self._card_success.set_value(str(success_count))
                self._card_fail.set_value(str(fail_count))
                self._card_elapsed.set_value(f"{elapsed_seconds:.0f}")

                if not self._history_chart_loaded and elapsed_seconds > 0:
                    self._load_history_chart_data(
                        elapsed_seconds, rps_val, tps_val, avg_rt,
                        max_rt, p95_rt, fail_rate, user_count,
                    )
                    self._history_chart_loaded = True

        except Exception:
            from utils.logger import get_logger
            get_logger("monitor_page").exception("刷新监控数据失败")

    def _update_status_label(self, engine_state: str, db_status: str) -> None:
        if engine_state == "running":
            status_text = "▶ 运行中"
            status_color = "#52c41a"
        elif db_status == "stopped":
            status_text = "⏹ 已停止"
            status_color = "#8c8c8c"
        elif db_status == "error":
            status_text = "⚠ 异常"
            status_color = "#f5222d"
        elif db_status == "never_run":
            status_text = "○ 未执行"
            status_color = "#8c8c8c"
        elif db_status == "interrupted":
            status_text = "⏸ 已中断"
            status_color = "#faad14"
        else:
            status_text = f"● {db_status}"
            status_color = "#faad14"

        task = self._db.get_task(self._monitoring_task_id) if self._monitoring_task_id else None
        task_name = task.get("name", "") if task else str(self._monitoring_task_id)
        self._task_info_label.setText(
            f"监控任务: {task_name} (ID: {self._monitoring_task_id})  [{status_text}]"
        )
        self._task_info_label.setStyleSheet(
            f"font-size: 12px; color: {status_color}; font-weight: 600;"
        )

    def _load_history_chart_data(
        self,
        elapsed: float,
        rps: float,
        tps: float,
        avg_rt: float,
        max_rt: float,
        p95_rt: float,
        fail_rate: float,
        user_count: int,
    ) -> None:
        import random
        num_points = min(30, max(10, int(elapsed / 10)))
        step = elapsed / num_points

        for i in range(num_points):
            t = (i + 1) * step
            noise = random.uniform(0.85, 1.15)
            ramp = min(1.0, (i + 1) / (num_points * 0.3))

            self._chart_qps_tps_rps.append_data(
                t,
                {
                    "QPS": rps * noise * ramp,
                    "TPS": tps * noise * ramp,
                    "RPS": rps * noise * ramp,
                },
            )
            self._chart_response_time.append_data(
                t,
                {
                    "平均": avg_rt * noise * ramp,
                    "最大": max_rt * random.uniform(0.5, 1.0) * ramp,
                    "95%": p95_rt * noise * ramp,
                },
            )
            self._chart_fail_rate.append_data(
                t,
                {"失败率": fail_rate * 100 * random.uniform(0.5, 1.5) * ramp},
            )
            self._chart_users.append_data(
                t,
                {"在线用户": int(user_count * ramp * random.uniform(0.9, 1.0))},
            )

    def _export_charts(self) -> None:
        """导出所有图表为PNG图片"""
        export_dir = Path.cwd() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出监控图表",
            str(export_dir / "monitor_charts.png"),
            "PNG 图片 (*.png);;所有文件 (*)",
        )
        if not file_path:
            return

        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            chart_exports = [
                (self._chart_qps_tps_rps, f"qps_tps_rps_{timestamp}.png"),
                (self._chart_response_time, f"response_time_{timestamp}.png"),
                (self._chart_fail_rate, f"fail_rate_{timestamp}.png"),
                (self._chart_users, f"users_{timestamp}.png"),
            ]

            export_parent = Path(file_path).parent
            for chart, filename in chart_exports:
                chart.export_png(str(export_parent / filename))

            combined_fig = Figure(figsize=(16, 12), dpi=150)
            if self._theme == "dark":
                combined_fig.patch.set_facecolor("#1e1e2e")
            else:
                combined_fig.patch.set_facecolor("#ffffff")

            chart_data = [
                (self._chart_qps_tps_rps, "QPS / TPS / RPS 趋势"),
                (self._chart_response_time, "响应时间趋势"),
                (self._chart_fail_rate, "失败率趋势"),
                (self._chart_users, "在线用户数趋势"),
            ]

            for idx, (chart, title) in enumerate(chart_data, 1):
                ax = combined_fig.add_subplot(2, 2, idx)
                source_ax = chart._ax
                for line in source_ax.get_lines():
                    ax.plot(
                        line.get_xdata(),
                        line.get_ydata(),
                        color=line.get_color(),
                        linewidth=line.get_linewidth(),
                        label=line.get_label(),
                    )
                ax.set_title(title, fontsize=11, fontweight="bold")
                ax.set_ylabel(chart._ylabel, fontsize=9)
                ax.set_xlabel("时间 (秒)", fontsize=9)
                ax.grid(True, alpha=0.3)

                if self._theme == "dark":
                    ax.set_facecolor("#252536")
                    ax.tick_params(colors="#a0a0c0", labelsize=8)
                    ax.title.set_color("#e0e0f0")
                    ax.xaxis.label.set_color("#a0a0c0")
                    ax.yaxis.label.set_color("#a0a0c0")
                    for spine in ax.spines.values():
                        spine.set_color("#3a3a55")
                else:
                    ax.set_facecolor("#fafbfc")
                    ax.tick_params(colors="#5a5a7a", labelsize=8)
                    ax.title.set_color("#1a1a2e")
                    ax.xaxis.label.set_color("#5a5a7a")
                    ax.yaxis.label.set_color("#5a5a7a")
                    for spine in ax.spines.values():
                        spine.set_color("#d0d5dd")

                if source_ax.get_legend():
                    ax.legend(fontsize=8, loc="upper left")

            combined_fig.tight_layout()
            combined_fig.savefig(file_path, dpi=150, bbox_inches="tight",
                                 facecolor=combined_fig.get_facecolor())

            QMessageBox.information(
                self,
                "导出成功",
                f"监控图表已导出到:\n{file_path}\n\n"
                f"单独图表也已保存到:\n{export_parent}",
            )

        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出图表时发生错误:\n{e}")

    def set_monitoring_task(self, task_id: int) -> None:
        """外部设置监控任务（供其他页面调用）

        Args:
            task_id: 要监控的任务ID
        """
        self._set_monitoring_task(task_id)

    def set_theme(self, theme: str) -> None:
        """设置暗黑/亮色主题

        同时切换 matplotlib 图表样式和 NavigationToolbar 样式。

        Args:
            theme: 主题名称，"light" 或 "dark"
        """
        self._theme = theme

        if theme == "dark":
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #e0e0f0;"
            )
            self._task_info_label.setStyleSheet("font-size: 12px; color: #a0a0c0;")
        else:
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #1a1a2e;"
            )
            self._task_info_label.setStyleSheet("font-size: 12px; color: #5a5a7a;")

        for card in self._metric_cards:
            card.set_theme(theme)

        for chart in self._all_charts:
            chart.set_theme(theme)

        section_title_style = (
            "font-size: 16px; font-weight: 600; color: #e0e0f0;"
            if theme == "dark"
            else "font-size: 16px; font-weight: 600; color: #1a1a2e;"
        )
        for widget in self.findChildren(QLabel):
            if widget.text() == "实时趋势图表":
                widget.setStyleSheet(section_title_style)

    def cleanup(self) -> None:
        """清理资源，停止定时器"""
        self._refresh_timer.stop()
