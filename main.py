import importlib.metadata
import os
import sys
from pathlib import Path


def setup_environment() -> None:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).resolve().parent

    os.environ.setdefault("APP_BASE_DIR", str(base_dir))

    data_dir = base_dir / "data"
    logs_dir = base_dir / "logs"
    exports_dir = base_dir / "exports"
    config_dir = base_dir / "config"

    for d in (data_dir, logs_dir, exports_dir, config_dir):
        d.mkdir(parents=True, exist_ok=True)


def check_dependencies() -> list[str]:
    missing = []
    required_packages = {
        "PySide6": "PySide6",
        "locust": "locust",
        "matplotlib": "matplotlib",
        "psutil": "psutil",
        "openpyxl": "openpyxl",
        "jinja2": "Jinja2",
        "apscheduler": "APScheduler",
        "fpdf": "fpdf2",
    }
    for module_name, package_name in required_packages.items():
        try:
            if module_name == "locust":
                importlib.metadata.version("locust")
            else:
                __import__(module_name)
        except (ImportError, importlib.metadata.PackageNotFoundError):
            missing.append(package_name)
        except Exception:
            pass
    return missing


def main() -> int:
    setup_environment()

    if getattr(sys, "frozen", False):
        os.environ["LOCUST_MODE"] = "standalone"

    missing = check_dependencies()
    if missing:
        print(f"缺少必要的依赖包: {', '.join(missing)}")
        print(f"请运行: pip install {' '.join(missing)}")
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "依赖缺失",
                f"缺少必要的依赖包:\n{chr(10).join(missing)}\n\n"
                f"请运行:\npip install {' '.join(missing)}",
            )
        except Exception:
            pass
        return 1

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("Locust压力测试平台")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("LocustPlatform")

    from utils.logger import setup_logger, get_logger
    setup_logger()
    logger = get_logger("main")
    logger.info("=" * 60)
    logger.info("Locust压力测试平台 启动中...")
    logger.info(f"Python版本: {sys.version}")
    logger.info(f"工作目录: {os.getcwd()}")
    logger.info("=" * 60)

    from config.settings import get_settings
    settings = get_settings()
    logger.info(f"配置加载完成: {settings}")

    from database.db_manager import DatabaseManager
    db = DatabaseManager()
    logger.info("数据库初始化完成")

    try:
        db.execute_update(
            "UPDATE task_results SET status = 'interrupted' WHERE status = 'running'",
            (),
        )
        logger.info("已清理上次未正常结束的运行中任务状态")
    except Exception as e:
        logger.warning(f"清理运行中任务状态失败: {e}")

    from core.plugin_manager import PluginManager
    plugin_mgr = PluginManager()
    plugins_dir = Path(settings._get_base_dir()) / "plugins"
    if plugins_dir.exists():
        try:
            count = plugin_mgr.load_plugins_from_dir(str(plugins_dir))
            logger.info(f"加载了 {count} 个插件")
        except Exception as e:
            logger.warning(f"加载插件失败: {e}")

    from ui.main_window import MainWindow
    from ui.styles import StyleManager

    window = MainWindow()
    window.show()

    logger.info("主窗口已显示，应用程序启动完成")

    exit_code = app.exec()

    logger.info(f"应用程序退出，退出码: {exit_code}")

    try:
        plugin_mgr.unload_all_plugins()
    except Exception as e:
        logger.warning(f"卸载插件失败: {e}")

    try:
        db.close()
    except Exception as e:
        logger.warning(f"关闭数据库失败: {e}")

    from utils.logger import shutdown as shutdown_logger
    shutdown_logger()

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            with open("crash.log", "w", encoding="utf-8") as f:
                f.write(f"Crash: {e}\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        sys.exit(1)
