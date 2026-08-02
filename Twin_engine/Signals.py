from __future__ import annotations

import asyncio
import signal

import structlog

logger = structlog.get_logger()


def setup_signal_handlers(
    shutdown_event: asyncio.Event,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    _loop = loop or asyncio.get_running_loop()

    def _handler(sig: signal.Signals):
        logger.info("signal_received", signal=sig.name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        _loop.add_signal_handler(sig, lambda s=sig: _handler(s))
