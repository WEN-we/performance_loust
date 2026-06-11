import logging
import sys
import traceback
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TextIO


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_loggers: dict[str, logging.Logger] = {}
_initialized = False


class _TracebackFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return True


class _ErrorTracebackHandler(logging.Handler):
    def __init__(self, stream: TextIO | None = None) -> None:
        super().__init__(logging.ERROR)
        self.stream = stream or sys.stderr

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if record.exc_info and record.exc_info[0] is not None:
                tb_text = "".join(traceback.format_exception(*record.exc_info))
                msg = msg + "\n" + tb_text
            self.stream.write(msg + "\n")
            self.stream.flush()
        except Exception:
            self.handleError(record)


def setup_logger(
    name: str = "performance_loust",
    log_dir: str | Path = "logs",
    level: int = logging.INFO,
    max_days: int = 30,
    console: bool = True,
) -> logging.Logger:
    global _initialized

    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / f"{name}.log"
    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=max_days,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"
    logger.addHandler(file_handler)

    error_handler = _ErrorTracebackHandler(stream=sys.stderr)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    _loggers[name] = logger
    _initialized = True

    return logger


def get_logger(name: str = "performance_loust") -> logging.Logger:
    if name in _loggers:
        return _loggers[name]

    if _initialized:
        parent = _loggers.get("performance_loust")
        if parent is not None:
            child = logging.getLogger(f"performance_loust.{name}")
            child.setLevel(parent.level)
            child.propagate = True
            _loggers[name] = child
            return child
        # 已初始化但找不到父logger（极端情况），fallback到直接设置
        return setup_logger(name)

    return setup_logger(name)


def set_log_level(level: int | str) -> None:
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    for logger in _loggers.values():
        logger.setLevel(level)
        for handler in logger.handlers:
            if not isinstance(handler, _ErrorTracebackHandler):
                handler.setLevel(level)


def shutdown() -> None:
    for logger in _loggers.values():
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
    _loggers.clear()
    logging.shutdown()
