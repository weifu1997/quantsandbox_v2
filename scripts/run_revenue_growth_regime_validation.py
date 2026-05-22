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
HORIZON = 10
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
        cross_vol=("daily_ret", "std"),
    ).reset_index()
    daily["eq_curve"] = (1 + daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_20d"] = daily["eq_curve"].pct_change(20)
    daily["vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["regime_trend_20d"] = np.where(daily["market_ret_20d"] >= 0, "uptrend", "downtrend")
    vol_med = float(daily["vol_20d"].median(skipna=True))
    daily["regime_vol_20d"] = np.where(daily["vol_20d"] >= vol_med, "high_vol", "low_vol")
    daily["regime_breadth_20d"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    daily["calendar_year"] = daily["date"].dt.year.astype(str)
    return daily


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def subset_and_run(dataset: pd.DataFrame, label: str, mask: pd.Series) -> dict:
    sample = dataset.loc[mask].copy()
    validation = run_factor_validation(
        sample,
        factor_col=f"factor:{FACTOR_NAME}",
        horizons=[HORIZON],
        groups=5,
        split_date=resolve_split_date(sample),
    )
    backtest = run_topn_backtest(
        dataset=sample,
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
        "rows": int(len(sample)),
        "unique_dates": int(sample["date"].nunique()),
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
    regimes = build_market_regimes(dataset)
    merged = dataset.merge(regimes, on="date", how="left")

    analyses = []
    analyses.append(subset_and_run(merged, "all_dates", merged["date"].notna()))
    analyses.append(subset_and_run(merged, "year_2024", merged["calendar_year"] == "2024"))
    analyses.append(subset_and_run(merged, "year_2025", merged["calendar_year"] == "2025"))

    for col in ["regime_trend_20d", "regime_vol_20d", "regime_breadth_20d"]:
        for value in sorted(merged[col].dropna().unique().tolist()):
            analyses.append(subset_and_run(merged, f"{col}__{value}", merged[col] == value))

    report = {
        "report_type": "revenue_growth_regime_validation_real_filemode",
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
        "market_regime_summary": {
            "date_count": int(len(regimes)),
            "vol_median_20d": float(regimes["vol_20d"].median(skipna=True)),
        },
        "analyses": analyses,
        "notes": [
            "Task 27: environment adaptation validation for revenue_growth_raw using a frequency-aligned weekly setup (10/W/top20).",
            "Goal: determine whether revenue_growth has a stable environment preference before promoting it into the second strategy-candidate line.",
        ],
    }

    out_path = Path("data/reports") / f"revenue_growth_regime_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
