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


VARIANTS = [
    ("always_on", None),
    ("uptrend_low_vol", {"regime_trend_60d": "uptrend", "regime_vol_20d": "low_vol"}),
]


YEAR_WINDOWS = [
    ("y2024", "20240101", "20241231"),
    ("y2025", "20250101", "20251231"),
]

ROLLING_WINDOWS = [
    ("2024H1_to_2024H2", "20240701", "20241231"),
    ("2024H2_to_2025H1", "20250101", "20250630"),
    ("2025H1_to_2025H2", "20250701", "20251231"),
]


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    return ref["ticker"].tolist()[:limit]


def load_larger_sample(limit: int = 2000) -> list[str]:
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


def build_dataset(tickers: list[str], start_date: str, end_date: str) -> tuple[pd.DataFrame, dict]:
    ds, summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        factor_names=[FACTOR_NAME],
        horizons=[HORIZON],
        experiment_id=None,
    )
    ds = ds.copy()
    ds["date"] = pd.to_datetime(ds["date"])
    ds = ds.merge(build_market_regimes(ds), on="date", how="left")
    return ds, summary


def apply_filter(ds: pd.DataFrame, condition: dict[str, str] | None) -> tuple[pd.DataFrame, dict]:
    if not condition:
        return ds.copy(), {"active_dates": int(ds["date"].nunique()), "total_dates": int(ds["date"].nunique()), "active_ratio": 1.0}
    mask = pd.Series(True, index=ds.index)
    for col, val in condition.items():
        mask &= ds[col] == val
    filtered = ds.loc[mask].copy()
    coverage = {
        "active_dates": int(filtered["date"].nunique()),
        "total_dates": int(ds["date"].nunique()),
        "active_ratio": float(filtered["date"].nunique() / ds["date"].nunique()) if ds["date"].nunique() else 0.0,
    }
    return filtered, coverage


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def run_block(label: str, dataset: pd.DataFrame, condition: dict[str, str] | None) -> dict:
    filtered, coverage = apply_filter(dataset, condition)
    validation = run_factor_validation(filtered, factor_col=f"factor:{FACTOR_NAME}", horizons=[HORIZON], groups=5, split_date=resolve_split_date(filtered))
    backtest = run_topn_backtest(filtered, factor_col=f"factor:{FACTOR_NAME}", top_n=TOP_N, rebalance_frequency=REBALANCE_FREQUENCY, weighting=WEIGHTING, benchmark=BENCHMARK, commission_bps=COMMISSION_BPS, slippage_bps=SLIPPAGE_BPS, horizon=HORIZON).payload
    print(f"[done] {label}", flush=True)
    return {"label": label, "coverage": coverage, "rows": int(len(filtered)), "validation": validation, "backtest": backtest}


def run_sample(tickers: list[str], sample_label: str) -> list[dict]:
    results = []
    for window_label, start_date, end_date in YEAR_WINDOWS:
        ds, summary = build_dataset(tickers, start_date, end_date)
        for variant_label, condition in VARIANTS:
            results.append(run_block(f"{sample_label}__{variant_label}__{window_label}", ds, condition))
    for window_label, start_date, end_date in ROLLING_WINDOWS:
        ds, summary = build_dataset(tickers, start_date, end_date)
        for variant_label, condition in VARIANTS:
            results.append(run_block(f"{sample_label}__{variant_label}__{window_label}", ds, condition))
    return results


def main() -> None:
    tickers_1000 = load_expanded_tickers(1000)
    tickers_2000 = load_larger_sample(2000)

    results = []
    results.extend(run_sample(tickers_1000, "s1000"))
    results.extend(run_sample(tickers_2000, "s2000"))

    report = {
        "report_type": "revgrowth_cross_sample_oos_real_filemode",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "factor": FACTOR_NAME,
            "horizon": HORIZON,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "sample_1000_count": len(tickers_1000),
            "sample_2000_count": len(tickers_2000),
            "windows": {"year": YEAR_WINDOWS, "rolling": ROLLING_WINDOWS},
            "variants": [v[0] for v in VARIANTS],
            "data_mode": "real_file_mode",
        },
        "results": results,
        "notes": [
            "Cross-sample OOS validation for revenue_growth candidates: always_on and uptrend_low_vol.",
            "Evaluated on s1000 and s2000 samples across yearly and half-year rolling windows.",
            "Purpose: confirm whether the growth-line candidates survive stricter out-of-sample evaluation."
        ],
    }
    out_path = Path("data/reports") / f"revgrowth_oos_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()