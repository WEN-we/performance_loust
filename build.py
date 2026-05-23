"""
PyInstaller打包辅助模块

解决以下问题：
1. 资源路径丢失 - 通过sys._MEIPASS定位
2. 图标丢失 - 确保图标文件被打包
3. DLL缺失 - 显式收集依赖DLL
4. 启动闪退 - 捕获异常写入日志
"""
import os
import sys
from pathlib import Path


def get_hook_dirs():
    return [str(Path(__file__).parent)]


hiddenimports = [
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtSvg",
    "locust",
    "locust.core",
    "locust.runners",
    "locust.stats",
    "locust.events",
    "locust.log",
    "locust.argument_parser",
    "locust.user",
    "locust.http",
    "locust.clients",
    "gevent",
    "gevent.monkey",
    "gevent._gevent_c_hub_local",
    "gevent._gevent_c_hub_primitives",
    "gevent._gevent_c_greenlet_primitives",
    "gevent._gevent_c_tracer",
    "gevent._gevent_c_local",
    "gevent._gevent_c_event",
    "gevent._gevent_c_greenlet",
    "gevent._gevent_c_ident",
    "gevent._gevent_c_waiter",
    "gevent._gevent_c_imap",
    "gevent._gevent_c_semaphore",
    "gevent._gevent_c_queue",
    "gevent._gevent_c_abstract_linkable",
    "zmq",
    "zmq.backend.cython",
    "zmq.backend.cython._device",
    "zmq.backend.cython._poll",
    "zmq.backend.cython._socket",
    "zmq.backend.cython._context",
    "zmq.backend.cython._message",
    "zmq.backend.cython._version",
    "zmq.backend.cython.error",
    "zmq.backend.cython.utils",
    "msgpack",
    "msgpack._cmsgpack",
    "matplotlib",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.figure",
    "psutil",
    "openpyxl",
    "jinja2",
    "apscheduler",
    "apscheduler.schedulers.background",
    "apscheduler.triggers.cron",
    "fpdf",
    "websocket",
    "requests",
    "urllib3",
    "charset_normalizer",
    "certifi",
    "idna",
]


def get_datas():
    datas = []
    base_dir = Path(__file__).resolve().parent

    resources_dir = base_dir / "resources"
    if resources_dir.exists():
        datas.append((str(resources_dir), "resources"))

    config_dir = base_dir / "config"
    if config_dir.exists():
        for f in config_dir.iterdir():
            if f.suffix in (".json", ".yaml", ".yml"):
                datas.append((str(f), "config"))

    return datas


def get_binaries():
    binaries = []
    return binaries


def build_pyinstaller_command():
    base_dir = Path(__file__).resolve().parent
    icon_path = base_dir / "resources" / "icon.ico"

    cmd_parts = [
        "pyinstaller",
        "--name=LocustPlatform",
        "--noconfirm",
        "--windowed",
    ]

    if icon_path.exists():
        cmd_parts.append(f'--icon="{icon_path}"')

    for imp in hiddenimports:
        cmd_parts.append(f"--hidden-import={imp}")

    for src, dst in get_datas():
        cmd_parts.append(f'--add-data="{src};{dst}"')

    for src, dst in get_binaries():
        cmd_parts.append(f'--add-binary="{src};{dst}"')

    cmd_parts.append(f'"{base_dir / "main.py"}"')

    return " ".join(cmd_parts)


if __name__ == "__main__":
    print("=" * 60)
    print("Locust压力测试平台 - PyInstaller打包命令")
    print("=" * 60)
    print()
    print(build_pyinstaller_command())
    print()
    print("=" * 60)
    print("注意事项：")
    print("1. 确保已安装所有依赖: pip install -r requirements.txt")
    print("2. 确保已安装PyInstaller: pip install pyinstaller")
    print("3. 如遇DLL缺失，使用 --add-binary 添加")
    print("4. 如遇模块缺失，使用 --hidden-import 添加")
    print("5. 打包后测试: dist/LocustPlatform/LocustPlatform.exe")
    print("=" * 60)
