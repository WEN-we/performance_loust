from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import get_settings
from pages.home_page import HomePage
from pages.create_task_page import CreateTaskPage
from pages.execute_task_page import ExecuteTaskPage
from pages.monitor_page import MonitorPage
from pages.history_page import HistoryPage
from pages.settings_page import SettingsPage
from ui.navigation import NavigationBar
from ui.status_bar import SystemStatusBar
from ui.styles import StyleManager
from utils.logger import get_logger

logger = get_logger(__name__)


class PlaceholderPage(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        header_layout = QHBoxLayout()
        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1a1a2e;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        desc = QLabel(f"「{title}」页面内容待实现")
        desc.setStyleSheet("font-size: 14px; color: #5a5a7a; margin-top: 8px;")
        layout.addWidget(desc)
        layout.addStretch()

    def set_theme(self, theme: str) -> None:
        if theme == "dark":
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #e0e0f0;"
            )
        else:
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #1a1a2e;"
            )


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = get_settings()
        self._style_manager = StyleManager.instance()
        self._current_theme = self._settings.theme

        self._setup_window()
        self._setup_ui()
        self._setup_menu_bar()
        self._connect_signals()
        self._apply_initial_theme()

    def _setup_window(self) -> None:
        self.setWindowTitle("Locust压力测试平台")
        w, h = self._settings.window_size
        self.resize(w, h)
        self.setMinimumSize(1024, 600)

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self._status_bar = SystemStatusBar(self)
        central_layout.addWidget(self._status_bar)

        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._navigation = NavigationBar(self)
        body_layout.addWidget(self._navigation)

        self._stacked_widget = QStackedWidget()
        self._stacked_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._pages: list[QWidget] = []
        self._page_instances: dict[int, QWidget] = {}
        self._init_pages()

        body_layout.addWidget(self._stacked_widget)

        central_layout.addWidget(body_widget, 1)

        self._window_status_bar = self.statusBar()
        self._window_status_bar.showMessage("就绪")
        self._status_connection_label = QLabel("连接状态: 就绪")
        self._window_status_bar.addPermanentWidget(self._status_connection_label)

    def _init_pages(self) -> None:
        page_factories = [
            ("首页", lambda: HomePage(self)),
            ("创建任务", lambda: CreateTaskPage(self)),
            ("执行任务", lambda: ExecuteTaskPage(self)),
            ("实时监控", lambda: MonitorPage(self)),
            ("历史记录", lambda: HistoryPage(self)),
            ("系统设置", lambda: SettingsPage(self)),
        ]
        for i, (name, factory) in enumerate(page_factories):
            try:
                page = factory()
                self._page_instances[i] = page
            except Exception as e:
                logger.warning(f"加载页面「{name}」失败，使用占位页面: {e}")
                page = PlaceholderPage(name, self)
            self._pages.append(page)
            self._stacked_widget.addWidget(page)

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件(&F)")

        self._new_task_action = QAction("新建任务(&N)", self)
        self._new_task_action.setShortcut(QKeySequence("Ctrl+N"))
        self._new_task_action.triggered.connect(lambda: self._switch_page(1))
        file_menu.addAction(self._new_task_action)

        file_menu.addSeparator()

        self._exit_action = QAction("退出(&Q)", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)
        file_menu.addAction(self._exit_action)

        view_menu = menu_bar.addMenu("视图(&V)")

        self._toggle_theme_action = QAction("切换暗黑模式(&D)", self)
        self._toggle_theme_action.setShortcut(QKeySequence("Ctrl+D"))
        self._toggle_theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._toggle_theme_action)

        view_menu.addSeparator()

        nav_menu = view_menu.addMenu("导航到(&G)")
        page_names = ["首页", "创建任务", "执行任务", "实时监控", "历史记录", "系统设置"]
        for i, name in enumerate(page_names):
            action = QAction(name, self)
            index = i
            action.triggered.connect(lambda checked=False, idx=index: self._switch_page(idx))
            nav_menu.addAction(action)

        help_menu = menu_bar.addMenu("帮助(&H)")

        self._about_action = QAction("关于(&A)", self)
        self._about_action.triggered.connect(self._show_about)
        help_menu.addAction(self._about_action)

    def _connect_signals(self) -> None:
        self._navigation.navigation_changed.connect(self._on_navigation_changed)

        for i, page in enumerate(self._pages):
            if hasattr(page, "navigate_requested"):
                page.navigate_requested.connect(self._switch_page)

    @Slot(int)
    def _on_navigation_changed(self, index: int) -> None:
        self._switch_page(index)

    def _switch_page(self, index: int) -> None:
        if 0 <= index < self._stacked_widget.count():
            self._stacked_widget.setCurrentIndex(index)
            self._navigation.set_current_index(index)
            page_names = ["首页", "创建任务", "执行任务", "实时监控", "历史记录", "系统设置"]
            name = page_names[index] if index < len(page_names) else ""
            self._window_status_bar.showMessage(f"当前页面: {name}")

    def _toggle_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        new_theme = self._style_manager.toggle_theme(app)
        self._current_theme = new_theme
        self._settings.theme = new_theme

        self._navigation.set_theme(new_theme)
        self._status_bar.set_theme(new_theme)
        for page in self._pages:
            if hasattr(page, "set_theme"):
                page.set_theme(new_theme)

        if new_theme == "dark":
            self._toggle_theme_action.setText("切换亮色模式(&L)")
            self._status_connection_label.setStyleSheet("color: #a0a0c0;")
        else:
            self._toggle_theme_action.setText("切换暗黑模式(&D)")
            self._status_connection_label.setStyleSheet("color: #5a5a7a;")

    def _apply_initial_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        theme = self._current_theme
        self._style_manager.apply_theme(app, theme)
        self._navigation.set_theme(theme)
        self._status_bar.set_theme(theme)
        for page in self._pages:
            if hasattr(page, "set_theme"):
                page.set_theme(theme)

        if theme == "dark":
            self._toggle_theme_action.setText("切换亮色模式(&L)")
            self._status_connection_label.setStyleSheet("color: #a0a0c0;")
        else:
            self._toggle_theme_action.setText("切换暗黑模式(&D)")
            self._status_connection_label.setStyleSheet("color: #5a5a7a;")

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "关于",
            "Locust压力测试平台 v1.0.0\n\n"
            "基于Locust的分布式压力测试工具\n"
            "提供可视化任务管理、实时监控与报告生成功能。",
        )

    def set_page(self, index: int, page: QWidget) -> None:
        if 0 <= index < self._stacked_widget.count():
            old_widget = self._stacked_widget.widget(index)
            self._stacked_widget.removeWidget(old_widget)
            old_widget.deleteLater()
            self._stacked_widget.insertWidget(index, page)
            self._pages[index] = page
            if hasattr(page, "set_theme"):
                page.set_theme(self._current_theme)

    def closeEvent(self, event) -> None:
        self._status_bar.cleanup()
        for page in self._pages:
            if hasattr(page, "cleanup"):
                try:
                    page.cleanup()
                except Exception as e:
                    logger.warning(f"清理页面资源失败: {e}")
        self._settings.window_size = (self.width(), self.height())
        self._settings.save()
        logger.info("应用程序关闭")
        super().closeEvent(event)
