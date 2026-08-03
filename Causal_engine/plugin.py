import importlib.util
import inspect
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class PluginMeta:
    name: str
    version: str
    module_path: str
    plugin_class: type    instance: Optional[Any] = None    hooks: Dict[str, Callable] = field(default_factory=dict)

class PluginLoader:
    def __init__(self, plugin_dirs: Optional[List[str]] = None) -> None:
        self.plugin_dirs = plugin_dirs or [
            "plugins",
            "arctus_causal_engine/plugins",
 ]
        self.plugins: Dict[str, PluginMeta] = {}

    async def discover(self) -> List[PluginMeta]:
        discovered: List[PluginMeta] = []
        for directory in self.plugin_dirs:
            if not os.path.isdir(directory):
                continue
            for filename in os.listdir(directory):
                if filename.endswith(".py") and not filename.startswith("_"):
                    path = os.path.join(directory, filename)
                    meta = self._load_from_path(path)
                    if meta:
                        discovered.append(meta)
                        self.plugins[meta.name] = meta
        return discovered

    def _load_from_path(self, path: str) -> Optional[PluginMeta]:
        try:
            spec = importlib.util.spec_from_file_location("dynamic_plugin", path)
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name.endswith("Plugin") and obj.__module__ == module.__name__:
                    return PluginMeta(
                        name=name,
                        version=getattr(module, "__version__", "0.0.1"),
                        module_path=path,
                        plugin_class=obj,
                    )
        except Exception as exc:
            logger.warning(f"Failed to load plugin {path}: {exc}")
        return None

    async def load_all(self) -> None:
        for name, meta in self.plugins.items():
            try:
                instance = meta.plugin_class()
                meta.instance = instance
                if hasattr(instance, "initialize"):
                    await instance.initialize()
                logger.info(f"Plugin activated: {name}")
            except Exception as exc:
                logger.error(f"Plugin activation failed {name}: {exc}")

    async def validate_all(self) -> bool:
        valid = True
        for name, meta in self.plugins.items():
            if meta.instance is None:
                continue
            try:
                if hasattr(meta.instance, "health_check"):
                    ok = await meta.instance.health_check()
                    if not ok:
                        logger.warning(f"Plugin validation failed: {name}")
                        valid = False
                if hasattr(meta.instance, "validate"):
                    ok = await meta.instance.validate()
                    if not ok:
                        valid = False except Exception as exc:
                logger.error(f"Plugin validation exception {name}: {exc}")
                valid = False
        return valid    async def unload_all(self) -> None:
        for name, meta in self.plugins.items():
            if meta.instance and hasattr(meta.instance, "shutdown"):
                try:
                    await meta.instance.shutdown()
                except Exception as exc:
                    logger.warning(f"Plugin shutdown error {name}: {exc}")
            meta.instance = None
