from PySide6.QtWidgets import QApplication

_LIGHT_VARIABLES = {
    "{{bg_primary}}": "#ffffff",
    "{{bg_secondary}}": "#f5f7fa",
    "{{bg_tertiary}}": "#e8ecf1",
    "{{bg_hover}}": "#e3e8ef",
    "{{bg_pressed}}": "#d5dbe5",
    "{{bg_input}}": "#ffffff",
    "{{text_primary}}": "#1a1a2e",
    "{{text_secondary}}": "#5a5a7a",
    "{{text_disabled}}": "#b0b0c0",
    "{{accent}}": "#4a90d9",
    "{{accent_hover}}": "#3a7bc8",
    "{{accent_pressed}}": "#2e6ab5",
    "{{accent_light}}": "#e8f0fe",
    "{{border}}": "#d0d5dd",
    "{{border_focus}}": "#4a90d9",
    "{{success}}": "#52c41a",
    "{{warning}}": "#faad14",
    "{{danger}}": "#f5222d",
    "{{danger_light}}": "#fff1f0",
    "{{shadow}}": "rgba(0, 0, 0, 0.08)",
    "{{scrollbar_bg}}": "#f0f0f0",
    "{{scrollbar_handle}}": "#c0c0c0",
    "{{scrollbar_handle_hover}}": "#a0a0a0",
    "{{nav_bg}}": "#f8f9fc",
    "{{nav_item_selected}}": "#e8f0fe",
    "{{nav_item_hover}}": "#edf1f7",
    "{{statusbar_bg}}": "#f8f9fc",
    "{{progress_bg}}": "#e8ecf1",
    "{{progress_chunk}}": "#4a90d9",
    "{{table_header_bg}}": "#f5f7fa",
    "{{table_row_alt}}": "#fafbfc",
    "{{tab_bg}}": "#f5f7fa",
    "{{tab_selected}}": "#ffffff",
}

_DARK_VARIABLES = {
    "{{bg_primary}}": "#1e1e2e",
    "{{bg_secondary}}": "#252536",
    "{{bg_tertiary}}": "#2d2d44",
    "{{bg_hover}}": "#353552",
    "{{bg_pressed}}": "#3d3d5c",
    "{{bg_input}}": "#2a2a3e",
    "{{text_primary}}": "#e0e0f0",
    "{{text_secondary}}": "#a0a0c0",
    "{{text_disabled}}": "#5a5a7a",
    "{{accent}}": "#5b9bd5",
    "{{accent_hover}}": "#6baae0",
    "{{accent_pressed}}": "#7bb9eb",
    "{{accent_light}}": "#2a3a5a",
    "{{border}}": "#3a3a55",
    "{{border_focus}}": "#5b9bd5",
    "{{success}}": "#73d13d",
    "{{warning}}": "#ffc53d",
    "{{danger}}": "#ff4d4f",
    "{{danger_light}}": "#3a1a1a",
    "{{shadow}}": "rgba(0, 0, 0, 0.3)",
    "{{scrollbar_bg}}": "#252536",
    "{{scrollbar_handle}}": "#4a4a6a",
    "{{scrollbar_handle_hover}}": "#5a5a7a",
    "{{nav_bg}}": "#1a1a2e",
    "{{nav_item_selected}}": "#2a3a5a",
    "{{nav_item_hover}}": "#252540",
    "{{statusbar_bg}}": "#1a1a2e",
    "{{progress_bg}}": "#2d2d44",
    "{{progress_chunk}}": "#5b9bd5",
    "{{table_header_bg}}": "#252536",
    "{{table_row_alt}}": "#222238",
    "{{tab_bg}}": "#252536",
    "{{tab_selected}}": "#1e1e2e",
}

