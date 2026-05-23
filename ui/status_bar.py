from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QWidget,
)

from utils.system_monitor import SystemMonitor


class StatusBarMetric(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBarMetric")
        self._title = title
        self._danger_threshold = 90.0
        self._warning_threshold = 70.0

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._title_label = QLabel(f"{self._title}:")
        self._title_label.setObjectName("titleLabel")
        self._title_label.setProperty("labelRole", "title")
        self._title_label.setFixedWidth(36)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setFixedWidth(100)

        self._value_label = QLabel("0.0%")
        self._value_label.setObjectName("valueLabel")
        self._value_label.setProperty("labelRole", "value")
        self._value_label.setFixedWidth(48)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._title_label)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._value_label)

    def set_value(self, percent: float) -> None:
        clamped = max(0.0, min(100.0, percent))
        self._progress_bar.setValue(int(clamped))
        self._value_label.setText(f"{clamped:.1f}%")

        self._progress_bar.setProperty("danger", clamped >= self._danger_threshold)
        self._progress_bar.setProperty("warning",
                                       clamped >= self._warning_threshold and clamped < self._danger_threshold)

        self._progress_bar.style().unpolish(self._progress_bar)
        self._progress_bar.style().polish(self._progress_bar)

    def set_thresholds(self, warning: float, danger: float) -> None:
        self._warning_threshold = warning
        self._danger_threshold = danger

    def set_theme(self, theme: str) -> None:
        if theme == "dark":
            self._title_label.setStyleSheet("color: #a0a0c0; font-size: 12px;")
            self._value_label.setStyleSheet("color: #e0e0f0; font-size: 12px; font-weight: 600;")
        else:
            self._title_label.setStyleSheet("color: #5a5a7a; font-size: 12px;")
            self._value_label.setStyleSheet("color: #1a1a2e; font-size: 12px; font-weight: 600;")


class SystemStatusBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SystemStatusBar")
        self._theme = "light"
        self._monitor = SystemMonitor(interval=2.0)
        self._refresh_timer = QTimer(self)
        self._refresh_interval = 2000

        self._setup_ui()
        self._connect_signals()
        self._start_monitoring()

    def _setup_ui(self) -> None:
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(16)

        self._cpu_metric = StatusBarMetric("CPU", self)
        self._memory_metric = StatusBarMetric("内存", self)
        self._memory_metric.set_thresholds(warning=75.0, danger=90.0)

        layout.addWidget(self._cpu_metric)

        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setFixedWidth(1)
        layout.addWidget(separator1)

        layout.addWidget(self._memory_metric)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFixedWidth(1)
        layout.addWidget(separator2)

        self._connection_label = QLabel("● 已连接")
        self._connection_label.setObjectName("connectionLabel")
        self._connection_label.setStyleSheet("color: #52c41a; font-size: 12px;")
        layout.addWidget(self._connection_label)

        layout.addStretch()

        self._time_label = QLabel("")
        self._time_label.setObjectName("timeLabel")
        self._time_label.setStyleSheet("color: #5a5a7a; font-size: 12px;")
        layout.addWidget(self._time_label)

    def _connect_signals(self) -> None:
        self._refresh_timer.timeout.connect(self._refresh_metrics)

    def _start_monitoring(self) -> None:
        self._monitor.start()
        self._refresh_timer.start(self._refresh_interval)
        self._refresh_metrics()

    @Slot()
    def _refresh_metrics(self) -> None:
        snapshot = self._monitor.latest

        if snapshot.timestamp > 0:
            self._cpu_metric.set_value(snapshot.cpu_percent)
            self._memory_metric.set_value(snapshot.memory_percent)
        else:
            try:
                cpu = self._monitor.get_cpu_percent()
                if isinstance(cpu, float):
                    self._cpu_metric.set_value(cpu)
                else:
                    self._cpu_metric.set_value(sum(cpu) / len(cpu) if cpu else 0.0)

                mem = self._monitor.get_memory_info()
                self._memory_metric.set_value(mem["percent"])
            except Exception:
                self._cpu_metric.set_value(0.0)
                self._memory_metric.set_value(0.0)

        from datetime import datetime
        now = datetime.now()
        self._time_label.setText(now.strftime("%H:%M:%S"))

    def set_connection_status(self, connected: bool) -> None:
        if connected:
            self._connection_label.setText("● 已连接")
            if self._theme == "dark":
                self._connection_label.setStyleSheet("color: #73d13d; font-size: 12px;")
            else:
                self._connection_label.setStyleSheet("color: #52c41a; font-size: 12px;")
        else:
            self._connection_label.setText("● 未连接")
            if self._theme == "dark":
                self._connection_label.setStyleSheet("color: #ff4d4f; font-size: 12px;")
            else:
                self._connection_label.setStyleSheet("color: #f5222d; font-size: 12px;")

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self._cpu_metric.set_theme(theme)
        self._memory_metric.set_theme(theme)

        if theme == "dark":
            self._time_label.setStyleSheet("color: #a0a0c0; font-size: 12px;")
        else:
            self._time_label.setStyleSheet("color: #5a5a7a; font-size: 12px;")

        is_connected = "已连接" in self._connection_label.text()
        self.set_connection_status(is_connected)

    def set_refresh_interval(self, interval_ms: int) -> None:
        self._refresh_interval = max(500, interval_ms)
        self._refresh_timer.setInterval(self._refresh_interval)

    def cleanup(self) -> None:
        self._refresh_timer.stop()
        self._monitor.stop()
