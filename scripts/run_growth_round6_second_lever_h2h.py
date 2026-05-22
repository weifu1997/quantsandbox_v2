from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.domain.backtest.dynamic_impact_model import estimate_dynamic_impact_bps
from app.domain.backtest.performance_metrics import annual_return, max_drawdown, periods_per_year, sharpe_ratio, total_return, win_rate
from app.domain.backtest.rebalance_calendar import select_rebalance_dates
from app.domain.data_contracts import factor_column
from scripts.build_research_realism_stress import build_candidate_dataset, find_registry_item, load_registry_and_reviews, latest_review

REPORTS_DIR = Path("data/reports")
TICKERS_FILE = REPORTS_DIR / "filtered_universe_growth_amount_bottom_50pct_latest.json"
OUTPUT_BASENAME = "growth_round6_second_lever"
AUM_ASSUMPTIONS = [
    {"label": "model_small", "aum": 1_000_000.0},
    {"label": "model_medium", "aum": 5_000_000.0},
    {"label": "model_large", "aum": 10_000_000.0},
]
BASELINE_NAME = "baseline_tail50_equal_top30"
CANDIDATE_A_NAME = "candidate_a_liquidity_cap_alpha_0p05"
CANDIDATE_B_NAME = "candidate_b_liquidity_tilt_top40"
PARTICIPATION_ALPHA = 0.05


def load_growth_context() -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    registry, reviews, _, _ = load_registry_and_reviews("growth_line")
    item = find_registry_item(registry, "revgrowth_always_on_v1")
    review = latest_review(reviews, "revgrowth_always_on_v1")
    tickers_payload = json.loads(TICKERS_FILE.read_text(encoding="utf-8"))
    tickers = [str(x) for x in tickers_payload["filtered_universe"]["tickers"]]
    dataset = build_candidate_dataset("growth_line", item, review, tickers=tickers)
    return item, review, dataset


def _prepare_sample(dataset: pd.DataFrame, factor_col: str, horizon: int) -> pd.DataFrame:
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    return_col = f"future_return_{horizon}d"
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample["amount"] = pd.to_numeric(sample["amount"], errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col, "amount"])
    return sample


def _ranked_cross_section(cross_section: pd.DataFrame, factor_col: str) -> pd.DataFrame:
    ranked = cross_section.copy()
    ranked[factor_col] = pd.to_numeric(ranked[factor_col], errors="coerce")
    ranked["amount"] = pd.to_numeric(ranked["amount"], errors="coerce")
    ranked = ranked.dropna(subset=[factor_col, "amount"]).sort_values(factor_col, ascending=False).reset_index(drop=True)
    return ranked


def build_equal_holdings(cross_section: pd.DataFrame, factor_col: str, top_n: int) -> dict[str, float]:
    ranked = _ranked_cross_section(cross_section, factor_col).head(top_n)
    if ranked.empty:
        return {}
    w = 1.0 / len(ranked)
    return {str(row["ticker"]): w for _, row in ranked.iterrows()}


def build_liquidity_cap_holdings(cross_section: pd.DataFrame, factor_col: str, top_n: int, aum: float, alpha: float) -> tuple[dict[str, float], dict[str, Any]]:
    ranked = _ranked_cross_section(cross_section, factor_col).head(top_n)
    if ranked.empty:
        return {}, {"cap_binding_count": 0, "unallocated_weight": 0.0, "alpha": alpha}
    base_weight = 1.0 / len(ranked)
    capacities: list[tuple[str, float]] = []
    for _, row in ranked.iterrows():
        ticker = str(row["ticker"])
        amount = float(row["amount"])
        cap_weight = float(alpha * amount / float(aum)) if aum > 0 else 0.0
        capacities.append((ticker, max(cap_weight, 0.0)))
    holdings = {ticker: 0.0 for ticker, _ in capacities}
    remaining = 1.0
    active = {ticker for ticker, _ in capacities}
    caps_map = dict(capacities)
    while remaining > 1e-12 and active:
        fair_share = remaining / len(active)
        progress = 0.0
        exhausted: set[str] = set()
        for ticker in list(active):
            headroom = max(caps_map[ticker] - holdings[ticker], 0.0)
            alloc = min(fair_share, headroom)
            if alloc > 0:
                holdings[ticker] += alloc
                progress += alloc
            if headroom <= fair_share + 1e-12:
                exhausted.add(ticker)
        remaining = max(remaining - progress, 0.0)
        active -= exhausted
        if progress <= 1e-12:
            break
    kept = {ticker: weight for ticker, weight in holdings.items() if weight > 1e-12}
    cap_binding_count = int(sum(1 for _, cap in capacities if cap < base_weight - 1e-12))
    return kept, {
        "cap_binding_count": cap_binding_count,
        "unallocated_weight": float(remaining),
        "alpha": alpha,
        "base_equal_weight": base_weight,
    }


