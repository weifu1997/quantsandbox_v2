from __future__ import annotations

import pandas as pd


def momentum_20d(df: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    return close.groupby(df["ticker"]).transform(lambda s: s / s.shift(20) - 1.0)


def momentum_60d(df: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    return close.groupby(df["ticker"]).transform(lambda s: s / s.shift(60) - 1.0)


def momentum_20d_skip5d(df: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    shifted5 = close.groupby(df["ticker"]).transform(lambda s: s.shift(5))
    shifted20 = close.groupby(df["ticker"]).transform(lambda s: s.shift(20))
    short_reversal_window = close / shifted5 - 1.0
    base_momentum_window = shifted5 / shifted20 - 1.0
    return base_momentum_window.where(short_reversal_window.notna())
