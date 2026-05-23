import json
import os
import sys
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG = {
    "thread_count": 4,
    "timeout": 30,
    "theme": "light",
    "log_dir": "logs",
    "export_dir": "exports",
    "database_path": "data/performance.db",
    "locust_host": "http://localhost:8089",
    "locust_users": 10,
    "locust_spawn_rate": 1,
    "locust_run_time": "5m",
    "window_width": 1280,
    "window_height": 800,
    "language": "zh_CN",
    "auto_save": True,
    "auto_save_interval": 60,
    "max_log_files": 30,
    "csv_delimiter": ",",
    "encoding": "utf-8",
}


class Settings:
    _instance = None
    _config: dict[str, Any]
    _config_path: Path

    def __new__(cls, config_path: str | Path | None = None) -> "Settings":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str | Path | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True

        if config_path is None:
            base_dir = self._get_base_dir()
            config_path = base_dir / "config" / "settings.json"
        self._config_path = Path(config_path)

        self._config = dict(_DEFAULT_CONFIG)
        self._load()

    @staticmethod
    def _get_base_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        return Path(__file__).resolve().parent.parent

    def _load(self) -> None:
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                self._config.update(user_config)
            except (json.JSONDecodeError, OSError) as e:
                print(f"[Settings] 加载配置文件失败，使用默认配置: {e}")

    def save(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
        except OSError as e:
            print(f"[Settings] 保存配置文件失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value

    def update(self, data: dict[str, Any]) -> None:
        self._config.update(data)

    def remove(self, key: str) -> bool:
        if key in self._config:
            del self._config[key]
            return True
        return False

    def reset_to_default(self) -> None:
        self._config = dict(_DEFAULT_CONFIG)

    @property
    def all_settings(self) -> dict[str, Any]:
        return dict(self._config)

    @property
    def thread_count(self) -> int:
        return int(self._config.get("thread_count", 4))

    @thread_count.setter
    def thread_count(self, value: int) -> None:
        self._config["thread_count"] = max(1, int(value))

    @property
    def timeout(self) -> int:
        return int(self._config.get("timeout", 30))

    @timeout.setter
    def timeout(self, value: int) -> None:
        self._config["timeout"] = max(1, int(value))

    @property
    def theme(self) -> str:
        return str(self._config.get("theme", "light"))

    @theme.setter
    def theme(self, value: str) -> None:
        if value in ("light", "dark"):
            self._config["theme"] = value

    @property
    def log_dir(self) -> Path:
        base = self._get_base_dir()
        return base / str(self._config.get("log_dir", "logs"))

    @property
    def export_dir(self) -> Path:
        base = self._get_base_dir()
        return base / str(self._config.get("export_dir", "exports"))

    @property
    def database_path(self) -> Path:
        base = self._get_base_dir()
        return base / str(self._config.get("database_path", "data/performance.db"))

    @property
    def locust_host(self) -> str:
        return str(self._config.get("locust_host", "http://localhost:8089"))

    @locust_host.setter
    def locust_host(self, value: str) -> None:
        self._config["locust_host"] = value

    @property
    def locust_users(self) -> int:
        return int(self._config.get("locust_users", 10))

    @locust_users.setter
    def locust_users(self, value: int) -> None:
        self._config["locust_users"] = max(1, int(value))

    @property
    def locust_spawn_rate(self) -> int:
        return int(self._config.get("locust_spawn_rate", 1))

    @locust_spawn_rate.setter
    def locust_spawn_rate(self, value: int) -> None:
        self._config["locust_spawn_rate"] = max(1, int(value))

    @property
    def locust_run_time(self) -> str:
        return str(self._config.get("locust_run_time", "5m"))

    @locust_run_time.setter
    def locust_run_time(self, value: str) -> None:
        self._config["locust_run_time"] = value

    @property
    def window_size(self) -> tuple[int, int]:
        w = int(self._config.get("window_width", 1280))
        h = int(self._config.get("window_height", 800))
        return w, h

    @window_size.setter
    def window_size(self, size: tuple[int, int]) -> None:
        self._config["window_width"] = size[0]
        self._config["window_height"] = size[1]

    @property
    def language(self) -> str:
        return str(self._config.get("language", "zh_CN"))

    @language.setter
    def language(self, value: str) -> None:
        self._config["language"] = value

    @property
    def auto_save(self) -> bool:
        return bool(self._config.get("auto_save", True))

    @auto_save.setter
    def auto_save(self, value: bool) -> None:
        self._config["auto_save"] = value

    @property
    def auto_save_interval(self) -> int:
        return int(self._config.get("auto_save_interval", 60))

    @auto_save_interval.setter
    def auto_save_interval(self, value: int) -> None:
        self._config["auto_save_interval"] = max(10, int(value))

    @property
    def max_log_files(self) -> int:
        return int(self._config.get("max_log_files", 30))

    @max_log_files.setter
    def max_log_files(self, value: int) -> None:
        self._config["max_log_files"] = max(1, int(value))

    @property
    def csv_delimiter(self) -> str:
        return str(self._config.get("csv_delimiter", ","))

    @property
    def encoding(self) -> str:
        return str(self._config.get("encoding", "utf-8"))

    def __repr__(self) -> str:
        return f"Settings(config_path={self._config_path!r}, items={len(self._config)})"


_settings_instance: Settings | None = None


def get_settings(config_path: str | Path | None = None) -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings(config_path)
    return _settings_instance
