import importlib
import importlib.util
import inspect
import sys
from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

from utils.logger import get_logger

logger = get_logger("plugin_manager")


class HookType(Enum):
    PRE_TEST = auto()
    POST_TEST = auto()
    PRE_REQUEST = auto()
    POST_REQUEST = auto()
    ON_START = auto()
    ON_STOP = auto()
    ON_ERROR = auto()
    ON_REPORT = auto()
    CUSTOM = auto()


class PluginBase(ABC):
    name: str = "unnamed_plugin"
    version: str = "0.1.0"
    description: str = ""
    author: str = ""

    def __init__(self) -> None:
        self._enabled: bool = True
        self._hooks: dict[HookType, Callable[..., Any]] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def register_hook(self, hook_type: HookType, callback: Callable[..., Any]) -> None:
        self._hooks[hook_type] = callback

    def unregister_hook(self, hook_type: HookType) -> bool:
        if hook_type in self._hooks:
            del self._hooks[hook_type]
            return True
        return False

    def get_hook(self, hook_type: HookType) -> Callable[..., Any] | None:
        return self._hooks.get(hook_type)

    @abstractmethod
    def on_load(self) -> None:
        ...

    @abstractmethod
    def on_unload(self) -> None:
        ...


class PluginManager:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}
        self._hooks: dict[HookType, list[Callable[..., Any]]] = {}
        for hook_type in HookType:
            self._hooks[hook_type] = []
        self._plugin_dirs: list[Path] = []

    def add_plugin_dir(self, directory: str | Path) -> None:
        p = Path(directory)
        if p.is_dir() and p not in self._plugin_dirs:
            self._plugin_dirs.append(p)
            logger.info("已添加插件目录: %s", p)

    def register_plugin(self, plugin: PluginBase) -> bool:
        if plugin.name in self._plugins:
            logger.warning("插件 '%s' 已注册, 跳过重复注册", plugin.name)
            return False

        self._plugins[plugin.name] = plugin

        for hook_type, callback in plugin._hooks.items():
            self._hooks[hook_type].append(callback)
            logger.info(
                "插件 '%s' 注册钩子: %s -> %s",
                plugin.name,
                hook_type.name,
                callback.__name__,
            )

        try:
            plugin.on_load()
            logger.info("插件 '%s' (v%s) 已注册并加载", plugin.name, plugin.version)
        except Exception as e:
            logger.error("插件 '%s' 加载失败: %s", plugin.name, e)
            self.unregister_plugin(plugin.name)
            return False

        return True

    def unregister_plugin(self, name: str) -> bool:
        if name not in self._plugins:
            logger.warning("插件 '%s' 未注册, 无法注销", name)
            return False

        plugin = self._plugins[name]

        for hook_type, callback in plugin._hooks.items():
            try:
                self._hooks[hook_type].remove(callback)
            except ValueError:
                pass

        try:
            plugin.on_unload()
            logger.info("插件 '%s' 已注销并卸载", name)
        except Exception as e:
            logger.error("插件 '%s' 卸载异常: %s", name, e)

        del self._plugins[name]
        return True

    def get_plugin(self, name: str) -> PluginBase | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for name, plugin in self._plugins.items():
            result.append({
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.description,
                "author": plugin.author,
                "enabled": plugin.enabled,
                "hooks": [ht.name for ht in plugin._hooks],
            })
        return result

    def enable_plugin(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin.enabled = True
        logger.info("插件 '%s' 已启用", name)
        return True

    def disable_plugin(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin.enabled = False
        logger.info("插件 '%s' 已禁用", name)
        return True

    def add_hook(self, hook_type: HookType, callback: Callable[..., Any]) -> None:
        self._hooks[hook_type].append(callback)
        logger.info("已注册全局钩子: %s -> %s", hook_type.name, callback.__name__)

    def remove_hook(self, hook_type: HookType, callback: Callable[..., Any]) -> bool:
        try:
            self._hooks[hook_type].remove(callback)
            logger.info("已移除全局钩子: %s -> %s", hook_type.name, callback.__name__)
            return True
        except ValueError:
            return False

    def trigger_hook(self, hook_type: HookType, *args: Any, **kwargs: Any) -> list[Any]:
        results: list[Any] = []
        callbacks = self._hooks.get(hook_type, [])

        for callback in callbacks:
            for plugin in self._plugins.values():
                if plugin._hooks.get(hook_type) is callback and not plugin.enabled:
                    continue
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(
                    "钩子 '%s' 回调 '%s' 执行异常: %s",
                    hook_type.name,
                    callback.__name__,
                    e,
                )

        return results

    def load_plugins_from_dir(self, directory: str | Path) -> int:
        plugin_dir = Path(directory)
        if not plugin_dir.is_dir():
            logger.warning("插件目录不存在: %s", plugin_dir)
            return 0

        loaded_count = 0

        for py_file in plugin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                loaded = self._load_plugin_from_file(py_file)
                if loaded:
                    loaded_count += 1
            except Exception as e:
                logger.error("从文件 '%s' 加载插件失败: %s", py_file, e)

        for pkg_dir in plugin_dir.iterdir():
            if not pkg_dir.is_dir():
                continue
            init_file = pkg_dir / "__init__.py"
            if not init_file.exists():
                continue
            if pkg_dir.name.startswith("_"):
                continue
            try:
                loaded = self._load_plugin_from_package(pkg_dir)
                if loaded:
                    loaded_count += 1
            except Exception as e:
                logger.error("从包 '%s' 加载插件失败: %s", pkg_dir, e)

        logger.info("从目录 '%s' 加载了 %d 个插件", plugin_dir, loaded_count)
        return loaded_count

    def _load_plugin_from_file(self, file_path: Path) -> bool:
        module_name = f"_plugin_{file_path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            logger.error("无法创建模块规格: %s", file_path)
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("执行模块 '%s' 失败: %s", file_path, e)
            sys.modules.pop(module_name, None)
            return False

        return self._extract_and_register_plugins(module)

    def _load_plugin_from_package(self, pkg_dir: Path) -> bool:
        module_name = f"_plugin_{pkg_dir.name}"

        spec = importlib.util.spec_from_file_location(
            module_name, str(pkg_dir / "__init__.py"),
            submodule_search_locations=[str(pkg_dir)],
        )
        if spec is None or spec.loader is None:
            logger.error("无法创建包模块规格: %s", pkg_dir)
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("执行包模块 '%s' 失败: %s", pkg_dir, e)
            sys.modules.pop(module_name, None)
            return False

        return self._extract_and_register_plugins(module)

    def _extract_and_register_plugins(self, module: Any) -> bool:
        registered = False

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                inspect.isclass(attr)
                and issubclass(attr, PluginBase)
                and attr is not PluginBase
            ):
                try:
                    plugin_instance = attr()
                    if self.register_plugin(plugin_instance):
                        registered = True
                except Exception as e:
                    logger.error("实例化插件类 '%s' 失败: %s", attr_name, e)

        return registered

    def load_all_plugins(self) -> int:
        total = 0
        for plugin_dir in self._plugin_dirs:
            total += self.load_plugins_from_dir(plugin_dir)
        return total

    def unload_all_plugins(self) -> None:
        names = list(self._plugins.keys())
        for name in names:
            self.unregister_plugin(name)
        logger.info("所有插件已卸载")

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    @property
    def enabled_count(self) -> int:
        return sum(1 for p in self._plugins.values() if p.enabled)