def build_liquidity_tilt_holdings(cross_section: pd.DataFrame, factor_col: str, top_n: int) -> dict[str, float]:
    ranked = _ranked_cross_section(cross_section, factor_col).head(top_n)
    if ranked.empty:
        return {}
    ranked["score_component"] = pd.to_numeric(ranked[factor_col], errors="coerce").clip(lower=0.0)
    ranked["liq_component"] = ranked["amount"].apply(lambda x: math.log1p(max(float(x), 0.0)))
    ranked["combined"] = ranked["score_component"] * ranked["liq_component"]
    total = float(ranked["combined"].sum())
    if total <= 1e-12:
        return build_equal_holdings(cross_section, factor_col, top_n)
    return {str(row["ticker"]): float(row["combined"] / total) for _, row in ranked.iterrows() if float(row["combined"]) > 0}


def compute_turnover(prev_holdings: dict[str, float], holdings: dict[str, float]) -> float:
    tickers = set(prev_holdings) | set(holdings)
    return float(sum(abs(float(holdings.get(t, 0.0)) - float(prev_holdings.get(t, 0.0))) for t in tickers))


def classify_recommendation(dynamic_payload: dict[str, Any]) -> dict[str, str]:
    diag = dynamic_payload["execution_diagnostics"]
    extreme = int(diag["bucket_counts"].get("extreme", 0))
    heavy = int(diag["bucket_counts"].get("heavy", 0))
    annual_return = float(dynamic_payload["annual_return"])
    avg_bps = float(diag.get("avg_dynamic_impact_bps", 0.0))
    if annual_return < 0 or extreme > 0:
        return {
            "status": "stop_using",
            "reason": "capital-scaled dynamic impact pushes the strategy into extreme execution buckets or negative executable return",
        }
    if avg_bps > 25 or heavy > 0:
        return {
            "status": "needs_revision",
            "reason": "capital-scaled dynamic impact materially degrades executability and now requires a revised working config",
        }
    if avg_bps > 10:
        return {
            "status": "keep_with_caution",
            "reason": "the strategy still works, but capital-scaled impact friction is high enough that the working config should only be kept cautiously",
        }
    return {
        "status": "keep",
        "reason": "even after capital scaling, impact diagnostics remain inside the current tolerance band",
    }


def first_bucket_entry(stress_cases: list[dict[str, Any]]) -> dict[str, str | None]:
    out: dict[str, str | None] = {"light": None, "medium": None, "heavy": None, "extreme": None}
    for case in stress_cases:
        counts = case["dynamic_impact_v1"]["execution_diagnostics"]["bucket_counts"]
        for label in ["light", "medium", "heavy", "extreme"]:
            if out[label] is None and int(counts.get(label, 0)) > 0:
                out[label] = str(case["capital_label"])
    return out


