from __future__ import annotations

import pandas as pd


def momentum_20d(df: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    return close / close.shift(20) - 1.0


def momentum_60d(df: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    return close / close.shift(60) - 1.0


def momentum_20d_skip5d(df: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    short_reversal_window = close / close.shift(5) - 1.0
    base_momentum_window = close.shift(5) / close.shift(20) - 1.0
    return base_momentum_window.where(short_reversal_window.notna())
