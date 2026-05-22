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
START_DATE = "20240101"
END_DATE = "20251231"


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


def build_base_dataset(tickers: list[str]) -> tuple[pd.DataFrame, dict]:
    ds, summary, _ = build_research_dataset(tickers=tickers, start_date=START_DATE, end_date=END_DATE, factor_names=[], horizons=[HORIZON], experiment_id=None)
    ds = ds.copy(); ds["date"] = pd.to_datetime(ds["date"])
    ref = pd.read_parquet(REFERENCE_FILE)[["ticker","industry"]].drop_duplicates(subset=["ticker"])
    ds = ds.merge(ref, on="ticker", how="left")
    idx = ds.set_index("date").index
    pb = pd.Series(pd.to_numeric(ds["pb"], errors="coerce").to_numpy(), index=idx)
    inds = pd.Series(ds["industry"].astype("string").to_numpy(), index=idx)
    ds[factor_column(FACTOR_NAME)] = (-industry_relative_zscore_by_date(winsorize_by_date(pb), inds)).reset_index(drop=True)
    return ds, summary


def build_market_regimes(ds: pd.DataFrame) -> pd.DataFrame:
    df = ds.copy().sort_values(["ticker","date"])
    df["daily_ret"] = df.groupby("ticker")["close"].pct_change()
    daily = df.groupby("date").agg(
        ew_ret=("daily_ret","mean"),
        breadth=("daily_ret", lambda s: float((pd.to_numeric(s, errors='coerce') > 0).mean())),
    ).reset_index()
    daily["eq_curve"] = (1+daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_60d"] = daily["eq_curve"].pct_change(60)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["regime_trend_60d"] = np.where(daily["market_ret_60d"] >= 0, "uptrend", "downtrend")
    daily["regime_breadth_20d"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    return daily[["date","regime_trend_60d","regime_breadth_20d","vol_20d"]]


def add_industry_concentration_signal(ds: pd.DataFrame) -> pd.DataFrame:
    sample = ds.copy()
    factor_col = factor_column(FACTOR_NAME)
    rows = []
    for dt, g in sample.groupby("date"):
        cross = g.copy()
        cross[factor_col] = pd.to_numeric(cross[factor_col], errors='coerce')
        top = cross.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).head(TOP_N)
        total = len(top)
        top3_share = 0.0
        if total > 0:
            counts = top['industry'].value_counts()
            top3_share = float(counts.head(3).sum() / total)
        rows.append({"date": dt, "top3_industry_share_pretrade": top3_share})
    return sample.merge(pd.DataFrame(rows), on='date', how='left')


def apply_variant(ds: pd.DataFrame, name: str) -> tuple[pd.DataFrame, dict]:
    sample = ds.copy()
    mask = sample['regime_trend_60d'] == 'downtrend'
    if name == 'downtrend_plus_narrow_weakness':
        mask &= sample['regime_breadth_20d'] == 'narrow_weakness'
    elif name == 'downtrend_plus_exclude_low_vol_drift':
        vol_thresh = float(sample['vol_20d'].median(skipna=True))
        mask &= sample['vol_20d'] >= vol_thresh
    elif name == 'downtrend_plus_industry_concentration_cap':
        mask &= sample['top3_industry_share_pretrade'] <= 0.8
    filtered = sample.loc[mask].copy()
    coverage = {
        'active_dates': int(filtered['date'].nunique()),
        'total_dates': int(sample['date'].nunique()),
        'active_ratio': float(filtered['date'].nunique()/sample['date'].nunique()) if sample['date'].nunique() else 0.0,
    }
    return filtered, coverage


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    ds = sorted(dataset['date'].drop_duplicates().tolist())
    return str(pd.Timestamp(ds[len(ds)//2]).date()) if ds else None


def run_variant(name: str, ds: pd.DataFrame) -> dict:
    filtered, coverage = apply_variant(ds, name)
    validation = run_factor_validation(filtered, factor_col=factor_column(FACTOR_NAME), horizons=[HORIZON], groups=5, split_date=resolve_split_date(filtered))
    backtest = run_topn_backtest(filtered, factor_col=factor_column(FACTOR_NAME), top_n=TOP_N, rebalance_frequency=REBALANCE_FREQUENCY, weighting=WEIGHTING, benchmark=BENCHMARK, commission_bps=COMMISSION_BPS, slippage_bps=SLIPPAGE_BPS, horizon=HORIZON).payload
    print(f"[done] {name}", flush=True)
    return {
        'label': name,
        'coverage': coverage,
        'rows': int(len(filtered)),
        'validation': validation,
        'backtest': backtest,
    }


def run() -> Path:
    tickers = load_expanded_tickers(1000)
    ds, summary = build_base_dataset(tickers)
    ds = ds.merge(build_market_regimes(ds), on='date', how='left')
    ds = add_industry_concentration_signal(ds)

    variants = [
        'downtrend_only',
        'downtrend_plus_narrow_weakness',
        'downtrend_plus_exclude_low_vol_drift',
        'downtrend_plus_industry_concentration_cap',
    ]
    results = [run_variant(v, ds) for v in variants]

    out = {
        'report_type': 'pbindlow_refined_filter_candidates',
        'generated_at': pd.Timestamp.now('UTC').isoformat(),
        'config': {
            'factor': FACTOR_NAME,
            'ticker_count': len(tickers),
            'start_date': START_DATE,
            'end_date': END_DATE,
            'horizon': HORIZON,
            'rebalance_frequency': REBALANCE_FREQUENCY,
            'top_n': TOP_N,
            'weighting': WEIGHTING,
            'benchmark': BENCHMARK,
        },
        'results': results,
        'notes': [
            'Candidate refinement validation for downtrend_only.',
            'Low-vol drift filter uses vol_20d >= full-sample median(vol_20d).',
            'Industry concentration cap uses pretrade top3 industry share <= 0.8.',
        ],
    }
    out_path = Path('data/reports') / f"pbindlow_refined_filters_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out_path)
    return out_path

if __name__ == '__main__':
    run()
