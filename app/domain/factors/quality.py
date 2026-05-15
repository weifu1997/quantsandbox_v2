from __future__ import annotations

import pandas as pd


def roe_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["roe"], errors="coerce")