_BASE_QSS = """
/* ===== 全局基础样式 ===== */
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
    color: {{text_primary}};
    background-color: {{bg_primary}};
}

QMainWindow {
    background-color: {{bg_primary}};
}

/* ===== 按钮样式 ===== */
QPushButton {
    background-color: {{accent}};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: {{accent_hover}};
}

QPushButton:pressed {
    background-color: {{accent_pressed}};
}

QPushButton:disabled {
    background-color: {{bg_tertiary}};
    color: {{text_disabled}};
}

QPushButton[secondary="true"] {
    background-color: {{bg_tertiary}};
    color: {{text_primary}};
    border: 1px solid {{border}};
}

QPushButton[secondary="true"]:hover {
    background-color: {{bg_hover}};
}

QPushButton[danger="true"] {
    background-color: {{danger}};
    color: #ffffff;
}

QPushButton[danger="true"]:hover {
    background-color: #ff7875;
}

/* ===== 输入框样式 ===== */
QLineEdit {
    background-color: {{bg_input}};
    border: 1px solid {{border}};
    border-radius: 6px;
    padding: 8px 12px;
    color: {{text_primary}};
    selection-background-color: {{accent}};
    selection-color: #ffffff;
    min-height: 20px;
}

QLineEdit:focus {
    border-color: {{border_focus}};
}

QLineEdit:disabled {
    background-color: {{bg_tertiary}};
    color: {{text_disabled}};
}

QTextEdit {
    background-color: {{bg_input}};
    border: 1px solid {{border}};
    border-radius: 6px;
    padding: 8px 12px;
    color: {{text_primary}};
    selection-background-color: {{accent}};
    selection-color: #ffffff;
}

QTextEdit:focus {
    border-color: {{border_focus}};
}

/* ===== 下拉框样式 ===== */
QComboBox {
    background-color: {{bg_input}};
    border: 1px solid {{border}};
    border-radius: 6px;
    padding: 8px 12px;
    color: {{text_primary}};
    min-height: 20px;
    min-width: 100px;
}

QComboBox:hover {
    border-color: {{border_focus}};
}

QComboBox:focus {
    border-color: {{border_focus}};
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 30px;
    border-left: 1px solid {{border}};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox::down-arrow {
    width: 10px;
    height: 10px;
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {{text_secondary}};
}

QComboBox QAbstractItemView {
    background-color: {{bg_primary}};
    border: 1px solid {{border}};
    border-radius: 4px;
    selection-background-color: {{accent_light}};
    selection-color: {{text_primary}};
    outline: none;
    padding: 4px;
}

QComboBox QAbstractItemView::item {
    min-height: 30px;
    padding: 4px 8px;
    border-radius: 4px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: {{bg_hover}};
}

/* ===== 表格样式 ===== */
QTableView {
    background-color: {{bg_primary}};
    alternate-background-color: {{table_row_alt}};
    border: 1px solid {{border}};
    border-radius: 6px;
    gridline-color: {{border}};
    selection-background-color: {{accent_light}};
    selection-color: {{text_primary}};
    outline: none;
}

QTableView::item {
    padding: 6px 12px;
    border-bottom: 1px solid {{border}};
}

QTableView::item:hover {
    background-color: {{bg_hover}};
}

QHeaderView::section {
    background-color: {{table_header_bg}};
    color: {{text_secondary}};
    font-weight: 600;
    padding: 8px 12px;
    border: none;
    border-bottom: 2px solid {{border}};
    border-right: 1px solid {{border}};
}

QHeaderView::section:hover {
    background-color: {{bg_hover}};
}

/* ===== 列表样式 ===== */
QListWidget {
    background-color: {{bg_primary}};
    border: 1px solid {{border}};
    border-radius: 6px;
    outline: none;
    padding: 4px;
}

QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
    margin: 2px 4px;
}

QListWidget::item:hover {
    background-color: {{bg_hover}};
}

QListWidget::item:selected {
    background-color: {{accent_light}};
    color: {{accent}};
}

QListWidget::item:selected:hover {
    background-color: {{accent_light}};
}

/* ===== 滚动条样式 ===== */
QScrollBar:vertical {
    background-color: {{scrollbar_bg}};
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: {{scrollbar_handle}};
    min-height: 30px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: {{scrollbar_handle_hover}};
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    background-color: {{scrollbar_bg}};
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: {{scrollbar_handle}};
    min-width: 30px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background-color: {{scrollbar_handle_hover}};
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: none;
}

/* ===== 标签页样式 ===== */
QTabWidget::pane {
    border: 1px solid {{border}};
    border-radius: 6px;
    background-color: {{bg_primary}};
    top: -1px;
}

QTabBar::tab {
    background-color: {{tab_bg}};
    color: {{text_secondary}};
    border: 1px solid {{border}};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 20px;
    margin-right: 2px;
    min-width: 80px;
}

QTabBar::tab:hover {
    background-color: {{bg_hover}};
    color: {{text_primary}};
}

QTabBar::tab:selected {
    background-color: {{tab_selected}};
    color: {{accent}};
    border-bottom: 2px solid {{accent}};
    font-weight: 600;
}

/* ===== 进度条样式 ===== */
QProgressBar {
    background-color: {{progress_bg}};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: {{progress_chunk}};
    border-radius: 4px;
}

/* ===== 复选框样式 ===== */
QCheckBox {
    spacing: 8px;
    color: {{text_primary}};
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {{border}};
    background-color: {{bg_input}};
}

QCheckBox::indicator:hover {
    border-color: {{accent}};
}

QCheckBox::indicator:checked {
    background-color: {{accent}};
    border-color: {{accent}};
}

/* ===== 单选框样式 ===== */
QRadioButton {
    spacing: 8px;
    color: {{text_primary}};
}

QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid {{border}};
    background-color: {{bg_input}};
}

QRadioButton::indicator:hover {
    border-color: {{accent}};
}

QRadioButton::indicator:checked {
    background-color: {{accent}};
    border-color: {{accent}};
}

/* ===== 旋转框样式 ===== */
QSpinBox, QDoubleSpinBox {
    background-color: {{bg_input}};
    border: 1px solid {{border}};
    border-radius: 6px;
    padding: 6px 10px;
    color: {{text_primary}};
    min-height: 20px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: {{border_focus}};
}

/* ===== 分组框样式 ===== */
QGroupBox {
    font-weight: 600;
    border: 1px solid {{border}};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0px 6px;
    color: {{text_primary}};
}

/* ===== 工具提示样式 ===== */
QToolTip {
    background-color: {{bg_secondary}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ===== 菜单样式 ===== */
QMenu {
    background-color: {{bg_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: {{accent_light}};
    color: {{accent}};
}

QMenu::separator {
    height: 1px;
    background-color: {{border}};
    margin: 4px 8px;
}

/* ===== 标签样式 ===== */
QLabel {
    color: {{text_primary}};
    background-color: transparent;
}

/* ===== 分割线样式 ===== */
QFrame[frameShape="4"] {
    background-color: {{border}};
    max-height: 1px;
}

QFrame[frameShape="5"] {
    background-color: {{border}};
    max-width: 1px;
}

/* ===== 滑块样式 ===== */
QSlider::groove:horizontal {
    height: 6px;
    background-color: {{progress_bg}};
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background-color: {{accent}};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background-color: {{accent_hover}};
}

QSlider::sub-page:horizontal {
    background-color: {{progress_chunk}};
    border-radius: 3px;
}

/* ===== 日期时间控件样式 ===== */
QDateEdit, QTimeEdit, QDateTimeEdit {
    background-color: {{bg_input}};
    border: 1px solid {{border}};
    border-radius: 6px;
    padding: 6px 10px;
    color: {{text_primary}};
    min-height: 20px;
}

QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {
    border-color: {{border_focus}};
}

/* ===== 导航栏样式 ===== */
NavigationBar {
    background-color: {{nav_bg}};
    border-right: 1px solid {{border}};
}

NavButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: left;
    color: {{text_secondary}};
    font-size: 13px;
    min-height: 20px;
}

NavButton:hover {
    background-color: {{nav_item_hover}};
    color: {{text_primary}};
}

NavButton[selected="true"] {
    background-color: {{nav_item_selected}};
    color: {{accent}};
    font-weight: 600;
}

NavButton[selected="true"]:hover {
    background-color: {{nav_item_selected}};
}

/* ===== 状态栏样式 ===== */
SystemStatusBar {
    background-color: {{statusbar_bg}};
    border-bottom: 1px solid {{border}};
}

StatusBarMetric {
    background-color: transparent;
    border: none;
    color: {{text_secondary}};
    font-size: 12px;
}

StatusBarMetric QLabel[labelRole="title"] {
    color: {{text_secondary}};
    font-size: 12px;
}

StatusBarMetric QLabel[labelRole="value"] {
    color: {{text_primary}};
    font-size: 12px;
    font-weight: 600;
}

StatusBarMetric QProgressBar {
    background-color: {{progress_bg}};
    border: none;
    border-radius: 3px;
    height: 6px;
    max-width: 100px;
}

StatusBarMetric QProgressBar::chunk {
    background-color: {{progress_chunk}};
    border-radius: 3px;
}

StatusBarMetric QProgressBar[danger="true"]::chunk {
    background-color: {{danger}};
}

StatusBarMetric QProgressBar[warning="true"]::chunk {
    background-color: {{warning}};
}

/* ===== 堆叠页面容器 ===== */
QStackedWidget {
    background-color: {{bg_primary}};
}

/* ===== 滚动区域样式 ===== */
QScrollArea {
    background-color: {{bg_primary}};
    border: none;
}

/* ===== 对话框样式 ===== */
QDialog {
    background-color: {{bg_primary}};
}
"""


class StyleManager:
    _instance = None

    def __new__(cls) -> "StyleManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._current_theme = "light"
        self._app = None

    @classmethod
    def instance(cls) -> "StyleManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def current_theme(self) -> str:
        return self._current_theme

    @property
    def is_dark(self) -> bool:
        return self._current_theme == "dark"

    def _resolve_variables(self, qss: str, theme: str) -> str:
        variables = _DARK_VARIABLES if theme == "dark" else _LIGHT_VARIABLES
        for placeholder, value in variables.items():
            qss = qss.replace(placeholder, value)
        return qss

    def get_qss(self, theme: str | None = None) -> str:
        theme = theme or self._current_theme
        return self._resolve_variables(_BASE_QSS, theme)

    def apply_theme(self, app: QApplication, theme: str | None = None) -> None:
        if theme is not None:
            self._current_theme = theme
        self._app = app
        qss = self.get_qss(self._current_theme)
        app.setStyleSheet(qss)

    def toggle_theme(self, app: QApplication) -> str:
        self._current_theme = "dark" if self._current_theme == "light" else "light"
        self.apply_theme(app)
        return self._current_theme

    @classmethod
    def reset(cls) -> None:
        cls._instance = None
