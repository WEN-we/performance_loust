import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import psutil

from utils.logger import get_logger

logger = get_logger("system_monitor")


@dataclass
class SystemSnapshot:
    timestamp: float = 0.0
    cpu_percent: float = 0.0
    cpu_per_core: list[float] = field(default_factory=list)
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    net_bytes_sent: int = 0
    net_bytes_recv: int = 0
    process_count: int = 0
    thread_count: int = 0


class SystemMonitor:
    def __init__(self, interval: float = 2.0) -> None:
        self._interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: SystemSnapshot = SystemSnapshot()
        self._history: list[SystemSnapshot] = []
        self._max_history = 500
        self._callbacks: list[Callable[[SystemSnapshot], None]] = []
        self._prev_net = psutil.net_io_counters()

    def get_cpu_percent(self, per_core: bool = False) -> float | list[float]:
        if per_core:
            return psutil.cpu_percent(interval=0.1, percpu=True)
        return psutil.cpu_percent(interval=0.1)

    def get_memory_info(self) -> dict[str, float]:
        mem = psutil.virtual_memory()
        return {
            "percent": mem.percent,
            "used_gb": mem.used / (1024 ** 3),
            "total_gb": mem.total / (1024 ** 3),
            "available_gb": mem.available / (1024 ** 3),
        }

    def get_disk_info(self, path: str = "/") -> dict[str, float]:
        try:
            disk = psutil.disk_usage(path)
            return {
                "percent": disk.percent,
                "used_gb": disk.used / (1024 ** 3),
                "total_gb": disk.total / (1024 ** 3),
                "free_gb": disk.free / (1024 ** 3),
            }
        except Exception:
            return {"percent": 0.0, "used_gb": 0.0, "total_gb": 0.0, "free_gb": 0.0}

    def get_network_info(self) -> dict[str, int]:
        net = psutil.net_io_counters()
        return {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }

    def get_process_info(self) -> dict[str, int]:
        p = psutil.Process()
        try:
            return {
                "process_count": len(psutil.pids()),
                "thread_count": p.num_threads(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"process_count": 0, "thread_count": 0}

    def take_snapshot(self) -> SystemSnapshot:
        now = time.time()
        cpu = self.get_cpu_percent()
        cpu_cores = self.get_cpu_percent(per_core=True)
        mem = self.get_memory_info()
        disk = self.get_disk_info()
        net = self.get_network_info()
        proc = self.get_process_info()

        snapshot = SystemSnapshot(
            timestamp=now,
            cpu_percent=cpu if isinstance(cpu, float) else sum(cpu) / len(cpu),
            cpu_per_core=cpu_cores,
            memory_percent=mem["percent"],
            memory_used_gb=mem["used_gb"],
            memory_total_gb=mem["total_gb"],
            disk_percent=disk["percent"],
            disk_used_gb=disk["used_gb"],
            disk_total_gb=disk["total_gb"],
            net_bytes_sent=net["bytes_sent"],
            net_bytes_recv=net["bytes_recv"],
            process_count=proc["process_count"],
            thread_count=proc["thread_count"],
        )

        with self._lock:
            self._latest = snapshot
            self._history.append(snapshot)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        return snapshot

    @property
    def latest(self) -> SystemSnapshot:
        with self._lock:
            return self._latest

    @property
    def history(self) -> list[SystemSnapshot]:
        with self._lock:
            return list(self._history)

    def add_callback(self, callback: Callable[[SystemSnapshot], None]) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[SystemSnapshot], None]) -> bool:
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    def _monitor_loop(self) -> None:
        logger.info("系统监控线程已启动, 采集间隔: %.1f秒", self._interval)
        while self._running:
            try:
                snapshot = self.take_snapshot()
                for cb in self._callbacks:
                    try:
                        cb(snapshot)
                    except Exception as e:
                        logger.error("监控回调执行异常: %s", e)
            except Exception as e:
                logger.error("系统监控采集异常: %s", e)

            time.sleep(self._interval)
        logger.info("系统监控线程已停止")

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="SystemMonitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval + 2.0)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running

    def get_network_speed(self) -> dict[str, float]:
        net1 = psutil.net_io_counters()
        time.sleep(1.0)
        net2 = psutil.net_io_counters()
        return {
            "upload_bytes_per_sec": net2.bytes_sent - net1.bytes_sent,
            "download_bytes_per_sec": net2.bytes_recv - net1.bytes_recv,
        }

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
