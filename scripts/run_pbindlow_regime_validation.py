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
from app.domain.research.validation import run_factor_validation
from app.domain.backtest.engine import run_topn_backtest
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
START_DATE = "20240101"
END_DATE = "20251231"


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    tickers = ref["ticker"].tolist()
    return tickers[:limit]


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


def build_dataset(tickers: list[str]) -> tuple[pd.DataFrame, dict]:
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
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
    df = dataset.copy()
    df = df.sort_values(["ticker", "date"])
    df["daily_ret"] = df.groupby("ticker")["close"].pct_change()
    daily = df.groupby("date").agg(
        ew_ret=("daily_ret", "mean"),
        median_ret=("daily_ret", "median"),
        cross_vol=("daily_ret", "std"),
        breadth=("daily_ret", lambda s: float((pd.to_numeric(s, errors='coerce') > 0).mean())),
    ).reset_index()
    daily["eq_curve"] = (1 + daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_20d"] = daily["eq_curve"].pct_change(20)
    daily["market_ret_60d"] = daily["eq_curve"].pct_change(60)
    daily["market_vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["regime_trend_60d"] = np.where(daily["market_ret_60d"] >= 0, "uptrend", "downtrend")
    vol_med = daily["market_vol_20d"].median(skipna=True)
    daily["regime_vol_20d"] = np.where(daily["market_vol_20d"] >= vol_med, "high_vol", "low_vol")
    daily["regime_breadth_20d"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    daily["calendar_year"] = daily["date"].dt.year.astype(str)
    return daily


def subset_and_run(dataset: pd.DataFrame, label: str, date_mask: pd.Series) -> dict:
    sample = dataset.loc[date_mask].copy()
    factor_col = factor_column(FACTOR_NAME)
    validation = run_factor_validation(sample, factor_col=factor_col, horizons=[HORIZON], groups=5, split_date=resolve_split_date(sample))
    backtest = run_topn_backtest(
        dataset=sample,
        factor_col=factor_col,
        top_n=TOP_N,
        rebalance_frequency=REBALANCE_FREQUENCY,
        weighting=WEIGHTING,
        benchmark=BENCHMARK,
        commission_bps=COMMISSION_BPS,
        slippage_bps=SLIPPAGE_BPS,
        horizon=HORIZON,
    ).payload
    return {
        "label": label,
        "rows": int(len(sample)),
        "unique_dates": int(sample["date"].nunique()),
        "validation": validation,
        "backtest": backtest,
    }


def run() -> Path:
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary = build_dataset(tickers)
    regimes = build_market_regimes(dataset)
    merged = dataset.merge(regimes, on="date", how="left")

    analyses = []
    analyses.append(subset_and_run(merged, "all_dates", merged["date"].notna()))
    analyses.append(subset_and_run(merged, "year_2024", merged["calendar_year"] == "2024"))
    analyses.append(subset_and_run(merged, "year_2025", merged["calendar_year"] == "2025"))

    for col in ["regime_trend_60d", "regime_vol_20d", "regime_breadth_20d"]:
        for value in sorted(merged[col].dropna().unique().tolist()):
            analyses.append(subset_and_run(merged, f"{col}__{value}", merged[col] == value))

    report = {
        "report_type": "pb_industry_lowpb_regime_validation",
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
        },
        "dataset_summary": dataset_summary,
        "market_regime_summary": {
            "vol_median_20d": float(regimes["market_vol_20d"].median(skipna=True)),
            "date_count": int(len(regimes)),
        },
        "analyses": analyses,
        "notes": [
            "Trend regime is defined by 60-day equal-weight market return sign.",
            "Vol regime is defined by above/below median 20-day equal-weight market volatility.",
            "Breadth regime is defined by 20-day average share of stocks with positive daily returns above/below 50%.",
            "Purpose: explain why the factor was stronger in 2024 than 2025 by conditioning on market environment.",
        ],
    }

    out_path = Path("data/reports") / f"pbindlow_regime_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path), flush=True)
    return out_path


if __name__ == "__main__":
    run()
