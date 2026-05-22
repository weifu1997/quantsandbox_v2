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

STATIC_WINDOWS = [
    ("y2024", "20240101", "20241231"),
    ("y2025", "20250101", "20251231"),
]

ROLLING_WINDOWS = [
    ("2024H1_to_2024H2", "20240101", "20240630", "20240701", "20241231"),
    ("2024H2_to_2025H1", "20240701", "20241231", "20250101", "20250630"),
    ("2025H1_to_2025H2", "20250101", "20250630", "20250701", "20251231"),
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
    mu = x.mean()
    sd = x.std(ddof=0)
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


def build_dataset(tickers: list[str], start_date: str, end_date: str) -> tuple[pd.DataFrame, dict]:
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        factor_names=[],
        horizons=[HORIZON],
        experiment_id=None,
    )
    dataset = dataset.copy()
    dataset["date"] = pd.to_datetime(dataset["date"])
    ref = pd.read_parquet(REFERENCE_FILE)[["ticker", "industry"]].drop_duplicates(subset=["ticker"])
    dataset = dataset.merge(ref, on="ticker", how="left")
    idx_date = dataset.set_index("date").index
    pb = pd.Series(pd.to_numeric(dataset["pb"], errors="coerce").to_numpy(), index=idx_date)
    industries = pd.Series(dataset["industry"].astype("string").to_numpy(), index=idx_date)
    pb_wins = winsorize_by_date(pb)
    pb_industry_z = industry_relative_zscore_by_date(pb_wins, industries)
    dataset[factor_column(FACTOR_NAME)] = (-pb_industry_z).reset_index(drop=True)
    return dataset, dataset_summary


def build_market_regimes(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy().sort_values(["ticker", "date"])
    df["daily_ret"] = df.groupby("ticker")["close"].pct_change()
    daily = df.groupby("date").agg(ew_ret=("daily_ret", "mean")).reset_index()
    daily["eq_curve"] = (1 + daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_60d"] = daily["eq_curve"].pct_change(60)
    daily["regime_trend_60d"] = np.where(daily["market_ret_60d"] >= 0, "uptrend", "downtrend")
    return daily[["date", "regime_trend_60d"]]


def apply_downtrend_only(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    filtered = dataset.loc[dataset["regime_trend_60d"] == "downtrend"].copy()
    total_dates = int(dataset["date"].nunique())
    active_dates = int(filtered["date"].nunique())
    return filtered, {
        "active_dates": active_dates,
        "total_dates": total_dates,
        "active_ratio": float(active_dates / total_dates) if total_dates else 0.0,
    }


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def run_block(label: str, dataset: pd.DataFrame, coverage: dict) -> dict:
    factor_col = factor_column(FACTOR_NAME)
    validation = run_factor_validation(
        dataset,
        factor_col=factor_col,
        horizons=[HORIZON],
        groups=5,
        split_date=resolve_split_date(dataset),
    )
    backtest = run_topn_backtest(
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
    print(f"[done] {label}", flush=True)
    return {
        "label": label,
        "coverage": coverage,
        "rows": int(len(dataset)),
        "validation": validation,
        "backtest": backtest,
    }


def run() -> Path:
    tickers = load_expanded_tickers(1000)
    results = []
    static_runs = []
    rolling_runs = []

    for label, start_date, end_date in STATIC_WINDOWS:
        ds, summary = build_dataset(tickers, start_date, end_date)
        regimes = build_market_regimes(ds)
        merged = ds.merge(regimes, on="date", how="left")
        filtered, coverage = apply_downtrend_only(merged)
        static_runs.append(run_block(f"static__{label}", filtered, coverage))

    for label, obs_start, obs_end, test_start, test_end in ROLLING_WINDOWS:
        # observe window is recorded for context; strategy rules remain fixed and are tested only on future window
        ds, summary = build_dataset(tickers, test_start, test_end)
        regimes = build_market_regimes(ds)
        merged = ds.merge(regimes, on="date", how="left")
        filtered, coverage = apply_downtrend_only(merged)
        block = run_block(f"rolling_test__{label}", filtered, coverage)
        block["observe_window"] = {"start_date": obs_start, "end_date": obs_end}
        block["test_window"] = {"start_date": test_start, "end_date": test_end}
        rolling_runs.append(block)

    results.extend(static_runs)
    results.extend(rolling_runs)

    report = {
        "report_type": "pb_industry_lowpb_downtrend_oos_validation",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "factor": FACTOR_NAME,
            "filter": "downtrend_only",
            "ticker_count": len(tickers),
            "horizon": HORIZON,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
        },
        "static_runs": static_runs,
        "rolling_runs": rolling_runs,
        "results": results,
        "notes": [
            "Static OOS compares 2024 and 2025 directly under the chosen downtrend_only strategy.",
            "Rolling validation uses fixed strategy rules and evaluates only future half-year windows.",
            "Goal: assess whether the chosen main version survives stricter time-forward evaluation.",
        ],
    }

    out_path = Path("data/reports") / f"pbindlow_downtrend_oos_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path), flush=True)
    return out_path


if __name__ == "__main__":
    run()
