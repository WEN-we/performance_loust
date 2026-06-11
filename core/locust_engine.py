"""
Locust引擎核心模块

使用ThreadPoolExecutor + requests实现并发压测，
支持HTTP/HTTPS压测、参数化变量、CSV数据驱动等功能。
"""

import base64
import os
import re
import time
import threading
import random
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import get_logger
from utils.helpers import read_csv

logger = get_logger("locust_engine")


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


def substitute_variables(template, variables, csv_row=None):
    """替换模板中的变量 ${var_name}，优先使用CSV行数据"""
    if not template:
        return template

    def _replacer(match):
        var_name = match.group(1)
        if csv_row and var_name in csv_row:
            return str(csv_row[var_name])
        if var_name in variables:
            return str(variables[var_name])
        return match.group(0)

    return _VAR_PATTERN.sub(_replacer, template)


def parse_run_time(run_time):
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


def _substitute_dict(data, variables, csv_row=None):
    """对字典中所有值进行变量替换"""
    return {k: substitute_variables(v, variables, csv_row) for k, v in data.items()}


def _substitute_json_body(body, variables, csv_row=None):
    """对JSON请求体递归进行变量替换"""
    if isinstance(body, str):
        return substitute_variables(body, variables, csv_row)
    if isinstance(body, dict):
        return {k: _substitute_json_body(v, variables, csv_row) for k, v in body.items()}
    if isinstance(body, list):
        return [_substitute_json_body(item, variables, csv_row) for item in body]
    return body


