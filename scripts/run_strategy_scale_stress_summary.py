from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.domain.backtest.cost_model import estimate_transaction_cost
from app.domain.backtest.dynamic_impact_model import estimate_dynamic_impact_bps
from app.domain.data_contracts import factor_column
from app.domain.backtest.portfolio_construction import build_topn_equal_weight_portfolio, build_topn_score_weight_portfolio
from app.domain.backtest.rebalance_calendar import select_rebalance_dates
from app.domain.backtest.performance_metrics import annual_return, max_drawdown, periods_per_year, sharpe_ratio, total_return, win_rate
from scripts.build_research_decision_summary import TRACKED_CANDIDATES
from scripts.build_research_realism_stress import build_candidate_dataset, find_registry_item, load_registry_and_reviews
from scripts.run_pbindlow_candidate_review import load_tickers_from_file

REPORTS_DIR = Path("data/reports")
AUM_ASSUMPTIONS = [
    {"label": "model_micro", "aum": 100_000.0},
    {"label": "model_small", "aum": 1_000_000.0},
    {"label": "model_medium", "aum": 5_000_000.0},
    {"label": "model_large", "aum": 10_000_000.0},
]
TRACKED_IDS = [
    TRACKED_CANDIDATES["growth_primary"],
    TRACKED_CANDIDATES["value_primary"],
    TRACKED_CANDIDATES["value_baseline_reference"],
]


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if abs(float(denominator)) < 1e-12:
        return None
    return float(numerator / denominator)


def candidate_line(strategy_id: str) -> str:
    if strategy_id == TRACKED_CANDIDATES["growth_primary"]:
        return "growth_line"
    return "valuation_line"


def latest_review(reviews: list[dict], strategy_id: str) -> dict:
    candidates = [r for r in reviews if r.get("strategy_id") == strategy_id]
    if not candidates:
        raise ValueError(f"No review rows found for {strategy_id}")
    return sorted(candidates, key=lambda x: (str(x.get("end_date", "")), str(x.get("review_id", ""))))[-1]


def build_holdings_tape(dataset: pd.DataFrame, params: dict[str, Any], factor_name: str) -> list[dict[str, Any]]:
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    factor_col = factor_column(factor_name)
    return_col = f"future_return_{int(params['horizon'])}d"
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col])
    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), str(params["rebalance_frequency"]))

    tape: list[dict[str, Any]] = []
    previous_holdings: dict[str, float] = {}
    for dt in rebalance_dates:
        cross = sample.loc[sample["date"] == dt].copy()
        if cross.empty:
            continue
        if str(params["weighting"]).lower() == "score":
            holdings = build_topn_score_weight_portfolio(cross, factor_col, int(params["top_n"]))
        else:
            holdings = build_topn_equal_weight_portfolio(cross, factor_col, int(params["top_n"]))
        if not holdings:
            continue
        cross = cross.set_index("ticker")
        gross = 0.0
        for ticker, weight in holdings.items():
            if ticker in cross.index:
                gross += float(weight) * float(cross.loc[ticker, return_col])
        tape.append(
            {
                "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                "holdings": {str(k): float(v) for k, v in holdings.items()},
                "previous_holdings": dict(previous_holdings),
                "gross_return": float(gross),
                "cross_section": cross[["amount"]].copy() if "amount" in cross.columns else pd.DataFrame(index=cross.index),
            }
        )
        previous_holdings = holdings
    return tape


def compute_turnover(prev_holdings: dict[str, float], holdings: dict[str, float]) -> float:
    tickers = set(prev_holdings) | set(holdings)
    return float(sum(abs(float(holdings.get(t, 0.0)) - float(prev_holdings.get(t, 0.0))) for t in tickers))


def run_scaled_scenario(tape: list[dict[str, Any]], params: dict[str, Any], aum: float, dynamic_impact: bool) -> dict[str, Any]:
    returns: list[float] = []
    equity_curve: list[float] = []
    cost_paid = 0.0
    impact_cost_paid = 0.0
    turnover_values: list[float] = []
    participation_rates: list[float] = []
    impact_bps_values: list[float] = []
    bucket_counts = {"very_light": 0, "light": 0, "medium": 0, "heavy": 0, "extreme": 0}
    equity = float(aum)

    for row in tape:
        holdings = row["holdings"]
        previous_holdings = row["previous_holdings"]
        gross = float(row["gross_return"])
        turnover = compute_turnover(previous_holdings, holdings)
        turnover_values.append(turnover)
        base_cost = float(estimate_transaction_cost(turnover, float(params.get("commission_bps", 10.0)), float(params.get("slippage_bps", 5.0))) * equity)
        impact_cost = 0.0
        cross = row["cross_section"]
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
            participation_rates.append(float(estimate.participation_rate))
            impact_bps_values.append(float(estimate.impact_bps))
            bucket_counts[estimate.bucket_label] = bucket_counts.get(estimate.bucket_label, 0) + 1
            if dynamic_impact:
                impact_cost += float(trade_notional * estimate.impact_bps / 10000.0)
        total_cost = base_cost + impact_cost
        net = gross - (total_cost / float(equity) if equity > 0 else 0.0)
        returns.append(float(net))
        cost_paid += total_cost
        impact_cost_paid += impact_cost
        equity *= 1.0 + float(net)
        equity_curve.append(float(equity))

    ppy = periods_per_year(str(params["rebalance_frequency"]))
    return {
        "aum": float(aum),
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
    }


