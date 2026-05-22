from __future__ import annotations

import json
import sys
from itertools import product
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

START_DATE = "20240101"
END_DATE = "20251231"
HORIZONS = [20, 60]
FREQUENCIES = ["W", "M"]
TOP_NS = [10, 20, 30]
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
BASE_REPORT = Path("data/reports/exp_8a03a423067c47579e75a9537e0b0b8e.json")
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
FACTOR_NAME = "pb_industry_lowpb_score"


def load_tickers() -> list[str]:
    data = json.loads(BASE_REPORT.read_text(encoding="utf-8"))
    tickers = data["config"]["tickers"]
    if len(tickers) != 300:
        raise ValueError(f"expected 300 tickers from baseline report, got {len(tickers)}")
    return tickers


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


def build_dataset() -> tuple[pd.DataFrame, dict, list[str]]:
    tickers = load_tickers()
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        factor_names=[],
        horizons=HORIZONS,
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
    return dataset, dataset_summary, tickers


def run() -> Path:
    dataset, dataset_summary, tickers = build_dataset()
    split_date = resolve_split_date(dataset)
    factor_col = factor_column(FACTOR_NAME)

    validation_by_horizon = run_factor_validation(
        dataset=dataset,
        factor_col=factor_col,
        horizons=HORIZONS,
        groups=5,
        split_date=split_date,
    )

    grid_results = []
    for horizon, freq, top_n in product(HORIZONS, FREQUENCIES, TOP_NS):
        bt = run_topn_backtest(
            dataset=dataset,
            factor_col=factor_col,
            top_n=top_n,
            rebalance_frequency=freq,
            weighting=WEIGHTING,
            benchmark=BENCHMARK,
            commission_bps=COMMISSION_BPS,
            slippage_bps=SLIPPAGE_BPS,
            horizon=horizon,
        ).payload
        grid_results.append(
            {
                "horizon": horizon,
                "rebalance_frequency": freq,
                "top_n": top_n,
                "validation_full_sample": validation_by_horizon["full_sample"][str(horizon)],
                "validation_in_sample": validation_by_horizon["in_sample"].get(str(horizon), {}),
                "validation_out_sample": validation_by_horizon["out_sample"].get(str(horizon), {}),
                "backtest": bt,
            }
        )
        print(f"[done] horizon={horizon} freq={freq} top_n={top_n}", flush=True)

    # simple ranking helper for quick inspection
    ranked = sorted(
        grid_results,
        key=lambda x: (
            x["backtest"].get("sharpe", 0.0),
            x["backtest"].get("annual_return", 0.0),
            -(x["backtest"].get("max_drawdown", 0.0) or 0.0),
        ),
        reverse=True,
    )

    report = {
        "report_type": "pb_industry_lowpb_score_robustness_grid",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "tickers": tickers,
            "factor": FACTOR_NAME,
            "horizons": HORIZONS,
            "rebalance_frequencies": FREQUENCIES,
            "top_ns": TOP_NS,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "baseline_report": str(BASE_REPORT),
        },
        "dataset_summary": dataset_summary,
        "grid_results": grid_results,
        "top_ranked_points": ranked[:5],
        "notes": [
            "This is the 12-point robustness grid for pb_industry_lowpb_score.",
            "Validation statistics are horizon-specific and reused across frequency/top_n because they depend on factor vs future return, not execution settings.",
            "Backtest metrics are the differentiator across W/M and top_n choices.",
        ],
    }

    out_path = Path("data/reports") / f"pbindlow_robustness_grid_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path), flush=True)
    return out_path


if __name__ == "__main__":
    run()
