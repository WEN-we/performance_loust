import csv
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def resource_path(relative_path: str | Path) -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent
    return base_path / str(relative_path)


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_copy(src: str | Path, dst: str | Path) -> Path:
    src = Path(src)
    dst = Path(dst)
    ensure_dir(dst.parent)
    shutil.copy2(str(src), str(dst))
    return dst


def safe_move(src: str | Path, dst: str | Path) -> Path:
    src = Path(src)
    dst = Path(dst)
    ensure_dir(dst.parent)
    shutil.move(str(src), str(dst))
    return dst


def safe_delete(path: str | Path, missing_ok: bool = True) -> bool:
    p = Path(path)
    try:
        if p.is_file():
            p.unlink(missing_ok=missing_ok)
            return True
        elif p.is_dir():
            shutil.rmtree(str(p))
            return True
    except OSError:
        return False
    return False


def get_file_size(path: str | Path) -> int:
    p = Path(path)
    if p.exists() and p.is_file():
        return p.stat().st_size
    return 0


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    size = float(size_bytes)
    while size >= 1024.0 and index < len(units) - 1:
        size /= 1024.0
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.2f} {units[index]}"


def format_timestamp(
    dt: datetime | None = None,
    fmt: str = "%Y-%m-%d %H:%M:%S",
) -> str:
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)


def parse_timestamp(ts_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    return datetime.strptime(ts_str, fmt)


def format_duration(seconds: float) -> str:
    if seconds < 0:
        return "0s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return "".join(parts)


def read_csv(
    file_path: str | Path,
    encoding: str = "utf-8",
    delimiter: str = ",",
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    p = Path(file_path)
    if not p.exists():
        return result

    with open(p, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            result.append(dict(row))
    return result


def write_csv(
    file_path: str | Path,
    data: list[dict[str, Any]],
    encoding: str = "utf-8",
    delimiter: str = ",",
) -> None:
    if not data:
        return

    p = Path(file_path)
    ensure_dir(p.parent)

    fieldnames = list(data[0].keys())
    with open(p, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(data)


def load_json(
    file_path: str | Path,
    encoding: str = "utf-8",
    default: Any = None,
) -> Any:
    p = Path(file_path)
    if not p.exists():
        return default

    try:
        with open(p, "r", encoding=encoding) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(
    file_path: str | Path,
    data: Any,
    encoding: str = "utf-8",
    indent: int = 4,
    ensure_ascii: bool = False,
) -> None:
    p = Path(file_path)
    ensure_dir(p.parent)

    with open(p, "w", encoding=encoding) as f:
        json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)


def list_files(
    directory: str | Path,
    pattern: str = "*",
    recursive: bool = False,
) -> list[Path]:
    p = Path(directory)
    if not p.exists():
        return []

    if recursive:
        return sorted(p.rglob(pattern))
    return sorted(p.glob(pattern))


def read_text(
    file_path: str | Path,
    encoding: str = "utf-8",
) -> str:
    p = Path(file_path)
    if not p.exists():
        return ""
    return p.read_text(encoding=encoding)


def write_text(
    file_path: str | Path,
    content: str,
    encoding: str = "utf-8",
) -> None:
    p = Path(file_path)
    ensure_dir(p.parent)
    p.write_text(content, encoding=encoding)
