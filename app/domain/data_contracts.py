from __future__ import annotations

import pandas as pd

REQUIRED_PRICE_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]

REQUIRED_RESEARCH_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


def validate_market_dataframe(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_PRICE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"market dataframe missing columns: {missing}")


def validate_research_dataset(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_RESEARCH_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"research dataset missing columns: {missing}")


def normalize_ticker(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_trade_date(value) -> pd.Timestamp:
    return pd.to_datetime(value)
