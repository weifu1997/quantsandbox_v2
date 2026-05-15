from __future__ import annotations

import pandas as pd


def split_in_sample_out_sample(
    df: pd.DataFrame,
    split_date: str | pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    threshold = pd.to_datetime(split_date)
    sample = df.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    in_sample = sample.loc[sample["date"] <= threshold].copy()
    out_sample = sample.loc[sample["date"] > threshold].copy()
    return in_sample, out_sample


def rolling_time_splits(
    df: pd.DataFrame,
    train_window: int,
    test_window: int,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    sample = df.copy().sort_values("date")
    unique_dates = sorted(pd.to_datetime(sample["date"]).drop_duplicates().tolist())
    results: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    start = 0
    while start + train_window + test_window <= len(unique_dates):
        train_dates = unique_dates[start : start + train_window]
        test_dates = unique_dates[start + train_window : start + train_window + test_window]
        train_df = sample.loc[pd.to_datetime(sample["date"]).isin(train_dates)].copy()
        test_df = sample.loc[pd.to_datetime(sample["date"]).isin(test_dates)].copy()
        results.append((train_df, test_df))
        start += test_window
    return results
