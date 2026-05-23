"""
Locust引擎核心模块

封装Locust的运行控制，支持HTTP/HTTPS压测、WebSocket压测、
参数化变量、CSV数据驱动、动态User类生成等功能。
通过编程API运行Locust，而非命令行方式。
"""

import base64
import os
import re
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

from utils.logger import get_logger
from utils.helpers import read_csv

logger = get_logger("locust_engine")

try:
    import websocket as _ws_client
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False


class EngineState(Enum):
    """引擎状态枚举"""
    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPING = auto()
    STOPPED = auto()


@dataclass
class TaskConfig:
    """单个压测任务的配置"""
    name: str = "unnamed_task"
    method: str = "GET"
    path: str = "/"
    headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    json_body: Any = None
    form_data: dict[str, str] | None = None
    files: list[dict[str, str]] | None = None
    weight: int = 1
    timeout: float = 30.0
    verify_ssl: bool = True
    ws_path: str = ""
    ws_message: str = ""
    ws_messages: list[str] = field(default_factory=list)
    ws_duration: float = 10.0
    ws_receive: bool = True


@dataclass
class EngineConfig:
    """Locust引擎配置"""
    host: str = "http://localhost:8089"
    users: int = 10
    spawn_rate: float = 1.0
    run_time: str = "5m"
    wait_min: float = 1.0
    wait_max: float = 3.0
    wait_type: str = "uniform"
    tasks: list[TaskConfig] = field(default_factory=list)
    csv_file: str | None = None
    csv_delimiter: str = ","
    csv_encoding: str = "utf-8"
    variables: dict[str, str] = field(default_factory=dict)
    auth_token: str | None = None
    auth_type: str = "bearer"
    auth_username: str | None = None
    auth_password: str | None = None
    tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    stop_on_error: bool = False
    stats_interval: float = 3.0


_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def substitute_variables(
    template: str,
    variables: dict[str, str],
    csv_row: dict[str, str] | None = None,
) -> str:
    """替换模板中的变量 ${var_name}，优先使用CSV行数据"""
    if not template:
        return template

    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        if csv_row and var_name in csv_row:
            return str(csv_row[var_name])
        if var_name in variables:
            return str(variables[var_name])
        return match.group(0)

    return _VAR_PATTERN.sub(_replacer, template)


def parse_run_time(run_time: str) -> int:
    """解析运行时间字符串为秒数，支持 10s/5m/1h/1h30m 等格式"""
    if not run_time:
        return 0
    run_time = run_time.lower().strip()
    total = 0
    pattern = re.compile(r"(\d+)([smh])")
    for match in pattern.finditer(run_time):
        value = int(match.group(1))
        unit = match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600}
        total += value * multipliers.get(unit, 0)
    if total == 0:
        digits = re.match(r"^(\d+)$", run_time)
        if digits:
            total = int(digits.group(1))
    return total


def _substitute_dict(
    data: dict[str, str],
    variables: dict[str, str],
    csv_row: dict[str, str] | None = None,
) -> dict[str, str]:
    """对字典中所有值进行变量替换"""
    return {k: substitute_variables(v, variables, csv_row) for k, v in data.items()}


def _substitute_json_body(
    body: Any,
    variables: dict[str, str],
    csv_row: dict[str, str] | None = None,
) -> Any:
    """对JSON请求体递归进行变量替换"""
    if isinstance(body, str):
        return substitute_variables(body, variables, csv_row)
    if isinstance(body, dict):
        return {
            k: _substitute_json_body(v, variables, csv_row) for k, v in body.items()
        }
    if isinstance(body, list):
        return [_substitute_json_body(item, variables, csv_row) for item in body]
    return body


