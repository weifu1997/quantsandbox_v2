from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from app.domain.backtest.engine import run_topn_backtest
from app.domain.backtest.performance_metrics import (
    annual_return,
    max_drawdown,
    periods_per_year,
    sharpe_ratio,
    total_return,
)
from app.domain.data_contracts import factor_column
from app.services.dataset_service import build_research_dataset

START_DATE = "20240101"
END_DATE = "20251231"
RESEARCH_HORIZONS = [10]
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")
REPORTS_DIR = Path("data/reports")

GROWTH_STRATEGIES = [
    {
        "strategy_id": "revgrowth_always_on_v1",
        "factor": "revenue_growth",
        "filter": {},
        "params": {
            "horizon": 10,
            "rebalance_frequency": "W",
            "top_n": 20,
            "weighting": "equal",
            "benchmark": "equal_weight_universe",
            "commission_bps": 10.0,
            "slippage_bps": 5.0,
        },
    },
    {
        "strategy_id": "revgrowth_uptrend_lowvol_v1",
        "factor": "revenue_growth",
        "filter": {
            "regime_trend_20d": "uptrend",
            "regime_vol_20d": "low_vol",
        },
        "params": {
            "horizon": 10,
            "rebalance_frequency": "W",
            "top_n": 20,
            "weighting": "equal",
            "benchmark": "equal_weight_universe",
            "commission_bps": 10.0,
            "slippage_bps": 5.0,
        },
    },
]

VALUE_STRATEGIES = [
    {
        "strategy_id": "pbindlow_downtrend_only_v1",
        "factor": "pb_industry_lowpb_score",
        "filter": {
            "trend_20d": "downtrend",
        },
        "params": {
            "horizon": 10,
            "rebalance_frequency": "W",
            "top_n": 10,
            "weighting": "equal",
            "benchmark": "equal_weight_universe",
            "commission_bps": 10.0,
            "slippage_bps": 5.0,
        },
    },
    {
        "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
        "factor": "pb_industry_lowpb_score",
        "filter": {
            "trend_20d": "downtrend",
            "breadth_regime": "narrow_weakness",
            "quality_refined": "true",
        },
        "params": {
            "horizon": 10,
            "rebalance_frequency": "W",
            "top_n": 10,
            "weighting": "equal",
            "benchmark": "equal_weight_universe",
            "commission_bps": 10.0,
            "slippage_bps": 5.0,
        },
    },
]

