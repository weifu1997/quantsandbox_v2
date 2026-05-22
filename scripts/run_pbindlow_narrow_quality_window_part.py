from __future__ import annotations

import argparse
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
HORIZON = 10
REBALANCE_FREQUENCY = "W"
TOP_N = 10
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")
OUT_DIR = Path("data/reports/refined_parts")
WINDOWS = {
    "2024H1": ("20240101", "20240630"),
    "2024H2": ("20240701", "20241231"),
    "2025H1": ("20250101", "20250630"),
    "2025H2": ("20250701", "20251231"),
}


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


def build_market_regimes(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy().sort_values(["ticker", "date"])
    df["daily_ret"] = df.groupby("ticker")["close"].pct_change()
    daily = df.groupby("date").agg(
        ew_ret=("daily_ret", "mean"),
        breadth=("daily_ret", lambda s: float((pd.to_numeric(s, errors='coerce') > 0).mean())),
    ).reset_index()
    daily["eq_curve"] = (1 + daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_20d"] = daily["eq_curve"].pct_change(20)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["trend_20d"] = np.where(daily["market_ret_20d"] >= 0, "uptrend", "downtrend")
    daily["breadth_regime"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    return daily[["date", "trend_20d", "breadth_regime"]]


def build_dataset(start_date: str, end_date: str) -> pd.DataFrame:
    tickers = load_expanded_tickers(1000)
    dataset, _, _ = build_research_dataset(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        factor_names=[],
        horizons=[HORIZON],
        experiment_id=None,
    )
    dataset = dataset.copy(); dataset["date"] = pd.to_datetime(dataset["date"])
    ref = pd.read_parquet(REFERENCE_FILE)[["ticker", "industry"]].drop_duplicates(subset=["ticker"])
    dataset = dataset.merge(ref, on="ticker", how="left")
    idx = dataset.set_index("date").index
    pb = pd.Series(pd.to_numeric(dataset["pb"], errors="coerce").to_numpy(), index=idx)
    inds = pd.Series(dataset["industry"].astype("string").to_numpy(), index=idx)
    dataset[factor_column(FACTOR_NAME)] = (-industry_relative_zscore_by_date(winsorize_by_date(pb), inds)).reset_index(drop=True)
    dataset = dataset.merge(build_market_regimes(dataset), on="date", how="left")
    return dataset


def apply_quality_narrow_filter(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    roe = pd.to_numeric(dataset["roe"], errors="coerce")
    pg = pd.to_numeric(dataset["profit_growth"], errors="coerce")
    filtered = dataset.loc[(dataset["trend_20d"] == "downtrend") & (dataset["breadth_regime"] == "narrow_weakness") & (roe > 0) & (pg > -0.2)].copy()
    total_dates = int(dataset["date"].nunique())
    active_dates = int(filtered["date"].nunique())
    return filtered, {
        "active_dates": active_dates,
        "total_dates": total_dates,
        "active_ratio": float(active_dates / total_dates) if total_dates else 0.0,
        "rows": int(len(filtered)),
    }


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    ds = sorted(dataset["date"].drop_duplicates().tolist())
    return str(pd.Timestamp(ds[len(ds)//2]).date()) if ds else None


def run_window(window_label: str) -> Path:
    start_date, end_date = WINDOWS[window_label]
    ds = build_dataset(start_date, end_date)
    filtered, coverage = apply_quality_narrow_filter(ds)
    validation = run_factor_validation(filtered, factor_col=factor_column(FACTOR_NAME), horizons=[HORIZON], groups=5, split_date=resolve_split_date(filtered))
    backtest = run_topn_backtest(filtered, factor_col=factor_column(FACTOR_NAME), top_n=TOP_N, rebalance_frequency=REBALANCE_FREQUENCY, weighting=WEIGHTING, benchmark=BENCHMARK, commission_bps=COMMISSION_BPS, slippage_bps=SLIPPAGE_BPS, horizon=HORIZON).payload
    out = {
        "report_type": "pbindlow_narrow_quality_window_part",
        "window_label": window_label,
        "start_date": start_date,
        "end_date": end_date,
        "coverage": coverage,
        "validation": validation,
        "backtest_summary": {
            "annual_return": backtest["annual_return"],
            "total_return": backtest["total_return"],
            "sharpe": backtest["sharpe"],
            "max_drawdown": backtest["max_drawdown"],
            "turnover": backtest["turnover"],
            "win_rate": backtest["win_rate"],
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"quality_window_{window_label}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", required=True, choices=sorted(WINDOWS.keys()))
    args = parser.parse_args()
    run_window(args.window)


if __name__ == '__main__':
    main()
