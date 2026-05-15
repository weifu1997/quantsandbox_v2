from __future__ import annotations

from pathlib import Path
from typing import Protocol
import time

import pandas as pd

from app.config.settings import get_settings
from app.utils.logging import get_logger, log_duration
from app.utils.rate_limit import get_tushare_rate_limiter


class FundamentalDataAdapter(Protocol):
    def fetch_fundamentals(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame: ...


class InMemoryFundamentalDataAdapter:
    """Deterministic placeholder fundamentals for phase-1 validation."""

    def fetch_fundamentals(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame(columns=["date", "ticker", "pe", "pb", "roe"])

        dates = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="B")
        rows: list[dict] = []
        for idx, ticker in enumerate(tickers, start=1):
            for i, dt in enumerate(dates):
                rows.append(
                    {
                        "date": dt,
                        "ticker": ticker,
                        "pe": 10.0 + idx + (i % 5) * 0.2,
                        "pb": 1.0 + idx * 0.1,
                        "roe": 0.08 + idx * 0.005,
                    }
                )
        return pd.DataFrame(rows)


class FileFundamentalDataAdapter:
    """Formal adapter reading standardized fundamentals from a partitioned directory.

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
            self.path = Path(path)
            self.dir_path = None
        else:
            self.path = None
            self.dir_path = Path(settings.fundamental_data_dir or settings.data_dir / "raw" / "fundamentals")

    def _read_ticker_file(self, ticker: str) -> pd.DataFrame | None:
        path = self.dir_path / f"{ticker}.parquet"
        if path.exists():
            return pd.read_parquet(path)
        return None

    def fetch_fundamentals(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if self.path is not None:
            if not self.path.exists():
                raise FileNotFoundError(f"fundamental data file not found: {self.path}")
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

        if self.dir_path is None or not self.dir_path.exists():
            return pd.DataFrame(columns=["date", "ticker", "pe", "pb", "roe"])

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
            return pd.DataFrame(columns=["date", "ticker", "pe", "pb", "roe"])
        return pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


class TushareFundamentalDataAdapter:
    """Online provider adapter using Tushare `daily_basic` + `fina_indicator`.

    Enhancements:
    - per ticker logging
    - retry + timeout guard
    - partial success warnings instead of whole-batch hard fail
    - ROE is aligned from quarterly `fina_indicator` onto daily rows via ann_date backward as-of join
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
        self.rate_limiter = get_tushare_rate_limiter()
        if not self.settings.tushare_token:
            raise RuntimeError("QS_TUSHARE_TOKEN is required for tushare mode")
        self.ts.set_token(self.settings.tushare_token)
        self.pro = self.ts.pro_api()
        if self.settings.tushare_http_url:
            self.pro._DataApi__http_url = self.settings.tushare_http_url

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.log.warning(message)

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

    def _apply_rate_limit(self, rate_kind: str) -> None:
        limiter = getattr(self, "rate_limiter", None)
        if limiter is not None:
            limiter.acquire(rate_kind)

    def _call_with_retry(self, fn, label: str, retries: int = 2, timeout_seconds: float = 20.0, rate_kind: str = "fundamental", **kwargs):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

        last_error = None
        for attempt in range(1, retries + 2):
            t0 = time.time()
            self._apply_rate_limit(rate_kind)
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
            self.log.warning("%s attempt %s failed: %s", label, attempt, last_error)
        raise last_error  # type: ignore[misc]

    def _fetch_daily_basic(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        ts_code = self._symbol_to_ts(ticker)
        df = self._call_with_retry(
            self.pro.daily_basic,
            label=f"tushare.daily_basic({ticker})",
            ts_code=ts_code,
            start_date=str(start_date),
            end_date=str(end_date),
            fields="ts_code,trade_date,pe,pb",
            rate_kind="fundamental",
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "ticker", "pe", "pb"])
        renamed = df.rename(columns={"trade_date": "date"})
        required = ["date", "pe", "pb"]
        missing = [col for col in required if col not in renamed.columns]
        if missing:
            raise ValueError(f"tushare daily_basic missing columns for {ticker}: {missing}")
        renamed = renamed[required].copy()
        renamed["ticker"] = ticker
        renamed["date"] = pd.to_datetime(renamed["date"])
        return renamed.sort_values("date").reset_index(drop=True)

    def _fetch_fina_indicator(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        ts_code = self._symbol_to_ts(ticker)
        # include a lookback window so the first trading dates can inherit the most recent announced ROE
        fina_start = (pd.to_datetime(start_date) - pd.Timedelta(days=500)).strftime("%Y%m%d")
        df = self._call_with_retry(
            self.pro.fina_indicator,
            label=f"tushare.fina_indicator({ticker})",
            ts_code=ts_code,
            start_date=fina_start,
            end_date=str(end_date),
            fields="ts_code,ann_date,end_date,roe",
            rate_kind="fundamental",
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=["ann_date", "roe"])
        renamed = df.rename(columns={"ann_date": "date"})
        if "date" not in renamed.columns or "roe" not in renamed.columns:
            raise ValueError(f"tushare fina_indicator missing ROE columns for {ticker}")
        renamed = renamed[["date", "roe"]].copy()
        renamed["date"] = pd.to_datetime(renamed["date"])
        renamed["roe"] = pd.to_numeric(renamed["roe"], errors="coerce")
        renamed = renamed.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
        return renamed.reset_index(drop=True)

    def fetch_fundamentals(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        self.warnings = []
        rows: list[pd.DataFrame] = []
        total = len(tickers)
        if total:
            self.log.info(
                "tushare fundamentals start | tickers=%s start_date=%s end_date=%s",
                total,
                start_date,
                end_date,
            )
        progress_every = max(1, min(50, total // 10 or 1))
        for idx, ticker in enumerate(tickers, start=1):
            if idx == 1 or idx == total or idx % progress_every == 0:
                self.log.info("tushare fundamentals progress | current=%s completed=%s/%s", ticker, idx, total)
            try:
                base = self._fetch_daily_basic(ticker, start_date, end_date)
            except Exception as exc:  # noqa: BLE001
                self._warn(f"daily_basic failed for {ticker}: {exc}")
                continue

            if base.empty:
                self._warn(f"daily_basic returned empty for {ticker}")
                continue

            try:
                roe_df = self._fetch_fina_indicator(ticker, start_date, end_date)
            except Exception as exc:  # noqa: BLE001
                self._warn(f"fina_indicator failed for {ticker}: {exc}")
                roe_df = pd.DataFrame(columns=["date", "roe"])

            if roe_df.empty:
                self._warn(f"fina_indicator returned empty for {ticker}")
                base["roe"] = None
            else:
                merged = pd.merge_asof(
                    base.sort_values("date"),
                    roe_df.sort_values("date"),
                    on="date",
                    direction="backward",
                )
                base = merged
            rows.append(base)

        if not rows:
            return pd.DataFrame(columns=["date", "ticker", "pe", "pb", "roe"])
        return pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def build_fundamental_data_adapter(mode: str | None = None) -> FundamentalDataAdapter:
    settings = get_settings()
    selected = (mode or settings.fundamental_data_mode or "memory").lower()
    if selected == "file":
        return FileFundamentalDataAdapter()
    if selected == "tushare":
        return TushareFundamentalDataAdapter()
    return InMemoryFundamentalDataAdapter()
