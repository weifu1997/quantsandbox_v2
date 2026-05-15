from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.config.settings import get_settings


@dataclass
class TushareRateLimiter:
    market_rpm: float
    fundamental_rpm: float
    retry_rpm: float
    sleeper: callable = time.sleep
    monotonic: callable = time.monotonic
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_called_at: dict[str, float] = field(default_factory=dict)

    def _interval_seconds(self, phase: str) -> float:
        rpm_map = {
            "market": self.market_rpm,
            "fundamental": self.fundamental_rpm,
            "retry": self.retry_rpm,
        }
        rpm = float(rpm_map.get(phase, self.fundamental_rpm))
        if rpm <= 0:
            return 0.0
        return 60.0 / rpm

    def acquire(self, phase: str) -> None:
        interval = self._interval_seconds(phase)
        if interval <= 0:
            return
        with self._lock:
            now = self.monotonic()
            last = self._last_called_at.get(phase)
            if last is not None:
                wait = interval - (now - last)
                if wait > 0:
                    self.sleeper(wait)
                    now = self.monotonic()
            self._last_called_at[phase] = now


_shared_limiter: TushareRateLimiter | None = None


def get_tushare_rate_limiter() -> TushareRateLimiter:
    global _shared_limiter
    if _shared_limiter is None:
        settings = get_settings()
        _shared_limiter = TushareRateLimiter(
            market_rpm=settings.tushare_market_requests_per_minute,
            fundamental_rpm=settings.tushare_fundamental_requests_per_minute,
            retry_rpm=settings.tushare_retry_requests_per_minute,
        )
    return _shared_limiter