def classify_working_config_recommendation(dynamic_payload: dict[str, Any]) -> dict[str, str]:
    diag = dynamic_payload["execution_diagnostics"]
    extreme = int(diag["bucket_counts"].get("extreme", 0))
    heavy = int(diag["bucket_counts"].get("heavy", 0))
    annual_return = float(dynamic_payload["annual_return"])
    avg_bps = float(diag.get("avg_dynamic_impact_bps", 0.0))
    total_trades = sum(int(v) for v in diag["bucket_counts"].values())
    extreme_ratio = float(extreme / total_trades) if total_trades > 0 else 0.0
    if annual_return < 0:
        return {
            "status": "stop_using",
            "reason": "executable return is negative after capital-scaled dynamic impact",
        }
    if extreme_ratio > 0.10:
        return {
            "status": "stop_using",
            "reason": f"extreme bucket ratio ({extreme_ratio:.3f}) exceeds hard stop threshold",
        }
    if extreme_ratio > 0.05:
        return {
            "status": "needs_revision",
            "reason": f"extreme bucket ratio ({extreme_ratio:.3f}) is elevated and requires working config revision",
        }
    if extreme > 0 or avg_bps > 25 or heavy > 0:
        return {
            "status": "keep_with_caution",
            "reason": f"some extreme ({extreme}) or heavy ({heavy}) buckets present; strategy works but capital-scaled friction warrants caution",
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


def build_deployability_schema(stress_cases: list[dict[str, Any]], bucket_thresholds: dict[str, str | None]) -> dict[str, Any]:
    deployable_aum_floor = None
    recommended_max_aum = None
    deployment_blocked = True
    blocking_reasons: list[str] = []
    for case in stress_cases:
        status = str((case.get("working_config_recommendation_impact") or {}).get("status", "needs_revision"))
        if status in {"keep", "keep_with_caution"} and deployable_aum_floor is None:
            deployable_aum_floor = str(case.get("capital_label"))
            deployment_blocked = False
        if status in {"keep", "keep_with_caution"}:
            recommended_max_aum = str(case.get("capital_label"))
        else:
            blocking_reasons.append(f"{case.get('capital_label')}:{status}")
    if recommended_max_aum is None and not deployment_blocked and stress_cases:
        recommended_max_aum = str(stress_cases[0].get("capital_label"))
    return {
        "deployable_aum_floor": deployable_aum_floor,
        "first_light_aum": bucket_thresholds.get("light"),
        "first_medium_aum": bucket_thresholds.get("medium"),
        "first_heavy_aum": bucket_thresholds.get("heavy"),
        "first_extreme_aum": bucket_thresholds.get("extreme"),
        "recommended_max_aum": recommended_max_aum,
        "deployment_blocked": deployment_blocked,
        "blocking_reasons": blocking_reasons,
    }


def build_case(strategy_id: str, capital_label: str, aum: float, tape: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    base = run_scaled_scenario(tape, params, aum, dynamic_impact=False)
    dynamic = run_scaled_scenario(tape, params, aum, dynamic_impact=True)
    annual_delta = float(dynamic["annual_return"] - base["annual_return"])
    sharpe_delta = float(dynamic["sharpe"] - base["sharpe"])
    annual_erosion_rate = safe_ratio(base["annual_return"] - dynamic["annual_return"], base["annual_return"])
    sharpe_erosion_rate = safe_ratio(base["sharpe"] - dynamic["sharpe"], base["sharpe"])
    recommendation = classify_working_config_recommendation(dynamic)
    return {
        "strategy_id": strategy_id,
        "capital_label": capital_label,
        "aum": float(aum),
        "comparison_discipline": {
            "same_strategy": True,
            "same_window": True,
            "same_universe": True,
            "same_params": True,
            "capital_assumption_only_change": True,
        },
        "fixed_cost_baseline": base,
        "dynamic_impact_v1": dynamic,
        "executable_alpha_erosion": {
            "annual_return_delta": annual_delta,
            "sharpe_delta": sharpe_delta,
            "annual_return_erosion_rate": annual_erosion_rate,
            "sharpe_erosion_rate": sharpe_erosion_rate,
            "base_cost_paid": float(dynamic["base_cost_paid"]),
            "impact_cost_paid": float(dynamic["impact_cost_paid"]),
            "total_cost_paid_with_impact": float(dynamic["total_cost_paid_with_impact"]),
        },
        "working_config_recommendation_impact": recommendation,
    }


def build_candidate_scale_stress(strategy_id: str, tickers: list[str] | None = None) -> dict[str, Any]:
    line = candidate_line(strategy_id)
    registry, reviews, _, _ = load_registry_and_reviews(line)
    registry_item = find_registry_item(registry, strategy_id)
    review = latest_review(reviews, strategy_id)
    dataset = build_candidate_dataset(line, registry_item, review, tickers=tickers)
    tape = build_holdings_tape(dataset, registry_item["params"], str(registry_item["factor"]))
    stress_cases = [build_case(strategy_id, item["label"], float(item["aum"]), tape, registry_item["params"]) for item in AUM_ASSUMPTIONS]
    bucket_thresholds = first_bucket_entry(stress_cases)
    return {
        "strategy_id": strategy_id,
        "line": line,
        "review_context": {
            "review_id": review.get("review_id"),
            "window_label": review.get("window_label"),
            "start_date": review.get("start_date"),
            "end_date": review.get("end_date"),
        },
        "operating_params": dict(registry_item.get("params", {})),
        "strategy_filter": dict(registry_item.get("filter", {})),
        "sample_summary": {
            "rows": int(len(dataset)),
            "active_dates": int(dataset["date"].nunique()) if "date" in dataset.columns else 0,
            "unique_tickers": int(dataset["ticker"].nunique()) if "ticker" in dataset.columns else 0,
            "rebalance_dates": len(tape),
        },
        "stress_cases": stress_cases,
        "bucket_entry_thresholds": bucket_thresholds,
        "deployability": build_deployability_schema(stress_cases, bucket_thresholds),
    }


def build_report(tickers_file: str | None = None) -> dict[str, Any]:
    tickers = load_tickers_from_file(tickers_file) if tickers_file else None
    candidate_scale_stress = [build_candidate_scale_stress(strategy_id, tickers=tickers) for strategy_id in TRACKED_IDS]
    by_strategy = {item["strategy_id"]: item for item in candidate_scale_stress}
    growth = by_strategy[TRACKED_CANDIDATES["growth_primary"]]
    return {
        "report_type": "strategy_scale_stress_summary",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "tracked_candidates": dict(TRACKED_CANDIDATES),
        "primary_strategy_id": TRACKED_CANDIDATES["growth_primary"],
        "review_context": growth["review_context"],
        "candidate_scale_stress": candidate_scale_stress,
        "source_artifacts": {
            "tickers_file": tickers_file,
            "growth_registry": str(REPORTS_DIR / "revgrowth_candidate_registry.json"),
            "value_registry": str(REPORTS_DIR / "pbindlow_candidate_registry.json"),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Strategy Scale Stress Summary",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Primary strategy: {report['primary_strategy_id']}",
        "",
    ]
    for item in report["candidate_scale_stress"]:
        lines.append(f"## {item['strategy_id']}")
        deployability = item.get("deployability", {})
        lines.append(f"- deployable_aum_floor: {deployability.get('deployable_aum_floor')}")
        lines.append(f"- recommended_max_aum: {deployability.get('recommended_max_aum')}")
        lines.append(f"- deployment_blocked: {deployability.get('deployment_blocked')}")
        lines.append(f"- blocking_reasons: {deployability.get('blocking_reasons')}")
        for label, capital in item["bucket_entry_thresholds"].items():
            lines.append(f"- first_{label}_aum: {capital}")
        for case in item["stress_cases"]:
            erosion = case["executable_alpha_erosion"]
            rec = case["working_config_recommendation_impact"]
            lines.append(f"### {case['capital_label']} (aum={case['aum']})")
            lines.append(f"- annual_return_delta: {erosion['annual_return_delta']}")
            lines.append(f"- sharpe_delta: {erosion['sharpe_delta']}")
            lines.append(f"- impact_cost_paid: {erosion['impact_cost_paid']}")
            lines.append(f"- bucket_counts: {case['dynamic_impact_v1']['execution_diagnostics']['bucket_counts']}")
            lines.append(f"- working_config_recommendation: {rec['status']} — {rec['reason']}")
            lines.append("")
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path) -> None:
    (REPORTS_DIR / "strategy_scale_stress_summary_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / "strategy_scale_stress_summary_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    parser = argparse.ArgumentParser(description="Run scale-stress for all tracked candidates")
    parser.add_argument("--tickers-file", default=None)
    args = parser.parse_args()
    report = build_report(tickers_file=args.tickers_file)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"strategy_scale_stress_summary_{timestamp}.json"
    md_path = REPORTS_DIR / f"strategy_scale_stress_summary_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
