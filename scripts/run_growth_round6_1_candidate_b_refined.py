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
from scripts.run_growth_round6_second_lever_h2h import (
    _prepare_sample,
    _ranked_cross_section,
    build_liquidity_tilt_holdings,
    classify_recommendation,
    compute_turnover,
    first_bucket_entry,
    load_growth_context,
    AUM_ASSUMPTIONS,
    TICKERS_FILE,
)

REPORTS_DIR = Path("data/reports")
OUTPUT_BASENAME = "growth_round6_1_candidate_b_refined"

CANDIDATES = [
    {"name": "b40_liquidity_tilt", "top_n": 40},
    {"name": "b50_liquidity_tilt", "top_n": 50},
]


def run_candidate_scenario(dataset: pd.DataFrame, factor_col: str, rebalance_frequency: str, horizon: int, top_n: int, aum: float) -> dict[str, Any]:
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
    previous_holdings: dict[str, float] = {}
    equity = float(aum)

    for dt in rebalance_dates:
        cross = sample.loc[sample["date"] == dt].copy()
        if cross.empty:
            continue
        holdings = build_liquidity_tilt_holdings(cross, factor_col, top_n)
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
        for ticker in all_tickers:
            target_weight = float(holdings.get(ticker, 0.0))
            current_weight = float(previous_holdings.get(ticker, 0.0))
            trade_notional = abs(target_weight - current_weight) * float(equity)
            amount = 0.0
            if ticker in cross.index and "amount" in cross.columns:
                maybe = cross.loc[ticker, "amount"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
                amount = float(maybe) if pd.notna(maybe) else 0.0
            estimate = estimate_dynamic_impact_bps(trade_notional, amount)
            impact_cost += float(trade_notional * estimate.impact_bps / 10000.0)
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
        previous_holdings = holdings

    ppy = periods_per_year(rebalance_frequency)
    return {
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
    }


def summarize_candidate(dataset: pd.DataFrame, name: str, factor_col: str, rebalance_frequency: str, horizon: int, top_n: int) -> dict[str, Any]:
    stress_cases = []
    for assumption in AUM_ASSUMPTIONS:
        payload = run_candidate_scenario(dataset, factor_col, rebalance_frequency, horizon, top_n, float(assumption["aum"]))
        recommendation = classify_recommendation(payload)
        stress_cases.append({
            "candidate_name": name,
            "capital_label": str(assumption["label"]),
            "aum": float(assumption["aum"]),
            "top_n": top_n,
            "dynamic_impact_v1": payload,
            "working_config_recommendation_impact": recommendation,
        })
    bucket_thresholds = first_bucket_entry(stress_cases)
    return {
        "candidate_name": name,
        "top_n": top_n,
        "stress_cases": stress_cases,
        "bucket_entry_thresholds": bucket_thresholds,
    }


def build_report() -> dict[str, Any]:
    registry_item, review, dataset = load_growth_context()
    factor_col = factor_column(str(registry_item["factor"]))
    params = registry_item["params"]
    candidates = []
    for cfg in CANDIDATES:
        result = summarize_candidate(dataset, cfg["name"], factor_col, str(params["rebalance_frequency"]), int(params["horizon"]), cfg["top_n"])
        candidates.append(result)
        print(f"[done] {cfg['name']} (top_n={cfg['top_n']})", flush=True)
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
        "weighting": "liquidity_tilted_score",
        "candidates": candidates,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Growth Round 6.1 — Candidate B Refined H2H",
        "",
        f"- Filter source: {report['filter_source']}",
        f"- Review window: {report['review_context']['window_label']} ({report['review_context']['start_date']} → {report['review_context']['end_date']})",
        f"- Weighting: {report['weighting']}",
        "",
        "| candidate | top_n | capital | annual | sharpe | impact_cost | low_liq_exposure | extreme_count | recommendation |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for candidate in report["candidates"]:
        for case in candidate["stress_cases"]:
            p = case["dynamic_impact_v1"]
            snap = p["capacity_snapshot"]
            counts = p["execution_diagnostics"]["bucket_counts"]
            rec = case["working_config_recommendation_impact"]["status"]
            lines.append(
                f"| {candidate['candidate_name']} | {candidate['top_n']} | {case['capital_label']} | {p['annual_return']:.4f} | {p['sharpe']:.4f} | {p['impact_cost_paid']:.2f} | {snap['low_liquidity_exposure_ratio'] if snap['low_liquidity_exposure_ratio'] is not None else 'NA'} | {counts.get('extreme', 0)} | {rec} |"
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
