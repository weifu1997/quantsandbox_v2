from __future__ import annotations

import pandas as pd

from app.domain.backtest.rebalance_calendar import select_rebalance_dates


def _equity_curve_from_returns(returns: list[float]) -> list[float]:
    curve: list[float] = []
    equity = 1.0
    for value in returns:
        equity *= (1.0 + float(value))
        curve.append(float(equity))
    return curve


def run_equal_weight_universe_benchmark(
    dataset: pd.DataFrame,
    return_col: str,
    rebalance_frequency: str,
) -> dict:
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample = sample.dropna(subset=[return_col])

    rebalance_dates = set(select_rebalance_dates(sample["date"].tolist(), rebalance_frequency))
    rows: list[tuple[str, float]] = []
    for raw_date, group in sample.groupby("date", sort=True):
        dt = pd.Timestamp(raw_date)
        if dt not in rebalance_dates:
            continue
        rows.append((dt.strftime("%Y-%m-%d"), float(group[return_col].mean())))
    dates = [x[0] for x in rows]
    returns = [x[1] for x in rows]
    return {
        "name": "equal_weight_universe",
        "dates": dates,
        "returns": returns,
        "equity_curve": _equity_curve_from_returns(returns),
    }


def run_benchmark(
    dataset: pd.DataFrame,
    return_col: str,
    benchmark: str,
    rebalance_frequency: str,
) -> dict:
    if benchmark == "equal_weight_universe":
        return run_equal_weight_universe_benchmark(dataset, return_col, rebalance_frequency)
    raise ValueError(f"unsupported benchmark: {benchmark}")
