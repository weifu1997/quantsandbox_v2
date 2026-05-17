from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol
import time

import pandas as pd

from app.config.settings import get_settings
from app.utils.logging import get_logger, log_duration
from app.utils.rate_limit import get_tushare_rate_limiter


def _classify_retry_reason(exc: Exception | BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    message = str(exc).lower()
    if "rate limit" in message or "too many request" in message or "429" in message:
        return "rate_limit"
    if "empty" in message:
        return "empty"
    return "error"


def _retry_backoff_seconds(reason: str, attempt: int) -> float:
    base_map = {
        "timeout": 1.5,
        "rate_limit": 3.0,
        "empty": 1.0,
        "error": 1.2,
    }
    base = base_map.get(reason, 1.2)
    return round(base * attempt, 2)


class MarketDataAdapter(Protocol):
    def fetch_daily_bars(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame: ...


class InMemoryMarketDataAdapter:
    """Deterministic local adapter for phase-1 development and tests.

    The simulated path deliberately avoids clean monotonic price ramps so factor IC
    does not look artificially strong just because the mock market is too smooth.
    """

    def __init__(self):
        import hashlib
        self._hash = hashlib.md5

    def _seed(self, ticker: str) -> int:
        return int(self._hash(ticker.encode()).hexdigest()[:8], 16)

    def fetch_daily_bars(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "amount"])

        import random

        dates = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="B")
        rows: list[dict] = []
        for idx, ticker in enumerate(tickers, start=1):
            rng = random.Random(self._seed(ticker))
            price = 18.0 + idx * 3.0 + rng.random() * 8.0
            base_volume = 800_000 + idx * 60_000 + int(rng.random() * 120_000)
            phase = rng.random() * math.pi * 2.0
            cycle = 12 + (idx % 7)

            for i, dt in enumerate(dates):
                seasonal = math.sin((i / cycle) + phase) * 0.012
                drift = ((i // 18) % 3 - 1) * 0.0015
                shock = (rng.random() - 0.5) * 0.035
                daily_return = seasonal + drift + shock

                open_price = max(1.0, price * (1.0 + (rng.random() - 0.5) * 0.02))
                close = max(1.0, open_price * (1.0 + daily_return))
                intraday_span = max(0.003, abs(daily_return) * 0.8 + rng.random() * 0.012)
                high = max(open_price, close) * (1.0 + intraday_span)
                low = min(open_price, close) * max(0.7, 1.0 - intraday_span)
                volume = max(10_000, int(base_volume * (1.0 + (rng.random() - 0.5) * 0.6)))

                rows.append(
                    {
                        "date": dt,
                        "ticker": ticker,
                        "open": round(open_price, 4),
                        "high": round(high, 4),
                        "low": round(low, 4),
                        "close": round(close, 4),
                        "volume": volume,
                        "amount": round(close * volume, 2),
                    }
                )
                price = close
        return pd.DataFrame(rows)


class FileMarketDataAdapter:
    """Formal adapter reading standardized market data from a partitioned directory.

    Directory structure:
        <dir>/
            sh600519.parquet
            sz000858.parquet
            ...

    Falls back to single-file mode when `path` is explicitly provided (legacy compat).
    """

    def __init__(self, path: str | Path | None = None):
        settings = get_settings()
        if path is not None:
            # legacy single-file mode
            self.path = Path(path)
            self.dir_path = None
        else:
            self.dir_path = Path(settings.market_data_dir or settings.data_dir / "raw" / "market")
            self.path = None

    def _read_ticker_file(self, ticker: str) -> pd.DataFrame | None:
        path = self.dir_path / f"{ticker}.parquet"
        if path.exists():
            return pd.read_parquet(path)
        return None

    def fetch_daily_bars(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if self.path is not None:
            if not self.path.exists():
                raise FileNotFoundError(f"market data file not found: {self.path}")
            if self.path.suffix.lower() == ".csv":
                df = pd.read_csv(self.path)
            else:
                df = pd.read_parquet(self.path)
            df["date"] = pd.to_datetime(df["date"])
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            sample = df.loc[
                df["ticker"].isin(tickers)
                & (df["date"] >= start)
                & (df["date"] <= end)
            ].copy()
            return sample.reset_index(drop=True)

        # partitioned mode
        if self.dir_path is None or not self.dir_path.exists():
            return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "amount"])

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        rows: list[pd.DataFrame] = []
        for ticker in tickers:
            df = self._read_ticker_file(ticker)
            if df is None or df.empty:
                continue
            df["date"] = pd.to_datetime(df["date"])
            sample = df.loc[(df["date"] >= start) & (df["date"] <= end)].copy()
            if not sample.empty:
                rows.append(sample)
        if not rows:
            return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "amount"])
        return pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


