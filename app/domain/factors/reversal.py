from __future__ import annotations

import pandas as pd


def reversal_5d(df: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(df["close"], errors="coerce")
    return -(close / close.shift(5) - 1.0)
