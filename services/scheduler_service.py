"""
定时任务服务模块

基于APScheduler实现定时执行性能测试任务，支持：
- Cron表达式定时调度
- 添加/移除/列出定时任务
- 暂停/恢复定时任务
- 任务执行结果自动保存
"""

import json
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from database.db_manager import DatabaseManager
from utils.logger import get_logger

logger = get_logger("scheduler_service")


class SchedulerService:
    """定时任务服务类

    使用APScheduler库实现基于Cron表达式的定时任务调度，
    支持对性能测试任务的定时启动、暂停、恢复和移除操作。
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        """初始化定时任务服务

        创建APScheduler后台调度器，配置内存任务存储和线程池执行器。

        Args:
            db: 数据库管理器实例，为None时使用单例
        """
        self._db = db or DatabaseManager()
        self._scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            executors={"default": ThreadPoolExecutor(max_workers=3)},
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone="Asia/Shanghai",
        )
        self._job_metadata: dict[str, dict[str, Any]] = {}
        self._started = False

    def start(self) -> None:
        """启动调度器

        启动APScheduler后台调度器，开始监听定时任务触发。
        必须在添加任务之前调用。
        """
        if self._started:
            logger.warning("调度器已在运行中")
            return

        self._scheduler.start()
        self._started = True
        logger.info("定时任务调度器已启动")

    def shutdown(self, wait: bool = True) -> None:
        """关闭调度器

        停止APScheduler调度器，可选择是否等待正在执行的任务完成。

        Args:
            wait: 是否等待正在执行的任务完成
        """
        if not self._started:
            return

        self._scheduler.shutdown(wait=wait)
        self._started = False
        logger.info("定时任务调度器已关闭")

    def add_scheduled_task(
        self,
        task_id: int,
        cron_expression: str,
        job_name: str | None = None,
        enabled: bool = True,
    ) -> str:
        """添加定时任务

        使用Cron表达式创建定时调度任务，到时间后自动启动指定的性能测试任务。

        Cron表达式格式为5个字段：分 时 日 月 周
        示例：
            "0 8 * * 1-5"   -> 每周一到周五8:00执行
            "30 9 * * *"    -> 每天9:30执行
            "0 10 1 * *"    -> 每月1日10:00执行

        Args:
            task_id: 要定时执行的任务ID
            cron_expression: Cron表达式（5字段）
            job_name: 定时任务名称，为None时自动生成
            enabled: 是否立即启用，为False时添加后暂停

        Returns:
            定时任务ID（APScheduler的job_id）

        Raises:
            ValueError: 任务不存在或Cron表达式格式错误
        """
        task = self._db.get_task(task_id)
        if task is None:
            raise ValueError(f"任务不存在，ID: {task_id}")

        if job_name is None:
            job_name = f"scheduled_{task.get('name', 'task')}_{task_id}"

        parts = cron_expression.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Cron表达式格式错误: {cron_expression}，"
                f"应为5个字段: 分 时 日 月 周"
            )

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone="Asia/Shanghai",
        )

        job_id = f"sched_task_{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        job = self._scheduler.add_job(
            func=self._execute_scheduled_task,
            trigger=trigger,
            args=[task_id],
            id=job_id,
            name=job_name,
            replace_existing=True,
        )

        self._job_metadata[job_id] = {
            "task_id": task_id,
            "task_name": task.get("name", ""),
            "cron_expression": cron_expression,
            "job_name": job_name,
            "enabled": enabled,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "next_run_time": str(job.next_run_time) if job.next_run_time else "",
        }

        if not enabled:
            self._scheduler.pause_job(job_id)
            self._job_metadata[job_id]["enabled"] = False

        logger.info(
            "添加定时任务成功，job_id=%s，task_id=%d，cron=%s",
            job_id,
            task_id,
            cron_expression,
        )
        return job_id

    def remove_scheduled_task(self, job_id: str) -> bool:
        """移除定时任务

        从调度器中移除指定的定时任务。

        Args:
            job_id: 定时任务ID

        Returns:
            是否移除成功
        """
        try:
            self._scheduler.remove_job(job_id)
            self._job_metadata.pop(job_id, None)
            logger.info("移除定时任务成功，job_id=%s", job_id)
            return True
        except Exception as e:
            logger.error("移除定时任务失败，job_id=%s: %s", job_id, e)
            return False

    def list_scheduled_tasks(self) -> list[dict[str, Any]]:
        """列出所有定时任务

        返回所有已注册的定时任务信息列表。

        Returns:
            定时任务信息列表，每项包含job_id、task_id、cron表达式等
        """
        result: list[dict[str, Any]] = []

        jobs = self._scheduler.get_jobs()
        for job in jobs:
            meta = self._job_metadata.get(job.id, {})
            result.append({
                "job_id": job.id,
                "job_name": job.name,
                "task_id": meta.get("task_id"),
                "task_name": meta.get("task_name", ""),
                "cron_expression": meta.get("cron_expression", ""),
                "enabled": meta.get("enabled", True),
                "created_at": meta.get("created_at", ""),
                "next_run_time": str(job.next_run_time) if job.next_run_time else "",
            })

        return result

    def pause_scheduled_task(self, job_id: str) -> bool:
        """暂停定时任务

        暂停指定定时任务的调度，任务不会被触发直到恢复。

        Args:
            job_id: 定时任务ID

        Returns:
            是否暂停成功
        """
        try:
            self._scheduler.pause_job(job_id)
            if job_id in self._job_metadata:
                self._job_metadata[job_id]["enabled"] = False
            logger.info("暂停定时任务成功，job_id=%s", job_id)
            return True
        except Exception as e:
            logger.error("暂停定时任务失败，job_id=%s: %s", job_id, e)
            return False

    def resume_scheduled_task(self, job_id: str) -> bool:
        """恢复定时任务

        恢复已暂停的定时任务，使其重新参与调度。

        Args:
            job_id: 定时任务ID

        Returns:
            是否恢复成功
        """
        try:
            self._scheduler.resume_job(job_id)
            if job_id in self._job_metadata:
                self._job_metadata[job_id]["enabled"] = True
            logger.info("恢复定时任务成功，job_id=%s", job_id)
            return True
        except Exception as e:
            logger.error("恢复定时任务失败，job_id=%s: %s", job_id, e)
            return False

    def get_scheduled_task(self, job_id: str) -> dict[str, Any] | None:
        """获取指定定时任务的详细信息

        Args:
            job_id: 定时任务ID

        Returns:
            定时任务信息字典，不存在则返回None
        """
        job = self._scheduler.get_job(job_id)
        if job is None:
            return None

        meta = self._job_metadata.get(job_id, {})
        return {
            "job_id": job.id,
            "job_name": job.name,
            "task_id": meta.get("task_id"),
            "task_name": meta.get("task_name", ""),
            "cron_expression": meta.get("cron_expression", ""),
            "enabled": meta.get("enabled", True),
            "created_at": meta.get("created_at", ""),
            "next_run_time": str(job.next_run_time) if job.next_run_time else "",
            "trigger": str(job.trigger),
        }

    def _execute_scheduled_task(self, task_id: int) -> None:
        """定时任务执行回调

        由APScheduler在指定时间触发，启动对应的性能测试任务。
        执行结果自动保存到数据库。

        Args:
            task_id: 任务ID
        """
        try:
            from services.execution_service import ExecutionService
            exec_service = ExecutionService(self._db)
            exec_service.start_task(task_id)
            logger.info("定时任务触发执行成功，task_id=%d", task_id)
        except Exception as e:
            logger.error("定时任务触发执行失败，task_id=%d: %s", task_id, e)

    @property
    def is_running(self) -> bool:
        """调度器是否正在运行"""
        return self._started

    @property
    def job_count(self) -> int:
        """当前定时任务数量"""
        return len(self._scheduler.get_jobs())
