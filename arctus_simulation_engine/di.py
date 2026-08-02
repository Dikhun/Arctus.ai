from __future__ import annotations

import inspect
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class DependencyError(Exception):
    pass


class DIContainer:
    def __init__(self) -> None:
        self._singletons: dict[type[Any], type[Any]] = {}
        self._factories: dict[type[Any], Callable[..., Any]] = {}
        self._instances: dict[type[Any], Any] = {}
        self._singleton_cache: dict[type[Any], Any] = {}

    def has(self, interface: type[Any]) -> bool:
        return interface in self._instances or interface in self._singletons or interface in self._factories

    def register_singleton(self, interface: type[T], implementation: type[T]) -> None:
        self._singletons[interface] = implementation
        self._factories.pop(interface, None)
        self._instances.pop(interface, None)
        self._singleton_cache.pop(interface, None)

    def register_factory(self, interface: type[T], factory: Callable[..., T]) -> None:
        self._factories[interface] = factory
        self._singletons.pop(interface, None)
        self._instances.pop(interface, None)
        self._singleton_cache.pop(interface, None)

    def register_instance(self, interface: type[T], instance: T) -> None:
        self._instances[interface] = instance
        self._singletons.pop(interface, None)
        self._factories.pop(interface, None)
        self._singleton_cache.pop(interface, None)

    async def resolve(self, interface: type[T]) -> T:
        if interface in self._instances:
            return self._instances[interface]

        if interface in self._singleton_cache:
            return self._singleton_cache[interface]

        if interface in self._factories:
            instance = await self._invoke(self._factories[interface])
            return instance

        if interface in self._singletons:
            impl = self._singletons[interface]
            instance = await self._invoke(impl)
            self._singleton_cache[interface] = instance
            return instance

        if inspect.isclass(interface):
            instance = await self._invoke(interface)
            return instance

        raise DependencyError(f"No registration for {interface}")

    async def _invoke(self, callable_obj: Callable[..., Any]) -> Any:
        if not inspect.isclass(callable_obj) and not callable(callable_obj):
            return callable_obj

        sig_source = callable_obj.__init__ if inspect.isclass(callable_obj) else callable_obj
        sig = inspect.signature(sig_source)

        kwargs: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.annotation is inspect.Parameter.empty:
                if param.default is not inspect.Parameter.empty:
                    continue
                raise DependencyError(f"Parameter {name} of {callable_obj} lacks type annotation")
            kwargs[name] = await self.resolve(param.annotation)

        result = callable_obj(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