class LocustEngine:
    """Locust引擎核心类，封装Locust的运行控制"""

    _locust_imported = False
    _HttpUser = None
    _User = None
    _Environment = None
    _LocalRunner = None
    _gevent = None
    _between = None
    _constant = None
    _constant_throughput = None

    @classmethod
    def _ensure_locust_imported(cls) -> None:
        if cls._locust_imported:
            return
        import gevent
        from gevent.monkey import patch_all as gevent_patch_all
        if not gevent.monkey.is_module_patched("threading"):
            try:
                gevent_patch_all()
            except Exception:
                pass
        from locust import HttpUser, User, between, constant, constant_throughput
        from locust.env import Environment
        from locust.runners import LocalRunner
        cls._gevent = gevent
        cls._HttpUser = HttpUser
        cls._User = User
        cls._Environment = Environment
        cls._LocalRunner = LocalRunner
        cls._between = between
        cls._constant = constant
        cls._constant_throughput = constant_throughput
        cls._locust_imported = True

    def __init__(self, config: EngineConfig | None = None) -> None:
        self._config = config or EngineConfig()
        self._state = EngineState.IDLE
        self._environment = None
        self._runner = None
        self._user_classes: list[type] = []
        self._thread: threading.Thread | None = None
        self._stats_greenlet = None
        self._stats_callback: Callable[[dict[str, Any]], None] | None = None
        self._csv_data: list[dict[str, str]] = []
        self._start_time: float = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._request_records: list[dict[str, Any]] = []
        self._auth_headers: dict[str, str] = {}

        self._load_csv_data()
        self._build_auth_headers()

    @property
    def state(self) -> EngineState:
        """获取引擎当前状态"""
        return self._state

    @property
    def is_running(self) -> bool:
        """引擎是否正在运行"""
        return self._state == EngineState.RUNNING

    @property
    def config(self) -> EngineConfig:
        """获取引擎配置"""
        return self._config

    def set_stats_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """设置实时统计回调函数，回调接收统计字典"""
        self._stats_callback = callback

    def start(self) -> bool:
        """启动Locust引擎（后台线程运行）"""
        self._ensure_locust_imported()
        with self._lock:
            if self._state == EngineState.RUNNING:
                logger.warning("引擎已在运行中，无需重复启动")
                return False
            if self._state == EngineState.PAUSED:
                return self.resume()

        self._stop_event.clear()
        self._request_records.clear()
        self._start_time = time.time()

        self._thread = threading.Thread(
            target=self._run,
            name="locust-engine",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            "Locust引擎已启动: host=%s, users=%d, spawn_rate=%.1f",
            self._config.host,
            self._config.users,
            self._config.spawn_rate,
        )
        return True

    def pause(self) -> bool:
        """暂停压测（停止所有虚拟用户，保留运行器）"""
        self._ensure_locust_imported()
        with self._lock:
            if self._state != EngineState.RUNNING:
                logger.warning("引擎未在运行中，无法暂停")
                return False

        try:
            if self._runner:
                self._runner.stop()
            self._state = EngineState.PAUSED
            logger.info("Locust引擎已暂停")
            return True
        except Exception as e:
            logger.error("暂停引擎失败: %s", e)
            return False

    def resume(self) -> bool:
        """恢复压测（重新生成虚拟用户）"""
        self._ensure_locust_imported()
        with self._lock:
            if self._state != EngineState.PAUSED:
                logger.warning("引擎未在暂停状态，无法恢复")
                return False

        try:
            if self._runner:
                self._runner.start(self._config.users, self._config.spawn_rate)
            self._state = EngineState.RUNNING
            logger.info("Locust引擎已恢复运行")
            return True
        except Exception as e:
            logger.error("恢复引擎失败: %s", e)
            return False

    def stop(self) -> bool:
        """停止压测并清理资源"""
        self._ensure_locust_imported()
        with self._lock:
            if self._state in (EngineState.IDLE, EngineState.STOPPED):
                logger.warning("引擎未在运行中，无需停止")
                return False

        self._state = EngineState.STOPPING
        self._stop_event.set()

        try:
            if self._runner:
                self._runner.quit()
            self._state = EngineState.STOPPED
            logger.info("Locust引擎已停止")
            return True
        except Exception as e:
            logger.error("停止引擎失败: %s", e)
            self._state = EngineState.STOPPED
            return False

    def wait_for_complete(self, timeout: float | None = None) -> bool:
        """等待压测完成，返回是否在超时前完成"""
        if self._thread is None:
            return False
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def get_stats(self) -> dict[str, Any]:
        """获取当前统计数据，响应时间单位为毫秒"""
        self._ensure_locust_imported()
        if not self._environment or not self._runner:
            return self._empty_stats()

        stats = self._environment.stats
        total = stats.total

        result: dict[str, Any] = {
            "timestamp": time.time(),
            "elapsed_seconds": time.time() - self._start_time if self._start_time else 0,
            "user_count": self._runner.user_count if self._runner else 0,
            "rps": total.total_rps,
            "total_requests": total.num_requests,
            "total_failures": total.num_failures,
            "failure_rate": (
                total.num_failures / total.num_requests
                if total.num_requests > 0
                else 0.0
            ),
            "avg_response_time": total.avg_response_time,
            "min_response_time": total.min_response_time or 0,
            "max_response_time": total.max_response_time or 0,
            "median_response_time": self._safe_percentile(total, 0.5),
            "p95_response_time": self._safe_percentile(total, 0.95),
            "p99_response_time": self._safe_percentile(total, 0.99),
            "total_content_length": total.total_content_length,
            "requests_per_method": {},
            "errors": [],
        }

        for key, entry in stats.entries.items():
            method, name = key
            entry_key = f"{method} {name}"
            result["requests_per_method"][entry_key] = {
                "num_requests": entry.num_requests,
                "num_failures": entry.num_failures,
                "avg_response_time": entry.avg_response_time,
                "min_response_time": entry.min_response_time or 0,
                "max_response_time": entry.max_response_time or 0,
                "median_response_time": self._safe_percentile(entry, 0.5),
                "p95_response_time": self._safe_percentile(entry, 0.95),
                "p99_response_time": self._safe_percentile(entry, 0.99),
                "rps": entry.total_rps,
            }

        for error in stats.errors.values():
            result["errors"].append(
                {
                    "method": error.method,
                    "name": error.name,
                    "error": error.error,
                    "occurrences": error.occurrences,
                }
            )

        return result

    def get_request_records(self) -> list[dict[str, Any]]:
        """获取所有请求记录列表"""
        return list(self._request_records)

    def clear_request_records(self) -> None:
        """清空请求记录"""
        self._request_records.clear()

    def update_config(self, **kwargs: Any) -> None:
        """更新引擎配置（仅在引擎未运行时可用）"""
        if self._state == EngineState.RUNNING:
            logger.warning("引擎运行中，无法更新配置")
            return

        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
            else:
                logger.warning("未知的配置项: %s", key)

        if "csv_file" in kwargs:
            self._load_csv_data()

        auth_keys = {"auth_token", "auth_type", "auth_username", "auth_password"}
        if auth_keys & set(kwargs.keys()):
            self._build_auth_headers()

        logger.info("引擎配置已更新")

    @staticmethod
    def _safe_percentile(stats_entry: Any, percentile: float) -> float:
        """安全获取百分位响应时间，异常时返回0"""
        try:
            return stats_entry.get_response_time_percentile(percentile)
        except Exception:
            return 0.0

    @staticmethod
    def _empty_stats() -> dict[str, Any]:
        """返回空统计数据"""
        return {
            "timestamp": time.time(),
            "elapsed_seconds": 0,
            "user_count": 0,
            "rps": 0.0,
            "total_requests": 0,
            "total_failures": 0,
            "failure_rate": 0.0,
            "avg_response_time": 0.0,
            "min_response_time": 0,
            "max_response_time": 0,
            "median_response_time": 0.0,
            "p95_response_time": 0.0,
            "p99_response_time": 0.0,
            "total_content_length": 0,
            "requests_per_method": {},
            "errors": [],
        }

    def _load_csv_data(self) -> None:
        """加载CSV数据文件用于数据驱动测试"""
        if not self._config.csv_file:
            return

        csv_path = Path(self._config.csv_file)
        if not csv_path.exists():
            logger.warning("CSV数据文件不存在: %s", csv_path)
            return

        try:
            self._csv_data = read_csv(
                csv_path,
                encoding=self._config.csv_encoding,
                delimiter=self._config.csv_delimiter,
            )
            logger.info("已加载CSV数据: %d 行, 文件=%s", len(self._csv_data), csv_path)
        except Exception as e:
            logger.error("加载CSV数据失败: %s", e)
            self._csv_data = []

    def _build_auth_headers(self) -> None:
        """根据配置构建认证请求头（支持Bearer JWT和Basic认证）"""
        self._auth_headers = {}

        if not self._config.auth_token:
            return

        auth_type = self._config.auth_type.lower()
        if auth_type == "bearer":
            self._auth_headers["Authorization"] = f"Bearer {self._config.auth_token}"
        elif auth_type == "basic":
            username = self._config.auth_username or ""
            password = self._config.auth_password or ""
            credentials = f"{username}:{password}"
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
            self._auth_headers["Authorization"] = f"Basic {encoded}"

    def _create_wait_time(self) -> Any:
        """根据配置创建Locust等待时间策略"""
        self._ensure_locust_imported()
        wait_type = self._config.wait_type.lower()
        if wait_type == "constant":
            return LocustEngine._constant(self._config.wait_min)
        elif wait_type == "constant_throughput":
            return LocustEngine._constant_throughput(self._config.wait_min)
        else:
            return LocustEngine._between(self._config.wait_min, self._config.wait_max)

    def _make_http_task(self, task_cfg: TaskConfig) -> Callable:
        """
        创建HTTP任务函数

        根据TaskConfig动态生成一个可被Locust调度的任务函数，
        支持GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS方法，
        支持自定义Header、Cookie、认证、JSON/表单/文件上传请求体，
        支持参数化变量和CSV数据驱动。
        """
        variables = dict(self._config.variables)
        csv_data = list(self._csv_data)
        auth_headers = dict(self._auth_headers)

        def task_func(user_instance: LocustEngine._HttpUser) -> None:
            # 获取当前用户的CSV行数据（轮询方式）
            csv_row: dict[str, str] | None = None
            if csv_data:
                counter = getattr(user_instance, "_csv_counter", 0)
                idx = counter % len(csv_data)
                csv_row = csv_data[idx]
                user_instance._csv_counter = counter + 1

            # 对路径进行变量替换
            path = substitute_variables(task_cfg.path, variables, csv_row)

            # 合并认证头和自定义请求头
            headers = dict(auth_headers)
            headers.update(_substitute_dict(task_cfg.headers, variables, csv_row))

            # 变量替换Cookie和查询参数
            cookies = (
                _substitute_dict(task_cfg.cookies, variables, csv_row)
                if task_cfg.cookies
                else {}
            )
            params = (
                _substitute_dict(task_cfg.params, variables, csv_row)
                if task_cfg.params
                else {}
            )

            method = task_cfg.method.upper()
            task_name = substitute_variables(task_cfg.name, variables, csv_row)

            # 构建请求关键字参数
            request_kwargs: dict[str, Any] = {
                "name": task_name,
                "timeout": task_cfg.timeout,
                "verify": task_cfg.verify_ssl,
            }
            if headers:
                request_kwargs["headers"] = headers
            if cookies:
                request_kwargs["cookies"] = cookies
            if params:
                request_kwargs["params"] = params

            # 设置请求体（JSON/表单/文件上传互斥优先级）
            opened_files: list = []
            try:
                if task_cfg.json_body is not None:
                    request_kwargs["json"] = _substitute_json_body(
                        task_cfg.json_body, variables, csv_row
                    )
                elif task_cfg.files:
                    # 文件上传（multipart/form-data）
                    files_list: list[tuple] = []
                    for file_info in task_cfg.files:
                        field_name = file_info.get("field", "file")
                        file_path = substitute_variables(
                            file_info.get("path", ""), variables, csv_row
                        )
                        content_type = file_info.get("content_type")
                        if os.path.isfile(file_path):
                            f = open(file_path, "rb")
                            opened_files.append(f)
                            file_name = os.path.basename(file_path)
                            if content_type:
                                files_list.append(
                                    (field_name, (file_name, f, content_type))
                                )
                            else:
                                files_list.append((field_name, (file_name, f)))
                    request_kwargs["files"] = files_list
                    # 文件上传可同时携带表单字段
                    if task_cfg.form_data:
                        request_kwargs["data"] = _substitute_dict(
                            task_cfg.form_data, variables, csv_row
                        )
                elif task_cfg.form_data:
                    request_kwargs["data"] = _substitute_dict(
                        task_cfg.form_data, variables, csv_row
                    )

                # 根据HTTP方法执行请求
                client = user_instance.client
                if method == "GET":
                    client.get(path, **request_kwargs)
                elif method == "POST":
                    client.post(path, **request_kwargs)
                elif method == "PUT":
                    client.put(path, **request_kwargs)
                elif method == "DELETE":
                    client.delete(path, **request_kwargs)
                elif method == "PATCH":
                    client.patch(path, **request_kwargs)
                elif method == "HEAD":
                    client.head(path, **request_kwargs)
                elif method == "OPTIONS":
                    client.options(path, **request_kwargs)
                else:
                    logger.warning("不支持的HTTP方法: %s", method)

            except Exception as e:
                logger.error("请求执行异常: %s %s - %s", method, path, e)
            finally:
                # 确保所有打开的文件句柄被关闭
                for f in opened_files:
                    try:
                        f.close()
                    except Exception:
                        pass

        task_func.__name__ = task_cfg.name
        task_func.locust_task_weight = task_cfg.weight
        return task_func

    def _make_ws_task(self, task_cfg: TaskConfig) -> Callable:
        """
        创建WebSocket任务函数

        根据TaskConfig动态生成WebSocket压测任务函数，
        支持连接、发送消息、接收响应、持续指定时长。
        需要安装 websocket-client 库。
        """
        if not _WS_AVAILABLE:
            raise ImportError(
                "WebSocket压测需要安装 websocket-client 库: pip install websocket-client"
            )

        variables = dict(self._config.variables)
        csv_data = list(self._csv_data)
        auth_headers = dict(self._auth_headers)
        host = self._config.host

        def task_func(user_instance: LocustEngine._User) -> None:
            # 获取当前CSV行数据
            csv_row: dict[str, str] | None = None
            if csv_data:
                counter = getattr(user_instance, "_csv_counter", 0)
                idx = counter % len(csv_data)
                csv_row = csv_data[idx]
                user_instance._csv_counter = counter + 1

            # 构建WebSocket URL（http->ws, https->wss）
            ws_path = substitute_variables(
                task_cfg.ws_path or task_cfg.path, variables, csv_row
            )
            ws_url = host.replace("http://", "ws://").replace("https://", "wss://")
            if not ws_url.endswith("/") and not ws_path.startswith("/"):
                ws_url += "/"
            ws_url += ws_path

            # 构建请求头
            headers = dict(auth_headers)
            headers.update(_substitute_dict(task_cfg.headers, variables, csv_row))
            ws_headers = [f"{k}: {v}" for k, v in headers.items()]

            start_time = time.time()
            request_meta = {
                "request_type": "WS",
                "name": task_cfg.name,
                "response_time": 0,
                "response_length": 0,
                "exception": None,
                "context": {},
            }

            try:
                ws_conn = _ws_client.create_connection(
                    ws_url,
                    header=ws_headers,
                    timeout=task_cfg.timeout,
                )

                # 准备消息列表
                messages = task_cfg.ws_messages or (
                    [task_cfg.ws_message] if task_cfg.ws_message else []
                )
                msg_idx = 0
                total_bytes = 0

                # 在指定时长内循环发送和接收消息
                while time.time() - start_time < task_cfg.ws_duration:
                    if messages:
                        msg = substitute_variables(
                            messages[msg_idx % len(messages)], variables, csv_row
                        )
                        ws_conn.send(msg)
                        total_bytes += len(msg.encode("utf-8"))
                        msg_idx += 1

                    if task_cfg.ws_receive:
                        remaining = task_cfg.ws_duration - (time.time() - start_time)
                        ws_conn.settimeout(max(0.1, remaining))
                        try:
                            recv_data = ws_conn.recv()
                            if recv_data:
                                total_bytes += len(
                                    recv_data.encode("utf-8")
                                    if isinstance(recv_data, str)
                                    else recv_data
                                )
                        except _ws_client.WebSocketTimeoutException:
                            pass

                    LocustEngine._gevent.sleep(0.1)

                ws_conn.close()

                # 记录成功的WebSocket请求统计
                request_meta["response_time"] = (time.time() - start_time) * 1000
                request_meta["response_length"] = total_bytes

            except Exception as e:
                request_meta["response_time"] = (time.time() - start_time) * 1000
                request_meta["exception"] = e
                logger.error("WebSocket任务执行异常: %s - %s", ws_url, e)

            # 通过Locust事件系统记录请求统计
            if user_instance.environment:
                user_instance.environment.events.request.fire(**request_meta)

        task_func.__name__ = task_cfg.name
        task_func.locust_task_weight = task_cfg.weight
        return task_func

    def _create_user_classes(self) -> list[type]:
        """根据任务配置动态创建Locust User类列表"""
        http_tasks: list[TaskConfig] = []
        ws_tasks: list[TaskConfig] = []

        for task_cfg in self._config.tasks:
            if task_cfg.method.upper() == "WEBSOCKET":
                ws_tasks.append(task_cfg)
            else:
                http_tasks.append(task_cfg)

        user_classes: list[type] = []

        if http_tasks:
            user_classes.append(self._build_http_user_class(http_tasks))

        if ws_tasks:
            user_classes.append(self._build_ws_user_class(ws_tasks))

        return user_classes

    def _build_http_user_class(self, task_configs: list[TaskConfig]) -> type:
        """
        构建动态HttpUser子类

        使用type()动态创建HttpUser子类，将任务配置转换为
        Locust可调度的任务函数，并设置权重、等待时间等属性。
        """
        self._ensure_locust_imported()
        task_funcs = [self._make_http_task(tc) for tc in task_configs]
        wait_time = self._create_wait_time()
        csv_data = list(self._csv_data)

        def on_start(self) -> None:
            """用户启动时初始化CSV计数器"""
            self._csv_counter = 0

        class_dict: dict[str, Any] = {
            "host": self._config.host,
            "wait_time": wait_time,
            "tasks": OrderedDict(
                {func: func.locust_task_weight for func in task_funcs}
            ),
            "on_start": on_start,
        }

        user_class = type("DynamicHttpUser", (LocustEngine._HttpUser,), class_dict)
        return user_class

    def _build_ws_user_class(self, task_configs: list[TaskConfig]) -> type:
        """
        构建动态WebSocket User子类

        使用type()动态创建User子类（非HttpUser），
        专门用于WebSocket协议的压测任务。
        """
        self._ensure_locust_imported()
        task_funcs = [self._make_ws_task(tc) for tc in task_configs]
        wait_time = self._create_wait_time()

        def on_start(self) -> None:
            """用户启动时初始化CSV计数器"""
            self._csv_counter = 0

        class_dict: dict[str, Any] = {
            "host": self._config.host,
            "wait_time": wait_time,
            "tasks": OrderedDict(
                {func: func.locust_task_weight for func in task_funcs}
            ),
            "on_start": on_start,
        }

        user_class = type("DynamicWebSocketUser", (LocustEngine._User,), class_dict)
        return user_class

    def _run(self) -> None:
        """
        在后台线程中运行Locust

        创建Locust Environment和LocalRunner，注册事件钩子，
        启动压测并等待完成或手动停止。
        """
        try:
            self._ensure_locust_imported()
            self._state = EngineState.RUNNING

            # 动态创建User类
            self._user_classes = self._create_user_classes()
            if not self._user_classes:
                logger.error("没有可用的任务配置，无法启动Locust")
                self._state = EngineState.STOPPED
                return

            # 创建Locust环境
            self._environment = LocustEngine._Environment(user_classes=self._user_classes)
            self._register_event_hooks()

            # 创建本地运行器
            self._runner = self._environment.create_local_runner()

            # 启动统计收集定时器
            self._start_stats_greenlet()

            # 启动压测
            self._runner.start(self._config.users, self._config.spawn_rate)
            logger.info(
                "Locust压测已开始: users=%d, spawn_rate=%.1f, host=%s",
                self._config.users,
                self._config.spawn_rate,
                self._config.host,
            )

            # 计算运行时间
            run_seconds = parse_run_time(self._config.run_time)

            if run_seconds > 0:
                # 有限时长：等待运行时间结束或收到停止信号
                self._stop_event.wait(timeout=run_seconds)
            else:
                # 无限运行直到手动停止
                while not self._stop_event.is_set():
                    LocustEngine._gevent.sleep(1)

            # 自然结束或被停止信号中断后，停止运行器
            if self._runner and self._state == EngineState.RUNNING:
                self._runner.stop()
                logger.info("Locust压测自然结束")

        except Exception as e:
            logger.error("Locust引擎运行异常: %s", e)
        finally:
            self._cleanup()

    def _register_event_hooks(self) -> None:
        """注册Locust事件钩子，用于收集统计数据和状态变更通知"""
        if not self._environment:
            return

        events = self._environment.events

        events.request.add_listener(self._on_request)
        events.test_start.add_listener(self._on_test_start)
        events.test_stop.add_listener(self._on_test_stop)
        events.user_error.add_listener(self._on_user_error)

        logger.info("已注册Locust事件钩子")

    def _on_request(
        self,
        request_type: str,
        name: str,
        response_time: float,
        response_length: int,
        exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """
        请求事件回调

        每次HTTP请求完成后由Locust触发，收集请求的详细数据
        包括请求类型、名称、响应时间、响应长度和异常信息。
        """
        record: dict[str, Any] = {
            "timestamp": time.time(),
            "request_type": request_type,
            "name": name,
            "response_time": response_time,
            "response_length": response_length,
            "exception": str(exception) if exception else None,
            "success": exception is None,
        }
        self._request_records.append(record)

    def _on_test_start(self, **kwargs: Any) -> None:
        """测试开始事件回调"""
        logger.info("Locust测试已开始")
        self._start_time = time.time()

    def _on_test_stop(self, **kwargs: Any) -> None:
        """测试结束事件回调"""
        logger.info("Locust测试已结束")

    def _on_user_error(
        self, user_instance: Any, exception: Exception, **kwargs: Any
    ) -> None:
        """
        用户错误事件回调

        当虚拟用户发生错误时触发，如果配置了stop_on_error
        则自动停止整个压测。
        """
        logger.error(
            "用户错误: %s - %s", type(user_instance).__name__, exception
        )
        if self._config.stop_on_error:
            logger.warning("配置了stop_on_error，正在停止引擎")
            self.stop()

    def _start_stats_greenlet(self) -> None:
        """启动统计收集的gevent greenlet，定时调用统计回调"""
        self._ensure_locust_imported()
        if self._stats_greenlet:
            try:
                self._stats_greenlet.kill()
            except Exception:
                pass

        self._stats_greenlet = LocustEngine._gevent.spawn(self._stats_loop)

    def _stats_loop(self) -> None:
        """
        统计收集循环

        以配置的间隔定时收集统计数据并通过回调函数
        传递QPS/TPS/RPS/响应时间/失败率等指标。
        """
        self._ensure_locust_imported()
        while self._state == EngineState.RUNNING:
            LocustEngine._gevent.sleep(self._config.stats_interval)
            if self._stats_callback and self._state == EngineState.RUNNING:
                try:
                    stats = self.get_stats()
                    self._stats_callback(stats)
                except Exception as e:
                    logger.error("统计回调执行异常: %s", e)

    def _cleanup(self) -> None:
        """清理Locust引擎资源，停止greenlet和运行器"""
        try:
            if self._stats_greenlet:
                self._stats_greenlet.kill()
                self._stats_greenlet = None

            if self._runner:
                try:
                    self._runner.quit()
                except Exception:
                    pass
                self._runner = None

            self._environment = None
            self._state = EngineState.STOPPED

            logger.info("Locust引擎资源已清理")
        except Exception as e:
            logger.error("清理资源异常: %s", e)
            self._state = EngineState.STOPPED
