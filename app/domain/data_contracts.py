from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

PRICE_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]

FUNDAMENTAL_COLUMNS = [
    "date",
    "ticker",
    "pe",
    "pb",
    "roe",
    "roa",
    "gross_margin",
    "revenue_growth",
    "profit_growth",
]

RESEARCH_BASE_COLUMNS = PRICE_COLUMNS + [
    "pe",
    "pb",
    "roe",
    "roa",
    "gross_margin",
    "revenue_growth",
    "profit_growth",
    "listed_days",
]

SAMPLE_FLAG_COLUMNS = [
    "is_valid_sample",
    "missing_reason",
]


def future_return_column(horizon: int) -> str:
    horizon_int = int(horizon)
    if horizon_int <= 0:
        raise ValueError("horizon must be positive")
    return f"future_return_{horizon_int}d"


def factor_column(name: str) -> str:
    clean = str(name or "").strip()
    if not clean:
        raise ValueError("factor name must not be empty")
    return f"factor:{clean}"


REQUIRED_PRICE_COLUMNS = list(PRICE_COLUMNS)
REQUIRED_FUNDAMENTAL_COLUMNS = list(FUNDAMENTAL_COLUMNS)
REQUIRED_RESEARCH_COLUMNS = list(RESEARCH_BASE_COLUMNS) + SAMPLE_FLAG_COLUMNS


def min_trading_days_per_ticker(df: pd.DataFrame) -> pd.Series:
    """Count ocurrence of each ticker (proxy for available trading days)."""
    return df.groupby("ticker")["date"].transform("size")


def add_sample_flags(
    dataset: pd.DataFrame,
    horizons: list[int],
    min_days: int = 60,
    min_listed_days: int = 120,
) -> pd.DataFrame:
    df = dataset.copy()
    df["is_valid_sample"] = True
    df["missing_reason"] = ""
    for horizon in horizons:
        col = future_return_column(horizon)
        missing = df[col].isna() & (df["missing_reason"] == "")
        df.loc[missing, "is_valid_sample"] = False
        df.loc[missing, "missing_reason"] = f"missing_future_return_{horizon}d"
    ticker_counts = min_trading_days_per_ticker(df)
    low_days = ticker_counts < min_days
    if low_days.any():
        mask = low_days & (df["missing_reason"] == "")
        df.loc[mask, "is_valid_sample"] = False
        df.loc[mask, "missing_reason"] = f"too_few_trading_days_min_{min_days}"
    if "listed_days" in df.columns:
        listed_days = pd.to_numeric(df["listed_days"], errors="coerce")
        short_listed = listed_days < min_listed_days
        if short_listed.any():
            mask = short_listed & (df["missing_reason"] == "")
            df.loc[mask, "is_valid_sample"] = False
            df.loc[mask, "missing_reason"] = f"too_few_listed_days_min_{min_listed_days}"
    return df


def build_listing_reference_map(reference_path: str | Path | None) -> pd.DataFrame:
    if reference_path is None:
        return pd.DataFrame(columns=["ticker", "list_date"])
    path = Path(reference_path)
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "list_date"])
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_parquet(path)
    if "ticker" not in df.columns or "list_date" not in df.columns:
        return pd.DataFrame(columns=["ticker", "list_date"])
    result = df[["ticker", "list_date"]].copy()
    result["ticker"] = result["ticker"].astype(str).str.lower().str.strip()
    result["list_date"] = pd.to_datetime(result["list_date"], errors="coerce")
    return result.dropna(subset=["ticker"]).drop_duplicates(subset=["ticker"], keep="last")


def attach_listing_days(
    dataset: pd.DataFrame,
    reference_path: str | Path | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = dataset.copy()
    if df.empty:
        df["listed_days"] = pd.Series(dtype="float64")
        return df, {"listing_reference_path": str(reference_path) if reference_path else None, "listing_days_attached": 0}

    listing_ref = build_listing_reference_map(reference_path)
    df["date"] = pd.to_datetime(df["date"])
    if listing_ref.empty:
        df["listed_days"] = pd.NA
        return df, {"listing_reference_path": str(reference_path) if reference_path else None, "listing_days_attached": 0}

    merged = df.merge(listing_ref, on="ticker", how="left")
    merged["listed_days"] = (merged["date"] - merged["list_date"]).dt.days
    attached = int(merged["listed_days"].notna().sum())
    return merged.drop(columns=["list_date"]), {
        "listing_reference_path": str(reference_path),
        "listing_days_attached": attached,
    }


def _missing_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    return [col for col in required if col not in df.columns]


def validate_market_dataframe(df: pd.DataFrame) -> None:
    missing = _missing_columns(df, REQUIRED_PRICE_COLUMNS)
    if missing:
        raise ValueError(f"market dataframe missing columns: {missing}")


def validate_fundamental_dataframe(df: pd.DataFrame) -> None:
    missing = _missing_columns(df, REQUIRED_FUNDAMENTAL_COLUMNS)
    if missing:
        raise ValueError(f"fundamental dataframe missing columns: {missing}")


def validate_research_dataset(
    df: pd.DataFrame,
    *,
    factor_names: list[str] | None = None,
    horizons: list[int] | None = None,
    require_sample_flags: bool = False,
) -> None:
    required = list(RESEARCH_BASE_COLUMNS)
    if require_sample_flags:
        required.extend(SAMPLE_FLAG_COLUMNS)
    if factor_names:
        required.extend([factor_column(name) for name in factor_names])
    if horizons:
        required.extend([future_return_column(h) for h in horizons])
    missing = _missing_columns(df, required)
    if missing:
        raise ValueError(f"research dataset missing columns: {missing}")


def validate_backtest_dataset(df: pd.DataFrame, factor_col: str, return_col: str) -> None:
    required = ["date", "ticker", factor_col, return_col]
    missing = _missing_columns(df, required)
    if missing:
        raise ValueError(f"backtest dataset missing columns: {missing}")


def normalize_ticker(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_trade_date(value) -> pd.Timestamp:
    return pd.to_datetime(value)
