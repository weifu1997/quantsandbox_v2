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

START_DATE = "20240101"
END_DATE = "20251231"
HORIZON = 20
REBALANCE_FREQUENCY = "W"
TOP_N = 10
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
BASE_REPORT = Path("data/reports/exp_8a03a423067c47579e75a9537e0b0b8e.json")
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")


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


def zscore_by_date(series: pd.Series) -> pd.Series:
    def _z(s: pd.Series) -> pd.Series:
        x = pd.to_numeric(s, errors="coerce")
        mu = x.mean()
        sd = x.std(ddof=0)
        if pd.isna(sd) or sd <= 1e-12:
            return pd.Series(np.zeros(len(x)), index=x.index, dtype="float64")
        return (x - mu) / sd

    return series.groupby(level=0, group_keys=False).transform(_z)


def percentile_rank_within_group(values: pd.Series, groups: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "g": groups})
    out = pd.Series(np.nan, index=frame.index, dtype="float64")
    for _, idx in frame.groupby("g", dropna=True).groups.items():
        sub = frame.loc[idx, "v"]
        ranks = sub.rank(method="average", pct=True)
        out.loc[idx] = ranks
    return out


def zscore_within_group(values: pd.Series, groups: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "g": groups})
    out = pd.Series(np.nan, index=frame.index, dtype="float64")
    for _, idx in frame.groupby("g", dropna=True).groups.items():
        sub = frame.loc[idx, "v"]
        mu = sub.mean()
        sd = sub.std(ddof=0)
        if pd.isna(sd) or sd <= 1e-12:
            out.loc[idx] = 0.0
        else:
            out.loc[idx] = (sub - mu) / sd
    return out


def industry_relative_rank_by_date(values: pd.Series, industries: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "industry": industries})
    out = pd.Series(np.nan, index=frame.index, dtype="float64")
    dates = frame.index.unique()
    for dt in dates:
        sub = frame.loc[dt].copy()
        if isinstance(sub, pd.Series):
            continue
        out.loc[dt] = percentile_rank_within_group(sub["v"], sub["industry"]).to_numpy()
    return out


def industry_relative_zscore_by_date(values: pd.Series, industries: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "industry": industries})
    out = pd.Series(np.nan, index=frame.index, dtype="float64")
    dates = frame.index.unique()
    for dt in dates:
        sub = frame.loc[dt].copy()
        if isinstance(sub, pd.Series):
            continue
        out.loc[dt] = zscore_within_group(sub["v"], sub["industry"]).to_numpy()
    return out


def build_variant_dataset() -> tuple[pd.DataFrame, dict, list[str]]:
    tickers = load_tickers()
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

    pb = pd.to_numeric(dataset["pb"], errors="coerce")
    idx_date = dataset.set_index("date").index
    by_date_pb = pd.Series(pb.to_numpy(), index=idx_date)
    by_date_industry = pd.Series(dataset["industry"].astype("string").to_numpy(), index=idx_date)

    pb_raw = by_date_pb
    pb_wins = winsorize_by_date(pb_raw)
    pb_industry_rank = industry_relative_rank_by_date(pb_wins, by_date_industry)
    pb_industry_zscore = industry_relative_zscore_by_date(pb_wins, by_date_industry)
    pb_industry_lowpb_score = -pb_industry_zscore

    variant_map = {
        "pb_raw": pb_raw,
        "pb_winsorized": pb_wins,
        "pb_industry_rank": pb_industry_rank,
        "pb_industry_zscore": pb_industry_zscore,
        "pb_industry_lowpb_score": pb_industry_lowpb_score,
    }

    for name, series in variant_map.items():
        dataset[factor_column(name)] = series.reset_index(drop=True)

    return dataset, dataset_summary, tickers


def run() -> Path:
    dataset, dataset_summary, tickers = build_variant_dataset()
    split_date = resolve_split_date(dataset)
    factor_names = [
        "pb_raw",
        "pb_winsorized",
        "pb_industry_rank",
        "pb_industry_zscore",
        "pb_industry_lowpb_score",
    ]

    factor_results = {}
    backtest_results = {}
    coverage = {}
    for name in factor_names:
        col = factor_column(name)
        factor_results[name] = run_factor_validation(
            dataset=dataset,
            factor_col=col,
            horizons=[HORIZON],
            groups=5,
            split_date=split_date,
        )
        backtest_results[name] = run_topn_backtest(
            dataset=dataset,
            factor_col=col,
            top_n=TOP_N,
            rebalance_frequency=REBALANCE_FREQUENCY,
            weighting=WEIGHTING,
            benchmark=BENCHMARK,
            commission_bps=COMMISSION_BPS,
            slippage_bps=SLIPPAGE_BPS,
            horizon=HORIZON,
        ).payload
        coverage[name] = {
            "non_null_ratio": float(pd.to_numeric(dataset[col], errors="coerce").notna().mean()),
            "valid_non_null_ratio": float(pd.to_numeric(dataset.loc[dataset["is_valid_sample"] == True, col], errors="coerce").notna().mean()),
        }
        print(f"[done] {name}", flush=True)

    report = {
        "report_type": "pb_industry_relative_experiment",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "tickers": tickers,
            "horizons": [HORIZON],
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "baseline_report": str(BASE_REPORT),
        },
        "dataset_summary": dataset_summary,
        "variant_coverage": coverage,
        "factor_results": factor_results,
        "backtest_results": backtest_results,
        "notes": [
            "pb variants are computed on top of the same 300-stock sample used by exp_8a03a423067c47579e75a9537e0b0b8e.",
            "Winsorization uses daily 1%/99% clipping.",
            "Industry rank is daily percentile rank within industry.",
            "Industry z-score is daily z-score within industry.",
            "Industry low-pb score is the negative of industry z-score so higher score means cheaper within industry.",
        ],
    }

    out_path = Path("data/reports") / f"pb_industry_relative_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path), flush=True)
    return out_path


if __name__ == "__main__":
    run()
