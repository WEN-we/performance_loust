from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QButtonGroup,
    QSizePolicy,
    QFrame,
)


_NAV_ITEMS = [
    {"id": 0, "text": "首页", "icon": "home"},
    {"id": 1, "text": "创建任务", "icon": "create"},
    {"id": 2, "text": "执行任务", "icon": "play"},
    {"id": 3, "text": "实时监控", "icon": "monitor"},
    {"id": 4, "text": "历史记录", "icon": "history"},
    {"id": 5, "text": "系统设置", "icon": "settings"},
]

_ICON_COLORS = {
    "light": "#5a5a7a",
    "dark": "#a0a0c0",
}

_ICON_SELECTED_COLORS = {
    "light": "#4a90d9",
    "dark": "#5b9bd5",
}


def _create_icon(icon_type: str, color: str, size: int = 20) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))

    if icon_type == "home":
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        cx, cy = size / 2, size / 2
        roof = QPolygonF([
            QPointF(cx, cy - 7),
            QPointF(cx + 8, cy - 1),
            QPointF(cx + 6, cy - 1),
            QPointF(cx + 6, cy + 7),
            QPointF(cx + 2, cy + 7),
            QPointF(cx + 2, cy + 2),
            QPointF(cx - 2, cy + 2),
            QPointF(cx - 2, cy + 7),
            QPointF(cx - 6, cy + 7),
            QPointF(cx - 6, cy - 1),
            QPointF(cx - 8, cy - 1),
        ])
        painter.drawPolygon(roof)

    elif icon_type == "create":
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        cx, cy = size / 2, size / 2
        painter.drawRect(int(cx - 7), int(cy - 7), 14, 14)
        painter.setPen(QColor(color))
        painter.drawLine(int(cx - 3), int(cy), int(cx + 3), int(cy))
        painter.drawLine(int(cx), int(cy - 3), int(cx), int(cy + 3))

    elif icon_type == "play":
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        cx, cy = size / 2, size / 2
        triangle = QPolygonF([
            QPointF(cx - 4, cy - 7),
            QPointF(cx + 7, cy),
            QPointF(cx - 4, cy + 7),
        ])
        painter.drawPolygon(triangle)

    elif icon_type == "monitor":
        cx, cy = size / 2, size / 2
        painter.drawRect(int(cx - 8), int(cy - 6), 16, 10)
        painter.drawRect(int(cx - 1), int(cy + 4), 2, 3)
        painter.drawRect(int(cx - 4), int(cy + 6), 8, 1)

    elif icon_type == "history":
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        cx, cy = size / 2, size / 2
        painter.drawEllipse(int(cx - 8), int(cy - 8), 16, 16)
        painter.setPen(QColor(color))
        painter.drawLine(int(cx), int(cy - 5), int(cx), int(cy))
        painter.drawLine(int(cx), int(cy), int(cx + 4), int(cy + 2))
        arrow = QPolygonF([
            QPointF(cx - 7, cy - 5),
            QPointF(cx - 3, cy - 5),
            QPointF(cx - 5, cy - 8),
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(arrow)

    elif icon_type == "settings":
        cx, cy = size / 2, size / 2
        painter.drawEllipse(int(cx - 4), int(cy - 4), 8, 8)
        painter.drawRect(int(cx - 1), int(cy - 9), 2, 4)
        painter.drawRect(int(cx - 1), int(cy + 5), 2, 4)
        painter.drawRect(int(cx - 9), int(cy - 1), 4, 2)
        painter.drawRect(int(cx + 5), int(cy - 1), 4, 2)

    painter.end()
    return QIcon(pixmap)


class NavButton(QPushButton):
    def __init__(self, item_id: int, text: str, icon_type: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item_id = item_id
        self._icon_type = icon_type
        self._selected = False
        self._theme = "light"

        self.setObjectName("NavButton")
        self.setText(text)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self._update_icon()
        self._update_style()

    @property
    def item_id(self) -> int:
        return self._item_id

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", selected)
        self._update_icon()
        self._update_style()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self._update_icon()
        self._update_style()

    def _update_icon(self) -> None:
        if self._selected:
            color = _ICON_SELECTED_COLORS.get(self._theme, "#4a90d9")
        else:
            color = _ICON_COLORS.get(self._theme, "#5a5a7a")
        icon = _create_icon(self._icon_type, color, 20)
        self.setIcon(icon)
        self.setIconSize(QPixmap(20, 20).size())

    def _update_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)


class NavigationBar(QWidget):
    navigation_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavigationBar")
        self._current_index = 0
        self._theme = "light"
        self._buttons: list[NavButton] = []
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        self.setFixedWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 12, 8, 12)
        main_layout.setSpacing(4)

        logo_layout = QHBoxLayout()
        logo_layout.setContentsMargins(8, 0, 8, 12)

        self._logo_label = QLabel("🦗")
        self._logo_label.setFixedSize(32, 32)
        self._logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_label.setStyleSheet("font-size: 24px;")

        self._title_label = QLabel("Locust")
        self._title_label.setObjectName("navTitle")
        self._title_label.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #4a90d9;"
        )

        logo_layout.addWidget(self._logo_label)
        logo_layout.addWidget(self._title_label)
        logo_layout.addStretch()

        main_layout.addLayout(logo_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFixedHeight(1)
        main_layout.addWidget(separator)

        for item in _NAV_ITEMS:
            btn = NavButton(item["id"], item["text"], item["icon"], self)
            self._buttons.append(btn)
            self._button_group.addButton(btn, item["id"])
            main_layout.addWidget(btn)

        if self._buttons:
            self._buttons[0].set_selected(True)

        main_layout.addStretch()

        self._version_label = QLabel("v1.0.0")
        self._version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._version_label.setStyleSheet("color: #b0b0c0; font-size: 11px;")
        main_layout.addWidget(self._version_label)

    def _connect_signals(self) -> None:
        self._button_group.idClicked.connect(self._on_button_clicked)

    def _on_button_clicked(self, button_id: int) -> None:
        for btn in self._buttons:
            btn.set_selected(btn.item_id == button_id)
        self._current_index = button_id
        self.navigation_changed.emit(button_id)

    @property
    def current_index(self) -> int:
        return self._current_index

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self._buttons) and self._current_index != index:
            self._buttons[index].click()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        for btn in self._buttons:
            btn.set_theme(theme)

        if theme == "dark":
            self._title_label.setStyleSheet(
                "font-size: 16px; font-weight: 700; color: #5b9bd5;"
            )
            self._version_label.setStyleSheet("color: #5a5a7a; font-size: 11px;")
        else:
            self._title_label.setStyleSheet(
                "font-size: 16px; font-weight: 700; color: #4a90d9;"
            )
            self._version_label.setStyleSheet("color: #b0b0c0; font-size: 11px;")

    def set_logo(self, icon: QIcon) -> None:
        self._logo_label.setPixmap(icon.pixmap(32, 32))
