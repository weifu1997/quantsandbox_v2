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
BASE_REPORT = Path("data/reports/exp_8a03a423067c47579e75a9537e0b0b8e.json")
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")


WINDOWS = [
    ("full_2024_2025", "20240101", "20251231"),
    ("y2024", "20240101", "20241231"),
    ("y2025", "20250101", "20251231"),
]


def load_baseline_tickers() -> list[str]:
    data = json.loads(BASE_REPORT.read_text(encoding="utf-8"))
    tickers = data["config"]["tickers"]
    if len(tickers) != 300:
        raise ValueError(f"expected 300 tickers from baseline report, got {len(tickers)}")
    return tickers


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    tickers = ref["ticker"].tolist()
    if len(tickers) < limit:
        raise ValueError(f"not enough expanded tickers with both market/fund data: {len(tickers)} < {limit}")
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
        lo = x.quantile(lower)
        hi = x.quantile(upper)
        return x.clip(lower=lo, upper=hi)

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
    dates = frame.index.unique()
    for dt in dates:
        sub = frame.loc[dt].copy()
        if isinstance(sub, pd.Series):
            continue
        result = pd.Series(np.nan, index=sub.index, dtype="float64")
        for _, idx in sub.groupby("industry", dropna=True).groups.items():
            group_values = sub.loc[idx, "v"]
            result.loc[idx] = zscore_series(group_values)
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
    pb_series = pd.Series(pd.to_numeric(dataset["pb"], errors="coerce").to_numpy(), index=idx_date)
    industry_series = pd.Series(dataset["industry"].astype("string").to_numpy(), index=idx_date)
    pb_wins = winsorize_by_date(pb_series)
    pb_industry_z = industry_relative_zscore_by_date(pb_wins, industry_series)
    pb_industry_lowpb_score = -pb_industry_z
    dataset[factor_column(FACTOR_NAME)] = pb_industry_lowpb_score.reset_index(drop=True)
    return dataset, dataset_summary


def run_single(label: str, tickers: list[str], start_date: str, end_date: str) -> dict:
    dataset, dataset_summary = build_dataset(tickers, start_date, end_date)
    split_date = resolve_split_date(dataset)
    factor_col = factor_column(FACTOR_NAME)
    validation = run_factor_validation(
        dataset=dataset,
        factor_col=factor_col,
        horizons=[HORIZON],
        groups=5,
        split_date=split_date,
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
        "ticker_count": len(tickers),
        "start_date": start_date,
        "end_date": end_date,
        "dataset_summary": dataset_summary,
        "validation": validation,
        "backtest": backtest,
    }


def run() -> Path:
    baseline_300 = load_baseline_tickers()
    expanded_1000 = load_expanded_tickers(1000)

    runs = []
    for window_label, start_date, end_date in WINDOWS:
        runs.append(run_single(f"baseline300__{window_label}", baseline_300, start_date, end_date))
        runs.append(run_single(f"expanded1000__{window_label}", expanded_1000, start_date, end_date))

    report = {
        "report_type": "pb_industry_lowpb_cross_sample_validation",
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
            "baseline_300_count": len(baseline_300),
            "expanded_1000_count": len(expanded_1000),
            "windows": WINDOWS,
        },
        "runs": runs,
        "notes": [
            "Cross-sample validation keeps the best parameter point fixed: pb_industry_lowpb_score @ 60 + W + top10.",
            "Expanded sample uses the first 1000 main-board tickers with both market and fundamental parquet coverage.",
            "Time-slice validation compares full period, 2024 only, and 2025 only.",
        ],
    }

    out_path = Path("data/reports") / f"pbindlow_crosssample_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path), flush=True)
    return out_path


if __name__ == "__main__":
    run()
