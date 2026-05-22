from __future__ import annotations

import argparse
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

REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")
REGISTRY_PATH = Path("data/reports/revgrowth_candidate_registry.json")
REVIEWS_PATH = Path("data/reports/revgrowth_candidate_reviews.json")


def load_tickers_from_file(path: str) -> list[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "filtered_universe" in payload:
        return [str(x) for x in payload["filtered_universe"].get("tickers", [])]
    if isinstance(payload, list):
        return [str(x) for x in payload]
    raise ValueError(f"unsupported ticker file format: {path}")


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    return ref["ticker"].tolist()[:limit]


def build_market_regimes(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy().sort_values(["ticker", "date"])
    df["daily_ret"] = df.groupby("ticker")["close"].pct_change()
    daily = df.groupby("date").agg(
        ew_ret=("daily_ret", "mean"),
        breadth=("daily_ret", lambda s: float((pd.to_numeric(s, errors='coerce') > 0).mean())),
    ).reset_index()
    daily["eq_curve"] = (1 + daily["ew_ret"].fillna(0)).cumprod()
    daily["market_ret_60d"] = daily["eq_curve"].pct_change(60)
    daily["breadth_20d"] = daily["breadth"].rolling(20).mean()
    daily["vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["regime_trend_60d"] = np.where(daily["market_ret_60d"] >= 0, "uptrend", "downtrend")
    vol_med = float(daily["vol_20d"].median(skipna=True))
    daily["regime_vol_20d"] = np.where(daily["vol_20d"] >= vol_med, "high_vol", "low_vol")
    daily["regime_breadth_20d"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    return daily[["date", "regime_trend_60d", "regime_vol_20d", "regime_breadth_20d"]]


def build_dataset(tickers: list[str], start_date: str, end_date: str, horizon: int, factor_name: str) -> pd.DataFrame:
    ds, _, _ = build_research_dataset(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        factor_names=[factor_name],
        horizons=[horizon],
        experiment_id=None,
    )
    ds = ds.copy()
    ds["date"] = pd.to_datetime(ds["date"])
    ds = ds.merge(build_market_regimes(ds), on="date", how="left")
    return ds


def apply_filter(ds: pd.DataFrame, filt: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    if not filt:
        coverage = {
            "active_dates": int(ds["date"].nunique()),
            "total_dates": int(ds["date"].nunique()),
            "active_ratio": 1.0,
        }
        return ds.copy(), coverage
    mask = pd.Series(True, index=ds.index)
    for k, v in filt.items():
        mask &= ds[k] == v
    filtered = ds.loc[mask].copy()
    coverage = {
        "active_dates": int(filtered["date"].nunique()),
        "total_dates": int(ds["date"].nunique()),
        "active_ratio": float(filtered["date"].nunique() / ds["date"].nunique()) if ds["date"].nunique() else 0.0,
    }
    return filtered, coverage


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def load_registry() -> list[dict]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_reviews() -> list[dict]:
    return json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))


def save_reviews(reviews: list[dict]) -> None:
    REVIEWS_PATH.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")


def save_registry(registry: list[dict]) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def review_result(metrics: dict) -> tuple[str, str]:
    sharpe = metrics['sharpe']
    annual = metrics['annual_return']
    spread = metrics['top_bottom_spread']
    active_ratio = metrics['active_ratio']
    if sharpe < 0 and annual < 0 and spread < 0:
        return 'watch', 'negative return, negative sharpe, and negative spread in this review window'
    if active_ratio < 0.1:
        return 'watch', 'coverage too low in this review window'
    return 'keep', 'review window still acceptable'


def main() -> None:
    parser = argparse.ArgumentParser(description='Run one growth-line candidate review window')
    parser.add_argument('--review-id', required=True)
    parser.add_argument('--window-label', required=True)
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--sample-name', default='expanded_main_board_1000')
    parser.add_argument('--sample-limit', type=int, default=1000)
    parser.add_argument('--tickers-file', default=None)
    args = parser.parse_args()

    registry = load_registry()
    reviews = load_reviews()
    tickers = load_tickers_from_file(args.tickers_file) if args.tickers_file else load_expanded_tickers(args.sample_limit)

    for item in registry:
        factor = item['factor']
        params = item['params']
        ds = build_dataset(tickers, args.start_date, args.end_date, params['horizon'], factor)
        filtered, coverage = apply_filter(ds, item['filter'])
        validation = run_factor_validation(filtered, factor_col=factor_column(factor), horizons=[params['horizon']], groups=5, split_date=resolve_split_date(filtered))
        filtered.attrs["growth_strategy_id"] = item.get("strategy_id")
        filtered.attrs["growth_turnover_annual_limit"] = params.get("annual_turnover_limit")
        if params.get("execution_assumptions"):
            execution = params.get("execution_assumptions", {})
            filtered.attrs["execution_config_enabled"] = True
            filtered.attrs["execution_bar_delay"] = execution.get("bar_delay", 1)
            filtered.attrs["execution_tick_size"] = execution.get("tick_size", 0.01)
            filtered.attrs["execution_base_tick_slippage_ticks"] = execution.get("base_tick_slippage_ticks", 1.0)
            filtered.attrs["execution_high_vol_extra_tick_slippage_ticks"] = execution.get("high_vol_extra_tick_slippage_ticks", 0.5)
            filtered.attrs["execution_high_vol_quantile"] = execution.get("high_vol_quantile", 0.8)
            filtered.attrs["execution_minimum_roundtrip_ticks"] = execution.get("minimum_roundtrip_ticks", 2.0)
            filtered.attrs["execution_commission_bps_override"] = execution.get("commission_bps", params.get("commission_bps"))
        backtest = run_topn_backtest(filtered, factor_col=factor_column(factor), top_n=params['top_n'], rebalance_frequency=params['rebalance_frequency'], weighting=params['weighting'], benchmark=params['benchmark'], commission_bps=params['commission_bps'], slippage_bps=params['slippage_bps'], horizon=params['horizon']).payload
        diag = validation['full_sample'][str(params['horizon'])]['diagnostics']['summary']
        metrics = {
            'rank_ic_mean': diag['rank_ic_mean'],
            'positive_ic_ratio': diag['positive_ic_ratio'],
            'monotonicity_score': diag['monotonicity_score'],
            'top_bottom_spread': diag['top_bottom_spread'],
            'annual_return': backtest['annual_return'],
            'sharpe': backtest['sharpe'],
            'max_drawdown': backtest['max_drawdown'],
            'turnover': backtest['turnover'],
            'active_ratio': coverage['active_ratio'],
        }
        result, comment = review_result(metrics)
        reviews.append({
            'review_id': args.review_id,
            'strategy_id': item['strategy_id'],
            'window_label': args.window_label,
            'start_date': args.start_date,
            'end_date': args.end_date,
            'sample_name': args.sample_name,
            'metrics': metrics,
            'review_result': result,
            'comment': comment,
        })
        item['last_review_at'] = pd.Timestamp.now('UTC').date().isoformat()
        if result == 'watch' and item['status'] == 'active':
            item['status'] = 'watch'

    save_reviews(reviews)
    save_registry(registry)
    print(json.dumps({'status': 'ok', 'review_id': args.review_id, 'review_count_added': len(registry)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
