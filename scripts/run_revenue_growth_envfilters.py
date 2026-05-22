from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from app.domain.backtest.engine import run_topn_backtest
from app.domain.research.validation import run_factor_validation
from app.services.dataset_service import build_research_dataset

FACTOR_NAME = "revenue_growth"
HORIZON = 60
REBALANCE_FREQUENCY = "W"
TOP_N = 20
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
START_DATE = "20240101"
END_DATE = "20251231"
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")

FILTERS = [
    ("baseline_always_on", None),
    ("uptrend_only", {"regime_trend_60d": "uptrend"}),
    ("low_vol_only", {"regime_vol_20d": "low_vol"}),
    ("uptrend_low_vol", {"regime_trend_60d": "uptrend", "regime_vol_20d": "low_vol"}),
    ("broad_strength_only", {"regime_breadth_20d": "broad_strength"}),
]


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    return ref["ticker"].tolist()[:limit]


def build_market_regimes(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy().sort_values(["ticker", "date"])
    df["daily_ret"] = df.groupby("ticker")["close"].pct_change()
    daily = df.groupby("date").agg(
        ew_ret=("daily_ret", "mean"),
        breadth=("daily_ret", lambda s: float((pd.to_numeric(s, errors='coerce') > 0).mean())),
    ).reset_index()
    daily["eq_curve"] = (1 + daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_60d"] = daily["eq_curve"].pct_change(60)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["regime_trend_60d"] = np.where(daily["market_ret_60d"] >= 0, "uptrend", "downtrend")
    vol_med = float(daily["vol_20d"].median(skipna=True))
    daily["regime_vol_20d"] = np.where(daily["vol_20d"] >= vol_med, "high_vol", "low_vol")
    daily["regime_breadth_20d"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    return daily[["date", "regime_trend_60d", "regime_vol_20d", "regime_breadth_20d"]]


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def apply_filter(dataset: pd.DataFrame, condition: dict[str, str] | None) -> tuple[pd.DataFrame, dict]:
    sample = dataset.copy()
    if not condition:
        coverage = {
            "active_dates": int(sample["date"].nunique()),
            "total_dates": int(sample["date"].nunique()),
            "active_ratio": 1.0,
        }
        return sample, coverage

    mask = pd.Series(True, index=sample.index)
    for col, val in condition.items():
        mask &= sample[col] == val
    filtered = sample.loc[mask].copy()
    total_dates = int(sample["date"].nunique())
    active_dates = int(filtered["date"].nunique())
    coverage = {
        "active_dates": active_dates,
        "total_dates": total_dates,
        "active_ratio": float(active_dates / total_dates) if total_dates else 0.0,
    }
    return filtered, coverage


def run_variant(label: str, dataset: pd.DataFrame, condition: dict[str, str] | None) -> dict:
    filtered, coverage = apply_filter(dataset, condition)
    validation = run_factor_validation(
        filtered,
        factor_col=f"factor:{FACTOR_NAME}",
        horizons=[HORIZON],
        groups=5,
        split_date=resolve_split_date(filtered),
    )
    backtest = run_topn_backtest(
        dataset=filtered,
        factor_col=f"factor:{FACTOR_NAME}",
        top_n=TOP_N,
        rebalance_frequency=REBALANCE_FREQUENCY,
        weighting=WEIGHTING,
        benchmark=BENCHMARK,
        commission_bps=COMMISSION_BPS,
        slippage_bps=SLIPPAGE_BPS,
        horizon=HORIZON,
    ).payload
    print(f"[done] {label}", flush=True)
    return {
        "label": label,
        "condition": condition,
        "coverage": coverage,
        "rows": int(len(filtered)),
        "validation": validation,
        "backtest": backtest,
    }


def main() -> None:
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        factor_names=[FACTOR_NAME],
        horizons=[HORIZON],
        experiment_id=None,
    )
    dataset = dataset.copy()
    dataset["date"] = pd.to_datetime(dataset["date"])
    dataset = dataset.merge(build_market_regimes(dataset), on="date", how="left")

    results = []
    for label, condition in FILTERS:
        results.append(run_variant(label, dataset, condition))

    report = {
        "report_type": "revenue_growth_environment_filters_real_filemode",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "factor": FACTOR_NAME,
            "ticker_count": len(tickers),
            "start_date": START_DATE,
            "end_date": END_DATE,
            "horizon": HORIZON,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "data_mode": "real_file_mode",
        },
        "dataset_summary": dataset_summary,
        "results": results,
        "notes": [
            "Task 28: environment-filter strategy validation for revenue_growth_raw.",
            "Goal: decide whether the growth-line main version should be treated as an always-on signal or as a conditional strategy.",
        ],
    }

    out_path = Path("data/reports") / f"revenue_growth_envfilters_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
