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

START_DATE = "20240101"
END_DATE = "20251231"
HORIZON = 60
REBALANCE_FREQUENCY = "W"
TOP_N = 20
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")
BASE_FACTOR = "revenue_growth"


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    return ref["ticker"].tolist()[:limit]


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def winsorize_by_date(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    def _clip(s: pd.Series) -> pd.Series:
        x = pd.to_numeric(s, errors="coerce")
        if x.notna().sum() < 5:
            return x
        return x.clip(lower=x.quantile(lower), upper=x.quantile(upper))
    return series.groupby(level=0, group_keys=False).transform(_clip)


def zscore_by_date(series: pd.Series) -> pd.Series:
    def _z(s: pd.Series) -> pd.Series:
        x = pd.to_numeric(s, errors="coerce")
        mu = x.mean()
        sd = x.std(ddof=0)
        if pd.isna(sd) or sd <= 1e-12:
            return pd.Series(np.zeros(len(x)), index=x.index, dtype="float64")
        return (x - mu) / sd
    return series.groupby(level=0, group_keys=False).transform(_z)


def build_dataset() -> tuple[pd.DataFrame, dict, list[str]]:
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        factor_names=[BASE_FACTOR],
        horizons=[HORIZON],
        experiment_id=None,
    )
    dataset = dataset.copy()
    dataset["date"] = pd.to_datetime(dataset["date"])
    raw = pd.to_numeric(dataset[f"factor:{BASE_FACTOR}"], errors="coerce")
    by_date = pd.Series(raw.to_numpy(), index=dataset["date"])
    variants = {
        "revenue_growth_raw": by_date,
        "revenue_growth_winsorized": winsorize_by_date(by_date),
        "revenue_growth_zscore": zscore_by_date(by_date),
        "revenue_growth_winsorized_zscore": zscore_by_date(winsorize_by_date(by_date)),
    }
    for name, series in variants.items():
        dataset[f"factor:{name}"] = series.reset_index(drop=True)
    return dataset, dataset_summary, tickers


def run() -> Path:
    dataset, dataset_summary, tickers = build_dataset()
    split_date = resolve_split_date(dataset)
    variants = [
        "revenue_growth_raw",
        "revenue_growth_winsorized",
        "revenue_growth_zscore",
        "revenue_growth_winsorized_zscore",
    ]

    factor_results = {}
    backtest_results = {}
    coverage = {}
    for name in variants:
        factor_col = f"factor:{name}"
        factor_results[name] = run_factor_validation(
            dataset=dataset,
            factor_col=factor_col,
            horizons=[HORIZON],
            groups=5,
            split_date=split_date,
        )
        backtest_results[name] = run_topn_backtest(
            dataset=dataset,
            factor_col=factor_col,
            top_n=TOP_N,
            rebalance_frequency=REBALANCE_FREQUENCY,
            weighting=WEIGHTING,
            benchmark=BENCHMARK,
            commission_bps=COMMISSION_BPS,
            slippage_bps=SLIPPAGE_BPS,
            horizon=HORIZON,
        ).payload
        coverage[name] = {
            "non_null_ratio": float(pd.to_numeric(dataset[factor_col], errors="coerce").notna().mean()),
            "valid_non_null_ratio": float(pd.to_numeric(dataset.loc[dataset["is_valid_sample"] == True, factor_col], errors="coerce").notna().mean()),
        }
        print(f"[done] {name}", flush=True)

    report = {
        "report_type": "revenue_growth_version_convergence_real_filemode",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "ticker_count": len(tickers),
            "base_factor": BASE_FACTOR,
            "horizon": HORIZON,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "data_mode": "real_file_mode",
        },
        "dataset_summary": dataset_summary,
        "coverage": coverage,
        "factor_results": factor_results,
        "backtest_results": backtest_results,
        "notes": [
            "Task 26: revenue_growth version convergence using the currently best execution area (60/W/top20).",
            "Goal: decide which normalized/preprocessed version should become the growth-line main version before environment adaptation work.",
        ],
    }

    out_path = Path("data/reports") / f"revenue_growth_convergence_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)
    return out_path


if __name__ == "__main__":
    run()
