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
from app.domain.data_contracts import factor_column
from app.domain.research.validation import run_factor_validation
from app.services.dataset_service import build_research_dataset

START_DATE = "20240101"
END_DATE = "20260514"
FACTOR_NAME = "pb_industry_lowpb_score"
HORIZON = 10
REBALANCE_FREQUENCY = "W"
TOP_NS = [10, 15, 20]
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")


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


def build_dataset() -> tuple[pd.DataFrame, dict]:
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
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
    roe = pd.to_numeric(dataset["roe"], errors="coerce")
    pg = pd.to_numeric(dataset["profit_growth"], errors="coerce")
    dataset = dataset.loc[(dataset["trend_20d"] == "downtrend") & (dataset["breadth_regime"] == "narrow_weakness") & (roe > 0) & (pg > -0.2)].copy()
    return dataset, dataset_summary


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def run() -> Path:
    dataset, dataset_summary = build_dataset()
    split_date = resolve_split_date(dataset)
    validation = run_factor_validation(dataset, factor_col=factor_column(FACTOR_NAME), horizons=[HORIZON], groups=5, split_date=split_date)

    results = []
    for top_n in TOP_NS:
        bt = run_topn_backtest(
            dataset=dataset,
            factor_col=factor_column(FACTOR_NAME),
            top_n=top_n,
            rebalance_frequency=REBALANCE_FREQUENCY,
            weighting=WEIGHTING,
            benchmark=BENCHMARK,
            commission_bps=COMMISSION_BPS,
            slippage_bps=SLIPPAGE_BPS,
            horizon=HORIZON,
        ).payload
        results.append({
            "top_n": top_n,
            "backtest": {
                "annual_return": bt["annual_return"],
                "total_return": bt["total_return"],
                "sharpe": bt["sharpe"],
                "max_drawdown": bt["max_drawdown"],
                "turnover": bt["turnover"],
                "win_rate": bt["win_rate"],
            },
        })
        print(f"[done] top_n={top_n}", flush=True)

    ranked = sorted(results, key=lambda x: (x["backtest"]["sharpe"], x["backtest"]["annual_return"], -x["backtest"]["max_drawdown"]), reverse=True)
    report = {
        "report_type": "pbindlow_narrow_quality_topn_robustness_extended_2026H1",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "horizon": HORIZON,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_ns": TOP_NS,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
        },
        "dataset_summary": dataset_summary,
        "coverage": {
            "rows": int(len(dataset)),
            "active_dates": int(dataset["date"].nunique()),
        },
        "validation": validation,
        "results": results,
        "ranked": ranked,
        "notes": [
            "Extended robustness check including the 2026H1 weakening window.",
            "Use this to judge whether wider top_n settings are more robust once the new weak window is included.",
        ],
    }
    out_path = Path("data/reports") / f"pbindlow_narrow_quality_topn_robustness_extended_2026H1_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)
    return out_path


if __name__ == '__main__':
    run()
