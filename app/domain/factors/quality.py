from __future__ import annotations

import pandas as pd


def roe_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["roe"], errors="coerce")


def roa_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["roa"], errors="coerce")


def gross_margin_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["gross_margin"], errors="coerce")


def revenue_growth_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["revenue_growth"], errors="coerce")


def profit_growth_factor(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["profit_growth"], errors="coerce")
