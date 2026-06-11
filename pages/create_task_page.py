"""
创建任务页面模块

提供完整的任务创建/编辑表单，包含基本信息、认证、请求头、Cookie、
请求体、参数化、压测配置等多个区域，支持表单验证和暗黑模式。
"""

import json
import csv
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from database.db_manager import DatabaseManager
from services.task_service import TaskService
from services.execution_service import ExecutionService


class JsonSyntaxHighlighter(QSyntaxHighlighter):
    """JSON 语法高亮器

    为 QPlainTextEdit 中的 JSON 内容提供关键字、字符串、数字、
    布尔值和 null 的高亮显示。
    """

    def __init__(self, parent: QPlainTextEdit) -> None:
        super().__init__(parent.document())
        self._setup_formats()

    def _setup_formats(self) -> None:
        """初始化各种语法元素的高亮格式"""
        self._key_format = QTextCharFormat()
        self._key_format.setForeground(QColor("#a626a4"))
        self._key_format.setFontWeight(QFont.Weight.Bold)

        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#50a14f"))

        self._number_format = QTextCharFormat()
        self._number_format.setForeground(QColor("#986801"))

        self._bool_format = QTextCharFormat()
        self._bool_format.setForeground(QColor("#0184bc"))

        self._null_format = QTextCharFormat()
        self._null_format.setForeground(QColor("#986801"))
        self._null_format.setFontItalic(True)

    def highlightBlock(self, text: str) -> None:
        """对文本块进行语法高亮处理

        Args:
            text: 当前文本块内容
        """
        import re

        for match in re.finditer(r'"([^"\\]|\\.)*"\s*:', text):
            self.setFormat(match.start(), match.end() - match.start(), self._key_format)

        for match in re.finditer(r':\s*"([^"\\]|\\.)*"', text):
            start = match.start()
            colon_end = text.index('"', start)
            self.setFormat(colon_end, match.end() - colon_end, self._string_format)

        for match in re.finditer(r':\s*(-?\d+\.?\d*([eE][+-]?\d+)?)\b', text):
            number_start = match.start() + 1
            while number_start < match.end() and text[number_start].isspace():
                number_start += 1
            self.setFormat(number_start, match.end() - number_start, self._number_format)

        for match in re.finditer(r':\s*(true|false)\b', text):
            value_start = match.start() + 1
            while value_start < match.end() and text[value_start].isspace():
                value_start += 1
            self.setFormat(value_start, match.end() - value_start, self._bool_format)

        for match in re.finditer(r':\s*null\b', text):
            value_start = match.start() + 1
            while value_start < match.end() and text[value_start].isspace():
                value_start += 1
            self.setFormat(value_start, match.end() - value_start, self._null_format)


