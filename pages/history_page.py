"""
历史记录页面模块

提供历史记录的查看、搜索、删除、导出等功能，
支持按日期范围和任务名称筛选，分页显示，暗黑模式。
"""

import json
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QDateEdit

from database.db_manager import DatabaseManager
from services.report_service import ReportService
from utils.helpers import format_duration
from config.settings import get_settings


class HistoryPage(QWidget):
    """历史记录页面

    展示性能测试的历史执行记录，支持查询、删除、导出等操作。
    """

    PAGE_SIZE = 20

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = "light"
        self._db = DatabaseManager()
        self._report_service = ReportService(self._db)
        self._current_page = 1
        self._total_count = 0

        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        """构建历史记录页面整体布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(16)

        main_layout.addWidget(self._create_header())
        main_layout.addWidget(self._create_filter_bar())
        main_layout.addWidget(self._create_table(), 1)
        main_layout.addWidget(self._create_pagination())
        main_layout.addWidget(self._create_action_buttons())

    def _create_header(self) -> QWidget:
        """创建页面标题区域"""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel("历史记录")
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1a1a2e;"
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._count_label = QLabel("共 0 条记录")
        self._count_label.setStyleSheet("font-size: 13px; color: #5a5a7a;")
        header_layout.addWidget(self._count_label)

        return header_widget

    def _create_filter_bar(self) -> QWidget:
        """创建查询筛选栏"""
        filter_widget = QWidget()
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(12)

        start_label = QLabel("起始日期:")
        filter_layout.addWidget(start_label)

        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        self._start_date.setDate(datetime.now().replace(day=1))
        filter_layout.addWidget(self._start_date)

        end_label = QLabel("结束日期:")
        filter_layout.addWidget(end_label)

        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date.setDate(datetime.now())
        filter_layout.addWidget(self._end_date)

        name_label = QLabel("任务名称:")
        filter_layout.addWidget(name_label)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入任务名称搜索...")
        self._search_input.setFixedWidth(200)
        filter_layout.addWidget(self._search_input)

        btn_search = QPushButton("查询")
        btn_search.setFixedWidth(80)
        btn_search.clicked.connect(self._on_search)
        filter_layout.addWidget(btn_search)

        btn_reset = QPushButton("重置")
        btn_reset.setProperty("secondary", True)
        btn_reset.setFixedWidth(80)
        btn_reset.clicked.connect(self._on_reset_filter)
        filter_layout.addWidget(btn_reset)

        filter_layout.addStretch()

        return filter_widget

    def _create_table(self) -> QTableWidget:
        """创建历史记录表格"""
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            [
                "任务名称",
                "执行时间",
                "持续时间",
                "总请求数",
                "成功/失败数",
                "平均响应时间",
                "失败率",
                "结果摘要",
            ]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)

        column_widths = [160, 160, 100, 100, 120, 120, 80, 200]
        for i, width in enumerate(column_widths):
            self._table.setColumnWidth(i, width)

        return self._table

    def _create_pagination(self) -> QWidget:
        """创建分页控件区域"""
        pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(pagination_widget)
        pagination_layout.setContentsMargins(0, 0, 0, 0)

        pagination_layout.addStretch()

        self._btn_prev_page = QPushButton("上一页")
        self._btn_prev_page.setProperty("secondary", True)
        self._btn_prev_page.setFixedWidth(80)
        self._btn_prev_page.clicked.connect(self._on_prev_page)
        pagination_layout.addWidget(self._btn_prev_page)

        self._page_label = QLabel("第 1 页 / 共 1 页")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedWidth(150)
        pagination_layout.addWidget(self._page_label)

        self._btn_next_page = QPushButton("下一页")
        self._btn_next_page.setProperty("secondary", True)
        self._btn_next_page.setFixedWidth(80)
        self._btn_next_page.clicked.connect(self._on_next_page)
        pagination_layout.addWidget(self._btn_next_page)

        page_size_label = QLabel("每页条数:")
        pagination_layout.addWidget(page_size_label)

        self._page_size_spin = QSpinBox()
        self._page_size_spin.setRange(5, 100)
        self._page_size_spin.setValue(self.PAGE_SIZE)
        self._page_size_spin.setSingleStep(5)
        self._page_size_spin.setFixedWidth(80)
        self._page_size_spin.valueChanged.connect(self._on_page_size_changed)
        pagination_layout.addWidget(self._page_size_spin)

        pagination_layout.addStretch()

        return pagination_widget

    def _create_action_buttons(self) -> QWidget:
        """创建操作按钮区域"""
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(12)

        self._btn_delete_selected = QPushButton("删除选中记录")
        self._btn_delete_selected.setProperty("danger", True)
        self._btn_delete_selected.setFixedHeight(36)
        self._btn_delete_selected.clicked.connect(self._on_delete_selected)
        action_layout.addWidget(self._btn_delete_selected)

        self._btn_clear_all = QPushButton("清空所有记录")
        self._btn_clear_all.setProperty("danger", True)
        self._btn_clear_all.setFixedHeight(36)
        self._btn_clear_all.clicked.connect(self._on_clear_all)
        action_layout.addWidget(self._btn_clear_all)

        action_layout.addStretch()

        self._btn_export_excel = QPushButton("导出Excel")
        self._btn_export_excel.setFixedHeight(36)
        self._btn_export_excel.clicked.connect(self._on_export_excel)
        action_layout.addWidget(self._btn_export_excel)

        self._btn_export_html = QPushButton("导出HTML报告")
        self._btn_export_html.setProperty("secondary", True)
        self._btn_export_html.setFixedHeight(36)
        self._btn_export_html.clicked.connect(self._on_export_html)
        action_layout.addWidget(self._btn_export_html)

        self._btn_export_pdf = QPushButton("导出PDF报告")
        self._btn_export_pdf.setProperty("secondary", True)
        self._btn_export_pdf.setFixedHeight(36)
        self._btn_export_pdf.clicked.connect(self._on_export_pdf)
        action_layout.addWidget(self._btn_export_pdf)

        self._btn_view_detail = QPushButton("查看详情")
        self._btn_view_detail.setProperty("secondary", True)
        self._btn_view_detail.setFixedHeight(36)
        self._btn_view_detail.clicked.connect(self._on_view_detail)
        action_layout.addWidget(self._btn_view_detail)

        return action_widget

    def _load_data(self) -> None:
        """从数据库加载历史记录并刷新表格"""
        start_time = self._start_date.date().toString("yyyy-MM-dd") + " 00:00:00"
        end_time = self._end_date.date().toString("yyyy-MM-dd") + " 23:59:59"
        keyword = self._search_input.text().strip()

        all_records = self._db.get_history_by_time_range(start_time, end_time)

        if keyword:
            all_records = [
                r for r in all_records if keyword in r.get("task_name", "")
            ]

        self._total_count = len(all_records)
        self._filtered_records = all_records

        total_pages = max(1, (self._total_count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self._current_page > total_pages:
            self._current_page = total_pages

        offset = (self._current_page - 1) * self.PAGE_SIZE
        page_records = all_records[offset: offset + self.PAGE_SIZE]

        self._refresh_table(page_records)
        self._refresh_pagination()

    def _refresh_table(self, records: list[dict]) -> None:
        """刷新表格数据"""
        self._table.setRowCount(len(records))

        for row, record in enumerate(records):
            task_name_item = QTableWidgetItem(record.get("task_name", ""))
            self._table.setItem(row, 0, task_name_item)

            execute_time_item = QTableWidgetItem(record.get("execute_time", ""))
            execute_time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, execute_time_item)

            duration_val = record.get("duration", 0.0)
            duration_item = QTableWidgetItem(format_duration(duration_val))
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, duration_item)

            stats = self._extract_stats(record)
            total_requests = stats.get("total_requests", 0)
            success_count = stats.get("success_count", 0)
            fail_count = stats.get("fail_count", 0)
            avg_response = stats.get("avg_response_time", 0.0)
            fail_rate = stats.get("fail_rate", 0.0)

            total_req_item = QTableWidgetItem(str(total_requests))
            total_req_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, total_req_item)

            success_fail_item = QTableWidgetItem(f"{success_count}/{fail_count}")
            success_fail_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 4, success_fail_item)

            avg_rt_item = QTableWidgetItem(f"{avg_response:.2f} ms")
            avg_rt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 5, avg_rt_item)

            fail_rate_item = QTableWidgetItem(f"{fail_rate:.2%}")
            fail_rate_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if fail_rate > 0.05:
                fail_rate_item.setForeground(
                    Qt.GlobalColor.red if self._theme == "light" else Qt.GlobalColor.red
                )
            self._table.setItem(row, 6, fail_rate_item)

            summary = record.get("result_summary", "")
            if len(summary) > 50:
                summary = summary[:50] + "..."
            summary_item = QTableWidgetItem(summary)
            self._table.setItem(row, 7, summary_item)

            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item and col != 6:
                    if self._theme == "dark":
                        item.setForeground(Qt.GlobalColor.white)
                    else:
                        item.setForeground(Qt.GlobalColor.black)

        self._count_label.setText(f"共 {self._total_count} 条记录")

    def _extract_stats(self, record: dict) -> dict:
        """从历史记录中提取统计数据

        优先从 stats_json 解析，若无则尝试通过 task_id 查询 task_results。

        Args:
            record: 历史记录字典

        Returns:
            统计数据字典
        """
        stats_json = record.get("stats_json", {})
        if isinstance(stats_json, str):
            try:
                stats_json = json.loads(stats_json)
            except (json.JSONDecodeError, TypeError):
                stats_json = {}

        result = {
            "total_requests": stats_json.get("total_requests", 0),
            "success_count": stats_json.get("success_count", 0),
            "fail_count": stats_json.get("fail_count", 0),
            "avg_response_time": stats_json.get("avg_response_time", 0.0),
            "fail_rate": stats_json.get("fail_rate", 0.0),
        }

        has_data = any(v != 0 for v in result.values())
        if not has_data:
            task_id = record.get("task_id", 0)
            if task_id:
                latest = self._db.get_latest_result_by_task(task_id)
                if latest:
                    result["total_requests"] = latest.get("total_requests", 0)
                    result["success_count"] = latest.get("success_count", 0)
                    result["fail_count"] = latest.get("fail_count", 0)
                    result["avg_response_time"] = latest.get("avg_response_time", 0.0)
                    result["fail_rate"] = latest.get("fail_rate", 0.0)

        return result

    def _refresh_pagination(self) -> None:
        """刷新分页控件状态"""
        total_pages = max(1, (self._total_count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._page_label.setText(f"第 {self._current_page} 页 / 共 {total_pages} 页")
        self._btn_prev_page.setEnabled(self._current_page > 1)
        self._btn_next_page.setEnabled(self._current_page < total_pages)

    def _get_selected_record(self) -> dict | None:
        """获取当前选中的历史记录，未选中则提示用户"""
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选择一条历史记录")
            return None

        row = selected_rows[0].row()
        offset = (self._current_page - 1) * self.PAGE_SIZE
        if offset + row < len(self._filtered_records):
            return self._filtered_records[offset + row]
        return None

    # ==================== 查询操作 ====================

    def _on_search(self) -> None:
        """执行查询操作"""
        self._current_page = 1
        self._load_data()

    def _on_reset_filter(self) -> None:
        """重置筛选条件"""
        self._start_date.setDate(datetime.now().replace(day=1))
        self._end_date.setDate(datetime.now())
        self._search_input.clear()
        self._current_page = 1
        self._load_data()

    # ==================== 分页操作 ====================

    def _on_prev_page(self) -> None:
        """上一页"""
        if self._current_page > 1:
            self._current_page -= 1
            self._load_data()

    def _on_next_page(self) -> None:
        """下一页"""
        total_pages = max(1, (self._total_count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self._current_page < total_pages:
            self._current_page += 1
            self._load_data()

    def _on_page_size_changed(self, value: int) -> None:
        """每页条数变化"""
        self.PAGE_SIZE = value
        self._current_page = 1
        self._load_data()

    # ==================== 删除操作 ====================

    def _on_delete_selected(self) -> None:
        """删除选中的历史记录"""
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选择要删除的记录")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_rows)} 条记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        offset = (self._current_page - 1) * self.PAGE_SIZE
        deleted_count = 0
        for index in sorted(
            [idx.row() for idx in selected_rows], reverse=True
        ):
            actual_index = offset + index
            if actual_index < len(self._filtered_records):
                record = self._filtered_records[actual_index]
                history_id = record.get("id", 0)
                if self._db.delete_history(history_id):
                    deleted_count += 1

        QMessageBox.information(self, "提示", f"已删除 {deleted_count} 条记录")
        self._load_data()

    def _on_clear_all(self) -> None:
        """清空所有历史记录"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有历史记录吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._db.execute_update("DELETE FROM history", ())

        self._db.vacuum_database()
        QMessageBox.information(self, "提示", "已清空所有历史记录")
        self._current_page = 1
        self._load_data()

    # ==================== 导出操作 ====================

    def _on_export_excel(self) -> None:
        """导出选中记录的Excel报告"""
        record = self._get_selected_record()
        if record is None:
            return

        task_id = record.get("task_id", 0)
        if not task_id:
            QMessageBox.warning(self, "警告", "该记录缺少关联任务ID，无法导出")
            return

        try:
            output_path = self._report_service.export_excel(task_id)
            QMessageBox.information(
                self, "导出成功", f"Excel报告已导出至:\n{output_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出Excel失败:\n{e}")

    def _on_export_html(self) -> None:
        """导出选中记录的HTML报告"""
        record = self._get_selected_record()
        if record is None:
            return

        task_id = record.get("task_id", 0)
        if not task_id:
            QMessageBox.warning(self, "警告", "该记录缺少关联任务ID，无法导出")
            return

        try:
            output_path = self._report_service.generate_html_report(task_id)
            QMessageBox.information(
                self, "导出成功", f"HTML报告已导出至:\n{output_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出HTML报告失败:\n{e}")

    def _on_export_pdf(self) -> None:
        """导出选中记录的PDF报告"""
        record = self._get_selected_record()
        if record is None:
            return

        task_id = record.get("task_id", 0)
        if not task_id:
            QMessageBox.warning(self, "警告", "该记录缺少关联任务ID，无法导出")
            return

        try:
            output_path = self._report_service.generate_pdf_report(task_id)
            QMessageBox.information(
                self, "导出成功", f"PDF报告已导出至:\n{output_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出PDF报告失败:\n{e}")

    # ==================== 查看详情 ====================

    def _on_view_detail(self) -> None:
        """查看选中记录的详细信息弹窗"""
        record = self._get_selected_record()
        if record is None:
            return

        stats = self._extract_stats(record)
        stats_json = record.get("stats_json", {})
        if isinstance(stats_json, str):
            try:
                stats_json = json.loads(stats_json)
            except (json.JSONDecodeError, TypeError):
                stats_json = {}

        detail_lines = [
            f"任务名称: {record.get('task_name', '-')}",
            f"任务ID: {record.get('task_id', '-')}",
            f"执行时间: {record.get('execute_time', '-')}",
            f"持续时间: {format_duration(record.get('duration', 0.0))}",
            "",
            "===== 统计数据 =====",
            f"总请求数: {stats.get('total_requests', 0)}",
            f"成功数: {stats.get('success_count', 0)}",
            f"失败数: {stats.get('fail_count', 0)}",
            f"失败率: {stats.get('fail_rate', 0.0):.2%}",
            f"平均响应时间: {stats.get('avg_response_time', 0.0):.2f} ms",
            "",
            f"结果摘要: {record.get('result_summary', '-')}",
            f"报告路径: {record.get('report_path', '-')}",
        ]

        per_method = stats_json.get("requests_per_method", {})
        if per_method:
            detail_lines.append("")
            detail_lines.append("===== 按接口统计 =====")
            for endpoint, entry in per_method.items():
                detail_lines.append(
                    f"  {endpoint}: "
                    f"请求={entry.get('num_requests', 0)}, "
                    f"失败={entry.get('num_failures', 0)}, "
                    f"平均RT={entry.get('avg_response_time', 0):.2f}ms, "
                    f"P95={entry.get('p95_response_time', 0):.2f}ms"
                )

        errors = stats_json.get("errors", [])
        if errors:
            detail_lines.append("")
            detail_lines.append(f"===== 错误列表 ({len(errors)}条) =====")
            for err in errors[:20]:
                detail_lines.append(
                    f"  {err.get('method', '')} {err.get('name', '')}: "
                    f"{err.get('error', '')} ({err.get('occurrences', 0)}次)"
                )

        dialog = QDialog(self)
        dialog.setWindowTitle("历史记录详情")
        dialog.setMinimumSize(600, 500)

        dialog_layout = QVBoxLayout(dialog)

        detail_text = QTextEdit()
        detail_text.setReadOnly(True)
        detail_text.setPlainText("\n".join(detail_lines))
        dialog_layout.addWidget(detail_text)

        btn_close = QPushButton("关闭")
        btn_close.setProperty("secondary", True)
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(dialog.close)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        dialog_layout.addLayout(btn_layout)

        if self._theme == "dark":
            dialog.setStyleSheet(
                "QDialog { background-color: #1e1e2e; }"
                "QTextEdit { background-color: #252536; color: #e0e0f0;"
                " border: 1px solid #3a3a55; border-radius: 6px; }"
                "QLabel { color: #e0e0f0; }"
            )

        dialog.exec()

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
            self._count_label.setStyleSheet("font-size: 13px; color: #a0a0c0;")
        else:
            self._title_label.setStyleSheet(
                "font-size: 22px; font-weight: 700; color: #1a1a2e;"
            )
            self._count_label.setStyleSheet("font-size: 13px; color: #5a5a7a;")

        for i in range(self._table.rowCount()):
            for j in range(self._table.columnCount()):
                item = self._table.item(i, j)
                if item is None:
                    continue
                if j == 6:
                    fail_rate_text = item.text().replace("%", "").strip()
                    try:
                        rate_val = float(fail_rate_text) / 100.0
                    except ValueError:
                        rate_val = 0.0
                    if rate_val > 0.05:
                        item.setForeground(Qt.GlobalColor.red)
                    elif theme == "dark":
                        item.setForeground(Qt.GlobalColor.white)
                    else:
                        item.setForeground(Qt.GlobalColor.black)
                else:
                    if theme == "dark":
                        item.setForeground(Qt.GlobalColor.white)
                    else:
                        item.setForeground(Qt.GlobalColor.black)
