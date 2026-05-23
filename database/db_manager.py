"""
SQLite 数据库管理器模块

提供单例模式的数据库管理器，支持：
- 自动建表
- CRUD 操作
- 事务支持
- 连接池管理
- 参数化查询防 SQL 注入
"""

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from utils.logger import get_logger

logger = get_logger("database")


class ConnectionPool:
    """SQLite 连接池

    由于 SQLite 是文件级数据库，真正的连接池意义有限，
    此处实现一个线程安全的连接管理器，为每个线程分配独立连接，
    并支持连接的获取、回收与统一关闭。
    """

    def __init__(
        self,
        db_path: str | Path,
        pool_size: int = 5,
        timeout: float = 30.0,
    ) -> None:
        self._db_path = str(db_path)
        self._pool_size = max(1, pool_size)
        self._timeout = timeout
        self._lock = threading.Lock()
        self._pool: list[sqlite3.Connection] = []
        self._in_use: dict[int, sqlite3.Connection] = {}
        self._closed = False

    def _create_connection(self) -> sqlite3.Connection:
        """创建一个新的数据库连接"""
        conn = sqlite3.connect(
            self._db_path,
            timeout=self._timeout,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def get_connection(self) -> sqlite3.Connection:
        """从连接池获取一个连接"""
        with self._lock:
            if self._closed:
                raise RuntimeError("连接池已关闭")

            thread_id = threading.get_ident()
            if thread_id in self._in_use:
                return self._in_use[thread_id]

            if self._pool:
                conn = self._pool.pop()
            elif len(self._in_use) < self._pool_size:
                conn = self._create_connection()
            else:
                raise RuntimeError(
                    f"连接池已满，当前活跃连接数: {len(self._in_use)}，"
                    f"最大连接数: {self._pool_size}"
                )

            self._in_use[thread_id] = conn
            return conn

    def return_connection(self, conn: sqlite3.Connection) -> None:
        """将连接归还到连接池"""
        with self._lock:
            thread_id = threading.get_ident()
            if thread_id in self._in_use:
                del self._in_use[thread_id]

            if not self._closed and len(self._pool) < self._pool_size:
                try:
                    conn.rollback()
                    self._pool.append(conn)
                except sqlite3.Error:
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass
            else:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    def close_all(self) -> None:
        """关闭连接池中所有连接"""
        with self._lock:
            self._closed = True
            for conn in self._in_use.values():
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            self._in_use.clear()

            for conn in self._pool:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            self._pool.clear()

    @property
    def active_count(self) -> int:
        """当前活跃连接数"""
        with self._lock:
            return len(self._in_use)

    @property
    def idle_count(self) -> int:
        """当前空闲连接数"""
        with self._lock:
            return len(self._pool)


class DatabaseManager:
    """SQLite 数据库管理器（单例模式）

    提供对 tasks、task_results、history、settings、distributed_nodes
    五张表的完整 CRUD 操作，以及事务和连接池管理。
    """

    _instance: "DatabaseManager | None" = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None, **kwargs: Any) -> "DatabaseManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        db_path: str | Path | None = None,
        pool_size: int = 5,
        timeout: float = 30.0,
    ) -> None:
        if self._initialized:
            return
        self._initialized = True

        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            db_path = base_dir / "data" / "performance.db"

        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._pool = ConnectionPool(
            db_path=self._db_path,
            pool_size=pool_size,
            timeout=timeout,
        )

        self._init_tables()
        logger.info(f"数据库管理器初始化完成，数据库路径: {self._db_path}")

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._pool.close_all()
                cls._instance._initialized = False
                cls._instance = None

    # ==================== 连接与事务管理 ====================

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取数据库连接的上下文管理器

        使用方式:
            with db.get_connection() as conn:
                cursor = conn.execute(...)
        """
        conn = self._pool.get_connection()
        try:
            yield conn
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"数据库操作异常，已回滚: {e}")
            raise
        finally:
            self._pool.return_connection(conn)

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """事务上下文管理器

        使用方式:
            with db.transaction() as conn:
                conn.execute(...)
                conn.execute(...)
                # 正常退出自动提交，异常自动回滚
        """
        conn = self._pool.get_connection()
        try:
            yield conn
            conn.commit()
            logger.debug("事务提交成功")
        except Exception as e:
            conn.rollback()
            logger.error(f"事务回滚: {e}")
            raise
        finally:
            self._pool.return_connection(conn)

    def execute_query(
        self,
        sql: str,
        params: tuple | list | None = None,
    ) -> list[dict[str, Any]]:
        """执行查询语句并返回字典列表

        参数化查询，防止 SQL 注入。

        Args:
            sql: SQL 查询语句，使用 ? 作为占位符
            params: 查询参数

        Returns:
            查询结果列表，每行为字典
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params or ())
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    def execute_update(
        self,
        sql: str,
        params: tuple | list | None = None,
    ) -> int:
        """执行更新语句（INSERT / UPDATE / DELETE）

        参数化查询，防止 SQL 注入。

        Args:
            sql: SQL 更新语句，使用 ? 作为占位符
            params: 更新参数

        Returns:
            受影响的行数
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params or ())
            conn.commit()
            return cursor.rowcount

    def execute_many(
        self,
        sql: str,
        params_list: list[tuple | list],
    ) -> int:
        """批量执行语句

        Args:
            sql: SQL 语句
            params_list: 参数列表

        Returns:
            受影响的总行数
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, params_list)
            conn.commit()
            return cursor.rowcount

    # ==================== 自动建表 ====================

    def _init_tables(self) -> None:
        """初始化所有数据表，若表不存在则自动创建"""
        with self.get_connection() as conn:
            conn.execute(self._SQL_CREATE_TASKS)
            conn.execute(self._SQL_CREATE_TASK_RESULTS)
            conn.execute(self._SQL_CREATE_HISTORY)
            conn.execute(self._SQL_CREATE_SETTINGS)
            conn.execute(self._SQL_CREATE_DISTRIBUTED_NODES)
            conn.commit()
            logger.info("数据表初始化/校验完成")

    # -------------------- 建表 SQL --------------------

    _SQL_CREATE_TASKS = """
    CREATE TABLE IF NOT EXISTS tasks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        type            TEXT    NOT NULL DEFAULT 'HTTP',
        method          TEXT    NOT NULL DEFAULT 'GET',
        url             TEXT    NOT NULL DEFAULT '',
        headers         TEXT    DEFAULT '{}',
        cookies         TEXT    DEFAULT '{}',
        token           TEXT    DEFAULT '',
        body            TEXT    DEFAULT '{}',
        body_type       TEXT    DEFAULT 'json',
        file_path       TEXT    DEFAULT '',
        params          TEXT    DEFAULT '{}',
        csv_path        TEXT    DEFAULT '',
        users           INTEGER DEFAULT 10,
        spawn_rate      INTEGER DEFAULT 1,
        run_time        TEXT    DEFAULT '5m',
        timeout         INTEGER DEFAULT 30,
        retry_count     INTEGER DEFAULT 0,
        created_at      TEXT    NOT NULL,
        updated_at      TEXT    NOT NULL
    )
    """

    _SQL_CREATE_TASK_RESULTS = """
    CREATE TABLE IF NOT EXISTS task_results (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id             INTEGER NOT NULL,
        status              TEXT    NOT NULL DEFAULT 'waiting',
        start_time          TEXT,
        end_time            TEXT,
        total_requests      INTEGER DEFAULT 0,
        success_count       INTEGER DEFAULT 0,
        fail_count          INTEGER DEFAULT 0,
        avg_response_time   REAL    DEFAULT 0.0,
        max_response_time   REAL    DEFAULT 0.0,
        min_response_time   REAL    DEFAULT 0.0,
        p95_response_time   REAL    DEFAULT 0.0,
        qps                 REAL    DEFAULT 0.0,
        tps                 REAL    DEFAULT 0.0,
        rps                 REAL    DEFAULT 0.0,
        fail_rate           REAL    DEFAULT 0.0,
        current_users       INTEGER DEFAULT 0,
        stats_json          TEXT    DEFAULT '{}',
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    )
    """

    _SQL_CREATE_HISTORY = """
    CREATE TABLE IF NOT EXISTS history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id         INTEGER NOT NULL,
        task_name       TEXT    NOT NULL DEFAULT '',
        execute_time    TEXT    NOT NULL,
        duration        REAL    DEFAULT 0.0,
        result_summary  TEXT    DEFAULT '',
        stats_json      TEXT    DEFAULT '{}',
        report_path     TEXT    DEFAULT '',
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    )
    """

    _SQL_CREATE_SETTINGS = """
    CREATE TABLE IF NOT EXISTS settings (
        key         TEXT PRIMARY KEY,
        value       TEXT    NOT NULL DEFAULT '',
        updated_at  TEXT    NOT NULL
    )
    """

    _SQL_CREATE_DISTRIBUTED_NODES = """
    CREATE TABLE IF NOT EXISTS distributed_nodes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id         INTEGER NOT NULL,
        node_type       TEXT    NOT NULL DEFAULT 'worker',
        host            TEXT    NOT NULL DEFAULT '127.0.0.1',
        port            INTEGER DEFAULT 5557,
        status          TEXT    NOT NULL DEFAULT 'offline',
        worker_count    INTEGER DEFAULT 1,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    )
    """

    # ==================== tasks 表 CRUD ====================

    def create_task(self, task_data: dict[str, Any]) -> int:
        """创建性能测试任务

        Args:
            task_data: 任务数据字典，可包含以下字段：
                name, type, method, url, headers, cookies, token,
                body, body_type, file_path, params, csv_path,
                users, spawn_rate, run_time, timeout, retry_count

        Returns:
            新建任务的 ID
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_data.setdefault("name", "未命名任务")
        task_data.setdefault("type", "HTTP")
        task_data.setdefault("method", "GET")
        task_data.setdefault("url", "")
        task_data.setdefault("headers", {})
        task_data.setdefault("cookies", {})
        task_data.setdefault("token", "")
        task_data.setdefault("body", {})
        task_data.setdefault("body_type", "json")
        task_data.setdefault("file_path", "")
        task_data.setdefault("params", {})
        task_data.setdefault("csv_path", "")
        task_data.setdefault("users", 10)
        task_data.setdefault("spawn_rate", 1)
        task_data.setdefault("run_time", "5m")
        task_data.setdefault("timeout", 30)
        task_data.setdefault("retry_count", 0)

        json_fields = ["headers", "cookies", "body", "params"]
        for field in json_fields:
            value = task_data.get(field)
            if not isinstance(value, str):
                task_data[field] = json.dumps(value, ensure_ascii=False)

        sql = """
        INSERT INTO tasks (
            name, type, method, url, headers, cookies, token,
            body, body_type, file_path, params, csv_path,
            users, spawn_rate, run_time, timeout, retry_count,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            task_data["name"],
            task_data["type"],
            task_data["method"],
            task_data["url"],
            task_data["headers"],
            task_data["cookies"],
            task_data["token"],
            task_data["body"],
            task_data["body_type"],
            task_data["file_path"],
            task_data["params"],
            task_data["csv_path"],
            task_data["users"],
            task_data["spawn_rate"],
            task_data["run_time"],
            task_data["timeout"],
            task_data["retry_count"],
            now,
            now,
        )

        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            task_id = cursor.lastrowid
            logger.info(f"创建任务成功，ID: {task_id}，名称: {task_data['name']}")
            return task_id

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        """根据 ID 获取单个任务

        Args:
            task_id: 任务 ID

        Returns:
            任务字典，不存在则返回 None
        """
        sql = "SELECT * FROM tasks WHERE id = ?"
        rows = self.execute_query(sql, (task_id,))
        if rows:
            return self._deserialize_task(rows[0])
        return None

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """获取所有任务列表

        Returns:
            任务字典列表，按创建时间降序排列
        """
        sql = "SELECT * FROM tasks ORDER BY created_at DESC"
        rows = self.execute_query(sql)
        return [self._deserialize_task(row) for row in rows]

    def update_task(self, task_id: int, task_data: dict[str, Any]) -> bool:
        """更新任务信息

        Args:
            task_id: 任务 ID
            task_data: 需要更新的字段字典

        Returns:
            是否更新成功
        """
        if not task_data:
            return False

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_data["updated_at"] = now

        json_fields = ["headers", "cookies", "body", "params"]
        for field in json_fields:
            if field in task_data and not isinstance(task_data[field], str):
                task_data[field] = json.dumps(task_data[field], ensure_ascii=False)

        set_clauses = []
        values: list[Any] = []
        for key, value in task_data.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(task_id)
        sql = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?"

        affected = self.execute_update(sql, tuple(values))
        if affected > 0:
            logger.info(f"更新任务成功，ID: {task_id}")
            return True
        logger.warning(f"更新任务失败，ID: {task_id} 不存在")
        return False

    def delete_task(self, task_id: int) -> bool:
        """删除任务

        Args:
            task_id: 任务 ID

        Returns:
            是否删除成功
        """
        sql = "DELETE FROM tasks WHERE id = ?"
        affected = self.execute_update(sql, (task_id,))
        if affected > 0:
            logger.info(f"删除任务成功，ID: {task_id}")
            return True
        logger.warning(f"删除任务失败，ID: {task_id} 不存在")
        return False

    def search_tasks(self, keyword: str) -> list[dict[str, Any]]:
        """按关键字搜索任务（匹配名称或 URL）

        Args:
            keyword: 搜索关键字

        Returns:
            匹配的任务列表
        """
        sql = "SELECT * FROM tasks WHERE name LIKE ? OR url LIKE ? ORDER BY created_at DESC"
        like_param = f"%{keyword}%"
        rows = self.execute_query(sql, (like_param, like_param))
        return [self._deserialize_task(row) for row in rows]

    def get_tasks_by_type(self, task_type: str) -> list[dict[str, Any]]:
        """按类型获取任务列表

        Args:
            task_type: 任务类型（HTTP / HTTPS / WebSocket）

        Returns:
            匹配的任务列表
        """
        sql = "SELECT * FROM tasks WHERE type = ? ORDER BY created_at DESC"
        rows = self.execute_query(sql, (task_type,))
        return [self._deserialize_task(row) for row in rows]

    @staticmethod
    def _deserialize_task(row: dict[str, Any]) -> dict[str, Any]:
        """反序列化任务行数据，将 JSON 字符串还原为 Python 对象"""
        json_fields = ["headers", "cookies", "body", "params"]
        for field in json_fields:
            value = row.get(field)
            if isinstance(value, str):
                try:
                    row[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    row[field] = {}
        return row

    # ==================== task_results 表 CRUD ====================

    def create_task_result(self, result_data: dict[str, Any]) -> int:
        """创建任务结果记录

        Args:
            result_data: 结果数据字典

        Returns:
            新建记录的 ID
        """
        result_data.setdefault("task_id", 0)
        result_data.setdefault("status", "waiting")
        result_data.setdefault("start_time", None)
        result_data.setdefault("end_time", None)
        result_data.setdefault("total_requests", 0)
        result_data.setdefault("success_count", 0)
        result_data.setdefault("fail_count", 0)
        result_data.setdefault("avg_response_time", 0.0)
        result_data.setdefault("max_response_time", 0.0)
        result_data.setdefault("min_response_time", 0.0)
        result_data.setdefault("p95_response_time", 0.0)
        result_data.setdefault("qps", 0.0)
        result_data.setdefault("tps", 0.0)
        result_data.setdefault("rps", 0.0)
        result_data.setdefault("fail_rate", 0.0)
        result_data.setdefault("current_users", 0)
        result_data.setdefault("stats_json", {})

        if not isinstance(result_data["stats_json"], str):
            result_data["stats_json"] = json.dumps(
                result_data["stats_json"], ensure_ascii=False
            )

        sql = """
        INSERT INTO task_results (
            task_id, status, start_time, end_time,
            total_requests, success_count, fail_count,
            avg_response_time, max_response_time, min_response_time,
            p95_response_time, qps, tps, rps, fail_rate,
            current_users, stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            result_data["task_id"],
            result_data["status"],
            result_data["start_time"],
            result_data["end_time"],
            result_data["total_requests"],
            result_data["success_count"],
            result_data["fail_count"],
            result_data["avg_response_time"],
            result_data["max_response_time"],
            result_data["min_response_time"],
            result_data["p95_response_time"],
            result_data["qps"],
            result_data["tps"],
            result_data["rps"],
            result_data["fail_rate"],
            result_data["current_users"],
            result_data["stats_json"],
        )

        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            result_id = cursor.lastrowid
            logger.info(
                f"创建任务结果成功，ID: {result_id}，任务ID: {result_data['task_id']}"
            )
            return result_id

    def get_task_result(self, result_id: int) -> dict[str, Any] | None:
        """根据 ID 获取单条任务结果

        Args:
            result_id: 结果 ID

        Returns:
            结果字典，不存在则返回 None
        """
        sql = "SELECT * FROM task_results WHERE id = ?"
        rows = self.execute_query(sql, (result_id,))
        if rows:
            return self._deserialize_result(rows[0])
        return None

    def get_results_by_task(self, task_id: int) -> list[dict[str, Any]]:
        """获取指定任务的所有结果记录

        Args:
            task_id: 任务 ID

        Returns:
            结果列表
        """
        sql = "SELECT * FROM task_results WHERE task_id = ? ORDER BY start_time DESC"
        rows = self.execute_query(sql, (task_id,))
        return [self._deserialize_result(row) for row in rows]

    def get_latest_result_by_task(self, task_id: int) -> dict[str, Any] | None:
        """获取指定任务的最新结果记录

        Args:
            task_id: 任务 ID

        Returns:
            最新的结果字典，不存在则返回 None
        """
        sql = """
        SELECT * FROM task_results
        WHERE task_id = ?
        ORDER BY start_time DESC
        LIMIT 1
        """
        rows = self.execute_query(sql, (task_id,))
        if rows:
            return self._deserialize_result(rows[0])
        return None

    def get_results_by_status(self, status: str) -> list[dict[str, Any]]:
        """按状态获取任务结果列表

        Args:
            status: 状态（waiting / running / stopped / error）

        Returns:
            匹配的结果列表
        """
        sql = "SELECT * FROM task_results WHERE status = ? ORDER BY start_time DESC"
        rows = self.execute_query(sql, (status,))
        return [self._deserialize_result(row) for row in rows]

    def update_task_result(self, result_id: int, result_data: dict[str, Any]) -> bool:
        """更新任务结果

        Args:
            result_id: 结果 ID
            result_data: 需要更新的字段字典

        Returns:
            是否更新成功
        """
        if not result_data:
            return False

        if "stats_json" in result_data and not isinstance(
            result_data["stats_json"], str
        ):
            result_data["stats_json"] = json.dumps(
                result_data["stats_json"], ensure_ascii=False
            )

        set_clauses = []
        values: list[Any] = []
        for key, value in result_data.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(result_id)
        sql = f"UPDATE task_results SET {', '.join(set_clauses)} WHERE id = ?"

        affected = self.execute_update(sql, tuple(values))
        if affected > 0:
            logger.info(f"更新任务结果成功，ID: {result_id}")
            return True
        logger.warning(f"更新任务结果失败，ID: {result_id} 不存在")
        return False

    def update_result_status(self, result_id: int, status: str) -> bool:
        """更新任务结果状态

        Args:
            result_id: 结果 ID
            status: 新状态

        Returns:
            是否更新成功
        """
        sql = "UPDATE task_results SET status = ? WHERE id = ?"
        affected = self.execute_update(sql, (status, result_id))
        if affected > 0:
            logger.info(f"更新任务结果状态成功，ID: {result_id}，新状态: {status}")
            return True
        return False

    def delete_task_result(self, result_id: int) -> bool:
        """删除任务结果

        Args:
            result_id: 结果 ID

        Returns:
            是否删除成功
        """
        sql = "DELETE FROM task_results WHERE id = ?"
        affected = self.execute_update(sql, (result_id,))
        if affected > 0:
            logger.info(f"删除任务结果成功，ID: {result_id}")
            return True
        logger.warning(f"删除任务结果失败，ID: {result_id} 不存在")
        return False

    def delete_results_by_task(self, task_id: int) -> int:
        """删除指定任务的所有结果记录

        Args:
            task_id: 任务 ID

        Returns:
            删除的记录数
        """
        sql = "DELETE FROM task_results WHERE task_id = ?"
        affected = self.execute_update(sql, (task_id,))
        logger.info(f"删除任务 {task_id} 的结果记录，共 {affected} 条")
        return affected

    @staticmethod
    def _deserialize_result(row: dict[str, Any]) -> dict[str, Any]:
        """反序列化任务结果行数据"""
        value = row.get("stats_json")
        if isinstance(value, str):
            try:
                row["stats_json"] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row["stats_json"] = {}
        return row

    # ==================== history 表 CRUD ====================

    def create_history(self, history_data: dict[str, Any]) -> int:
        """创建历史记录

        Args:
            history_data: 历史数据字典

        Returns:
            新建记录的 ID
        """
        history_data.setdefault("task_id", 0)
        history_data.setdefault("task_name", "")
        history_data.setdefault("execute_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        history_data.setdefault("duration", 0.0)
        history_data.setdefault("result_summary", "")
        history_data.setdefault("stats_json", {})
        history_data.setdefault("report_path", "")

        if not isinstance(history_data["stats_json"], str):
            history_data["stats_json"] = json.dumps(
                history_data["stats_json"], ensure_ascii=False
            )

        sql = """
        INSERT INTO history (
            task_id, task_name, execute_time, duration,
            result_summary, stats_json, report_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            history_data["task_id"],
            history_data["task_name"],
            history_data["execute_time"],
            history_data["duration"],
            history_data["result_summary"],
            history_data["stats_json"],
            history_data["report_path"],
        )

        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            history_id = cursor.lastrowid
            logger.info(f"创建历史记录成功，ID: {history_id}，任务: {history_data['task_name']}")
            return history_id

    def get_history(self, history_id: int) -> dict[str, Any] | None:
        """根据 ID 获取单条历史记录

        Args:
            history_id: 历史 ID

        Returns:
            历史字典，不存在则返回 None
        """
        sql = "SELECT * FROM history WHERE id = ?"
        rows = self.execute_query(sql, (history_id,))
        if rows:
            return self._deserialize_history(rows[0])
        return None

    def get_all_history(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """获取所有历史记录（分页）

        Args:
            limit: 每页数量
            offset: 偏移量

        Returns:
            历史记录列表
        """
        sql = "SELECT * FROM history ORDER BY execute_time DESC LIMIT ? OFFSET ?"
        rows = self.execute_query(sql, (limit, offset))
        return [self._deserialize_history(row) for row in rows]

    def get_history_by_task(self, task_id: int) -> list[dict[str, Any]]:
        """获取指定任务的历史记录

        Args:
            task_id: 任务 ID

        Returns:
            历史记录列表
        """
        sql = "SELECT * FROM history WHERE task_id = ? ORDER BY execute_time DESC"
        rows = self.execute_query(sql, (task_id,))
        return [self._deserialize_history(row) for row in rows]

    def get_history_by_time_range(
        self,
        start_time: str,
        end_time: str,
    ) -> list[dict[str, Any]]:
        """按时间范围获取历史记录

        Args:
            start_time: 起始时间（格式: YYYY-MM-DD HH:MM:SS）
            end_time: 结束时间（格式: YYYY-MM-DD HH:MM:SS）

        Returns:
            匹配的历史记录列表
        """
        sql = """
        SELECT * FROM history
        WHERE execute_time BETWEEN ? AND ?
        ORDER BY execute_time DESC
        """
        rows = self.execute_query(sql, (start_time, end_time))
        return [self._deserialize_history(row) for row in rows]

    def update_history(self, history_id: int, history_data: dict[str, Any]) -> bool:
        """更新历史记录

        Args:
            history_id: 历史 ID
            history_data: 需要更新的字段字典

        Returns:
            是否更新成功
        """
        if not history_data:
            return False

        if "stats_json" in history_data and not isinstance(
            history_data["stats_json"], str
        ):
            history_data["stats_json"] = json.dumps(
                history_data["stats_json"], ensure_ascii=False
            )

        set_clauses = []
        values: list[Any] = []
        for key, value in history_data.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(history_id)
        sql = f"UPDATE history SET {', '.join(set_clauses)} WHERE id = ?"

        affected = self.execute_update(sql, tuple(values))
        if affected > 0:
            logger.info(f"更新历史记录成功，ID: {history_id}")
            return True
        logger.warning(f"更新历史记录失败，ID: {history_id} 不存在")
        return False

    def delete_history(self, history_id: int) -> bool:
        """删除历史记录

        Args:
            history_id: 历史 ID

        Returns:
            是否删除成功
        """
        sql = "DELETE FROM history WHERE id = ?"
        affected = self.execute_update(sql, (history_id,))
        if affected > 0:
            logger.info(f"删除历史记录成功，ID: {history_id}")
            return True
        logger.warning(f"删除历史记录失败，ID: {history_id} 不存在")
        return False

    def delete_history_by_task(self, task_id: int) -> int:
        """删除指定任务的所有历史记录

        Args:
            task_id: 任务 ID

        Returns:
            删除的记录数
        """
        sql = "DELETE FROM history WHERE task_id = ?"
        affected = self.execute_update(sql, (task_id,))
        logger.info(f"删除任务 {task_id} 的历史记录，共 {affected} 条")
        return affected

    def get_history_count(self) -> int:
        """获取历史记录总数

        Returns:
            记录总数
        """
        sql = "SELECT COUNT(*) AS cnt FROM history"
        rows = self.execute_query(sql)
        return rows[0]["cnt"] if rows else 0

    @staticmethod
    def _deserialize_history(row: dict[str, Any]) -> dict[str, Any]:
        """反序列化历史记录行数据"""
        value = row.get("stats_json")
        if isinstance(value, str):
            try:
                row["stats_json"] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row["stats_json"] = {}
        return row

    # ==================== settings 表 CRUD ====================

    def set_setting(self, key: str, value: Any) -> None:
        """设置配置项（存在则更新，不存在则插入）

        Args:
            key: 配置键
            value: 配置值（自动序列化为 JSON 字符串）
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value

        sql = """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """
        self.execute_update(sql, (key, value_str, now))
        logger.debug(f"设置配置项: {key}")

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值，尝试 JSON 反序列化；不存在则返回默认值
        """
        sql = "SELECT value FROM settings WHERE key = ?"
        rows = self.execute_query(sql, (key,))
        if rows:
            raw = rows[0]["value"]
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        return default

    def get_all_settings(self) -> dict[str, Any]:
        """获取所有配置项

        Returns:
            配置字典
        """
        sql = "SELECT key, value FROM settings"
        rows = self.execute_query(sql)
        result: dict[str, Any] = {}
        for row in rows:
            raw = row["value"]
            try:
                result[row["key"]] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = raw
        return result

    def delete_setting(self, key: str) -> bool:
        """删除配置项

        Args:
            key: 配置键

        Returns:
            是否删除成功
        """
        sql = "DELETE FROM settings WHERE key = ?"
        affected = self.execute_update(sql, (key,))
        if affected > 0:
            logger.info(f"删除配置项成功: {key}")
            return True
        logger.warning(f"删除配置项失败: {key} 不存在")
        return False

    def batch_set_settings(self, settings: dict[str, Any]) -> None:
        """批量设置配置项

        Args:
            settings: 配置字典
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """
        params_list: list[tuple[str, str, str]] = []
        for key, value in settings.items():
            value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            params_list.append((key, value_str, now))

        self.execute_many(sql, params_list)
        logger.info(f"批量设置配置项，共 {len(settings)} 项")

    # ==================== distributed_nodes 表 CRUD ====================

    def create_node(self, node_data: dict[str, Any]) -> int:
        """创建分布式节点记录

        Args:
            node_data: 节点数据字典

        Returns:
            新建记录的 ID
        """
        node_data.setdefault("task_id", 0)
        node_data.setdefault("node_type", "worker")
        node_data.setdefault("host", "127.0.0.1")
        node_data.setdefault("port", 5557)
        node_data.setdefault("status", "offline")
        node_data.setdefault("worker_count", 1)

        sql = """
        INSERT INTO distributed_nodes (
            task_id, node_type, host, port, status, worker_count
        ) VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            node_data["task_id"],
            node_data["node_type"],
            node_data["host"],
            node_data["port"],
            node_data["status"],
            node_data["worker_count"],
        )

        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            node_id = cursor.lastrowid
            logger.info(
                f"创建节点成功，ID: {node_id}，"
                f"类型: {node_data['node_type']}，"
                f"地址: {node_data['host']}:{node_data['port']}"
            )
            return node_id

    def get_node(self, node_id: int) -> dict[str, Any] | None:
        """根据 ID 获取节点信息

        Args:
            node_id: 节点 ID

        Returns:
            节点字典，不存在则返回 None
        """
        sql = "SELECT * FROM distributed_nodes WHERE id = ?"
        rows = self.execute_query(sql, (node_id,))
        return rows[0] if rows else None

    def get_nodes_by_task(self, task_id: int) -> list[dict[str, Any]]:
        """获取指定任务的所有节点

        Args:
            task_id: 任务 ID

        Returns:
            节点列表
        """
        sql = "SELECT * FROM distributed_nodes WHERE task_id = ? ORDER BY node_type, id"
        rows = self.execute_query(sql, (task_id,))
        return rows

    def get_nodes_by_type(self, node_type: str) -> list[dict[str, Any]]:
        """按节点类型获取节点列表

        Args:
            node_type: 节点类型（master / worker）

        Returns:
            匹配的节点列表
        """
        sql = "SELECT * FROM distributed_nodes WHERE node_type = ? ORDER BY id"
        rows = self.execute_query(sql, (node_type,))
        return rows

    def get_nodes_by_status(self, status: str) -> list[dict[str, Any]]:
        """按状态获取节点列表

        Args:
            status: 节点状态

        Returns:
            匹配的节点列表
        """
        sql = "SELECT * FROM distributed_nodes WHERE status = ? ORDER BY id"
        rows = self.execute_query(sql, (status,))
        return rows

    def update_node(self, node_id: int, node_data: dict[str, Any]) -> bool:
        """更新节点信息

        Args:
            node_id: 节点 ID
            node_data: 需要更新的字段字典

        Returns:
            是否更新成功
        """
        if not node_data:
            return False

        set_clauses = []
        values: list[Any] = []
        for key, value in node_data.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(node_id)
        sql = f"UPDATE distributed_nodes SET {', '.join(set_clauses)} WHERE id = ?"

        affected = self.execute_update(sql, tuple(values))
        if affected > 0:
            logger.info(f"更新节点成功，ID: {node_id}")
            return True
        logger.warning(f"更新节点失败，ID: {node_id} 不存在")
        return False

    def update_node_status(self, node_id: int, status: str) -> bool:
        """更新节点状态

        Args:
            node_id: 节点 ID
            status: 新状态

        Returns:
            是否更新成功
        """
        sql = "UPDATE distributed_nodes SET status = ? WHERE id = ?"
        affected = self.execute_update(sql, (status, node_id))
        if affected > 0:
            logger.info(f"更新节点状态成功，ID: {node_id}，新状态: {status}")
            return True
        return False

    def delete_node(self, node_id: int) -> bool:
        """删除节点

        Args:
            node_id: 节点 ID

        Returns:
            是否删除成功
        """
        sql = "DELETE FROM distributed_nodes WHERE id = ?"
        affected = self.execute_update(sql, (node_id,))
        if affected > 0:
            logger.info(f"删除节点成功，ID: {node_id}")
            return True
        logger.warning(f"删除节点失败，ID: {node_id} 不存在")
        return False

    def delete_nodes_by_task(self, task_id: int) -> int:
        """删除指定任务的所有节点

        Args:
            task_id: 任务 ID

        Returns:
            删除的记录数
        """
        sql = "DELETE FROM distributed_nodes WHERE task_id = ?"
        affected = self.execute_update(sql, (task_id,))
        logger.info(f"删除任务 {task_id} 的节点记录，共 {affected} 条")
        return affected

    def get_master_node(self, task_id: int) -> dict[str, Any] | None:
        """获取指定任务的 master 节点

        Args:
            task_id: 任务 ID

        Returns:
            master 节点字典，不存在则返回 None
        """
        sql = "SELECT * FROM distributed_nodes WHERE task_id = ? AND node_type = 'master' LIMIT 1"
        rows = self.execute_query(sql, (task_id,))
        return rows[0] if rows else None

    def get_worker_nodes(self, task_id: int) -> list[dict[str, Any]]:
        """获取指定任务的所有 worker 节点

        Args:
            task_id: 任务 ID

        Returns:
            worker 节点列表
        """
        sql = "SELECT * FROM distributed_nodes WHERE task_id = ? AND node_type = 'worker' ORDER BY id"
        rows = self.execute_query(sql, (task_id,))
        return rows

    # ==================== 统计与辅助方法 ====================

    def get_task_count(self) -> int:
        """获取任务总数

        Returns:
            任务总数
        """
        sql = "SELECT COUNT(*) AS cnt FROM tasks"
        rows = self.execute_query(sql)
        return rows[0]["cnt"] if rows else 0

    def get_running_task_count(self) -> int:
        """获取正在运行的任务数量

        Returns:
            正在运行的任务数
        """
        sql = "SELECT COUNT(*) AS cnt FROM task_results WHERE status = 'running'"
        rows = self.execute_query(sql)
        return rows[0]["cnt"] if rows else 0

    def get_task_statistics(self, task_id: int) -> dict[str, Any]:
        """获取任务的汇总统计信息

        Args:
            task_id: 任务 ID

        Returns:
            统计信息字典
        """
        result = {
            "task_id": task_id,
            "total_runs": 0,
            "total_requests": 0,
            "total_success": 0,
            "total_fail": 0,
            "avg_response_time": 0.0,
            "max_response_time": 0.0,
            "min_response_time": 0.0,
        }

        sql = """
        SELECT
            COUNT(*)          AS total_runs,
            SUM(total_requests) AS total_requests,
            SUM(success_count)  AS total_success,
            SUM(fail_count)     AS total_fail,
            AVG(avg_response_time) AS avg_response_time,
            MAX(max_response_time) AS max_response_time,
            MIN(min_response_time) AS min_response_time
        FROM task_results
        WHERE task_id = ?
        """
        rows = self.execute_query(sql, (task_id,))
        if rows and rows[0]["total_runs"] is not None:
            row = rows[0]
            result["total_runs"] = row["total_runs"]
            result["total_requests"] = row["total_requests"] or 0
            result["total_success"] = row["total_success"] or 0
            result["total_fail"] = row["total_fail"] or 0
            result["avg_response_time"] = round(row["avg_response_time"] or 0.0, 3)
            result["max_response_time"] = round(row["max_response_time"] or 0.0, 3)
            result["min_response_time"] = round(row["min_response_time"] or 0.0, 3)

        return result

    def cleanup_old_history(self, days: int = 30) -> int:
        """清理指定天数之前的历史记录

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        cutoff = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(time.time() - days * 86400),
        )
        sql = "DELETE FROM history WHERE execute_time < ?"
        affected = self.execute_update(sql, (cutoff,))
        logger.info(f"清理 {days} 天前的历史记录，共删除 {affected} 条")
        return affected

    def vacuum_database(self) -> None:
        """压缩数据库文件，回收空间"""
        with self.get_connection() as conn:
            conn.execute("VACUUM")
            logger.info("数据库压缩完成")

    def get_database_info(self) -> dict[str, Any]:
        """获取数据库基本信息

        Returns:
            数据库信息字典
        """
        info: dict[str, Any] = {
            "db_path": str(self._db_path),
            "db_size": 0,
            "tables": {},
        }

        db_file = self._db_path
        if db_file.exists():
            info["db_size"] = db_file.stat().st_size

        table_names = ["tasks", "task_results", "history", "settings", "distributed_nodes"]
        for table in table_names:
            sql = f"SELECT COUNT(*) AS cnt FROM {table}"
            rows = self.execute_query(sql)
            info["tables"][table] = rows[0]["cnt"] if rows else 0

        return info

    def close(self) -> None:
        """关闭数据库管理器，释放所有连接"""
        self._pool.close_all()
        logger.info("数据库管理器已关闭")

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
