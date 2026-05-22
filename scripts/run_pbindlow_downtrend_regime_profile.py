from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from app.services.dataset_service import build_research_dataset
from app.domain.data_contracts import factor_column

FACTOR_NAME = "pb_industry_lowpb_score"
HORIZON = 60
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")
OUTPUT = Path("data/reports/pbindlow_downtrend_regime_profile_20260517.json")
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


def build_dataset(tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    ds, _, _ = build_research_dataset(tickers=tickers, start_date=start_date, end_date=end_date, factor_names=[], horizons=[HORIZON], experiment_id=None)
    ds = ds.copy().sort_values(["ticker","date"])
    ds["date"] = pd.to_datetime(ds["date"])
    ds["daily_ret"] = ds.groupby("ticker")["close"].pct_change()
    return ds


def summarize_window(ds: pd.DataFrame, label: str) -> dict:
    daily = ds.groupby("date").agg(
        ew_ret=("daily_ret","mean"),
        breadth=("daily_ret", lambda s: float((pd.to_numeric(s, errors='coerce') > 0).mean())),
        cross_vol=("daily_ret","std"),
    ).reset_index()
    daily["eq_curve"] = (1+daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_20d"] = daily["eq_curve"].pct_change(20)
    daily["market_ret_60d"] = daily["eq_curve"].pct_change(60)
    daily["vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["regime_trend_60d"] = np.where(daily["market_ret_60d"] >= 0, "uptrend", "downtrend")
    vol_med = float(daily["vol_20d"].median(skipna=True))
    return {
        "label": label,
        "date_count": int(len(daily)),
        "mean_market_ret_20d": float(daily["market_ret_20d"].mean(skipna=True)),
        "mean_market_ret_60d": float(daily["market_ret_60d"].mean(skipna=True)),
        "downtrend_ratio": float((daily["regime_trend_60d"] == "downtrend").mean()),
        "mean_breadth_20d": float(daily["breadth_20d"].mean(skipna=True)),
        "breadth_below_50_ratio": float((daily["breadth_20d"] < 0.5).mean()),
        "mean_vol_20d": float(daily["vol_20d"].mean(skipna=True)),
        "high_vol_ratio": float((daily["vol_20d"] >= vol_med).mean()),
        "min_market_ret_60d": float(daily["market_ret_60d"].min(skipna=True)),
        "max_market_ret_60d": float(daily["market_ret_60d"].max(skipna=True)),
    }


def run() -> Path:
    tickers = load_expanded_tickers(1000)
    results = []
    for label, start_date, end_date in WINDOWS:
        ds = build_dataset(tickers, start_date, end_date)
        results.append(summarize_window(ds, label))
        print(f"[done] {label}", flush=True)
    out = {"report_type":"pbindlow_downtrend_regime_profile","generated_at":pd.Timestamp.now('UTC').isoformat(),"results":results}
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUTPUT)
    return OUTPUT

if __name__ == '__main__':
    run()
