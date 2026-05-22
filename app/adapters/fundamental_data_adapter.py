from __future__ import annotations

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


class FundamentalDataAdapter(Protocol):
    def fetch_fundamentals(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame: ...


class InMemoryFundamentalDataAdapter:
    """Placeholder fundamentals with realistic-noise data for phase-1 validation.

    Does NOT produce monotonic or deterministically-high-IC data.
    Each ticker gets a stable random seed so values are deterministic across runs
    but not linearly increasing with ticker index or date.
    """

    def __init__(self):
        import hashlib
        self._hash = hashlib.md5

    def _seed(self, ticker: str) -> int:
        return int(self._hash(ticker.encode()).hexdigest()[:8], 16)

    def fetch_fundamentals(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        import random

        empty_cols = ["date", "ticker", "pe", "pb", "roe", "roa", "gross_margin", "revenue_growth", "profit_growth"]
        if not tickers:
            return pd.DataFrame(columns=empty_cols)

        dates = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="B")
        rows: list[dict] = []
        for ticker in tickers:
            rng = random.Random(self._seed(ticker))
            ticker_pe = 15.0 + (rng.random() - 0.5) * 20.0
            ticker_pb = 1.5 + (rng.random() - 0.5) * 2.0
            ticker_roe = 0.08 + (rng.random() - 0.5) * 0.10
            ticker_roa = 0.04 + (rng.random() - 0.5) * 0.06
            ticker_gm = 0.25 + (rng.random() - 0.5) * 0.20
            ticker_rg = 0.10 + (rng.random() - 0.5) * 0.15
            ticker_pg = 0.08 + (rng.random() - 0.5) * 0.12

            for dt in dates:
                noise = (rng.random() - 0.5)
                rows.append({
                    "date": dt,
                    "ticker": ticker,
                    "pe": max(2.0, ticker_pe + noise * 10),
                    "pb": max(0.2, ticker_pb + noise * 2),
                    "roe": max(-0.30, ticker_roe + noise * 0.02),
                    "roa": max(-0.20, ticker_roa + noise * 0.01),
                    "gross_margin": max(0.0, ticker_gm + noise * 0.1),
                    "revenue_growth": max(-0.50, ticker_rg + noise * 0.05),
                    "profit_growth": max(-0.80, ticker_pg + noise * 0.08),
                })
        return pd.DataFrame(rows)


class FileFundamentalDataAdapter:
    """Formal adapter reading standardized fundamentals from a partitioned directory."""

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
        empty_cols = ["date", "ticker", "pe", "pb", "roe", "roa", "gross_margin", "revenue_growth", "profit_growth"]
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
            return pd.DataFrame(columns=empty_cols)

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
            return pd.DataFrame(columns=empty_cols)
        return pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


class TushareFundamentalDataAdapter:
    """Online provider adapter using Tushare daily_basic + fina_indicator."""

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

    def _call_with_retry(self, fn, label: str, retries: int = 2, timeout_seconds: float = 20.0, rate_kind: str = "fundamental", **kwargs):
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
        fina_start = (pd.to_datetime(start_date) - pd.Timedelta(days=500)).strftime("%Y%m%d")
        df = self._call_with_retry(
            self.pro.fina_indicator,
            label=f"tushare.fina_indicator({ticker})",
            ts_code=ts_code,
            start_date=fina_start,
            end_date=str(end_date),
            fields="ts_code,ann_date,end_date,roe,roa,grossprofit_margin,tr_yoy,netprofit_yoy",
            rate_kind="fundamental",
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "roe", "roa", "gross_margin", "revenue_growth", "profit_growth"])
        renamed = df.rename(columns={
            "ann_date": "date",
            "grossprofit_margin": "gross_margin",
            "tr_yoy": "revenue_growth",
            "netprofit_yoy": "profit_growth",
        })
        required = ["date", "roe", "roa", "gross_margin", "revenue_growth", "profit_growth"]
        missing = [col for col in required if col not in renamed.columns]
        if missing:
            raise ValueError(f"tushare fina_indicator missing columns for {ticker}: {missing}")
        renamed = renamed[required].copy()
        renamed["date"] = pd.to_datetime(renamed["date"])
        for col in ["roe", "roa", "gross_margin", "revenue_growth", "profit_growth"]:
            renamed[col] = pd.to_numeric(renamed[col], errors="coerce")
        renamed = renamed.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
        return renamed.reset_index(drop=True)

    def fetch_fundamentals(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        empty_cols = ["date", "ticker", "pe", "pb", "roe", "roa", "gross_margin", "revenue_growth", "profit_growth"]
        self.warnings = []
        self.retry_stats = {"attempts": 0, "timeouts": 0, "rate_limits": 0, "empties": 0, "errors": 0}
        rows: list[pd.DataFrame] = []
        total = len(tickers)
        if total:
            self.log.info("tushare fundamentals start | tickers=%s start_date=%s end_date=%s", total, start_date, end_date)
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
                fi_df = self._fetch_fina_indicator(ticker, start_date, end_date)
            except Exception as exc:  # noqa: BLE001
                self._warn(f"fina_indicator failed for {ticker}: {exc}")
                fi_df = pd.DataFrame(columns=["date", "roe", "roa", "gross_margin", "revenue_growth", "profit_growth"])

            if fi_df.empty:
                self._warn(f"fina_indicator returned empty for {ticker}")
                base["roe"] = None
                base["roa"] = None
                base["gross_margin"] = None
                base["revenue_growth"] = None
                base["profit_growth"] = None
            else:
                merged = pd.merge_asof(
                    base.sort_values("date"),
                    fi_df.sort_values("date"),
                    on="date",
                    direction="backward",
                )
                base = merged
            rows.append(base)

        if not rows:
            return pd.DataFrame(columns=empty_cols)
        return pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def build_fundamental_data_adapter(mode: str | None = None) -> FundamentalDataAdapter:
    settings = get_settings()
    selected = (mode or settings.fundamental_data_mode or "memory").lower()
    if selected == "file":
        return FileFundamentalDataAdapter()
    if selected == "tushare":
        return TushareFundamentalDataAdapter()
    return InMemoryFundamentalDataAdapter()
