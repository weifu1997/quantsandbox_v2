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

from app.domain.backtest.engine import run_topn_backtest
from app.domain.data_contracts import factor_column
from scripts.build_research_decision_summary import TRACKED_CANDIDATES, latest_matching_file, load_json
from scripts.run_pbindlow_candidate_review import load_tickers_from_file
from scripts.run_revgrowth_candidate_review import (
    apply_filter as apply_growth_filter,
    build_dataset as build_growth_dataset,
    load_expanded_tickers,
)

REPORTS_DIR = Path("data/reports")
DEFAULT_STRATEGY_ID = TRACKED_CANDIDATES["growth_primary"]
BASE_COST_SCENARIO = {"label": "fixed_cost_baseline", "commission_bps": 10.0, "slippage_bps": 5.0}
DYNAMIC_COST_SCENARIO = {"label": "dynamic_impact_v1", "commission_bps": 10.0, "slippage_bps": 5.0}


def find_growth_registry_item(strategy_id: str, reports_dir: Path = REPORTS_DIR) -> dict[str, Any]:
    registry = load_json(reports_dir / "revgrowth_candidate_registry.json")
    for item in registry:
        if item.get("strategy_id") == strategy_id:
            return item
    raise ValueError(f"No growth registry item found for strategy_id={strategy_id}")


def latest_growth_review(strategy_id: str, reports_dir: Path = REPORTS_DIR) -> dict[str, Any]:
    reviews = load_json(reports_dir / "revgrowth_candidate_reviews.json")
    candidates = [r for r in reviews if r.get("strategy_id") == strategy_id]
    if not candidates:
        raise ValueError(f"No growth review found for strategy_id={strategy_id}")
    return sorted(candidates, key=lambda x: (str(x.get("end_date", "")), str(x.get("review_id", ""))))[-1]


def resolve_tickers(tickers_file: str | None, sample_limit: int) -> tuple[list[str], str | None]:
    if tickers_file:
        return load_tickers_from_file(tickers_file), tickers_file
    return load_expanded_tickers(sample_limit), None


def build_growth_sample(
    strategy_id: str,
    tickers_file: str | None = None,
    sample_limit: int = 1000,
    reports_dir: Path = REPORTS_DIR,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any], str | None]:
    registry_item = find_growth_registry_item(strategy_id, reports_dir)
    review = latest_growth_review(strategy_id, reports_dir)
    tickers, tickers_trace = resolve_tickers(tickers_file, sample_limit)
    params = registry_item["params"]
    dataset = build_growth_dataset(
        tickers=tickers,
        start_date=review["start_date"],
        end_date=review["end_date"],
        horizon=int(params["horizon"]),
        factor_name=str(registry_item["factor"]),
    )
    filtered, coverage = apply_growth_filter(dataset, registry_item.get("filter", {}))
    return filtered, registry_item, review, tickers_trace


