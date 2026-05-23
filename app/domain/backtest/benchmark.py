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

    if "close" not in sample.columns:
        raise ValueError("benchmark requires close column for real mark-to-market pricing")

    entry_col = None
    if "next_open_price" in sample.columns:
        entry_col = "next_open_price"
    elif "open" in sample.columns:
        entry_col = "open"
    else:
        raise ValueError("benchmark requires next_open_price or open column for entry pricing")

    sample[entry_col] = pd.to_numeric(sample[entry_col], errors="coerce")
    sample["close"] = pd.to_numeric(sample["close"], errors="coerce")
    sample = sample.dropna(subset=[entry_col, "close"])
    sample = sample.loc[(sample[entry_col] > 0) & (sample["close"] > 0)].copy()
    sample["realized_mark_return"] = sample["close"] / sample[entry_col] - 1.0

    rebalance_dates = set(select_rebalance_dates(sample["date"].tolist(), rebalance_frequency))
    rows: list[tuple[str, float]] = []
    for raw_date, group in sample.groupby("date", sort=True):
        dt = pd.Timestamp(raw_date)
        if dt not in rebalance_dates:
            continue
        rows.append((dt.strftime("%Y-%m-%d"), float(group["realized_mark_return"].mean())))
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