def run_strategy_scenario(dataset: pd.DataFrame, strategy_name: str, factor_col: str, rebalance_frequency: str, horizon: int, aum: float) -> dict[str, Any]:
    sample = _prepare_sample(dataset, factor_col, horizon)
    return_col = f"future_return_{horizon}d"
    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), rebalance_frequency)
    returns: list[float] = []
    equity_curve: list[float] = []
    cost_paid = 0.0
    impact_cost_paid = 0.0
    turnover_values: list[float] = []
    participation_rates: list[float] = []
    impact_bps_values: list[float] = []
    bucket_counts = {"very_light": 0, "light": 0, "medium": 0, "heavy": 0, "extreme": 0}
    liquidity_ratios: list[float] = []
    diagnostics: list[dict[str, Any]] = []
    previous_holdings: dict[str, float] = {}
    equity = float(aum)

    for dt in rebalance_dates:
        cross = sample.loc[sample["date"] == dt].copy()
        if cross.empty:
            continue
        meta: dict[str, Any] = {}
        if strategy_name == BASELINE_NAME:
            holdings = build_equal_holdings(cross, factor_col, top_n=30)
        elif strategy_name == CANDIDATE_A_NAME:
            holdings, meta = build_liquidity_cap_holdings(cross, factor_col, top_n=30, aum=aum, alpha=PARTICIPATION_ALPHA)
        elif strategy_name == CANDIDATE_B_NAME:
            holdings = build_liquidity_tilt_holdings(cross, factor_col, top_n=40)
        else:
            raise ValueError(f"Unknown strategy_name={strategy_name}")
        if not holdings:
            continue
        cross = cross.set_index("ticker")
        gross = 0.0
        for ticker, weight in holdings.items():
            if ticker in cross.index:
                gross += float(weight) * float(cross.loc[ticker, return_col])
        turnover = compute_turnover(previous_holdings, holdings)
        turnover_values.append(turnover)
        base_cost = turnover * 0.0015 * equity
        impact_cost = 0.0
        all_tickers = set(previous_holdings) | set(holdings)
        per_name_rates: list[float] = []
        per_name_bps: list[float] = []
        for ticker in all_tickers:
            target_weight = float(holdings.get(ticker, 0.0))
            current_weight = float(previous_holdings.get(ticker, 0.0))
            trade_notional = abs(target_weight - current_weight) * float(equity)
            amount = 0.0
            if ticker in cross.index:
                maybe = cross.loc[ticker, "amount"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
                amount = float(maybe) if pd.notna(maybe) else 0.0
            estimate = estimate_dynamic_impact_bps(trade_notional, amount)
            impact_cost += float(trade_notional * estimate.impact_bps / 10000.0)
            per_name_rates.append(float(estimate.participation_rate))
            per_name_bps.append(float(estimate.impact_bps))
            participation_rates.append(float(estimate.participation_rate))
            impact_bps_values.append(float(estimate.impact_bps))
            bucket_counts[estimate.bucket_label] = bucket_counts.get(estimate.bucket_label, 0) + 1
            if target_weight > 1e-12 and amount > 0:
                liquidity_ratios.append(float((target_weight * equity) / amount))
        total_cost = base_cost + impact_cost
        net = gross - (total_cost / equity if equity > 0 else 0.0)
        returns.append(float(net))
        cost_paid += total_cost
        impact_cost_paid += impact_cost
        equity *= 1.0 + float(net)
        equity_curve.append(float(equity))
        diagnostics.append({
            "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
            "holdings_count": len(holdings),
            **meta,
        })
        previous_holdings = holdings

    ppy = periods_per_year(rebalance_frequency)
    payload = {
        "annual_return": annual_return(returns, ppy),
        "total_return": total_return(equity_curve),
        "sharpe": sharpe_ratio(returns, ppy),
        "max_drawdown": max_drawdown(equity_curve),
        "turnover": float(sum(turnover_values) / len(turnover_values)) if turnover_values else 0.0,
        "win_rate": win_rate(returns),
        "base_cost_paid": float(cost_paid - impact_cost_paid),
        "impact_cost_paid": float(impact_cost_paid),
        "total_cost_paid_with_impact": float(cost_paid),
        "execution_diagnostics": {
            "avg_participation_rate": float(pd.Series(participation_rates).mean()) if participation_rates else 0.0,
            "p90_participation_rate": float(pd.Series(participation_rates).quantile(0.90)) if participation_rates else 0.0,
            "max_participation_rate": float(max(participation_rates)) if participation_rates else 0.0,
            "avg_dynamic_impact_bps": float(pd.Series(impact_bps_values).mean()) if impact_bps_values else 0.0,
            "bucket_counts": bucket_counts,
        },
        "capacity_snapshot": {
            "median_position_to_amount_ratio": float(pd.Series(liquidity_ratios).median()) if liquidity_ratios else None,
            "p90_position_to_amount_ratio": float(pd.Series(liquidity_ratios).quantile(0.90)) if liquidity_ratios else None,
            "max_position_to_amount_ratio": float(max(liquidity_ratios)) if liquidity_ratios else None,
            "low_liquidity_exposure_ratio": float(sum(1 for x in liquidity_ratios if x > 0.10) / len(liquidity_ratios)) if liquidity_ratios else None,
        },
        "strategy_diagnostics": diagnostics,
    }
    return payload


def build_case(strategy_name: str, capital_label: str, aum: float, payload: dict[str, Any]) -> dict[str, Any]:
    recommendation = classify_recommendation(payload)
    return {
        "strategy_name": strategy_name,
        "capital_label": capital_label,
        "aum": float(aum),
        "dynamic_impact_v1": payload,
        "working_config_recommendation_impact": recommendation,
    }


def summarize_strategy(dataset: pd.DataFrame, strategy_name: str, factor_col: str, rebalance_frequency: str, horizon: int) -> dict[str, Any]:
    stress_cases = []
    for assumption in AUM_ASSUMPTIONS:
        payload = run_strategy_scenario(dataset, strategy_name, factor_col, rebalance_frequency, horizon, float(assumption["aum"]))
        stress_cases.append(build_case(strategy_name, str(assumption["label"]), float(assumption["aum"]), payload))
    bucket_thresholds = first_bucket_entry(stress_cases)
    return {
        "strategy_name": strategy_name,
        "stress_cases": stress_cases,
        "bucket_entry_thresholds": bucket_thresholds,
    }


def build_report() -> dict[str, Any]:
    registry_item, review, dataset = load_growth_context()
    factor_col = factor_column(str(registry_item["factor"]))
    params = registry_item["params"]
    strategies = [
        summarize_strategy(dataset, BASELINE_NAME, factor_col, str(params["rebalance_frequency"]), int(params["horizon"])),
        summarize_strategy(dataset, CANDIDATE_A_NAME, factor_col, str(params["rebalance_frequency"]), int(params["horizon"])),
        summarize_strategy(dataset, CANDIDATE_B_NAME, factor_col, str(params["rebalance_frequency"]), int(params["horizon"])),
    ]
    return {
        "report_type": OUTPUT_BASENAME,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "filter_source": str(TICKERS_FILE),
        "review_context": {
            "review_id": review.get("review_id"),
            "window_label": review.get("window_label"),
            "start_date": review.get("start_date"),
            "end_date": review.get("end_date"),
        },
        "growth_registry_params": dict(params),
        "candidate_strategies": strategies,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Growth Round 6 Second Lever H2H",
        "",
        f"- Filter source: {report['filter_source']}",
        f"- Review window: {report['review_context']['window_label']} ({report['review_context']['start_date']} → {report['review_context']['end_date']})",
        "",
        "| strategy | capital | annual | sharpe | impact_cost_paid | low_liq_exposure | first_extreme? |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for strategy in report["candidate_strategies"]:
        for case in strategy["stress_cases"]:
            payload = case["dynamic_impact_v1"]
            snapshot = payload["capacity_snapshot"]
            counts = payload["execution_diagnostics"]["bucket_counts"]
            lines.append(
                f"| {strategy['strategy_name']} | {case['capital_label']} | {payload['annual_return']:.4f} | {payload['sharpe']:.4f} | {payload['impact_cost_paid']:.2f} | {snapshot['low_liquidity_exposure_ratio'] if snapshot['low_liquidity_exposure_ratio'] is not None else 'NA'} | {counts.get('extreme', 0)} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> tuple[Path, Path]:
    report = build_report()
    ts = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"{OUTPUT_BASENAME}_{ts}.json"
    md_path = REPORTS_DIR / f"{OUTPUT_BASENAME}_{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    (REPORTS_DIR / f"{OUTPUT_BASENAME}_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / f"{OUTPUT_BASENAME}_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))
    return json_path, md_path


if __name__ == "__main__":
    main()