def run_backtest_pair(dataset: pd.DataFrame, registry_item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    params = registry_item["params"]
    factor_col = factor_column(str(registry_item["factor"]))
    base = run_topn_backtest(
        dataset=dataset,
        factor_col=factor_col,
        top_n=int(params["top_n"]),
        rebalance_frequency=str(params["rebalance_frequency"]),
        weighting=str(params["weighting"]),
        benchmark=str(params["benchmark"]),
        commission_bps=float(BASE_COST_SCENARIO["commission_bps"]),
        slippage_bps=float(BASE_COST_SCENARIO["slippage_bps"]),
        horizon=int(params["horizon"]),
    ).payload
    dynamic = run_topn_backtest(
        dataset=dataset,
        factor_col=factor_col,
        top_n=int(params["top_n"]),
        rebalance_frequency=str(params["rebalance_frequency"]),
        weighting=str(params["weighting"]),
        benchmark=str(params["benchmark"]),
        commission_bps=float(DYNAMIC_COST_SCENARIO["commission_bps"]),
        slippage_bps=float(DYNAMIC_COST_SCENARIO["slippage_bps"]),
        horizon=int(params["horizon"]),
    ).payload
    return base, dynamic


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < 1e-12:
        return None
    return float(numerator / denominator)


def build_headline(base: dict[str, Any], dynamic: dict[str, Any]) -> dict[str, Any]:
    annual_delta = float(dynamic["annual_return"] - base["annual_return"])
    sharpe_delta = float(dynamic["sharpe"] - base["sharpe"])
    total_cost_delta = float(dynamic["total_cost_paid_with_impact"] - base["total_cost_paid_with_impact"])
    impact_cost_paid = float(dynamic.get("impact_cost_paid", 0.0))
    annual_erosion_rate = safe_ratio(base["annual_return"] - dynamic["annual_return"], base["annual_return"])
    sharpe_erosion_rate = safe_ratio(base["sharpe"] - dynamic["sharpe"], base["sharpe"])
    if annual_erosion_rate is None:
        status = "unknown"
        note = "Baseline annual return is too close to zero to express executable alpha erosion as a stable ratio."
    elif annual_erosion_rate <= 0.10:
        status = "acceptable"
        note = "Dynamic impact only trims a limited share of the fixed-cost annual return."
    elif annual_erosion_rate <= 0.25:
        status = "warning"
        note = "Dynamic impact materially erodes executable alpha and should constrain confidence."
    else:
        status = "elevated"
        note = "Dynamic impact erodes too much annual return to treat the fixed-cost result as operationally clean."
    return {
        "annual_return_delta": annual_delta,
        "sharpe_delta": sharpe_delta,
        "total_cost_delta": total_cost_delta,
        "impact_cost_paid": impact_cost_paid,
        "annual_return_erosion_rate": annual_erosion_rate,
        "sharpe_erosion_rate": sharpe_erosion_rate,
        "status": status,
        "note": note,
    }


def summarize_case(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "annual_return": payload["annual_return"],
        "total_return": payload["total_return"],
        "sharpe": payload["sharpe"],
        "max_drawdown": payload["max_drawdown"],
        "turnover": payload["turnover"],
        "base_cost_paid": payload.get("base_cost_paid"),
        "impact_cost_paid": payload.get("impact_cost_paid", 0.0),
        "total_cost_paid_with_impact": payload.get("total_cost_paid_with_impact", payload.get("cost_paid")),
        "cost_paid": payload.get("cost_paid"),
        "execution_diagnostics": payload.get("execution_diagnostics", {}),
    }


def build_report(
    strategy_id: str = DEFAULT_STRATEGY_ID,
    tickers_file: str | None = None,
    sample_limit: int = 1000,
    reports_dir: Path = REPORTS_DIR,
) -> dict[str, Any]:
    dataset, registry_item, review, tickers_trace = build_growth_sample(
        strategy_id=strategy_id,
        tickers_file=tickers_file,
        sample_limit=sample_limit,
        reports_dir=reports_dir,
    )
    base, dynamic = run_backtest_pair(dataset, registry_item)
    erosion = build_headline(base, dynamic)
    realism_path = latest_matching_file("research_realism_stress_*.json", reports_dir)
    capacity_path = latest_matching_file("research_capacity_constraints_*.json", reports_dir)
    decision_path = latest_matching_file("research_decision_summary_*.json", reports_dir)
    return {
        "report_type": "growth_executable_alpha_validation",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "strategy_id": strategy_id,
        "review_context": {
            "review_id": review.get("review_id"),
            "window_label": review.get("window_label"),
            "start_date": review.get("start_date"),
            "end_date": review.get("end_date"),
        },
        "comparison_discipline": {
            "same_strategy": True,
            "same_window": True,
            "same_universe": True,
            "same_params": True,
            "tickers_file": tickers_trace,
        },
        "operating_params": dict(registry_item.get("params", {})),
        "strategy_filter": dict(registry_item.get("filter", {})),
        "sample_summary": {
            "rows": int(len(dataset)),
            "active_dates": int(dataset["date"].nunique()) if "date" in dataset.columns else 0,
            "unique_tickers": int(dataset["ticker"].nunique()) if "ticker" in dataset.columns else 0,
        },
        "before_after": {
            "fixed_cost_baseline": summarize_case(BASE_COST_SCENARIO["label"], base),
            "dynamic_impact_v1": summarize_case(DYNAMIC_COST_SCENARIO["label"], dynamic),
        },
        "executable_alpha_erosion": erosion,
        "cost_breakdown": {
            "base_cost_paid": float(dynamic.get("base_cost_paid", 0.0)),
            "impact_cost_paid": float(dynamic.get("impact_cost_paid", 0.0)),
            "total_cost_paid_with_impact": float(dynamic.get("total_cost_paid_with_impact", dynamic.get("cost_paid", 0.0))),
        },
        "source_artifacts": {
            "realism_report": str(realism_path),
            "capacity_report": str(capacity_path),
            "decision_summary": str(decision_path),
            "registry": str(reports_dir / "revgrowth_candidate_registry.json"),
            "reviews": str(reports_dir / "revgrowth_candidate_reviews.json"),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    before = report["before_after"]["fixed_cost_baseline"]
    after = report["before_after"]["dynamic_impact_v1"]
    erosion = report["executable_alpha_erosion"]
    lines = [
        "# Growth Executable Alpha Validation",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Strategy: {report['strategy_id']}",
        f"- Review window: {report['review_context']['window_label']} ({report['review_context']['start_date']} → {report['review_context']['end_date']})",
        "",
        "## Comparison discipline",
        f"- same_strategy: {report['comparison_discipline']['same_strategy']}",
        f"- same_window: {report['comparison_discipline']['same_window']}",
        f"- same_universe: {report['comparison_discipline']['same_universe']}",
        f"- same_params: {report['comparison_discipline']['same_params']}",
        "",
        "## Before vs after",
        f"- Fixed-cost annual_return: {before['annual_return']}",
        f"- Dynamic-impact annual_return: {after['annual_return']}",
        f"- Annual return delta: {erosion['annual_return_delta']}",
        f"- Fixed-cost Sharpe: {before['sharpe']}",
        f"- Dynamic-impact Sharpe: {after['sharpe']}",
        f"- Sharpe delta: {erosion['sharpe_delta']}",
        f"- Turnover (baseline): {before['turnover']}",
        f"- Turnover (dynamic): {after['turnover']}",
        "",
        "## Executable alpha erosion",
        f"- status: {erosion['status']}",
        f"- note: {erosion['note']}",
        f"- annual_return_erosion_rate: {erosion['annual_return_erosion_rate']}",
        f"- sharpe_erosion_rate: {erosion['sharpe_erosion_rate']}",
        "",
        "## Cost breakdown",
        f"- base_cost_paid: {report['cost_breakdown']['base_cost_paid']}",
        f"- impact_cost_paid: {report['cost_breakdown']['impact_cost_paid']}",
        f"- total_cost_paid_with_impact: {report['cost_breakdown']['total_cost_paid_with_impact']}",
        "",
        "## Execution diagnostics",
        f"- avg_participation_rate: {after['execution_diagnostics'].get('avg_participation_rate')}",
        f"- p90_participation_rate: {after['execution_diagnostics'].get('p90_participation_rate')}",
        f"- avg_dynamic_impact_bps: {after['execution_diagnostics'].get('avg_dynamic_impact_bps')}",
        f"- bucket_counts: {after['execution_diagnostics'].get('bucket_counts')}",
        "",
    ]
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path, reports_dir: Path = REPORTS_DIR) -> None:
    (reports_dir / "growth_executable_alpha_validation_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (reports_dir / "growth_executable_alpha_validation_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    parser = argparse.ArgumentParser(description="Run growth executable alpha validation under dynamic impact")
    parser.add_argument("--strategy-id", default=DEFAULT_STRATEGY_ID)
    parser.add_argument("--tickers-file", default=None)
    parser.add_argument("--sample-limit", type=int, default=1000)
    args = parser.parse_args()

    report = build_report(strategy_id=args.strategy_id, tickers_file=args.tickers_file, sample_limit=args.sample_limit)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"growth_executable_alpha_validation_{timestamp}.json"
    md_path = REPORTS_DIR / f"growth_executable_alpha_validation_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
