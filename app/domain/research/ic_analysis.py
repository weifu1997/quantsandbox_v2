from __future__ import annotations

import pandas as pd


def compute_ic_series(dataset: pd.DataFrame, factor_col: str, return_col: str) -> pd.Series:
    values: list[float] = []
    index: list[pd.Timestamp] = []
    for raw_date, group in dataset.groupby("date", sort=True):
        sample = group[[factor_col, return_col]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sample) < 2:
            continue
        ic = sample[factor_col].corr(sample[return_col], method="pearson")
        if pd.notna(ic):
            values.append(float(ic))
            index.append(pd.Timestamp(raw_date))
    return pd.Series(values, index=index, dtype="float64")


def compute_rank_ic_series(dataset: pd.DataFrame, factor_col: str, return_col: str) -> pd.Series:
    values: list[float] = []
    index: list[pd.Timestamp] = []
    for raw_date, group in dataset.groupby("date", sort=True):
        sample = group[[factor_col, return_col]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sample) < 2:
            continue
        ranked_factor = sample[factor_col].rank(method="average")
        ranked_return = sample[return_col].rank(method="average")
        ric = ranked_factor.corr(ranked_return, method="pearson")
        if pd.notna(ric):
            values.append(float(ric))
            index.append(pd.Timestamp(raw_date))
    return pd.Series(values, index=index, dtype="float64")


def summarize_ic(ic_series: pd.Series, rank_ic_series: pd.Series) -> dict:
    if len(ic_series) == 0 and len(rank_ic_series) == 0:
        return {
            "ic_mean": 0.0,
            "ic_std": 0.0,
            "rank_ic_mean": 0.0,
            "rank_ic_std": 0.0,
            "sample_count": 0,
            "positive_ic_ratio": 0.0,
        }
    return {
        "ic_mean": float(ic_series.mean()) if len(ic_series) else 0.0,
        "ic_std": float(ic_series.std(ddof=0)) if len(ic_series) else 0.0,
        "rank_ic_mean": float(rank_ic_series.mean()) if len(rank_ic_series) else 0.0,
        "rank_ic_std": float(rank_ic_series.std(ddof=0)) if len(rank_ic_series) else 0.0,
        "sample_count": int(max(len(ic_series), len(rank_ic_series))),
        "positive_ic_ratio": float((ic_series > 0).mean()) if len(ic_series) else 0.0,
    }