class LocustEngine:
    """Locust引擎核心类，使用ThreadPoolExecutor实现并发压测"""

    def __init__(self, config=None):
        self._config = config or EngineConfig()
        self._state = EngineState.IDLE
        self._executor = None
        self._stats_callback = None
        self._csv_data = []
        self._start_time = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._request_records = []
        self._auth_headers = {}
        self._stats_thread = None
        self._active_users = 0
        self._total_requests = 0
        self._total_failures = 0
        self._response_times = []
        self._errors = []

        self._load_csv_data()
        self._build_auth_headers()

    @property
    def state(self):
        return self._state

    @property
    def is_running(self):
        return self._state == EngineState.RUNNING

    @property
    def config(self):
        return self._config

    def set_stats_callback(self, callback):
        self._stats_callback = callback

    def start(self):
        if self._state == EngineState.RUNNING:
            logger.warning("引擎已在运行中，无需重复启动")
            return False

        self._stop_event.clear()
        self._request_records.clear()
        self._start_time = time.time()
        self._active_users = 0
        self._total_requests = 0
        self._total_failures = 0
        self._response_times.clear()
        self._errors.clear()
        self._state = EngineState.RUNNING

        self._thread = threading.Thread(target=self._run_users, name="locust-engine", daemon=True)
        self._thread.start()

        self._stats_thread = threading.Thread(target=self._stats_loop, name="stats-collector", daemon=True)
        self._stats_thread.start()

        logger.info("压测引擎已启动: host=%s, users=%d, spawn_rate=%.1f", self._config.host, self._config.users, self._config.spawn_rate)
        return True

    def pause(self):
        if self._state != EngineState.RUNNING:
            return False
        self._state = EngineState.PAUSED
        logger.info("压测引擎已暂停")
        return True

    def resume(self):
        if self._state != EngineState.PAUSED:
            return False
        self._state = EngineState.RUNNING
        logger.info("压测引擎已恢复运行")
        return True

    def stop(self):
        if self._state in (EngineState.IDLE, EngineState.STOPPED):
            return False
        self._state = EngineState.STOPPING
        self._stop_event.set()
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
        self._state = EngineState.STOPPED
        logger.info("压测引擎已停止")
        return True

    def wait_for_complete(self, timeout=None):
        if self._thread is None:
            return False
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def get_stats(self):
        with self._lock:
            total_requests = self._total_requests
            total_failures = self._total_failures
            response_times = list(self._response_times)
            errors = list(self._errors)
            active_users = self._active_users

        elapsed = time.time() - self._start_time if self._start_time else 0
        avg_rt = statistics.mean(response_times) if response_times else 0
        min_rt = min(response_times) if response_times else 0
        max_rt = max(response_times) if response_times else 0
        p95_rt = (statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_rt) if response_times else 0
        rps = total_requests / max(elapsed, 1)

        return {
            "timestamp": time.time(),
            "elapsed_seconds": elapsed,
            "user_count": active_users,
            "rps": rps,
            "total_requests": total_requests,
            "total_failures": total_failures,
            "failure_rate": total_failures / total_requests if total_requests > 0 else 0.0,
            "avg_response_time": avg_rt,
            "min_response_time": min_rt,
            "max_response_time": max_rt,
            "p95_response_time": p95_rt,
            "errors": errors,
        }

    def get_request_records(self):
        with self._lock:
            return list(self._request_records)

    def clear_request_records(self):
        self._request_records.clear()

    def update_config(self, **kwargs):
        if self._state == EngineState.RUNNING:
            logger.warning("引擎运行中，无法更新配置")
            return
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        if "csv_file" in kwargs:
            self._load_csv_data()
        auth_keys = {"auth_token", "auth_type", "auth_username", "auth_password"}
        if auth_keys & set(kwargs.keys()):
            self._build_auth_headers()

    def _load_csv_data(self):
        if not self._config.csv_file:
            return
        csv_path = Path(self._config.csv_file)
        if not csv_path.exists():
            logger.warning("CSV数据文件不存在: %s", csv_path)
            return
        try:
            self._csv_data = read_csv(csv_path, encoding=self._config.csv_encoding, delimiter=self._config.csv_delimiter)
            logger.info("已加载CSV数据: %d 行", len(self._csv_data))
        except Exception as e:
            logger.error("加载CSV数据失败: %s", e)
            self._csv_data = []

    def _build_auth_headers(self):
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

    def _get_wait_time(self):
        wait_type = self._config.wait_type.lower()
        if wait_type == "constant":
            return self._config.wait_min
        return random.uniform(self._config.wait_min, self._config.wait_max)

    def _create_session(self):
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _send_request(self, session, task_cfg, csv_row):
        variables = dict(self._config.variables)
        path = substitute_variables(task_cfg.path, variables, csv_row)
        url = self._config.host.rstrip("/") + "/" + path.lstrip("/")

        headers = dict(self._auth_headers)
        headers.update(_substitute_dict(task_cfg.headers, variables, csv_row))
        cookies = _substitute_dict(task_cfg.cookies, variables, csv_row) if task_cfg.cookies else {}
        params = _substitute_dict(task_cfg.params, variables, csv_row) if task_cfg.params else {}
        method = task_cfg.method.upper()

        request_kwargs = {"timeout": task_cfg.timeout, "verify": task_cfg.verify_ssl}
        if headers:
            request_kwargs["headers"] = headers
        if cookies:
            request_kwargs["cookies"] = cookies
        if params:
            request_kwargs["params"] = params

        bodyless_methods = {"HEAD", "OPTIONS"}
        opened_files = []
        start_time = time.time()

        try:
            if method not in bodyless_methods:
                if task_cfg.json_body is not None:
                    request_kwargs["json"] = _substitute_json_body(task_cfg.json_body, variables, csv_row)
                elif task_cfg.files:
                    files_list = []
                    for file_info in task_cfg.files:
                        field_name = file_info.get("field", "file")
                        file_path = substitute_variables(file_info.get("path", ""), variables, csv_row)
                        content_type = file_info.get("content_type")
                        if os.path.isfile(file_path):
                            f = open(file_path, "rb")
                            opened_files.append(f)
                            file_name = os.path.basename(file_path)
                            if content_type:
                                files_list.append((field_name, (file_name, f, content_type)))
                            else:
                                files_list.append((field_name, (file_name, f)))
                    request_kwargs["files"] = files_list
                    if task_cfg.form_data:
                        request_kwargs["data"] = _substitute_dict(task_cfg.form_data, variables, csv_row)
                elif task_cfg.form_data:
                    request_kwargs["data"] = _substitute_dict(task_cfg.form_data, variables, csv_row)

            if method == "GET":
                response = session.get(url, **request_kwargs)
            elif method == "POST":
                response = session.post(url, **request_kwargs)
            elif method == "PUT":
                response = session.put(url, **request_kwargs)
            elif method == "DELETE":
                response = session.delete(url, **request_kwargs)
            elif method == "PATCH":
                response = session.patch(url, **request_kwargs)
            elif method == "HEAD":
                response = session.head(url, **request_kwargs)
            elif method == "OPTIONS":
                response = session.options(url, **request_kwargs)
            else:
                return {"success": False, "error": f"不支持的HTTP方法: {method}"}

            response_time = (time.time() - start_time) * 1000
            return {"success": True, "status_code": response.status_code, "response_time": response_time, "response_length": len(response.content)}

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {"success": False, "error": str(e), "response_time": response_time}
        finally:
            for f in opened_files:
                try:
                    f.close()
                except Exception:
                    pass

    def _user_worker(self, user_id):
        session = self._create_session()
        csv_data = list(self._csv_data)
        csv_counter = 0
        tasks = self._config.tasks
        if not tasks:
            with self._lock:
                self._active_users = max(0, self._active_users - 1)
            return

        weights = [t.weight for t in tasks]
        total_weight = sum(weights)

        while not self._stop_event.is_set():
            # 支持暂停/恢复
            if self._state == EngineState.PAUSED:
                time.sleep(0.5)
                continue
            if self._state != EngineState.RUNNING:
                break

            if total_weight > 0:
                r = random.uniform(0, total_weight)
                cumulative = 0
                task_cfg = tasks[0]
                for t in tasks:
                    cumulative += t.weight
                    if r <= cumulative:
                        task_cfg = t
                        break
            else:
                task_cfg = tasks[0]

            csv_row = None
            if csv_data:
                csv_row = csv_data[csv_counter % len(csv_data)]
                csv_counter += 1

            result = self._send_request(session, task_cfg, csv_row)

            with self._lock:
                self._total_requests += 1
                if result.get("success"):
                    self._response_times.append(result["response_time"])
                    if len(self._response_times) > 10000:
                        self._response_times = self._response_times[-5000:]
                else:
                    self._total_failures += 1
                    self._errors.append({"method": task_cfg.method, "name": task_cfg.name, "error": result.get("error", "Unknown"), "occurrences": 1})
                    if len(self._errors) > 100:
                        self._errors = self._errors[-50:]

                self._request_records.append({
                    "timestamp": time.time(),
                    "request_type": "HTTP",
                    "name": task_cfg.name,
                    "response_time": result.get("response_time", 0),
                    "response_length": result.get("response_length", 0),
                    "exception": result.get("error"),
                    "success": result.get("success", False),
                })
                if len(self._request_records) > 10000:
                    self._request_records = self._request_records[-5000:]

            wait_time = self._get_wait_time()
            if self._stop_event.wait(timeout=wait_time):
                break

        session.close()
        with self._lock:
            self._active_users = max(0, self._active_users - 1)

    def _run_users(self):
        try:
            run_seconds = parse_run_time(self._config.run_time)
            end_time = time.time() + run_seconds if run_seconds > 0 else float('inf')

            with ThreadPoolExecutor(max_workers=self._config.users) as executor:
                self._executor = executor
                futures = []

                for i in range(self._config.users):
                    if self._stop_event.is_set() or self._state != EngineState.RUNNING:
                        break
                    future = executor.submit(self._user_worker, i)
                    futures.append(future)
                    with self._lock:
                        self._active_users += 1
                    if self._config.spawn_rate > 0:
                        time.sleep(1.0 / self._config.spawn_rate)

                if run_seconds > 0:
                    remaining = end_time - time.time()
                    if remaining > 0:
                        self._stop_event.wait(timeout=remaining)
                else:
                    for future in as_completed(futures):
                        if self._stop_event.is_set():
                            break

            with self._lock:
                self._active_users = 0

        except Exception as e:
            logger.error("引擎运行异常: %s", e)
        finally:
            self._state = EngineState.STOPPED
            logger.info("Locust压测自然结束")

    def _stats_loop(self):
        while self._state in (EngineState.RUNNING, EngineState.PAUSED):
            if self._stats_callback and self._state == EngineState.RUNNING:
                try:
                    stats = self.get_stats()
                    self._stats_callback(stats)
                except Exception as e:
                    logger.error("统计回调执行异常: %s", e)

            for _ in range(int(self._config.stats_interval * 2)):
                if self._stop_event.is_set() or self._state not in (EngineState.RUNNING, EngineState.PAUSED):
                    return
                time.sleep(0.5)
