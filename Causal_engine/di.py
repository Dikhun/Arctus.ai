import asyncio
import inspect
from typing import Any, Callable, Dict, Type, TypeVar

T = TypeVar("T")

class DIContainer:
    def __init__(self) -> None:
        self._registrations: Dict[Type, tuple[Callable[["DIContainer"], Any], bool]] = {}
        self._singletons: Dict[Type, Any] = {}
        self._lock = asyncio.Lock()

    def register(
        self,
        interface: Type[T],
        factory: Callable[["DIContainer"], T],
        singleton: bool = False,
    ) -> None:
        self._registrations[interface] = (factory, singleton)

    async def resolve(self, interface: Type[T]) -> T:
        async with self._lock:
            if interface in self._singletons:
                return self._singletons[interface]
            if interface in self._registrations:
                factory, is_singleton = self._registrations[interface]
                instance = factory(self)
                if is_singleton:
                    self._singletons[interface] = instance
                return instance
            return self._construct(interface)

    def _construct(self, cls: Type[T]) -> T:
        sig = inspect.signature(cls.__init__)
        params: list = list(sig.parameters.items())[1:]
        kwargs: Dict[str, Any] = {}
        for name, param in params:
            ann = param.annotation
            if ann != inspect.Parameter.empty and ann in self._registrations:
                kwargs[name] = self._resolve_sync(ann)
            elif param.default != inspect.Parameter.empty:
                kwargs[name] = param.default
            else:
                kwargs[name] = None
        return cls(**kwargs)

    def _resolve_sync(self, interface: Type[T]) -> T:
        if interface in self._singletons:
            return self._singletons[interface]
        if interface in self._registrations:
            factory, is_singleton = self._registrations[interface]
            instance = factory(self)
            if is_singleton:
                self._singletons[interface] = instance
            return instance
        return self._construct(interface)
