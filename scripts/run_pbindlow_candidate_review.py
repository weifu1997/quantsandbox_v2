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
REGISTRY_PATH = Path("data/reports/pbindlow_candidate_registry.json")
REVIEWS_PATH = Path("data/reports/pbindlow_candidate_reviews.json")


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


def build_market_regimes(ds: pd.DataFrame) -> pd.DataFrame:
    df = ds.copy().sort_values(["ticker", "date"])
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


def build_dataset(tickers: list[str], start_date: str, end_date: str, horizon: int, factor_name: str) -> pd.DataFrame:
    ds, _, _ = build_research_dataset(tickers=tickers, start_date=start_date, end_date=end_date, factor_names=[], horizons=[horizon], experiment_id=None)
    ds = ds.copy(); ds["date"] = pd.to_datetime(ds["date"])
    ref = pd.read_parquet(REFERENCE_FILE)[["ticker", "industry"]].drop_duplicates(subset=["ticker"])
    ds = ds.merge(ref, on="ticker", how="left")
    idx = ds.set_index("date").index
    pb = pd.Series(pd.to_numeric(ds["pb"], errors="coerce").to_numpy(), index=idx)
    inds = pd.Series(ds["industry"].astype("string").to_numpy(), index=idx)
    ds[factor_column(factor_name)] = (-industry_relative_zscore_by_date(winsorize_by_date(pb), inds)).reset_index(drop=True)
    ds = ds.merge(build_market_regimes(ds), on="date", how="left")
    roe = pd.to_numeric(ds["roe"], errors="coerce")
    pg = pd.to_numeric(ds["profit_growth"], errors="coerce")
    ds["quality_refined"] = np.where((roe > 0) & (pg > -0.2), "true", "false")
    return ds


def apply_filter(ds: pd.DataFrame, filt: dict[str, str]) -> tuple[pd.DataFrame, dict]:
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
    ds = sorted(dataset["date"].drop_duplicates().tolist())
    return str(pd.Timestamp(ds[len(ds)//2]).date()) if ds else None


def load_registry() -> list[dict]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_reviews() -> list[dict]:
    return json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))


def save_reviews(reviews: list[dict]) -> None:
    REVIEWS_PATH.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")


def save_registry(registry: list[dict]) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def review_result(metrics: dict) -> tuple[str, str]:
    sharpe = metrics["sharpe"]
    annual = metrics["annual_return"]
    spread = metrics["top_bottom_spread"]
    active_ratio = metrics["active_ratio"]
    if sharpe < 0 and annual < 0 and spread < 0:
        return "watch", "negative return, negative sharpe, and negative spread in this review window"
    if active_ratio < 0.1:
        return "watch", "coverage too low in this review window"
    return "keep", "review window still acceptable"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one candidate-pool review window")
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--window-label", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--sample-name", default="expanded_main_board_1000")
    parser.add_argument("--sample-limit", type=int, default=1000)
    parser.add_argument("--tickers-file", default=None)
    args = parser.parse_args()

    registry = load_registry()
    reviews = load_reviews()
    tickers = load_tickers_from_file(args.tickers_file) if args.tickers_file else load_expanded_tickers(args.sample_limit)

    for item in registry:
        factor = item["factor"]
        params = item["params"]
        ds = build_dataset(tickers, args.start_date, args.end_date, params["horizon"], factor)
        filtered, coverage = apply_filter(ds, item["filter"])
        validation = run_factor_validation(filtered, factor_col=factor_column(factor), horizons=[params["horizon"]], groups=5, split_date=resolve_split_date(filtered))
        backtest = run_topn_backtest(filtered, factor_col=factor_column(factor), top_n=params["top_n"], rebalance_frequency=params["rebalance_frequency"], weighting=params["weighting"], benchmark=params["benchmark"], commission_bps=params["commission_bps"], slippage_bps=params["slippage_bps"], horizon=params["horizon"]).payload
        diag = validation["full_sample"][str(params["horizon"])]["diagnostics"]["summary"]
        metrics = {
            "rank_ic_mean": diag["rank_ic_mean"],
            "positive_ic_ratio": diag["positive_ic_ratio"],
            "monotonicity_score": diag["monotonicity_score"],
            "top_bottom_spread": diag["top_bottom_spread"],
            "annual_return": backtest["annual_return"],
            "sharpe": backtest["sharpe"],
            "max_drawdown": backtest["max_drawdown"],
            "turnover": backtest["turnover"],
            "active_ratio": coverage["active_ratio"],
        }
        result, comment = review_result(metrics)
        reviews.append({
            "review_id": args.review_id,
            "strategy_id": item["strategy_id"],
            "window_label": args.window_label,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "sample_name": args.sample_name,
            "metrics": metrics,
            "review_result": result,
            "comment": comment,
        })
        item["last_review_at"] = pd.Timestamp.now("UTC").date().isoformat()
        if result == "watch" and item["status"] == "active":
            item["status"] = "watch"
        elif result == "keep":
            item["status"] = "active"

    save_reviews(reviews)
    save_registry(registry)
    print(json.dumps({"status": "ok", "review_id": args.review_id, "review_count_added": len(registry)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
