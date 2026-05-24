"""
任务执行服务模块

管理性能测试任务的执行，包括：
- 单任务启动、停止、暂停、恢复
- 多任务队列按顺序执行
- 执行状态跟踪
- 执行完成后自动保存结果到数据库
"""

import json
import threading
import time
from datetime import datetime
from typing import Any

from core.locust_engine import LocustEngine, EngineConfig, TaskConfig, EngineState
from database.db_manager import DatabaseManager
from utils.logger import get_logger
from utils.helpers import format_duration

logger = get_logger("execution_service")


class ExecutionService:
    """任务执行服务类（单例模式）

    管理任务的执行生命周期，封装 LocustEngine 的启停控制，
    维护执行状态映射，支持多任务队列顺序执行，
    并在执行完成后自动将结果持久化到数据库。

    所有页面共享同一实例，确保运行中的引擎状态全局可见。
    """

    _instance: "ExecutionService | None" = None
    _init_lock = threading.Lock()

    def __new__(cls, db: DatabaseManager | None = None, **kwargs: Any) -> "ExecutionService":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db: DatabaseManager | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._db = db or DatabaseManager()
        self._engines: dict[int, LocustEngine] = {}
        self._result_ids: dict[int, int] = {}
        self._lock = threading.Lock()
        self._queue: list[int] = []
        self._queue_running = False
        self._queue_thread: threading.Thread | None = None
        self._queue_stop_event = threading.Event()

    @classmethod
    def reset_instance(cls) -> None:
        with cls._init_lock:
            if cls._instance is not None:
                cls._instance._initialized = False
                cls._instance = None

    def start_task(self, task_id: int) -> bool:
        """启动任务

        根据数据库中的任务配置构建 EngineConfig 和 TaskConfig，
        创建 LocustEngine 实例并启动压测。
        同时在 task_results 表中创建一条运行状态记录。

        Args:
            task_id: 任务ID

        Returns:
            是否启动成功

        Raises:
            ValueError: 任务不存在或已在运行
        """
        task = self._db.get_task(task_id)
        if task is None:
            raise ValueError(f"任务不存在，ID: {task_id}")

        with self._lock:
            if task_id in self._engines and self._engines[task_id].is_running:
                raise ValueError(f"任务已在运行中，ID: {task_id}")

        engine_config = self._build_engine_config(task)
        engine = LocustEngine(engine_config)

        result_data = {
            "task_id": task_id,
            "status": "running",
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_users": task.get("users", 10),
        }
        result_id = self._db.create_task_result(result_data)

        engine.set_stats_callback(
            lambda stats, tid=task_id, rid=result_id: self._on_stats_update(tid, rid, stats)
        )

        success = engine.start()
        if not success:
            self._db.update_task_result(result_id, {
                "status": "error",
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            logger.error("启动任务失败，ID=%d", task_id)
            return False

        with self._lock:
            self._engines[task_id] = engine
            self._result_ids[task_id] = result_id

        watcher = threading.Thread(
            target=self._watch_task_completion,
            args=(task_id, result_id),
            name=f"task-watcher-{task_id}",
            daemon=True,
        )
        watcher.start()

        logger.info(
            "启动任务成功，ID=%d，名称=%s，result_id=%d",
            task_id,
            task.get("name", ""),
            result_id,
        )
        return True

    def stop_task(self, task_id: int) -> bool:
        """停止任务

        停止指定任务的Locust引擎，并将结果状态更新为stopped。

        Args:
            task_id: 任务ID

        Returns:
            是否停止成功
        """
        with self._lock:
            engine = self._engines.get(task_id)

        if engine is None:
            logger.warning("任务未在运行中，无法停止，ID=%d", task_id)
            return False

        success = engine.stop()
        if success:
            self._save_final_results(task_id)
            with self._lock:
                self._engines.pop(task_id, None)
                self._result_ids.pop(task_id, None)
            logger.info("停止任务成功，ID=%d", task_id)
        else:
            logger.warning("停止任务失败，ID=%d", task_id)

        return success

    def pause_task(self, task_id: int) -> bool:
        """暂停任务

        暂停正在运行的Locust引擎，保留运行器以便恢复。

        Args:
            task_id: 任务ID

        Returns:
            是否暂停成功
        """
        with self._lock:
            engine = self._engines.get(task_id)

        if engine is None:
            logger.warning("任务未在运行中，无法暂停，ID=%d", task_id)
            return False

        success = engine.pause()
        if success:
            result_id = self._result_ids.get(task_id)
            if result_id:
                self._db.update_task_result(result_id, {"status": "paused"})
            logger.info("暂停任务成功，ID=%d", task_id)
        return success

    def resume_task(self, task_id: int) -> bool:
        """恢复任务

        恢复已暂停的Locust引擎继续执行。

        Args:
            task_id: 任务ID

        Returns:
            是否恢复成功
        """
        with self._lock:
            engine = self._engines.get(task_id)

        if engine is None:
            logger.warning("任务未在运行中，无法恢复，ID=%d", task_id)
            return False

        success = engine.resume()
        if success:
            result_id = self._result_ids.get(task_id)
            if result_id:
                self._db.update_task_result(result_id, {"status": "running"})
            logger.info("恢复任务成功，ID=%d", task_id)
        return success

    def get_task_status(self, task_id: int) -> dict[str, Any]:
        """获取任务执行状态

        返回任务的引擎状态、实时统计数据等信息。

        Args:
            task_id: 任务ID

        Returns:
            状态信息字典
        """
        with self._lock:
            engine = self._engines.get(task_id)
            result_id = self._result_ids.get(task_id)

        if engine is None:
            latest = self._db.get_latest_result_by_task(task_id)
            if latest:
                return {
                    "task_id": task_id,
                    "engine_state": "idle",
                    "result_id": latest.get("id"),
                    "status": latest.get("status", "unknown"),
                    "stats": latest.get("stats_json", {}),
                }
            return {
                "task_id": task_id,
                "engine_state": "idle",
                "status": "never_run",
            }

        stats = engine.get_stats()
        engine_state = engine.state.name.lower()

        return {
            "task_id": task_id,
            "engine_state": engine_state,
            "result_id": result_id,
            "status": "running" if engine.is_running else engine_state,
            "stats": stats,
        }

    def execute_queue(self, task_ids: list[int]) -> bool:
        """多任务队列执行

        将多个任务按顺序依次执行，前一个任务完成后自动启动下一个。
        队列在后台线程中运行，不会阻塞调用方。

        Args:
            task_ids: 任务ID列表，按顺序执行

        Returns:
            是否成功启动队列执行
        """
        if not task_ids:
            logger.warning("任务队列为空")
            return False

        with self._lock:
            if self._queue_running:
                logger.warning("已有队列在执行中，无法重复启动")
                return False
            self._queue = list(task_ids)
            self._queue_running = True
            self._queue_stop_event.clear()

        self._queue_thread = threading.Thread(
            target=self._run_queue,
            name="task-queue-runner",
            daemon=True,
        )
        self._queue_thread.start()

        logger.info("任务队列已启动，共 %d 个任务", len(task_ids))
        return True

    def stop_queue(self) -> bool:
        """停止队列执行

        停止当前正在运行的任务，并取消队列中剩余的任务。

        Returns:
            是否成功停止
        """
        with self._lock:
            if not self._queue_running:
                return False
            self._queue_stop_event.set()
            self._queue_running = False
            self._queue.clear()

        with self._lock:
            for task_id in list(self._engines.keys()):
                engine = self._engines.get(task_id)
                if engine and engine.is_running:
                    engine.stop()
                    self._save_final_results(task_id)
                self._engines.pop(task_id, None)
                self._result_ids.pop(task_id, None)

        logger.info("任务队列已停止")
        return True

    def get_queue_status(self) -> dict[str, Any]:
        """获取队列执行状态

        Returns:
            队列状态信息字典
        """
        with self._lock:
            return {
                "running": self._queue_running,
                "remaining": len(self._queue),
                "queue": list(self._queue),
            }

    def _run_queue(self) -> None:
        """队列执行线程函数

        按顺序执行队列中的任务，每个任务完成后自动启动下一个。
        支持通过 stop_queue() 中断队列执行。
        """
        while not self._queue_stop_event.is_set():
            with self._lock:
                if not self._queue:
                    self._queue_running = False
                    break
                task_id = self._queue.pop(0)

            try:
                logger.info("队列开始执行任务，ID=%d，剩余=%d", task_id, len(self._queue))
                self.start_task(task_id)

                engine = self._engines.get(task_id)
                if engine:
                    engine.wait_for_complete()

                with self._lock:
                    if task_id in self._engines:
                        self._save_final_results(task_id)
                        self._engines.pop(task_id, None)
                        self._result_ids.pop(task_id, None)

                logger.info("队列任务执行完成，ID=%d", task_id)

            except Exception as e:
                logger.error("队列任务执行异常，ID=%d，错误=%s", task_id, e)
                with self._lock:
                    self._engines.pop(task_id, None)
                    self._result_ids.pop(task_id, None)

        with self._lock:
            self._queue_running = False
        logger.info("队列执行线程结束")

    def _watch_task_completion(self, task_id: int, result_id: int) -> None:
        """监控任务完成状态

        在后台线程中等待任务引擎运行结束，
        完成后自动保存最终结果到数据库。

        Args:
            task_id: 任务ID
            result_id: 结果记录ID
        """
        with self._lock:
            engine = self._engines.get(task_id)
            if engine is None:
                return

        engine.wait_for_complete()

        with self._lock:
            if task_id in self._engines:
                self._save_final_results(task_id)
                self._engines.pop(task_id, None)
                self._result_ids.pop(task_id, None)

    def _save_final_results(self, task_id: int) -> None:
        """保存任务最终执行结果到数据库

        从引擎获取最终统计数据，更新 task_results 记录，
        同时在 history 表中创建一条历史记录。

        Args:
            task_id: 任务ID
        """
        result_id = self._result_ids.get(task_id)
        engine = self._engines.get(task_id)

        if result_id is None or engine is None:
            return

        stats = engine.get_stats()
        task = self._db.get_task(task_id)
        task_name = task.get("name", "") if task else ""

        elapsed = stats.get("elapsed_seconds", 0)
        total_requests = stats.get("total_requests", 0)
        total_failures = stats.get("total_failures", 0)
        success_count = total_requests - total_failures
        fail_rate = stats.get("failure_rate", 0.0)
        rps_value = stats.get("rps", 0.0)
        tps_value = success_count / max(elapsed, 1) if success_count > 0 and elapsed > 0 else 0.0

        result_update = {
            "status": "stopped",
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_requests": total_requests,
            "success_count": success_count,
            "fail_count": total_failures,
            "avg_response_time": round(stats.get("avg_response_time", 0.0), 3),
            "max_response_time": round(stats.get("max_response_time", 0.0), 3),
            "min_response_time": round(stats.get("min_response_time", 0.0), 3),
            "p95_response_time": round(stats.get("p95_response_time", 0.0), 3),
            "qps": round(rps_value, 3),
            "tps": round(tps_value, 3),
            "rps": round(rps_value, 3),
            "fail_rate": round(fail_rate, 4),
            "current_users": stats.get("user_count", 0),
            "stats_json": stats,
        }
        self._db.update_task_result(result_id, result_update)

        result_summary = (
            f"总请求: {total_requests}, "
            f"成功: {success_count}, "
            f"失败: {total_failures}, "
            f"失败率: {fail_rate:.2%}, "
            f"平均响应时间: {stats.get('avg_response_time', 0):.2f}ms, "
            f"耗时: {format_duration(elapsed)}"
        )

        history_data = {
            "task_id": task_id,
            "task_name": task_name,
            "duration": round(elapsed, 2),
            "result_summary": result_summary,
            "stats_json": stats,
        }
        self._db.create_history(history_data)

        logger.info(
            "任务结果已保存，ID=%d，result_id=%d，总请求=%d，失败率=%.2f%%",
            task_id,
            result_id,
            total_requests,
            fail_rate * 100,
        )

    def _on_stats_update(
        self,
        task_id: int,
        result_id: int,
        stats: dict[str, Any],
    ) -> None:
        """实时统计回调

        引擎定时回调，更新 task_results 中的实时统计数据。

        Args:
            task_id: 任务ID
            result_id: 结果记录ID
            stats: 实时统计数据
        """
        try:
            total_requests = stats.get("total_requests", 0)
            total_failures = stats.get("total_failures", 0)
            success_count = total_requests - total_failures
            fail_rate = stats.get("failure_rate", 0.0)
            rps_value = stats.get("rps", 0.0)
            elapsed = stats.get("elapsed_seconds", 0)
            tps_value = success_count / max(elapsed, 1) if success_count > 0 and elapsed > 0 else 0.0

            update_data = {
                "total_requests": total_requests,
                "success_count": success_count,
                "fail_count": total_failures,
                "avg_response_time": round(stats.get("avg_response_time", 0.0), 3),
                "max_response_time": round(stats.get("max_response_time", 0.0), 3),
                "min_response_time": round(stats.get("min_response_time", 0.0), 3),
                "p95_response_time": round(stats.get("p95_response_time", 0.0), 3),
                "qps": round(rps_value, 3),
                "tps": round(tps_value, 3),
                "rps": round(rps_value, 3),
                "fail_rate": round(fail_rate, 4),
                "current_users": stats.get("user_count", 0),
                "stats_json": stats,
            }
            self._db.update_task_result(result_id, update_data)
        except Exception as e:
            logger.error("更新实时统计异常，任务ID=%d: %s", task_id, e)

    @staticmethod
    def _build_engine_config(task: dict[str, Any]) -> EngineConfig:
        """根据任务数据构建 Locust 引擎配置

        将数据库中的任务字段映射为 EngineConfig 和 TaskConfig。
        自动从完整URL中解析出host(基地址)和path(路径部分)。

        Args:
            task: 任务数据字典

        Returns:
            EngineConfig 实例
        """
        from urllib.parse import urlparse

        method = task.get("method", "GET").upper()
        url = task.get("url", "")

        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else url
        path = parsed.path or "/"

        if parsed.query:
            path = f"{path}?{parsed.query}"

        if method == "WEBSOCKET":
            task_cfg = TaskConfig(
                name=task.get("name", "ws_task"),
                method="WEBSOCKET",
                path=path,
                headers=task.get("headers", {}),
                cookies=task.get("cookies", {}),
                params=task.get("params", {}),
                timeout=float(task.get("timeout", 30)),
                ws_path=path,
                ws_message="",
                ws_duration=10.0,
            )
        else:
            body = task.get("body", {})
            json_body = body if body and task.get("body_type", "json") == "json" else None
            form_data = body if body and task.get("body_type", "json") == "form" else None

            task_cfg = TaskConfig(
                name=task.get("name", "http_task"),
                method=method,
                path=path,
                headers=task.get("headers", {}),
                cookies=task.get("cookies", {}),
                params=task.get("params", {}),
                json_body=json_body,
                form_data=form_data,
                timeout=float(task.get("timeout", 30)),
            )

        config = EngineConfig(
            host=host,
            users=int(task.get("users", 10)),
            spawn_rate=float(task.get("spawn_rate", 1)),
            run_time=str(task.get("run_time", "5m")),
            tasks=[task_cfg],
            csv_file=task.get("csv_path") or None,
            auth_token=task.get("token") or None,
        )

        return config
