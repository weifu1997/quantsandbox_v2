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
    daily["vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["regime_trend_20d"] = np.where(daily["market_ret_20d"] >= 0, "uptrend", "downtrend")
    daily["trend_20d"] = daily["regime_trend_20d"]
    vol_med = float(daily["vol_20d"].median(skipna=True))
    daily["regime_vol_20d"] = np.where(daily["vol_20d"] >= vol_med, "high_vol", "low_vol")
    daily["regime_breadth_20d"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    daily["breadth_regime"] = daily["regime_breadth_20d"]
    return daily


def build_dataset(tickers: list[str]) -> tuple[pd.DataFrame, dict]:
    ds, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        factor_names=["revenue_growth"],
        horizons=[10],
        experiment_id=None,
    )
    ds = ds.copy()
    ds["date"] = pd.to_datetime(ds["date"])
    ref = pd.read_parquet(REFERENCE_FILE)[["ticker", "industry"]].drop_duplicates(subset=["ticker"])
    ds = ds.merge(ref, on="ticker", how="left")
    idx = ds.set_index("date").index
    pb = pd.Series(pd.to_numeric(ds["pb"], errors="coerce").to_numpy(), index=idx)
    inds = pd.Series(ds["industry"].astype("string").to_numpy(), index=idx)
    ds[factor_column("pb_industry_lowpb_score")] = (-industry_relative_zscore_by_date(winsorize_by_date(pb), inds)).reset_index(drop=True)
    ds = ds.merge(build_market_regimes(ds), on="date", how="left")
    return ds, dataset_summary


def apply_filter(ds: pd.DataFrame, filt: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    if not filt:
        return ds.copy(), {
            "active_dates": int(ds["date"].nunique()),
            "total_dates": int(ds["date"].nunique()),
            "active_ratio": 1.0,
        }
    mask = pd.Series(True, index=ds.index)
    for k, v in filt.items():
        mask &= ds[k] == v
    filtered = ds.loc[mask].copy()
    return filtered, {
        "active_dates": int(filtered["date"].nunique()),
        "total_dates": int(ds["date"].nunique()),
        "active_ratio": float(filtered["date"].nunique() / ds["date"].nunique()) if ds["date"].nunique() else 0.0,
    }


def run_case(ds: pd.DataFrame, strategy_id: str, factor_name: str, filt: dict[str, str], top_n: int) -> dict:
    sample, coverage = apply_filter(ds, filt)
    bt = run_topn_backtest(
        dataset=sample,
        factor_col=factor_column(factor_name),
        top_n=top_n,
        rebalance_frequency="W",
        weighting="equal",
        benchmark="equal_weight_universe",
        commission_bps=10.0,
        slippage_bps=5.0,
        horizon=10,
    ).payload
    return {
        "strategy_id": strategy_id,
        "factor_name": factor_name,
        "filter": filt,
        "top_n": top_n,
        "coverage": coverage,
        "backtest": {
            "annual_return": bt["annual_return"],
            "total_return": bt["total_return"],
            "sharpe": bt["sharpe"],
            "max_drawdown": bt["max_drawdown"],
            "turnover": bt["turnover"],
            "win_rate": bt["win_rate"],
        },
    }


def main() -> None:
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary = build_dataset(tickers)

    cases = [
        run_case(dataset, "revgrowth_always_on_v1", "revenue_growth", {}, 20),
        run_case(dataset, "revgrowth_uptrend_lowvol_v1", "revenue_growth", {"regime_trend_20d": "uptrend", "regime_vol_20d": "low_vol"}, 20),
        run_case(dataset, "pbindlow_downtrend_only_v1", "pb_industry_lowpb_score", {"trend_20d": "downtrend"}, 10),
        run_case(dataset, "pbindlow_downtrend_narrow_v1", "pb_industry_lowpb_score", {"trend_20d": "downtrend", "breadth_regime": "narrow_weakness"}, 10),
    ]

    ranked = sorted(
        cases,
        key=lambda x: (
            x["backtest"]["sharpe"],
            x["backtest"]["annual_return"],
            -x["backtest"]["max_drawdown"],
        ),
        reverse=True,
    )

    report = {
        "report_type": "growth_value_corrected_head_to_head",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "ticker_count": len(tickers),
            "rebalance_frequency": "W",
            "horizon": 10,
            "weighting": "equal",
            "benchmark": "equal_weight_universe",
            "data_mode": "real_file_mode",
        },
        "dataset_summary": dataset_summary,
        "cases": cases,
        "ranked": ranked,
        "notes": [
            "Corrected setup head-to-head after removing overlapping-forward-return distortion from W+60d.",
            "Use this report to compare whether growth core or value conditional strategies deserve priority in the next research stage.",
        ],
    }

    out_path = Path("data/reports") / f"growth_value_head_to_head_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