ALLOCATOR_PRESETS = {
    "baseline_growth_only": {
        "label": "growth only baseline",
        "rules": [
            {
                "when": {},
                "growth": 1.0,
                "value": 0.0,
            }
        ],
    },
    "simple_regime_allocator": {
        "label": "growth core + conditional value overlay",
        "rules": [
            {
                "when": {
                    "regime_trend_20d": "uptrend",
                    "regime_vol_20d": "low_vol",
                },
                "growth": 1.0,
                "value": 0.0,
            },
            {
                "when": {
                    "trend_20d": "downtrend",
                    "breadth_regime": "narrow_weakness",
                },
                "growth": 0.6,
                "value": 0.4,
            },
            {
                "when": {
                    "trend_20d": "downtrend",
                },
                "growth": 0.8,
                "value": 0.2,
            },
            {
                "when": {},
                "growth": 0.9,
                "value": 0.0,
            },
        ],
    },
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_deployability_map(reports_dir: Path = REPORTS_DIR) -> dict[str, Any]:
    summary_path = reports_dir / "research_decision_summary_latest.json"
    if not summary_path.exists():
        return {}
    summary = load_json(summary_path)
    return summary.get("deployability", {}) or {}


def strategy_deployability_key(strategy_id: str) -> str:
    if strategy_id == "revgrowth_always_on_v1":
        return "growth"
    if strategy_id == "pbindlow_downtrend_narrow_quality_v1":
        return "value_primary"
    if strategy_id == "pbindlow_downtrend_only_v1":
        return "value_baseline_reference"
    return strategy_id


def allocator_overlay_blocked(strategy_id: str, deployability_map: dict[str, Any]) -> bool:
    item = deployability_map.get(strategy_deployability_key(strategy_id), {}) or {}
    return bool(item.get("deployment_blocked"))


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


def build_base_dataset(tickers: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    ds, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        factor_names=["revenue_growth"],
        horizons=RESEARCH_HORIZONS,
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
    roe = pd.to_numeric(ds["roe"], errors="coerce")
    pg = pd.to_numeric(ds["profit_growth"], errors="coerce")
    ds["quality_refined"] = np.where((roe > 0) & (pg > -0.2), "true", "false")
    return ds, dataset_summary


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
    daily["vol_20d"] = daily["ew_ret"].rolling(20).std(ddof=0)
    daily["regime_trend_20d"] = np.where(daily["market_ret_20d"] >= 0, "uptrend", "downtrend")
    daily["trend_20d"] = daily["regime_trend_20d"]
    vol_med = float(daily["vol_20d"].median(skipna=True))
    daily["regime_vol_20d"] = np.where(daily["vol_20d"] >= vol_med, "high_vol", "low_vol")
    daily["regime_breadth_20d"] = np.where(daily["breadth_20d"] >= 0.5, "broad_strength", "narrow_weakness")
    daily["breadth_regime"] = daily["regime_breadth_20d"]
    return daily


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


def run_strategy(ds: pd.DataFrame, strategy: dict) -> dict:
    filtered, coverage = apply_filter(ds, strategy["filter"])
    params = strategy["params"]
    backtest = run_topn_backtest(
        filtered,
        factor_col=factor_column(strategy["factor"]),
        top_n=params["top_n"],
        rebalance_frequency=params["rebalance_frequency"],
        weighting=params["weighting"],
        benchmark=params["benchmark"],
        commission_bps=params["commission_bps"],
        slippage_bps=params["slippage_bps"],
        horizon=params["horizon"],
    ).payload
    return {
        "strategy_id": strategy["strategy_id"],
        "factor": strategy["factor"],
        "filter": strategy["filter"],
        "coverage": coverage,
        "backtest": backtest,
    }


def choose_allocator_rule(row: pd.Series, rules: list[dict], value_blocked: bool) -> dict:
    for rule in rules:
        cond = rule["when"]
        if all(row.get(k) == v for k, v in cond.items()):
            selected = dict(rule)
            if value_blocked:
                selected["growth"] = 1.0
                selected["value"] = 0.0
                selected["deployability_override"] = "value_blocked"
            return selected
    selected = dict(rules[-1])
    if value_blocked:
        selected["growth"] = 1.0
        selected["value"] = 0.0
        selected["deployability_override"] = "value_blocked"
    return selected


def merge_strategy_returns(growth_result: dict, value_result: dict, regime_daily: pd.DataFrame, preset_name: str, deployability_map: dict[str, Any]) -> dict:
    preset = ALLOCATOR_PRESETS[preset_name]
    growth_returns = growth_result["backtest"].get("returns_by_rebalance_date", {})
    value_returns = value_result["backtest"].get("returns_by_rebalance_date", {})
    growth_frequency = growth_result["backtest"]["rebalance_frequency"]
    regime_weekly = regime_daily[["date", "regime_trend_20d", "regime_vol_20d", "trend_20d", "breadth_regime"]].copy()
    regime_weekly["rebalance_date"] = regime_weekly["date"].dt.strftime("%Y-%m-%d")
    regime_weekly = regime_weekly.drop_duplicates(subset=["rebalance_date"], keep="last").set_index("rebalance_date")

    value_blocked = allocator_overlay_blocked(value_result["strategy_id"], deployability_map)
    growth_blocked = allocator_overlay_blocked(growth_result["strategy_id"], deployability_map)
    if growth_blocked:
        raise ValueError(f"growth core {growth_result['strategy_id']} is deployment_blocked; allocator should not run with this core")

    all_dates = sorted(set(growth_returns.keys()) | set(value_returns.keys()))
    combined_returns: list[float] = []
    allocation_trace: list[dict] = []
    for dt in all_dates:
        row = regime_weekly.loc[dt] if dt in regime_weekly.index else pd.Series(dtype=object)
        rule = choose_allocator_rule(row, preset["rules"], value_blocked=value_blocked)
        growth_weight = float(rule["growth"])
        value_weight = float(rule["value"])
        growth_ret = float(growth_returns.get(dt, 0.0))
        value_ret = float(value_returns.get(dt, 0.0))
        combined = growth_weight * growth_ret + value_weight * value_ret
        combined_returns.append(combined)
        allocation_trace.append({
            "date": dt,
            "growth_weight": growth_weight,
            "value_weight": value_weight,
            "growth_return": growth_ret,
            "value_return": value_ret,
            "combined_return": combined,
            "matched_rule": rule["when"],
            "deployability_override": rule.get("deployability_override"),
        })

    equity = 1.0
    equity_curve: list[float] = []
    for ret in combined_returns:
        equity *= (1.0 + float(ret))
        equity_curve.append(float(equity))

    ppy = periods_per_year(growth_frequency)
    return {
        "preset_name": preset_name,
        "preset_label": preset["label"],
        "period_count": len(combined_returns),
        "annual_return": annual_return(combined_returns, ppy),
        "total_return": total_return(equity_curve),
        "sharpe": sharpe_ratio(combined_returns, ppy),
        "max_drawdown": max_drawdown(equity_curve),
        "equity_curve": [float(x) for x in equity_curve],
        "returns_by_rebalance_date": {item["date"]: float(item["combined_return"]) for item in allocation_trace},
        "allocation_trace": allocation_trace,
        "deployability_consumed": {
            "growth": deployability_map.get(strategy_deployability_key(growth_result["strategy_id"]), {}),
            "value": deployability_map.get(strategy_deployability_key(value_result["strategy_id"]), {}),
        },
    }


def main() -> None:
    deployability_map = load_deployability_map(REPORTS_DIR)
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary = build_base_dataset(tickers, START_DATE, END_DATE)
    regimes = build_market_regimes(dataset)
    merged = dataset.merge(regimes, on="date", how="left")

    growth_results = [run_strategy(merged, strategy) for strategy in GROWTH_STRATEGIES]
    value_results = [run_strategy(merged, strategy) for strategy in VALUE_STRATEGIES]

    growth_core = next(x for x in growth_results if x["strategy_id"] == "revgrowth_always_on_v1")
    value_overlay = next(x for x in value_results if x["strategy_id"] == "pbindlow_downtrend_narrow_quality_v1")

    growth_blocked = allocator_overlay_blocked(growth_core["strategy_id"], deployability_map)
    growth_deployability = deployability_map.get(strategy_deployability_key(growth_core["strategy_id"]), {}) or {}
    value_deployability = deployability_map.get(strategy_deployability_key(value_overlay["strategy_id"]), {}) or {}
    max_daily_drawdown_stop = 0.03
    if growth_blocked:
        allocator_reports = []
        allocator_status = {
            "status": "blocked",
            "reason": f"growth core {growth_core['strategy_id']} is deployment_blocked by deployability schema",
        }
    else:
        allocator_reports = [
            merge_strategy_returns(growth_core, value_overlay, regimes, preset_name, deployability_map)
            for preset_name in ALLOCATOR_PRESETS.keys()
        ]
        allocator_status = {
            "status": "limited" if value_deployability.get("deployment_blocked") else "active",
            "reason": "single deployable growth core allowed with 100% weight while blocked overlays remain soft-disabled" if value_deployability.get("deployment_blocked") else "allocator consumed deployability schema and ran on eligible core/overlay set",
        }

    value_blocked = allocator_overlay_blocked(value_overlay["strategy_id"], deployability_map)
    report = {
        "report_type": "strategy_line_allocator_validation_real_filemode",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "ticker_count": len(tickers),
            "research_horizons": RESEARCH_HORIZONS,
            "data_mode": "real_file_mode",
        },
        "deployability_consumed": deployability_map,
        "allocator_status": allocator_status,
        "dataset_summary": dataset_summary,
        "growth_line_candidates": [
            {
                "strategy_id": x["strategy_id"],
                "coverage": x["coverage"],
                "backtest_summary": {
                    "annual_return": x["backtest"]["annual_return"],
                    "total_return": x["backtest"]["total_return"],
                    "sharpe": x["backtest"]["sharpe"],
                    "max_drawdown": x["backtest"]["max_drawdown"],
                },
            }
            for x in growth_results
        ],
        "value_line_candidates": [
            {
                "strategy_id": x["strategy_id"],
                "coverage": x["coverage"],
                "backtest_summary": {
                    "annual_return": x["backtest"]["annual_return"],
                    "total_return": x["backtest"]["total_return"],
                    "sharpe": x["backtest"]["sharpe"],
                    "max_drawdown": x["backtest"]["max_drawdown"],
                },
            }
            for x in value_results
        ],
        "allocator_reports": allocator_reports,
        "recommendation": [
            "Use revgrowth_always_on_v1 as the growth core baseline only when its deployability schema is not blocked.",
            "Treat pbindlow_downtrend_narrow_quality_v1 as a conditional overlay only if deployment_blocked=false and recommended_max_aum is not exceeded.",
            "Promote allocator testing only if simple_regime_allocator beats baseline_growth_only on sharpe without a meaningfully worse max drawdown and without violating deployability constraints.",
        ],
        "portfolio_constraints": {
            "growth_blocked": allocator_overlay_blocked(growth_core["strategy_id"], deployability_map),
            "value_blocked": value_blocked,
            "recommended_max_aum": growth_deployability.get("recommended_max_aum") or deployability_map.get(strategy_deployability_key(value_overlay["strategy_id"]), {}).get("recommended_max_aum"),
            "max_daily_drawdown_stop": max_daily_drawdown_stop,
        },
        "trial_weights": {
            "growth": 1.0,
            "value": 0.0 if value_blocked else None,
        },
    }

    out_path = REPORTS_DIR / f"strategy_line_allocator_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path = REPORTS_DIR / "strategy_line_allocator_latest.json"
    latest_path.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