class TushareMarketDataAdapter:
    """Online provider adapter using Tushare official SDK, with optional third-party proxy URL.

    Enhancements:
    - use multi-ticker `daily` where available
    - retry + timeout guard via threaded execution
    - partial success warnings instead of whole-batch hard fail when some tickers fail
    """

    def __init__(self):
        try:
            import tushare as ts  # type: ignore
        except ImportError as exc:
            raise RuntimeError("tushare is not installed; please install requirements.txt") from exc
        self.ts = ts
        self.settings = get_settings()
        self.log = get_logger(__name__)
        self.warnings: list[str] = []
        self.retry_stats: dict[str, int] = {"attempts": 0, "timeouts": 0, "rate_limits": 0, "empties": 0, "errors": 0}
        self.rate_limiter = get_tushare_rate_limiter()
        if not self.settings.tushare_token:
            raise RuntimeError("QS_TUSHARE_TOKEN is required for tushare mode")
        self.ts.set_token(self.settings.tushare_token)
        self.pro = self.ts.pro_api()
        if self.settings.tushare_http_url:
            self.pro._DataApi__http_url = self.settings.tushare_http_url

    @staticmethod
    def _symbol_to_ts(symbol: str) -> str:
        s = str(symbol).strip().lower()
        if s.startswith("sh"):
            return f"{s[2:]}.SH"
        if s.startswith("sz"):
            return f"{s[2:]}.SZ"
        if s.endswith(".SH") or s.endswith(".SZ"):
            return s.upper()
        return s.upper()

    @staticmethod
    def _symbol_from_ts(ts_code: str) -> str:
        s = str(ts_code).upper()
        if s.endswith(".SH"):
            return f"sh{s[:-3]}".lower()
        if s.endswith(".SZ"):
            return f"sz{s[:-3]}".lower()
        return s.lower()

    def _call_with_retry(self, fn, label: str, retries: int = 2, timeout_seconds: float = 20.0, rate_kind: str = "market", **kwargs):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

        last_error = None
        for attempt in range(1, retries + 2):
            t0 = time.time()
            self.rate_limiter.acquire(rate_kind)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fn, **kwargs)
                try:
                    result = future.result(timeout=timeout_seconds)
                    log_duration(self.log, label, time.time() - t0, {"attempt": attempt})
                    return result
                except FutureTimeoutError:
                    future.cancel()
                    last_error = TimeoutError(f"timeout after {timeout_seconds}s")
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            reason = _classify_retry_reason(last_error)
            self.retry_stats["attempts"] += 1
            if reason == "timeout":
                self.retry_stats["timeouts"] += 1
            elif reason == "rate_limit":
                self.retry_stats["rate_limits"] += 1
            elif reason == "empty":
                self.retry_stats["empties"] += 1
            else:
                self.retry_stats["errors"] += 1
            backoff = _retry_backoff_seconds(reason, attempt)
            warning = f"retry_warning|label={label}|attempt={attempt}|reason={reason}|backoff_seconds={backoff}|error={last_error}"
            self.warnings.append(warning)
            self.log.warning("%s attempt %s failed (%s), backing off %.2fs: %s", label, attempt, reason, backoff, last_error)
            if attempt <= retries:
                time.sleep(backoff)
        raise last_error  # type: ignore[misc]

    def fetch_daily_bars(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        self.warnings = []
        self.retry_stats = {"attempts": 0, "timeouts": 0, "rate_limits": 0, "empties": 0, "errors": 0}
        if not tickers:
            return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "amount"])

        ts_codes = [self._symbol_to_ts(t) for t in tickers]
        joined = ",".join(ts_codes)
        try:
            df = self._call_with_retry(
                self.pro.daily,
                label="tushare.daily(batch)",
                ts_code=joined,
                start_date=str(start_date),
                end_date=str(end_date),
                rate_kind="market",
            )
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f"batch daily failed: {exc}; falling back to per-ticker fetch")
            rows: list[pd.DataFrame] = []
            for ticker in tickers:
                ts_code = self._symbol_to_ts(ticker)
                try:
                    single = self._call_with_retry(
                        self.pro.daily,
                        label=f"tushare.daily({ticker})",
                        ts_code=ts_code,
                        start_date=str(start_date),
                        end_date=str(end_date),
                        rate_kind="retry",
                    )
                    if single is None or single.empty:
                        self.warnings.append(f"daily returned empty for {ticker}")
                        continue
                    rows.append(single)
                except Exception as inner_exc:  # noqa: BLE001
                    self.warnings.append(f"daily failed for {ticker}: {inner_exc}")
                    continue
            if not rows:
                return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "amount"])
            df = pd.concat(rows, ignore_index=True)

        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume", "amount"])

        renamed = df.rename(columns={"trade_date": "date", "vol": "volume", "ts_code": "ticker"})
        required = ["date", "ticker", "open", "high", "low", "close", "volume", "amount"]
        missing = [col for col in required if col not in renamed.columns]
        if missing:
            raise ValueError(f"tushare market data missing columns: {missing}")
        renamed = renamed[required].copy()
        renamed["ticker"] = renamed["ticker"].apply(self._symbol_from_ts)
        renamed["date"] = pd.to_datetime(renamed["date"])
        present = set(renamed["ticker"].unique())
        for ticker in tickers:
            if ticker not in present:
                self.warnings.append(f"daily missing ticker in result: {ticker}")
        return renamed.sort_values(["ticker", "date"]).reset_index(drop=True)


def build_market_data_adapter(mode: str | None = None) -> MarketDataAdapter:
    settings = get_settings()
    selected = (mode or settings.market_data_mode or "memory").lower()
    if selected == "file":
        return FileMarketDataAdapter()
    if selected == "tushare":
        return TushareMarketDataAdapter()
    return InMemoryMarketDataAdapter()
