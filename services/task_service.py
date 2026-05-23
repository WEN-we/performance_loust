"""
任务管理服务模块

封装任务的完整生命周期管理，包括：
- 任务的创建、更新、删除、查询
- 任务配置的保存与加载（JSON文件）
- CSV数据导入
- 任务配置校验
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from database.db_manager import DatabaseManager
from utils.logger import get_logger
from utils.helpers import ensure_dir, save_json, load_json

logger = get_logger("task_service")


class TaskService:
    """任务管理服务类

    封装任务的完整生命周期管理，对 DatabaseManager 的任务相关操作
    进行业务层封装，并扩展了配置文件保存/加载、CSV导入、校验等功能。
    """

    VALID_TASK_TYPES = {"HTTP", "HTTPS", "WebSocket"}
    VALID_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "WEBSOCKET"}
    VALID_BODY_TYPES = {"json", "form", "xml", "raw", "none"}

    def __init__(self, db: DatabaseManager | None = None) -> None:
        """初始化任务管理服务

        Args:
            db: 数据库管理器实例，为None时使用单例
        """
        self._db = db or DatabaseManager()

    @property
    def db(self) -> DatabaseManager:
        """获取数据库管理器实例"""
        return self._db

    def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """创建任务配置

        校验任务数据后写入数据库，返回包含新建任务ID和完整信息的字典。

        Args:
            task_data: 任务数据字典，可包含以下字段：
                name, type, method, url, headers, cookies, token,
                body, body_type, file_path, params, csv_path,
                users, spawn_rate, run_time, timeout, retry_count

        Returns:
            包含 id 和任务信息的字典

        Raises:
            ValueError: 任务数据校验失败
        """
        errors = self.validate_task(task_data)
        if errors:
            raise ValueError(f"任务数据校验失败: {'; '.join(errors)}")

        task_id = self._db.create_task(task_data)
        task = self._db.get_task(task_id)

        logger.info("创建任务成功，ID=%d，名称=%s", task_id, task_data.get("name", ""))
        return task or {"id": task_id}

    def update_task(self, task_id: int, task_data: dict[str, Any]) -> dict[str, Any]:
        """更新任务配置

        校验更新数据后更新数据库中对应的任务记录。

        Args:
            task_id: 任务ID
            task_data: 需要更新的字段字典

        Returns:
            更新后的任务完整信息

        Raises:
            ValueError: 任务不存在或数据校验失败
        """
        existing = self._db.get_task(task_id)
        if existing is None:
            raise ValueError(f"任务不存在，ID: {task_id}")

        merged = dict(existing)
        merged.update(task_data)

        errors = self.validate_task(merged)
        if errors:
            raise ValueError(f"任务数据校验失败: {'; '.join(errors)}")

        success = self._db.update_task(task_id, task_data)
        if not success:
            raise ValueError(f"更新任务失败，ID: {task_id}")

        updated = self._db.get_task(task_id)
        logger.info("更新任务成功，ID=%d", task_id)
        return updated or {}

    def delete_task(self, task_id: int) -> bool:
        """删除任务

        同时删除任务关联的结果记录和历史记录。

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        existing = self._db.get_task(task_id)
        if existing is None:
            logger.warning("删除任务失败，任务不存在，ID=%d", task_id)
            return False

        self._db.delete_results_by_task(task_id)
        self._db.delete_history_by_task(task_id)
        self._db.delete_nodes_by_task(task_id)

        success = self._db.delete_task(task_id)
        if success:
            logger.info("删除任务成功，ID=%d，名称=%s", task_id, existing.get("name", ""))
        return success

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        """根据ID查询单个任务

        Args:
            task_id: 任务ID

        Returns:
            任务字典，不存在则返回None
        """
        return self._db.get_task(task_id)

    def list_tasks(
        self,
        task_type: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询任务列表

        支持按类型和关键字过滤，不传参数则返回全部任务。

        Args:
            task_type: 按任务类型过滤（HTTP/HTTPS/WebSocket）
            keyword: 按名称或URL关键字搜索

        Returns:
            任务字典列表
        """
        if keyword:
            return self._db.search_tasks(keyword)
        if task_type:
            return self._db.get_tasks_by_type(task_type)
        return self._db.get_all_tasks()

    def save_task_config(self, task_id: int, file_path: str | Path | None = None) -> Path:
        """保存任务配置到JSON文件

        将指定任务的完整配置序列化为JSON并写入文件，
        文件默认保存到 exports 目录下。

        Args:
            task_id: 任务ID
            file_path: 保存路径，为None时自动生成

        Returns:
            保存的文件路径

        Raises:
            ValueError: 任务不存在
        """
        task = self._db.get_task(task_id)
        if task is None:
            raise ValueError(f"任务不存在，ID: {task_id}")

        if file_path is None:
            from config.settings import get_settings
            settings = get_settings()
            export_dir = settings.export_dir
            ensure_dir(export_dir)
            safe_name = task.get("name", "unnamed").replace(" ", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = export_dir / f"task_{safe_name}_{timestamp}.json"

        file_path = Path(file_path)
        ensure_dir(file_path.parent)

        config_data = {
            "task_id": task.get("id"),
            "name": task.get("name"),
            "type": task.get("type"),
            "method": task.get("method"),
            "url": task.get("url"),
            "headers": task.get("headers", {}),
            "cookies": task.get("cookies", {}),
            "token": task.get("token", ""),
            "body": task.get("body", {}),
            "body_type": task.get("body_type", "json"),
            "file_path": task.get("file_path", ""),
            "params": task.get("params", {}),
            "csv_path": task.get("csv_path", ""),
            "users": task.get("users", 10),
            "spawn_rate": task.get("spawn_rate", 1),
            "run_time": task.get("run_time", "5m"),
            "timeout": task.get("timeout", 30),
            "retry_count": task.get("retry_count", 0),
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        save_json(file_path, config_data)
        logger.info("任务配置已保存到文件，ID=%d，路径=%s", task_id, file_path)
        return file_path

    def load_task_config(self, file_path: str | Path) -> dict[str, Any]:
        """从JSON文件加载任务配置

        读取JSON配置文件并创建新的任务记录到数据库。

        Args:
            file_path: 配置文件路径

        Returns:
            新创建的任务信息

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 配置数据校验失败
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {file_path}")

        config_data = load_json(file_path)
        if config_data is None:
            raise ValueError(f"配置文件内容为空或格式错误: {file_path}")

        task_data = {
            "name": config_data.get("name", "导入任务"),
            "type": config_data.get("type", "HTTP"),
            "method": config_data.get("method", "GET"),
            "url": config_data.get("url", ""),
            "headers": config_data.get("headers", {}),
            "cookies": config_data.get("cookies", {}),
            "token": config_data.get("token", ""),
            "body": config_data.get("body", {}),
            "body_type": config_data.get("body_type", "json"),
            "file_path": config_data.get("file_path", ""),
            "params": config_data.get("params", {}),
            "csv_path": config_data.get("csv_path", ""),
            "users": config_data.get("users", 10),
            "spawn_rate": config_data.get("spawn_rate", 1),
            "run_time": config_data.get("run_time", "5m"),
            "timeout": config_data.get("timeout", 30),
            "retry_count": config_data.get("retry_count", 0),
        }

        task = self.create_task(task_data)
        logger.info("从文件加载任务配置成功，路径=%s，任务ID=%s", file_path, task.get("id"))
        return task

    def import_csv_data(
        self,
        csv_path: str | Path,
        task_id: int | None = None,
        encoding: str = "utf-8",
        delimiter: str = ",",
    ) -> list[dict[str, str]]:
        """导入CSV数据

        读取CSV文件内容并返回数据行列表。
        如果指定了task_id，则同时更新任务的csv_path字段。

        Args:
            csv_path: CSV文件路径
            task_id: 关联的任务ID，为None时不更新任务
            encoding: 文件编码
            delimiter: 分隔符

        Returns:
            CSV数据行列表，每行为字典

        Raises:
            FileNotFoundError: CSV文件不存在
            ValueError: CSV文件为空
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV文件不存在: {csv_path}")

        rows: list[dict[str, str]] = []
        with open(csv_path, "r", encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                rows.append(dict(row))

        if not rows:
            raise ValueError(f"CSV文件为空: {csv_path}")

        if task_id is not None:
            self._db.update_task(task_id, {"csv_path": str(csv_path)})
            logger.info("已更新任务的CSV路径，任务ID=%d，路径=%s", task_id, csv_path)

        logger.info(
            "导入CSV数据成功，文件=%s，行数=%d，列=%s",
            csv_path,
            len(rows),
            list(rows[0].keys()) if rows else [],
        )
        return rows

    def validate_task(self, task_data: dict[str, Any]) -> list[str]:
        """校验任务配置

        对任务数据进行完整性校验，返回错误信息列表。
        空列表表示校验通过。

        Args:
            task_data: 任务数据字典

        Returns:
            错误信息列表，空列表表示校验通过
        """
        errors: list[str] = []

        name = task_data.get("name", "").strip()
        if not name:
            errors.append("任务名称不能为空")

        task_type = task_data.get("type", "HTTP").upper()
        if task_type not in self.VALID_TASK_TYPES:
            errors.append(f"不支持的任务类型: {task_type}，有效值: {', '.join(sorted(self.VALID_TASK_TYPES))}")

        method = task_data.get("method", "GET").upper()
        if method not in self.VALID_METHODS:
            errors.append(f"不支持的HTTP方法: {method}，有效值: {', '.join(sorted(self.VALID_METHODS))}")

        url = task_data.get("url", "").strip()
        if not url and method != "WEBSOCKET":
            errors.append("目标URL不能为空")

        body_type = task_data.get("body_type", "json").lower()
        if body_type not in self.VALID_BODY_TYPES:
            errors.append(f"不支持的请求体类型: {body_type}，有效值: {', '.join(sorted(self.VALID_BODY_TYPES))}")

        users = task_data.get("users", 10)
        if not isinstance(users, (int, float)) or users < 1:
            errors.append("并发用户数必须为大于0的数字")

        spawn_rate = task_data.get("spawn_rate", 1)
        if not isinstance(spawn_rate, (int, float)) or spawn_rate < 1:
            errors.append("用户生成速率必须为大于0的数字")

        run_time = task_data.get("run_time", "5m")
        if isinstance(run_time, str) and run_time.strip():
            import re
            if not re.match(r"^\d+[smh]?$", run_time.strip().lower()):
                errors.append(f"运行时间格式错误: {run_time}，应为如 10s/5m/1h 的格式")

        timeout = task_data.get("timeout", 30)
        if not isinstance(timeout, (int, float)) or timeout < 0:
            errors.append("超时时间不能为负数")

        retry_count = task_data.get("retry_count", 0)
        if not isinstance(retry_count, int) or retry_count < 0:
            errors.append("重试次数不能为负数")

        csv_path = task_data.get("csv_path", "")
        if csv_path:
            csv_file = Path(csv_path)
            if not csv_file.exists():
                errors.append(f"CSV数据文件不存在: {csv_path}")

        file_path = task_data.get("file_path", "")
        if file_path:
            fp = Path(file_path)
            if not fp.exists():
                errors.append(f"请求体文件不存在: {file_path}")

        return errors

    def get_task_statistics(self, task_id: int) -> dict[str, Any]:
        """获取任务的汇总统计信息

        Args:
            task_id: 任务ID

        Returns:
            统计信息字典
        """
        return self._db.get_task_statistics(task_id)

    def get_task_count(self) -> int:
        """获取任务总数"""
        return self._db.get_task_count()

    def search_tasks(self, keyword: str) -> list[dict[str, Any]]:
        """按关键字搜索任务

        Args:
            keyword: 搜索关键字

        Returns:
            匹配的任务列表
        """
        return self._db.search_tasks(keyword)
