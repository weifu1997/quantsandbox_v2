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
from app.services.dataset_service import build_research_dataset

START_DATE = "20240101"
END_DATE = "20251231"
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
OUTPUT = Path("data/reports/pbindlow_narrow_refined_variant_corrected.json")


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


def build_dataset(tickers: list[str]) -> pd.DataFrame:
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
    dataset[factor_column("pb_industry_lowpb_score")] = (-industry_relative_zscore_by_date(winsorize_by_date(pb), inds)).reset_index(drop=True)
    dataset = dataset.merge(build_market_regimes(dataset), on="date", how="left")
    return dataset, dataset_summary


def build_refined_subsample(dataset: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, dict]:
    base = dataset.loc[(dataset["trend_20d"] == "downtrend") & (dataset["breadth_regime"] == "narrow_weakness")].copy()
    total_dates = int(dataset["date"].nunique())

    if mode == "baseline_narrow":
        filtered = base
    elif mode == "narrow_plus_quality":
        filtered = base.loc[(pd.to_numeric(base["roe"], errors="coerce") > 0) & (pd.to_numeric(base["profit_growth"], errors="coerce") > -0.2)].copy()
    elif mode == "narrow_plus_quality_indcap":
        rows = []
        factor_col = factor_column("pb_industry_lowpb_score")
        base[factor_col] = pd.to_numeric(base[factor_col], errors="coerce")
        base["roe"] = pd.to_numeric(base["roe"], errors="coerce")
        base["profit_growth"] = pd.to_numeric(base["profit_growth"], errors="coerce")
        for dt, g in base.groupby("date"):
            cross = g.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).copy()
            cross = cross.loc[(cross["roe"] > 0) & (cross["profit_growth"] > -0.2)].copy()
            if cross.empty:
                continue
            picked = []
            industry_counts = {}
            for _, row in cross.iterrows():
                industry = row.get("industry")
                if industry_counts.get(industry, 0) >= 2:
                    continue
                picked.append(row)
                industry_counts[industry] = industry_counts.get(industry, 0) + 1
                if len(picked) >= TOP_N:
                    break
            if picked:
                rows.extend(picked)
        filtered = pd.DataFrame(rows) if rows else base.iloc[0:0].copy()
    else:
        raise ValueError(mode)

    active_dates = int(filtered["date"].nunique()) if not filtered.empty else 0
    return filtered, {
        "active_dates": active_dates,
        "total_dates": total_dates,
        "active_ratio": float(active_dates / total_dates) if total_dates else 0.0,
        "rows": int(len(filtered)),
    }


def run_variant(dataset: pd.DataFrame, mode: str) -> dict:
    filtered, coverage = build_refined_subsample(dataset, mode)
    backtest = run_topn_backtest(
        dataset=filtered,
        factor_col=factor_column("pb_industry_lowpb_score"),
        top_n=TOP_N,
        rebalance_frequency=REBALANCE_FREQUENCY,
        weighting=WEIGHTING,
        benchmark=BENCHMARK,
        commission_bps=COMMISSION_BPS,
        slippage_bps=SLIPPAGE_BPS,
        horizon=HORIZON,
    ).payload
    return {
        "label": mode,
        "coverage": coverage,
        "backtest_summary": {
            "annual_return": backtest["annual_return"],
            "total_return": backtest["total_return"],
            "sharpe": backtest["sharpe"],
            "max_drawdown": backtest["max_drawdown"],
            "turnover": backtest["turnover"],
            "win_rate": backtest["win_rate"],
        },
    }


def run() -> Path:
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary = build_dataset(tickers)
    results = [
        run_variant(dataset, "baseline_narrow"),
        run_variant(dataset, "narrow_plus_quality"),
        run_variant(dataset, "narrow_plus_quality_indcap"),
    ]
    out = {
        "report_type": "pbindlow_narrow_refined_variant_corrected",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "horizon": HORIZON,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
        },
        "dataset_summary": dataset_summary,
        "results": results,
        "notes": [
            "baseline_narrow = downtrend_20d + narrow_weakness",
            "narrow_plus_quality = baseline + roe > 0 + profit_growth > -20%",
            "narrow_plus_quality_indcap = quality filter + max 2 names per industry per rebalance",
        ],
    }
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    run()
