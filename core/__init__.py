from core.plugin_manager import PluginManager, PluginBase, HookType

__all__ = [
    "PluginManager",
    "PluginBase",
    "HookType",
    "LocustEngine",
    "EngineState",
    "EngineConfig",
    "TaskConfig",
    "substitute_variables",
    "parse_run_time",
    "DistributedManager",
    "DistributedConfig",
    "NodeState",
    "NodeInfo",
]


def __getattr__(name):
    if name in ("LocustEngine", "EngineState", "EngineConfig", "TaskConfig", "substitute_variables", "parse_run_time"):
        from core import locust_engine as _le
        return getattr(_le, name)
    if name in ("DistributedManager", "DistributedConfig", "NodeState", "NodeInfo"):
        from core import distributed_manager as _dm
        return getattr(_dm, name)
    raise AttributeError(f"module 'core' has no attribute {name!r}")
