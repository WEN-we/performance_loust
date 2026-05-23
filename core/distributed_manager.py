"""
分布式Locust管理模块

实现Locust的Master/Worker分布式压测模式，
支持启动和管理Master节点与多个Worker节点，
监控节点状态，协调分布式压测任务。
"""

import multiprocessing
import time
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import gevent
from gevent.monkey import patch_all as gevent_patch_all

if not gevent.monkey.is_module_patched("threading"):
    gevent_patch_all()

from locust.env import Environment

from utils.logger import get_logger

logger = get_logger("distributed_manager")


class NodeState(Enum):
    """节点状态枚举"""
    INIT = auto()
    RUNNING = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass
class NodeInfo:
    """节点信息数据类"""
    name: str
    host: str
    port: int
    state: NodeState = NodeState.INIT
    process: multiprocessing.Process | None = None
    user_count: int = 0
    worker_count: int = 0
    pid: int = 0
    start_time: float = 0.0
    error_message: str = ""


@dataclass
class DistributedConfig:
    """分布式压测配置"""
    master_host: str = "*"
    master_port: int = 5557
    worker_count: int = 1
    expect_workers: int = 1
    host: str = "http://localhost:8089"
    users: int = 10
    spawn_rate: float = 1.0
    run_time: str = "5m"
    task_configs: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    auth_token: str | None = None
    auth_type: str = "bearer"