class KeyValueRow(QWidget):
    """动态键值对行组件

    用于请求头、Cookie、表单数据、参数化等区域的动态添加/删除行，
    每行包含一个 Key 输入框、一个 Value 输入框和删除按钮。
    """

    removed = Signal(object)

    def __init__(
        self,
        key: str = "",
        value: str = "",
        key_placeholder: str = "Key",
        value_placeholder: str = "Value",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._key_placeholder = key_placeholder
        self._value_placeholder = value_placeholder
        self._setup_ui(key, value)

    def _setup_ui(self, key: str, value: str) -> None:
        """构建键值对行布局"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self._key_edit = QLineEdit(key)
        self._key_edit.setPlaceholderText(self._key_placeholder)
        self._key_edit.setMinimumWidth(150)
        layout.addWidget(self._key_edit)

        self._value_edit = QLineEdit(value)
        self._value_edit.setPlaceholderText(self._value_placeholder)
        self._value_edit.setMinimumWidth(150)
        layout.addWidget(self._value_edit)

        self._remove_btn = QPushButton("X")
        self._remove_btn.setFixedSize(32, 32)
        self._remove_btn.setProperty("danger", True)
        self._remove_btn.setToolTip("删除")
        self._remove_btn.setStyleSheet(
            "padding: 0px; margin: 0px; "
            "font-size: 14px; font-weight: bold; "
            "min-height: 0px;"
        )
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(self._remove_btn)

    @property
    def key(self) -> str:
        """获取 Key 值"""
        return self._key_edit.text().strip()

    @property
    def value(self) -> str:
        """获取 Value 值"""
        return self._value_edit.text().strip()

    def to_dict(self) -> tuple[str, str]:
        """转换为 (key, value) 元组"""
        return self.key, self.value


class KeyValueSection(QWidget):
    """动态键值对区域组件

    管理多个 KeyValueRow，支持动态添加和删除行，
    并提供将所有行导出为字典的方法。
    """

    def __init__(
        self,
        title: str = "",
        key_placeholder: str = "Key",
        value_placeholder: str = "Value",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rows: list[KeyValueRow] = []
        self._key_placeholder = key_placeholder
        self._value_placeholder = value_placeholder
        self._setup_ui(title)

    def _setup_ui(self, title: str) -> None:
        """构建键值对区域布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        header_layout = QHBoxLayout()
        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
            header_layout.addWidget(title_label)
        header_layout.addStretch()

        self._add_btn = QPushButton("+ 添加")
        self._add_btn.setProperty("secondary", True)
        self._add_btn.setFixedWidth(80)
        self._add_btn.clicked.connect(lambda: self._add_row())
        header_layout.addWidget(self._add_btn)

        main_layout.addLayout(header_layout)

        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(2)
        main_layout.addLayout(self._rows_container)

    def _add_row(self, key: str = "", value: str = "") -> None:
        """添加一行键值对

        Args:
            key: 初始 Key 值
            value: 初始 Value 值
        """
        row = KeyValueRow(
            key,
            value,
            key_placeholder=self._key_placeholder,
            value_placeholder=self._value_placeholder,
            parent=self,
        )
        row.removed.connect(self._remove_row)
        self._rows.append(row)
        self._rows_container.addWidget(row)

    def _remove_row(self, row: KeyValueRow) -> None:
        """删除指定键值对行

        Args:
            row: 要删除的 KeyValueRow 实例
        """
        if row in self._rows:
            self._rows.remove(row)
            self._rows_container.removeWidget(row)
            row.deleteLater()

    def to_dict(self) -> dict[str, str]:
        """将所有键值对导出为字典

        Returns:
            键值对字典
        """
        result: dict[str, str] = {}
        for row in self._rows:
            key, value = row.to_dict()
            if key:
                result[key] = value
        return result

    def load_dict(self, data: dict[str, str]) -> None:
        """从字典加载键值对，清空现有行后重新填充

        Args:
            data: 键值对字典
        """
        for row in self._rows:
            self._rows_container.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        for key, value in data.items():
            self._add_row(str(key), str(value))

    def clear_all(self) -> None:
        """清空所有键值对行"""
        for row in self._rows:
            self._rows_container.removeWidget(row)
            row.deleteLater()
        self._rows.clear()


class CreateTaskPage(QWidget):
    """创建/编辑任务页面

    提供完整的任务配置表单，包含基本信息、认证、请求头、Cookie、
    请求体、参数化、压测配置等区域，支持表单验证、编辑已有任务
    和暗黑模式切换。
    """

    task_saved = Signal(int)
    task_executed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = "light"
        self._editing_task_id: int | None = None
        self._db = DatabaseManager()
        self._task_service = TaskService(self._db)
        self._execution_service = ExecutionService(self._db)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建创建任务页面整体布局"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(32, 24, 32, 16)

        self._title_label = QLabel("创建任务")
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1a1a2e;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()
        outer_layout.addLayout(header_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        scroll_content = QWidget()
        self._form_layout = QVBoxLayout(scroll_content)
        self._form_layout.setContentsMargins(32, 0, 32, 32)
        self._form_layout.setSpacing(20)

        self._setup_basic_info_section()
        self._setup_auth_section()
        self._setup_headers_section()
        self._setup_cookies_section()
        self._setup_body_section()
        self._setup_params_section()
        self._setup_stress_config_section()
        self._setup_action_buttons()

        self._form_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(scroll_area, 1)

    def _create_group_box(self, title: str) -> tuple[QGroupBox, QVBoxLayout]:
        """创建统一风格的分组框

        Args:
            title: 分组框标题

        Returns:
            (QGroupBox, QVBoxLayout) 元组
        """
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 20, 16, 16)
        return group, layout

    def _create_form_row(
        self,
        label_text: str,
        widget: QWidget,
        layout: QVBoxLayout | QGridLayout,
        row: int = -1,
        col: int = 0,
    ) -> None:
        """创建表单行（标签 + 控件）

        Args:
            label_text: 标签文本
            widget: 表单控件
            layout: 目标布局
            row: 网格行号（QGridLayout 时使用）
            col: 网格列号
        """
        label = QLabel(label_text)
        label.setFixedWidth(100)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(12)
        row_layout.addWidget(label)
        row_layout.addWidget(widget, 1)

        if isinstance(layout, QGridLayout):
            layout.addLayout(row_layout, row, col, 1, 2)
        else:
            layout.addLayout(row_layout)

    def _create_form_row_with_container(
        self,
        label_text: str,
        widget: QWidget,
        layout: QVBoxLayout | QGridLayout,
        row: int = -1,
        col: int = 0,
    ) -> QWidget:
        """创建表单行（标签 + 控件），返回可整体隐藏的容器Widget

        Args:
            label_text: 标签文本
            widget: 表单控件
            layout: 目标布局
            row: 网格行号（QGridLayout 时使用）
            col: 网格列号

        Returns:
            包含标签和控件的容器QWidget
        """
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(12)

        label = QLabel(label_text)
        label.setFixedWidth(100)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        container_layout.addWidget(label)
        container_layout.addWidget(widget, 1)

        if isinstance(layout, QGridLayout):
            layout.addWidget(container, row, col, 1, 2)
        else:
            layout.addWidget(container)

        return container

    def _setup_basic_info_section(self) -> None:
        """创建基本信息区域"""
        group, layout = self._create_group_box("基本信息")

        self._task_name_edit = QLineEdit()
        self._task_name_edit.setPlaceholderText("请输入任务名称")
        self._create_form_row("任务名称:", self._task_name_edit, layout)

        type_and_method_layout = QHBoxLayout()
        type_and_method_layout.setSpacing(16)

        type_label = QLabel("任务类型:")
        type_label.setFixedWidth(100)
        type_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        type_and_method_layout.addWidget(type_label)

        self._task_type_combo = QComboBox()
        self._task_type_combo.addItems(["HTTP", "HTTPS", "WebSocket"])
        self._task_type_combo.setMinimumWidth(140)
        type_and_method_layout.addWidget(self._task_type_combo)

        method_label = QLabel("请求方法:")
        method_label.setFixedWidth(80)
        method_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        type_and_method_layout.addWidget(method_label)

        self._method_combo = QComboBox()
        self._method_combo.addItems(["GET", "POST", "PUT", "DELETE", "PATCH"])
        self._method_combo.setMinimumWidth(140)
        type_and_method_layout.addWidget(self._method_combo)

        type_and_method_layout.addStretch()
        layout.addLayout(type_and_method_layout)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("请输入请求地址，例如 https://api.example.com/test")
        self._create_form_row("请求地址:", self._url_edit, layout)

        self._form_layout.addWidget(group)

    def _setup_auth_section(self) -> None:
        """创建认证区域"""
        group, layout = self._create_group_box("认证配置")

        auth_type_layout = QHBoxLayout()
        auth_type_layout.setSpacing(12)

        auth_type_label = QLabel("认证类型:")
        auth_type_label.setFixedWidth(100)
        auth_type_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        auth_type_layout.addWidget(auth_type_label)

        self._auth_type_combo = QComboBox()
        self._auth_type_combo.addItems(["None", "Bearer Token", "Basic Auth"])
        self._auth_type_combo.setMinimumWidth(160)
        self._auth_type_combo.currentIndexChanged.connect(
            self._on_auth_type_changed
        )
        auth_type_layout.addWidget(self._auth_type_combo)
        auth_type_layout.addStretch()
        layout.addLayout(auth_type_layout)

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("请输入 Bearer Token")
        self._token_row = self._create_form_row_with_container("Token:", self._token_edit, layout)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("请输入用户名")
        self._username_row = self._create_form_row_with_container("用户名:", self._username_edit, layout)

        self._password_edit = QLineEdit()
        self._password_edit.setPlaceholderText("请输入密码")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_row = self._create_form_row_with_container("密码:", self._password_edit, layout)

        self._form_layout.addWidget(group)

        # 初始化认证输入行的可见性（默认 None，全部隐藏）
        self._on_auth_type_changed(0)

    def _on_auth_type_changed(self, index: int) -> None:
        """认证类型切换时的处理

        Args:
            index: 当前选中的认证类型索引
        """
        is_bearer = index == 1
        is_basic = index == 2

        self._token_row.setVisible(is_bearer)
        self._username_row.setVisible(is_basic)
        self._password_row.setVisible(is_basic)

    def _setup_headers_section(self) -> None:
        """创建请求头区域"""
        group, layout = self._create_group_box("请求头")

        self._headers_section = KeyValueSection(
            "自定义请求头", key_placeholder="Header名", value_placeholder="Header值"
        )
        layout.addWidget(self._headers_section)

        self._form_layout.addWidget(group)

    def _setup_cookies_section(self) -> None:
        """创建 Cookie 区域"""
        group, layout = self._create_group_box("Cookie")

        self._cookies_section = KeyValueSection(
            "自定义 Cookie", key_placeholder="Cookie名", value_placeholder="Cookie值"
        )
        layout.addWidget(self._cookies_section)

        self._form_layout.addWidget(group)

    def _setup_body_section(self) -> None:
        """创建请求体区域"""
        group, layout = self._create_group_box("请求体")

        body_type_layout = QHBoxLayout()
        body_type_layout.setSpacing(12)

        body_type_label = QLabel("请求体类型:")
        body_type_label.setFixedWidth(100)
        body_type_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        body_type_layout.addWidget(body_type_label)

        self._body_type_combo = QComboBox()
        self._body_type_combo.addItems(["None", "JSON", "Form", "File Upload"])
        self._body_type_combo.setMinimumWidth(160)
        self._body_type_combo.currentIndexChanged.connect(
            self._on_body_type_changed
        )
        body_type_layout.addWidget(self._body_type_combo)
        body_type_layout.addStretch()
        layout.addLayout(body_type_layout)

        self._json_editor = QPlainTextEdit()
        self._json_editor.setPlaceholderText(
            '请输入 JSON 格式数据，例如:\n{\n  "key": "value"\n}'
        )
        self._json_editor.setMinimumHeight(180)
        self._json_editor.setVisible(False)
        self._json_highlighter = JsonSyntaxHighlighter(self._json_editor)
        layout.addWidget(self._json_editor)

        self._form_data_section = KeyValueSection(
            "表单数据", key_placeholder="字段名", value_placeholder="字段值"
        )
        self._form_data_section.setVisible(False)
        layout.addWidget(self._form_data_section)

        self._file_row = QWidget()
        file_layout = QHBoxLayout(self._file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(12)

        file_label = QLabel("文件路径:")
        file_label.setFixedWidth(100)
        file_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        file_layout.addWidget(file_label)

        self._file_path_edit = QLineEdit()
        self._file_path_edit.setPlaceholderText("请选择要上传的文件路径")
        file_layout.addWidget(self._file_path_edit, 1)

        self._file_browse_btn = QPushButton("浏览...")
        self._file_browse_btn.setProperty("secondary", True)
        self._file_browse_btn.setFixedWidth(80)
        self._file_browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self._file_browse_btn)

        self._file_row.setVisible(False)
        layout.addWidget(self._file_row)

        self._form_layout.addWidget(group)

    def _on_body_type_changed(self, index: int) -> None:
        """请求体类型切换时的处理

        Args:
            index: 当前选中的请求体类型索引
        """
        is_json = index == 1
        is_form = index == 2
        is_file = index == 3

        self._json_editor.setVisible(is_json)
        self._form_data_section.setVisible(is_form)
        self._file_row.setVisible(is_file)

    def _browse_file(self) -> None:
        """打开文件选择对话框，选择上传文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择文件",
            "",
            "所有文件 (*);;JSON 文件 (*.json);;CSV 文件 (*.csv);;文本文件 (*.txt)",
        )
        if file_path:
            self._file_path_edit.setText(file_path)

    def _setup_params_section(self) -> None:
        """创建参数化区域"""
        group, layout = self._create_group_box("参数化配置")

        self._params_section = KeyValueSection(
            "变量定义", key_placeholder="变量名", value_placeholder="默认值"
        )
        layout.addWidget(self._params_section)

        csv_layout = QHBoxLayout()
        csv_layout.setSpacing(12)

        csv_label = QLabel("CSV 导入:")
        csv_label.setFixedWidth(100)
        csv_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        csv_layout.addWidget(csv_label)

        self._csv_path_edit = QLineEdit()
        self._csv_path_edit.setPlaceholderText("选择 CSV 文件导入参数化数据")
        csv_layout.addWidget(self._csv_path_edit, 1)

        self._csv_browse_btn = QPushButton("浏览...")
        self._csv_browse_btn.setProperty("secondary", True)
        self._csv_browse_btn.setFixedWidth(80)
        self._csv_browse_btn.clicked.connect(self._browse_csv)
        csv_layout.addWidget(self._csv_browse_btn)

        self._csv_import_btn = QPushButton("导入")
        self._csv_import_btn.setProperty("secondary", True)
        self._csv_import_btn.setFixedWidth(80)
        self._csv_import_btn.clicked.connect(self._import_csv)
        csv_layout.addWidget(self._csv_import_btn)

        layout.addLayout(csv_layout)
        self._form_layout.addWidget(group)

    def _browse_csv(self) -> None:
        """打开文件选择对话框，选择 CSV 文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 CSV 文件",
            "",
            "CSV 文件 (*.csv);;所有文件 (*)",
        )
        if file_path:
            self._csv_path_edit.setText(file_path)

    def _import_csv(self) -> None:
        """导入 CSV 文件中的参数化数据"""
        csv_path = self._csv_path_edit.text().strip()
        if not csv_path:
            QMessageBox.warning(self, "提示", "请先选择 CSV 文件路径")
            return

        if not Path(csv_path).exists():
            QMessageBox.warning(self, "提示", f"CSV 文件不存在: {csv_path}")
            return

        try:
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            rows = self._task_service.import_csv_data(csv_path, max_rows=10000)
            QCoreApplication.restoreOverrideCursor()
            if rows:
                headers = list(rows[0].keys())
                self._params_section.clear_all()
                for header in headers:
                    self._params_section._add_row(header, "")
                QMessageBox.information(
                    self,
                    "导入成功",
                    f"已导入 CSV 文件，共 {len(rows)} 行数据，{len(headers)} 列",
                )
            else:
                QMessageBox.warning(self, "提示", "CSV 文件为空")
        except Exception as e:
            QCoreApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "导入失败", f"导入 CSV 数据失败:\n{e}")

    def _setup_stress_config_section(self) -> None:
        """创建压测配置区域"""
        group, layout = self._create_group_box("压测配置")

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        users_label = QLabel("并发用户数:")
        users_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(users_label, 0, 0)

        self._users_spin = QSpinBox()
        self._users_spin.setRange(1, 100000)
        self._users_spin.setValue(10)
        self._users_spin.setToolTip("同时模拟的并发用户数")
        grid.addWidget(self._users_spin, 0, 1)

        spawn_rate_label = QLabel("启动速率:")
        spawn_rate_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(spawn_rate_label, 0, 2)

        self._spawn_rate_spin = QDoubleSpinBox()
        self._spawn_rate_spin.setRange(0.1, 10000.0)
        self._spawn_rate_spin.setValue(1.0)
        self._spawn_rate_spin.setSingleStep(0.5)
        self._spawn_rate_spin.setDecimals(1)
        self._spawn_rate_spin.setSuffix(" 用户/秒")
        self._spawn_rate_spin.setToolTip("每秒启动的用户数")
        grid.addWidget(self._spawn_rate_spin, 0, 3)

        run_time_label = QLabel("持续时间:")
        run_time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(run_time_label, 1, 0)

        self._run_time_edit = QLineEdit()
        self._run_time_edit.setText("5m")
        self._run_time_edit.setPlaceholderText("例如: 10s / 5m / 1h")
        self._run_time_edit.setToolTip("压测持续时间，支持 s/m/h 后缀")
        grid.addWidget(self._run_time_edit, 1, 1)

        timeout_label = QLabel("超时时间:")
        timeout_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(timeout_label, 1, 2)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(1, 600)
        self._timeout_spin.setValue(30)
        self._timeout_spin.setSuffix(" 秒")
        self._timeout_spin.setToolTip("单次请求超时时间")
        grid.addWidget(self._timeout_spin, 1, 3)

        retry_label = QLabel("重试次数:")
        retry_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(retry_label, 2, 0)

        self._retry_spin = QSpinBox()
        self._retry_spin.setRange(0, 100)
        self._retry_spin.setValue(0)
        self._retry_spin.setToolTip("请求失败后的重试次数")
        grid.addWidget(self._retry_spin, 2, 1)

        layout.addLayout(grid)
        self._form_layout.addWidget(group)

    def _setup_action_buttons(self) -> None:
        """创建底部操作按钮区域"""
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        btn_layout.addStretch()

        self._reset_btn = QPushButton("重置表单")
        self._reset_btn.setProperty("secondary", True)
        self._reset_btn.setFixedHeight(40)
        self._reset_btn.setMinimumWidth(120)
        self._reset_btn.clicked.connect(self._reset_form)
        btn_layout.addWidget(self._reset_btn)

        self._save_btn = QPushButton("保存任务")
        self._save_btn.setFixedHeight(40)
        self._save_btn.setMinimumWidth(120)
        self._save_btn.clicked.connect(self._save_task)
        btn_layout.addWidget(self._save_btn)

        self._save_exec_btn = QPushButton("保存并执行")
        self._save_exec_btn.setFixedHeight(40)
        self._save_exec_btn.setMinimumWidth(120)
        self._save_exec_btn.clicked.connect(self._save_and_execute)
        btn_layout.addWidget(self._save_exec_btn)

        self._form_layout.addLayout(btn_layout)

    def _collect_form_data(self) -> dict:
        """收集表单所有区域的数据

        Returns:
            包含所有表单字段的字典
        """
        task_type = self._task_type_combo.currentText()
        method = self._method_combo.currentText()

        if task_type == "WebSocket":
            method = "WEBSOCKET"

        body_type = self._body_type_combo.currentText().lower()
        if body_type == "file upload":
            body_type = "file"

        body: dict | str = {}
        if self._body_type_combo.currentIndex() == 1:
            json_text = self._json_editor.toPlainText().strip()
            if json_text:
                try:
                    body = json.loads(json_text)
                except json.JSONDecodeError:
                    body = {}
        elif self._body_type_combo.currentIndex() == 2:
            body = self._form_data_section.to_dict()

        token = ""
        auth_index = self._auth_type_combo.currentIndex()
        if auth_index == 1:
            token = f"Bearer {self._token_edit.text().strip()}"
        elif auth_index == 2:
            username = self._username_edit.text().strip()
            password = self._password_edit.text().strip()
            import base64
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            token = f"Basic {credentials}"

        return {
            "name": self._task_name_edit.text().strip(),
            "type": task_type,
            "method": method,
            "url": self._url_edit.text().strip(),
            "headers": self._headers_section.to_dict(),
            "cookies": self._cookies_section.to_dict(),
            "token": token,
            "body": body,
            "body_type": body_type,
            "file_path": self._file_path_edit.text().strip(),
            "params": self._params_section.to_dict(),
            "csv_path": self._csv_path_edit.text().strip(),
            "users": self._users_spin.value(),
            "spawn_rate": self._spawn_rate_spin.value(),
            "run_time": self._run_time_edit.text().strip(),
            "timeout": self._timeout_spin.value(),
            "retry_count": self._retry_spin.value(),
        }

    def _validate_form(self) -> list[str]:
        """校验表单数据

        Returns:
            错误信息列表，空列表表示校验通过
        """
        errors: list[str] = []

        if not self._task_name_edit.text().strip():
            errors.append("任务名称不能为空")

        if not self._url_edit.text().strip() and self._task_type_combo.currentText() != "WebSocket":
            errors.append("请求地址不能为空")

        run_time = self._run_time_edit.text().strip()
        if run_time:
            import re
            if not re.match(r"^(\d+[smh])+$", run_time.lower()):
                errors.append("持续时间格式错误，应为如 10s/5m/1h/1h30m 的格式")

        if self._body_type_combo.currentIndex() == 1:
            json_text = self._json_editor.toPlainText().strip()
            if json_text:
                try:
                    json.loads(json_text)
                except json.JSONDecodeError as e:
                    errors.append(f"JSON 格式错误: {e}")

        csv_path = self._csv_path_edit.text().strip()
        if csv_path and not Path(csv_path).exists():
            errors.append(f"CSV 文件不存在: {csv_path}")

        file_path = self._file_path_edit.text().strip()
        if file_path and not Path(file_path).exists():
            errors.append(f"上传文件不存在: {file_path}")

        return errors

    def _save_task(self) -> int | None:
        """保存任务到数据库

        Returns:
            保存成功返回任务 ID，失败返回 None
        """
        errors = self._validate_form()
        if errors:
            QMessageBox.warning(
                self, "表单校验失败", "\n".join(f"• {e}" for e in errors)
            )
            return None

        task_data = self._collect_form_data()

        try:
            if self._editing_task_id is not None:
                self._task_service.update_task(
                    self._editing_task_id, task_data
                )
                task_id = self._editing_task_id
                self._title_label.setText(f"编辑任务 - {task_data.get('name', self._task_name_edit.text())}")
                QMessageBox.information(self, "成功", f"任务已更新，ID: {task_id}")
            else:
                task = self._task_service.create_task(task_data)
                task_id = task.get("id")
                QMessageBox.information(self, "成功", f"任务已创建，ID: {task_id}")

            self.task_saved.emit(task_id)
            return task_id

        except ValueError as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return None
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存任务时发生错误:\n{e}")
            return None

    def _save_and_execute(self) -> None:
        """保存任务并立即执行"""
        task_id = self._save_task()
        if task_id is not None:
            try:
                self._execution_service.start_task(task_id)
                self.task_executed.emit(task_id)
                QMessageBox.information(
                    self, "执行中", f"任务 {task_id} 已开始执行"
                )
            except ValueError as e:
                QMessageBox.warning(self, "启动失败", str(e))
            except Exception as e:
                QMessageBox.critical(
                    self, "启动失败", f"启动任务时发生错误:\n{e}"
                )

    def _reset_form(self) -> None:
        """重置表单为初始状态（阻断信号避免触发不必要的UI更新）"""
        self._editing_task_id = None

        self._task_name_edit.clear()
        self._task_type_combo.setCurrentIndex(0)
        self._method_combo.setCurrentIndex(0)
        self._url_edit.clear()

        # 阻断信号避免重置过程中触发UI更新
        self._auth_type_combo.blockSignals(True)
        self._body_type_combo.blockSignals(True)

        self._auth_type_combo.setCurrentIndex(0)
        self._token_edit.clear()
        self._username_edit.clear()
        self._password_edit.clear()

        self._headers_section.clear_all()
        self._cookies_section.clear_all()

        self._body_type_combo.setCurrentIndex(0)
        self._json_editor.clear()
        self._form_data_section.clear_all()
        self._file_path_edit.clear()

        self._params_section.clear_all()
        self._csv_path_edit.clear()

        self._users_spin.setValue(10)
        self._spawn_rate_spin.setValue(1.0)
        self._run_time_edit.setText("5m")
        self._timeout_spin.setValue(30)
        self._retry_spin.setValue(0)

        self._title_label.setText("创建任务")

        # 恢复信号
        self._auth_type_combo.blockSignals(False)
        self._body_type_combo.blockSignals(False)

    def load_task(self, task_id: int) -> None:
        """加载已有任务数据到表单，用于编辑

        Args:
            task_id: 要编辑的任务 ID
        """
        # 先重置表单状态，清除上一次的编辑数据
        self._reset_form()

        task = self._task_service.get_task(task_id)
        if task is None:
            QMessageBox.warning(self, "提示", f"任务不存在，ID: {task_id}")
            return

        self._editing_task_id = task_id
        self._title_label.setText(f"编辑任务 - {task.get('name', '')}")

        self._task_name_edit.setText(task.get("name", ""))

        task_type = task.get("type", "HTTP")
        type_index = self._task_type_combo.findText(task_type)
        if type_index >= 0:
            self._task_type_combo.setCurrentIndex(type_index)

        method = task.get("method", "GET")
        method_index = self._method_combo.findText(method)
        if method_index >= 0:
            self._method_combo.setCurrentIndex(method_index)
        else:
            self._method_combo.setCurrentIndex(0)

        self._url_edit.setText(task.get("url", ""))

        # 阻断信号避免UI闪烁，加载完成后再恢复并手动触发更新
        self._auth_type_combo.blockSignals(True)
        self._body_type_combo.blockSignals(True)

        token = task.get("token", "")
        if token.startswith("Bearer "):
            self._auth_type_combo.setCurrentIndex(1)
            self._token_edit.setText(token[7:])
        elif token.startswith("Basic "):
            self._auth_type_combo.setCurrentIndex(2)
            try:
                import base64
                decoded = base64.b64decode(token[6:]).decode()
                if ":" in decoded:
                    username, password = decoded.split(":", 1)
                    self._username_edit.setText(username)
                    self._password_edit.setText(password)
            except Exception:
                pass
        else:
            self._auth_type_combo.setCurrentIndex(0)

        headers = task.get("headers", {})
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except json.JSONDecodeError:
                headers = {}
        self._headers_section.load_dict(headers if isinstance(headers, dict) else {})

        cookies = task.get("cookies", {})
        if isinstance(cookies, str):
            try:
                cookies = json.loads(cookies)
            except json.JSONDecodeError:
                cookies = {}
        self._cookies_section.load_dict(cookies if isinstance(cookies, dict) else {})

        body_type = task.get("body_type", "json").lower()
        body_type_map = {"none": 0, "json": 1, "form": 2, "file": 3}
        self._body_type_combo.setCurrentIndex(body_type_map.get(body_type, 0))

        # 恢复信号并手动触发一次UI更新
        self._auth_type_combo.blockSignals(False)
        self._body_type_combo.blockSignals(False)
        self._on_auth_type_changed(self._auth_type_combo.currentIndex())
        self._on_body_type_changed(self._body_type_combo.currentIndex())

        body = task.get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        if isinstance(body, dict):
            self._json_editor.setPlainText(
                json.dumps(body, ensure_ascii=False, indent=2)
            )
            self._form_data_section.load_dict(body)

        self._file_path_edit.setText(task.get("file_path", ""))

        params = task.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        self._params_section.load_dict(params if isinstance(params, dict) else {})

        self._csv_path_edit.setText(task.get("csv_path", ""))

        self._users_spin.setValue(task.get("users", 10))
        self._spawn_rate_spin.setValue(task.get("spawn_rate", 1))
        self._run_time_edit.setText(task.get("run_time", "5m"))
        self._timeout_spin.setValue(task.get("timeout", 30))
        self._retry_spin.setValue(task.get("retry_count", 0))

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
        else:
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #1a1a2e;"
            )
