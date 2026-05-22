from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from app.domain.data_contracts import factor_column
from app.domain.backtest.engine import run_topn_backtest
from app.domain.research.validation import run_factor_validation
from app.services.dataset_service import build_research_dataset

FACTOR_NAME = "pb_industry_lowpb_score"
HORIZON = 60
REBALANCE_FREQUENCY = "W"
TOP_N = 10
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")
OUTPUT = Path("data/reports/pbindlow_downtrend_window_summary_20260517.json")
WINDOWS = [
    ("2024H2", "20240701", "20241231"),
    ("2025H1", "20250101", "20250630"),
    ("2025H2", "20250701", "20251231"),
]


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    return ref["ticker"].tolist()[:limit]


def winsorize_by_date(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    def _clip(s: pd.Series) -> pd.Series:
        x = pd.to_numeric(s, errors="coerce")
        if x.notna().sum() < 5:
            return x
        return x.clip(lower=x.quantile(lower), upper=x.quantile(upper))
    return series.groupby(level=0, group_keys=False).transform(_clip)


def zscore_series(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    mu = x.mean(); sd = x.std(ddof=0)
    if pd.isna(sd) or sd <= 1e-12:
        return pd.Series(np.zeros(len(x)), index=series.index, dtype="float64")
    return (x - mu) / sd


def industry_relative_zscore_by_date(values: pd.Series, industries: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "industry": industries})
    out = pd.Series(np.nan, index=frame.index, dtype="float64")
    for dt in frame.index.unique():
        sub = frame.loc[dt].copy()
        if isinstance(sub, pd.Series):
            continue
        result = pd.Series(np.nan, index=sub.index, dtype="float64")
        for _, idx in sub.groupby("industry", dropna=True).groups.items():
            result.loc[idx] = zscore_series(sub.loc[idx, "v"])
        out.loc[dt] = result.to_numpy()
    return out


def build_dataset(tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    dataset, _, _ = build_research_dataset(tickers=tickers, start_date=start_date, end_date=end_date, factor_names=[], horizons=[HORIZON], experiment_id=None)
    dataset = dataset.copy(); dataset["date"] = pd.to_datetime(dataset["date"])
    ref = pd.read_parquet(REFERENCE_FILE)[["ticker", "industry"]].drop_duplicates(subset=["ticker"])
    dataset = dataset.merge(ref, on="ticker", how="left")
    idx = dataset.set_index("date").index
    pb = pd.Series(pd.to_numeric(dataset["pb"], errors="coerce").to_numpy(), index=idx)
    inds = pd.Series(dataset["industry"].astype("string").to_numpy(), index=idx)
    dataset[factor_column(FACTOR_NAME)] = (-industry_relative_zscore_by_date(winsorize_by_date(pb), inds)).reset_index(drop=True)
    return dataset


def build_regime(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy().sort_values(["ticker","date"])
    df["daily_ret"] = df.groupby("ticker")["close"].pct_change()
    daily = df.groupby("date").agg(ew_ret=("daily_ret","mean")).reset_index()
    daily["eq_curve"] = (1+daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_60d"] = daily["eq_curve"].pct_change(60)
    daily["regime_trend_60d"] = np.where(daily["market_ret_60d"] >= 0, "uptrend", "downtrend")
    return daily[["date","regime_trend_60d"]]


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    ds = sorted(dataset["date"].drop_duplicates().tolist())
    return str(pd.Timestamp(ds[len(ds)//2]).date()) if ds else None


def run() -> Path:
    tickers = load_expanded_tickers(1000)
    results = []
    for label, start_date, end_date in WINDOWS:
        ds = build_dataset(tickers, start_date, end_date)
        regime = build_regime(ds)
        merged = ds.merge(regime, on="date", how="left")
        filtered = merged.loc[merged["regime_trend_60d"] == "downtrend"].copy()
        coverage = {
            "active_dates": int(filtered["date"].nunique()),
            "total_dates": int(merged["date"].nunique()),
            "active_ratio": float(filtered["date"].nunique()/merged["date"].nunique()) if merged["date"].nunique() else 0.0,
        }
        validation = run_factor_validation(filtered, factor_col=factor_column(FACTOR_NAME), horizons=[HORIZON], groups=5, split_date=resolve_split_date(filtered))
        backtest = run_topn_backtest(filtered, factor_col=factor_column(FACTOR_NAME), top_n=TOP_N, rebalance_frequency=REBALANCE_FREQUENCY, weighting=WEIGHTING, benchmark=BENCHMARK, commission_bps=COMMISSION_BPS, slippage_bps=SLIPPAGE_BPS, horizon=HORIZON).payload
        results.append({"label": label, "start_date": start_date, "end_date": end_date, "coverage": coverage, "validation": validation, "backtest": backtest, "rows": int(len(filtered))})
        print(f"[done] {label}", flush=True)
    out = {"report_type":"pbindlow_downtrend_window_summary","generated_at":pd.Timestamp.now('UTC').isoformat(),"results":results}
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUTPUT)
    return OUTPUT

if __name__ == '__main__':
    run()
