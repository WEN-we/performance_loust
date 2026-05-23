"""
系统设置页面模块

提供应用程序的全局配置管理，包括并发用户数、超时时间、主题、
路径配置、Locust默认参数等，支持保存、恢复默认、暗黑模式。
"""

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config.settings import get_settings
from database.db_manager import DatabaseManager
from utils.helpers import ensure_dir


class SettingsPage(QWidget):
    """系统设置页面

    管理应用程序的所有全局配置项，支持保存到配置文件、恢复默认值、
    打开目录、清理数据库等操作。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = "light"
        self._settings = get_settings()
        self._db = DatabaseManager()

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """构建系统设置页面整体布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(20)

        header_layout = QHBoxLayout()
        self._title_label = QLabel("系统设置")
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1a1a2e;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        main_layout.addWidget(self._create_performance_group())
        main_layout.addWidget(self._create_appearance_group())
        main_layout.addWidget(self._create_path_group())
        main_layout.addWidget(self._create_locust_group())
        main_layout.addStretch()
        main_layout.addWidget(self._create_action_buttons())

    def _create_performance_group(self) -> QGroupBox:
        """创建性能参数设置分组"""
        group = QGroupBox("性能参数")
        layout = QGridLayout(group)
        layout.setSpacing(12)
        layout.setColumnMinimumWidth(0, 140)
        layout.setColumnMinimumWidth(2, 40)

        label_users = QLabel("默认并发用户数:")
        layout.addWidget(label_users, 0, 0)

        self._spin_users = QSpinBox()
        self._spin_users.setRange(1, 10000)
        self._spin_users.setSingleStep(10)
        self._spin_users.setToolTip("Locust默认并发用户数")
        layout.addWidget(self._spin_users, 0, 1)

        label_timeout = QLabel("默认超时时间(秒):")
        layout.addWidget(label_timeout, 1, 0)

        self._spin_timeout = QSpinBox()
        self._spin_timeout.setRange(1, 3600)
        self._spin_timeout.setSingleStep(5)
        self._spin_timeout.setToolTip("请求默认超时时间，单位秒")
        layout.addWidget(self._spin_timeout, 1, 1)

        return group

    def _create_appearance_group(self) -> QGroupBox:
        """创建外观设置分组"""
        group = QGroupBox("外观设置")
        layout = QGridLayout(group)
        layout.setSpacing(12)
        layout.setColumnMinimumWidth(0, 140)

        label_theme = QLabel("默认主题:")
        layout.addWidget(label_theme, 0, 0)

        self._combo_theme = QComboBox()
        self._combo_theme.addItem("亮色", "light")
        self._combo_theme.addItem("暗色", "dark")
        self._combo_theme.setToolTip("选择应用程序默认主题")
        layout.addWidget(self._combo_theme, 0, 1)

        return group

    def _create_path_group(self) -> QGroupBox:
        """创建路径设置分组"""
        group = QGroupBox("路径设置")
        layout = QGridLayout(group)
        layout.setSpacing(12)
        layout.setColumnMinimumWidth(0, 140)

        label_log_dir = QLabel("日志路径:")
        layout.addWidget(label_log_dir, 0, 0)

        self._edit_log_dir = QLineEdit()
        self._edit_log_dir.setPlaceholderText("日志文件存储目录")
        layout.addWidget(self._edit_log_dir, 0, 1)

        self._btn_browse_log = QPushButton("浏览")
        self._btn_browse_log.setProperty("secondary", True)
        self._btn_browse_log.setFixedWidth(80)
        self._btn_browse_log.clicked.connect(self._on_browse_log_dir)
        layout.addWidget(self._btn_browse_log, 0, 2)

        label_export_dir = QLabel("导出目录:")
        layout.addWidget(label_export_dir, 1, 0)

        self._edit_export_dir = QLineEdit()
        self._edit_export_dir.setPlaceholderText("报告导出存储目录")
        layout.addWidget(self._edit_export_dir, 1, 1)

        self._btn_browse_export = QPushButton("浏览")
        self._btn_browse_export.setProperty("secondary", True)
        self._btn_browse_export.setFixedWidth(80)
        self._btn_browse_export.clicked.connect(self._on_browse_export_dir)
        layout.addWidget(self._btn_browse_export, 1, 2)

        label_db_path = QLabel("数据库路径:")
        layout.addWidget(label_db_path, 2, 0)

        self._edit_db_path = QLineEdit()
        self._edit_db_path.setPlaceholderText("SQLite数据库文件路径")
        layout.addWidget(self._edit_db_path, 2, 1)

        self._btn_browse_db = QPushButton("浏览")
        self._btn_browse_db.setProperty("secondary", True)
        self._btn_browse_db.setFixedWidth(80)
        self._btn_browse_db.clicked.connect(self._on_browse_db_path)
        layout.addWidget(self._btn_browse_db, 2, 2)

        return group

    def _create_locust_group(self) -> QGroupBox:
        """创建Locust默认参数设置分组"""
        group = QGroupBox("Locust 默认参数")
        layout = QGridLayout(group)
        layout.setSpacing(12)
        layout.setColumnMinimumWidth(0, 140)
        layout.setColumnMinimumWidth(2, 40)

        label_host = QLabel("默认Host:")
        layout.addWidget(label_host, 0, 0)

        self._edit_locust_host = QLineEdit()
        self._edit_locust_host.setPlaceholderText("http://localhost:8089")
        self._edit_locust_host.setToolTip("Locust Web界面的默认Host地址")
        layout.addWidget(self._edit_locust_host, 0, 1)

        label_port = QLabel("默认端口:")
        layout.addWidget(label_port, 1, 0)

        self._spin_locust_port = QSpinBox()
        self._spin_locust_port.setRange(1, 65535)
        self._spin_locust_port.setValue(8089)
        self._spin_locust_port.setToolTip("Locust Web界面的默认端口")
        layout.addWidget(self._spin_locust_port, 1, 1)

        return group

    def _create_action_buttons(self) -> QWidget:
        """创建操作按钮区域"""
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(12)

        self._btn_save = QPushButton("保存设置")
        self._btn_save.setFixedHeight(40)
        self._btn_save.setMinimumWidth(120)
        self._btn_save.clicked.connect(self._on_save)
        action_layout.addWidget(self._btn_save)

        self._btn_reset = QPushButton("恢复默认")
        self._btn_reset.setProperty("secondary", True)
        self._btn_reset.setFixedHeight(40)
        self._btn_reset.setMinimumWidth(120)
        self._btn_reset.clicked.connect(self._on_reset)
        action_layout.addWidget(self._btn_reset)

        self._btn_open_log_dir = QPushButton("打开日志目录")
        self._btn_open_log_dir.setProperty("secondary", True)
        self._btn_open_log_dir.setFixedHeight(40)
        self._btn_open_log_dir.setMinimumWidth(120)
        self._btn_open_log_dir.clicked.connect(self._on_open_log_dir)
        action_layout.addWidget(self._btn_open_log_dir)

        self._btn_open_export_dir = QPushButton("打开导出目录")
        self._btn_open_export_dir.setProperty("secondary", True)
        self._btn_open_export_dir.setFixedHeight(40)
        self._btn_open_export_dir.setMinimumWidth(120)
        self._btn_open_export_dir.clicked.connect(self._on_open_export_dir)
        action_layout.addWidget(self._btn_open_export_dir)

        self._btn_cleanup_db = QPushButton("清理数据库")
        self._btn_cleanup_db.setProperty("danger", True)
        self._btn_cleanup_db.setFixedHeight(40)
        self._btn_cleanup_db.setMinimumWidth(120)
        self._btn_cleanup_db.clicked.connect(self._on_cleanup_db)
        action_layout.addWidget(self._btn_cleanup_db)

        action_layout.addStretch()

        return action_widget

    # ==================== 加载/保存设置 ====================

    def _load_settings(self) -> None:
        """从Settings实例读取当前配置并填充到控件"""
        self._spin_users.setValue(self._settings.locust_users)
        self._spin_timeout.setValue(self._settings.timeout)

        theme = self._settings.theme
        idx = self._combo_theme.findData(theme)
        if idx >= 0:
            self._combo_theme.setCurrentIndex(idx)

        self._edit_log_dir.setText(str(self._settings.log_dir))
        self._edit_export_dir.setText(str(self._settings.export_dir))
        self._edit_db_path.setText(str(self._settings.database_path))
        self._edit_locust_host.setText(self._settings.locust_host)

        host = self._settings.locust_host
        try:
            if ":" in host.split("//")[-1]:
                port_str = host.split("//")[-1].split(":")[-1].split("/")[0]
                self._spin_locust_port.setValue(int(port_str))
            else:
                self._spin_locust_port.setValue(8089)
        except (ValueError, IndexError):
            self._spin_locust_port.setValue(8089)

    def _on_save(self) -> None:
        """保存当前设置到配置文件"""
        self._settings.locust_users = self._spin_users.value()
        self._settings.timeout = self._spin_timeout.value()

        theme_data = self._combo_theme.currentData()
        if theme_data:
            self._settings.theme = theme_data

        self._settings.set("log_dir", self._edit_log_dir.text().strip())
        self._settings.set("export_dir", self._edit_export_dir.text().strip())
        self._settings.set("database_path", self._edit_db_path.text().strip())

        host_text = self._edit_locust_host.text().strip()
        port = self._spin_locust_port.value()
        if host_text:
            base = host_text.split("//")[0] + "//" if "//" in host_text else ""
            addr = host_text.split("//")[-1] if "//" in host_text else host_text
            addr_no_port = addr.split(":")[0]
            self._settings.locust_host = f"{base}{addr_no_port}:{port}"
        else:
            self._settings.locust_host = f"http://localhost:{port}"

        ensure_dir(self._settings.log_dir)
        ensure_dir(self._settings.export_dir)

        self._settings.save()
        QMessageBox.information(self, "保存成功", "设置已保存")

    def _on_reset(self) -> None:
        """恢复所有设置项为默认值"""
        reply = QMessageBox.question(
            self,
            "确认恢复",
            "确定要恢复所有设置为默认值吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._settings.reset_to_default()
        self._settings.save()
        self._load_settings()
        QMessageBox.information(self, "恢复成功", "已恢复为默认设置")

    # ==================== 浏览路径 ====================

    def _on_browse_log_dir(self) -> None:
        """浏览选择日志目录"""
        current = self._edit_log_dir.text().strip() or str(self._settings.log_dir)
        directory = QFileDialog.getExistingDirectory(
            self, "选择日志目录", current
        )
        if directory:
            self._edit_log_dir.setText(directory)

    def _on_browse_export_dir(self) -> None:
        """浏览选择导出目录"""
        current = self._edit_export_dir.text().strip() or str(self._settings.export_dir)
        directory = QFileDialog.getExistingDirectory(
            self, "选择导出目录", current
        )
        if directory:
            self._edit_export_dir.setText(directory)

    def _on_browse_db_path(self) -> None:
        """浏览选择数据库文件路径"""
        current = self._edit_db_path.text().strip() or str(self._settings.database_path)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "选择数据库文件", current, "SQLite数据库 (*.db);;所有文件 (*)"
        )
        if file_path:
            self._edit_db_path.setText(file_path)

    # ==================== 打开目录 ====================

    def _on_open_log_dir(self) -> None:
        """打开日志目录"""
        log_dir = self._edit_log_dir.text().strip() or str(self._settings.log_dir)
        self._open_directory(log_dir, "日志目录")

    def _on_open_export_dir(self) -> None:
        """打开导出目录"""
        export_dir = self._edit_export_dir.text().strip() or str(self._settings.export_dir)
        self._open_directory(export_dir, "导出目录")

    def _open_directory(self, path_str: str, name: str) -> None:
        """使用系统文件管理器打开指定目录

        Args:
            path_str: 目录路径字符串
            name: 目录名称（用于提示消息）
        """
        target = Path(path_str)
        if not target.exists():
            ensure_dir(target)

        try:
            if sys.platform == "win32":
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except OSError as e:
            QMessageBox.warning(
                self, "打开失败", f"无法打开{name}:\n{e}"
            )

    # ==================== 清理数据库 ====================

    def _on_cleanup_db(self) -> None:
        """清理数据库，压缩空间"""
        reply = QMessageBox.question(
            self,
            "确认清理",
            "将清理30天前的历史记录并压缩数据库，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted = self._db.cleanup_old_history(days=30)
            self._db.vacuum_database()
            QMessageBox.information(
                self, "清理完成", f"已清理 {deleted} 条过期历史记录，数据库已压缩"
            )
        except Exception as e:
            QMessageBox.critical(self, "清理失败", f"数据库清理失败:\n{e}")

    # ==================== 暗黑模式 ====================

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
