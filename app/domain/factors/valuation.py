from __future__ import annotations

import pandas as pd


def pe_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["pe"], errors="coerce")


def pb_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["pb"], errors="coerce")
