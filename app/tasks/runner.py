from __future__ import annotations

import atexit
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from app.utils.logging import get_logger

_executor = ThreadPoolExecutor(max_workers=2)
_log = get_logger(__name__)

atexit.register(lambda: _executor.shutdown(wait=True, cancel_futures=True))


def _log_future_result(future: Future) -> None:
    exc = future.exception()
    if exc is not None:
        _log.exception("background task failed", exc_info=exc)
    else:
        _log.info("background task completed")


def submit_background(fn: Callable[..., Any], *args, **kwargs):
    future = _executor.submit(fn, *args, **kwargs)
    future.add_done_callback(_log_future_result)
    return future