class DistributedManager:
    """
    分布式Locust管理器

    管理Master/Worker模式的分布式压测：
    - 启动和停止Master节点进程
    - 启动和停止Worker节点进程
    - 监控各节点运行状态
    - 协调分布式压测的开始和结束
    """

    def __init__(self, config: DistributedConfig | None = None) -> None:
        self._config = config or DistributedConfig()
        self._master_info: NodeInfo | None = None
        self._worker_infos: dict[str, NodeInfo] = {}
        self._lock = threading.Lock()
        self._monitor_thread: threading.Thread | None = None
        self._monitor_stop_event = threading.Event()
        self._master_env: Environment | None = None

    @property
    def config(self) -> DistributedConfig:
        """获取分布式配置"""
        return self._config

    @property
    def master_info(self) -> NodeInfo | None:
        """获取Master节点信息"""
        return self._master_info

    @property
    def worker_infos(self) -> dict[str, NodeInfo]:
        """获取所有Worker节点信息"""
        return dict(self._worker_infos)

    def start_master(
        self,
        host: str | None = None,
        port: int | None = None,
    ) -> bool:
        """
        启动Master节点

        Master节点负责协调所有Worker节点，收集和聚合统计数据。
        通过子进程运行，避免gevent事件循环冲突。

        Args:
            host: Master绑定地址，默认使用配置值
            port: Master绑定端口，默认使用配置值

        Returns:
            是否启动成功
        """
        with self._lock:
            if self._master_info and self._master_info.state == NodeState.RUNNING:
                logger.warning("Master节点已在运行中")
                return False

        bind_host = host or self._config.master_host
        bind_port = port or self._config.master_port

        master_info = NodeInfo(
            name="master",
            host=bind_host,
            port=bind_port,
            state=NodeState.INIT,
            start_time=time.time(),
        )

        # 序列化任务配置供子进程使用
        task_configs = list(self._config.task_configs)
        variables = dict(self._config.variables)
        auth_token = self._config.auth_token
        auth_type = self._config.auth_type
        target_host = self._config.host

        process = multiprocessing.Process(
            target=self._run_master_process,
            args=(
                bind_host,
                bind_port,
                target_host,
                task_configs,
                variables,
                auth_token,
                auth_type,
            ),
            name="locust-master",
            daemon=True,
        )

        try:
            process.start()
            master_info.process = process
            master_info.pid = process.pid or 0
            master_info.state = NodeState.RUNNING
            self._master_info = master_info

            logger.info(
                "Master节点已启动: host=%s, port=%d, pid=%d",
                bind_host,
                bind_port,
                master_info.pid,
            )
            return True
        except Exception as e:
            master_info.state = NodeState.ERROR
            master_info.error_message = str(e)
            logger.error("启动Master节点失败: %s", e)
            return False

    def start_workers(
        self,
        count: int | None = None,
        master_host: str | None = None,
        master_port: int | None = None,
    ) -> int:
        """
        启动多个Worker节点

        Worker节点执行实际的压测任务，向Master节点报告统计数据。
        每个Worker在独立的子进程中运行。

        Args:
            count: 启动的Worker数量，默认使用配置值
            master_host: Master节点地址，默认使用配置值
            master_port: Master节点端口，默认使用配置值

        Returns:
            成功启动的Worker数量
        """
        worker_count = count or self._config.worker_count
        m_host = master_host or self._resolve_master_host()
        m_port = master_port or self._config.master_port

        # 序列化任务配置供子进程使用
        task_configs = list(self._config.task_configs)
        variables = dict(self._config.variables)
        auth_token = self._config.auth_token
        auth_type = self._config.auth_type
        target_host = self._config.host

        started = 0
        for i in range(worker_count):
            worker_name = f"worker-{len(self._worker_infos) + 1}"

            worker_info = NodeInfo(
                name=worker_name,
                host=m_host,
                port=m_port,
                state=NodeState.INIT,
                start_time=time.time(),
            )

            process = multiprocessing.Process(
                target=self._run_worker_process,
                args=(
                    m_host,
                    m_port,
                    target_host,
                    task_configs,
                    variables,
                    auth_token,
                    auth_type,
                ),
                name=f"locust-{worker_name}",
                daemon=True,
            )

            try:
                process.start()
                worker_info.process = process
                worker_info.pid = process.pid or 0
                worker_info.state = NodeState.RUNNING
                self._worker_infos[worker_name] = worker_info
                started += 1

                logger.info(
                    "Worker节点已启动: name=%s, master=%s:%d, pid=%d",
                    worker_name,
                    m_host,
                    m_port,
                    worker_info.pid,
                )
            except Exception as e:
                worker_info.state = NodeState.ERROR
                worker_info.error_message = str(e)
                self._worker_infos[worker_name] = worker_info
                logger.error("启动Worker节点 '%s' 失败: %s", worker_name, e)

        return started

    def stop_master(self) -> bool:
        """
        停止Master节点

        终止Master进程并更新节点状态。
        """
        if not self._master_info:
            logger.warning("Master节点未启动")
            return False

        return self._stop_node(self._master_info, "Master")

    def stop_worker(self, name: str) -> bool:
        """
        停止指定Worker节点

        Args:
            name: Worker节点名称

        Returns:
            是否停止成功
        """
        if name not in self._worker_infos:
            logger.warning("Worker节点 '%s' 不存在", name)
            return False

        return self._stop_node(self._worker_infos[name], f"Worker '{name}'")

    def stop_all_workers(self) -> int:
        """
        停止所有Worker节点

        Returns:
            成功停止的Worker数量
        """
        stopped = 0
        for name in list(self._worker_infos.keys()):
            if self.stop_worker(name):
                stopped += 1
        return stopped

    def stop_all(self) -> bool:
        """
        停止所有节点（Master和所有Worker）

        Returns:
            是否全部停止成功
        """
        success = True

        worker_stopped = self.stop_all_workers()
        if worker_stopped != len(self._worker_infos):
            success = False

        if not self.stop_master():
            success = False

        # 停止监控线程
        self._stop_monitor()

        if success:
            logger.info("所有节点已停止")
        else:
            logger.warning("部分节点停止失败")

        return success

    def start_distributed_test(
        self,
        users: int | None = None,
        spawn_rate: float | None = None,
    ) -> bool:
        """
        通过Master节点启动分布式压测

        在Master节点上触发压测开始命令，Worker节点将
        根据分配的用户数开始执行任务。

        Args:
            users: 总并发用户数
            spawn_rate: 用户生成速率

        Returns:
            是否启动成功
        """
        if not self._master_info or self._master_info.state != NodeState.RUNNING:
            logger.error("Master节点未运行，无法启动分布式压测")
            return False

        if not self._master_env:
            logger.error("Master环境未初始化，无法启动分布式压测")
            return False

        total_users = users or self._config.users
        rate = spawn_rate or self._config.spawn_rate

        try:
            runner = self._master_env.runner
            if runner:
                runner.start(total_users, rate)
                logger.info(
                    "分布式压测已启动: users=%d, spawn_rate=%.1f",
                    total_users,
                    rate,
                )
                return True
            else:
                logger.error("Master运行器未就绪")
                return False
        except Exception as e:
            logger.error("启动分布式压测失败: %s", e)
            return False

    def stop_distributed_test(self) -> bool:
        """
        通过Master节点停止分布式压测

        Returns:
            是否停止成功
        """
        if not self._master_env:
            logger.error("Master环境未初始化")
            return False

        try:
            runner = self._master_env.runner
            if runner:
                runner.stop()
                logger.info("分布式压测已停止")
                return True
            return False
        except Exception as e:
            logger.error("停止分布式压测失败: %s", e)
            return False

    def get_master_status(self) -> dict[str, Any]:
        """
        获取Master节点状态信息

        Returns:
            包含Master节点详细状态的字典
        """
        if not self._master_info:
            return {"state": "not_started"}

        self._refresh_node_state(self._master_info)

        info = self._master_info
        result: dict[str, Any] = {
            "name": info.name,
            "host": info.host,
            "port": info.port,
            "state": info.state.name,
            "pid": info.pid,
            "start_time": info.start_time,
            "uptime": time.time() - info.start_time if info.start_time else 0,
            "error_message": info.error_message,
        }

        # 如果Master环境可用，附加运行器统计信息
        if self._master_env and self._master_env.runner:
            runner = self._master_env.runner
            stats = self._master_env.stats
            result.update(
                {
                    "user_count": runner.user_count,
                    "worker_count": runner.worker_count,
                    "total_requests": stats.total.num_requests,
                    "total_failures": stats.total.num_failures,
                    "rps": stats.total.total_rps,
                    "avg_response_time": stats.total.avg_response_time,
                }
            )

        return result

    def get_worker_status(self, name: str) -> dict[str, Any] | None:
        """
        获取指定Worker节点状态信息

        Args:
            name: Worker节点名称

        Returns:
            节点状态字典，不存在则返回None
        """
        if name not in self._worker_infos:
            return None

        info = self._worker_infos[name]
        self._refresh_node_state(info)

        return {
            "name": info.name,
            "host": info.host,
            "port": info.port,
            "state": info.state.name,
            "pid": info.pid,
            "start_time": info.start_time,
            "uptime": time.time() - info.start_time if info.start_time else 0,
            "error_message": info.error_message,
        }

    def list_workers(self) -> list[dict[str, Any]]:
        """
        列出所有Worker节点状态

        Returns:
            Worker节点状态列表
        """
        result: list[dict[str, Any]] = []
        for name in list(self._worker_infos.keys()):
            status = self.get_worker_status(name)
            if status:
                result.append(status)
        return result

    def start_monitor(self, interval: float = 5.0) -> None:
        """
        启动节点状态监控线程

        定期检查各节点进程的存活状态，更新节点信息。

        Args:
            interval: 监控检查间隔（秒）
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("监控线程已在运行中")
            return

        self._monitor_stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            name="distributed-monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("节点状态监控已启动，间隔=%.1f秒", interval)

    def _stop_monitor(self) -> None:
        """停止节点状态监控线程"""
        self._monitor_stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
            self._monitor_thread = None
        logger.info("节点状态监控已停止")

    def _monitor_loop(self, interval: float) -> None:
        """
        监控循环

        定期检查Master和Worker节点的进程存活状态，
        如果进程意外退出则更新节点状态为ERROR。
        """
        while not self._monitor_stop_event.is_set():
            try:
                # 检查Master节点
                if self._master_info:
                    self._refresh_node_state(self._master_info)

                # 检查Worker节点
                for info in self._worker_infos.values():
                    self._refresh_node_state(info)

            except Exception as e:
                logger.error("监控检查异常: %s", e)

            self._monitor_stop_event.wait(timeout=interval)

    def _refresh_node_state(self, info: NodeInfo) -> None:
        """
        刷新节点状态

        检查节点进程是否存活，如果进程已退出则更新状态。
        """
        if info.state in (NodeState.STOPPED, NodeState.ERROR):
            return

        if info.process and info.process.is_alive():
            info.state = NodeState.RUNNING
        else:
            if info.state == NodeState.RUNNING:
                # 进程意外退出
                exit_code = info.process.exitcode if info.process else None
                if exit_code is not None and exit_code != 0:
                    info.state = NodeState.ERROR
                    info.error_message = f"进程异常退出，退出码: {exit_code}"
                else:
                    info.state = NodeState.STOPPED
                logger.warning(
                    "节点 '%s' 进程已退出: state=%s, exit_code=%s",
                    info.name,
                    info.state.name,
                    exit_code,
                )

    def _stop_node(self, info: NodeInfo, label: str) -> bool:
        """
        停止指定节点

        先尝试优雅终止进程，超时后强制杀死。

        Args:
            info: 节点信息
            label: 节点标签（用于日志）

        Returns:
            是否停止成功
        """
        if info.state in (NodeState.STOPPED, NodeState.ERROR):
            logger.warning("%s 节点已处于停止状态", label)
            return True

        if not info.process:
            info.state = NodeState.STOPPED
            return True

        try:
            # 优雅终止
            info.process.terminate()
            info.process.join(timeout=5.0)

            if info.process.is_alive():
                # 强制杀死
                info.process.kill()
                info.process.join(timeout=3.0)

            info.state = NodeState.STOPPED
            logger.info("%s 节点已停止", label)
            return True
        except Exception as e:
            info.state = NodeState.ERROR
            info.error_message = str(e)
            logger.error("停止 %s 节点失败: %s", label, e)
            return False

    def _resolve_master_host(self) -> str:
        """解析Master节点的主机地址，供Worker连接使用"""
        if self._config.master_host == "*":
            return "127.0.0.1"
        return self._config.master_host

    @staticmethod
    def _run_master_process(
        bind_host: str,
        bind_port: int,
        target_host: str,
        task_configs: list[dict[str, Any]],
        variables: dict[str, str],
        auth_token: str | None,
        auth_type: str,
    ) -> None:
        """
        Master节点子进程入口函数

        在子进程中创建Locust Environment和MasterRunner，
        等待Worker节点连接后协调分布式压测。

        Args:
            bind_host: Master绑定地址
            bind_port: Master绑定端口
            target_host: 目标压测主机
            task_configs: 任务配置列表
            variables: 参数化变量
            auth_token: 认证令牌
            auth_type: 认证类型
        """
        import gevent.monkey

        if not gevent.monkey.is_module_patched("threading"):
            gevent.monkey.patch_all()

        from locust.env import Environment
        from core.locust_engine import (
            LocustEngine,
            EngineConfig,
            TaskConfig,
        )

        # 在子进程中重建引擎和User类
        engine_config = EngineConfig(
            host=target_host,
            variables=variables,
            auth_token=auth_token,
            auth_type=auth_type,
            tasks=[TaskConfig(**tc) for tc in task_configs],
        )
        engine = LocustEngine(engine_config)
        user_classes = engine._create_user_classes()

        if not user_classes:
            logger.error("Master进程: 没有可用的User类")
            return

        try:
            env = Environment(user_classes=user_classes)
            master = env.create_master_runner(
                master_bind_host=bind_host,
                master_bind_port=bind_port,
            )

            logger.info(
                "Master进程已就绪: bind=%s:%d, 等待Worker连接...",
                bind_host,
                bind_port,
            )

            # 保持运行，等待Worker连接和压测指令
            while True:
                gevent.sleep(1)

        except KeyboardInterrupt:
            logger.info("Master进程收到中断信号，正在退出")
        except Exception as e:
            logger.error("Master进程运行异常: %s", e)

    @staticmethod
    def _run_worker_process(
        master_host: str,
        master_port: int,
        target_host: str,
        task_configs: list[dict[str, Any]],
        variables: dict[str, str],
        auth_token: str | None,
        auth_type: str,
    ) -> None:
        """
        Worker节点子进程入口函数

        在子进程中创建Locust Environment和WorkerRunner，
        连接到Master节点并等待任务分配。

        Args:
            master_host: Master节点地址
            master_port: Master节点端口
            target_host: 目标压测主机
            task_configs: 任务配置列表
            variables: 参数化变量
            auth_token: 认证令牌
            auth_type: 认证类型
        """
        import gevent.monkey

        if not gevent.monkey.is_module_patched("threading"):
            gevent.monkey.patch_all()

        from locust.env import Environment
        from core.locust_engine import (
            LocustEngine,
            EngineConfig,
            TaskConfig,
        )

        # 在子进程中重建引擎和User类
        engine_config = EngineConfig(
            host=target_host,
            variables=variables,
            auth_token=auth_token,
            auth_type=auth_type,
            tasks=[TaskConfig(**tc) for tc in task_configs],
        )
        engine = LocustEngine(engine_config)
        user_classes = engine._create_user_classes()

        if not user_classes:
            logger.error("Worker进程: 没有可用的User类")
            return

        try:
            env = Environment(user_classes=user_classes)
            worker = env.create_worker_runner(
                master_host=master_host,
                master_port=master_port,
            )

            logger.info(
                "Worker进程已连接: master=%s:%d",
                master_host,
                master_port,
            )

            # 保持运行，等待Master分配任务
            while True:
                gevent.sleep(1)

        except KeyboardInterrupt:
            logger.info("Worker进程收到中断信号，正在退出")
        except Exception as e:
            logger.error("Worker进程运行异常: %s", e)

    @property
    def running_worker_count(self) -> int:
        """获取正在运行的Worker节点数量"""
        return sum(
            1
            for info in self._worker_infos.values()
            if info.state == NodeState.RUNNING
        )

    @property
    def total_worker_count(self) -> int:
        """获取Worker节点总数（含已停止的）"""
        return len(self._worker_infos)
