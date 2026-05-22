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
from scripts.run_pbindlow_candidate_review import (
    build_dataset as build_value_dataset,
    load_expanded_tickers as load_value_tickers,
    load_tickers_from_file,
)
from scripts.run_revgrowth_candidate_review import (
    apply_filter as apply_growth_filter,
    build_dataset as build_growth_dataset,
    load_expanded_tickers as load_growth_tickers,
)
from scripts.run_pbindlow_candidate_review import apply_filter as apply_value_filter

REPORTS_DIR = Path("data/reports")

COST_SCENARIOS = [
    {"label": "base", "commission_bps": 10.0, "slippage_bps": 5.0},
    {"label": "stress_1", "commission_bps": 15.0, "slippage_bps": 10.0},
    {"label": "stress_2", "commission_bps": 20.0, "slippage_bps": 15.0},
]

CONCENTRATION_THRESHOLDS = {
    "single_name_weight_warn": 0.12,
    "top3_weight_warn": 0.35,
    "top5_weight_warn": 0.55,
}

LIQUIDITY_THRESHOLDS = {
    "position_to_daily_turnover_warn": 0.05,
    "position_to_daily_turnover_elevated": 0.10,
}


def default_status_note(status: str = "unknown", note: str = "") -> dict:
    return {"status": status, "note": note}


def load_registry_and_reviews(line: str) -> tuple[list[dict], list[dict], Path, Path]:
    if line == "growth_line":
        registry_path = REPORTS_DIR / "revgrowth_candidate_registry.json"
        reviews_path = REPORTS_DIR / "revgrowth_candidate_reviews.json"
    else:
        registry_path = REPORTS_DIR / "pbindlow_candidate_registry.json"
        reviews_path = REPORTS_DIR / "pbindlow_candidate_reviews.json"
    return load_json(registry_path), load_json(reviews_path), registry_path, reviews_path


def find_registry_item(registry: list[dict], strategy_id: str) -> dict:
    for item in registry:
        if item.get("strategy_id") == strategy_id:
            return item
    raise ValueError(f"No registry item found for {strategy_id}")


def latest_review(reviews: list[dict], strategy_id: str) -> dict:
    candidates = [r for r in reviews if r.get("strategy_id") == strategy_id]
    if not candidates:
        raise ValueError(f"No review rows found for {strategy_id}")
    return sorted(candidates, key=lambda x: (str(x.get("end_date", "")), str(x.get("review_id", ""))))[-1]


def build_candidate_dataset(line: str, registry_item: dict, review_row: dict, tickers: list[str] | None = None) -> pd.DataFrame:
    factor = registry_item["factor"]
    params = registry_item["params"]
    start_date = review_row["start_date"]
    end_date = review_row["end_date"]
    if line == "growth_line":
        selected = tickers if tickers is not None else load_growth_tickers(1000)
        ds = build_growth_dataset(selected, start_date, end_date, params["horizon"], factor)
        filtered, _ = apply_growth_filter(ds, registry_item.get("filter", {}))
        filtered.attrs["growth_strategy_id"] = registry_item.get("strategy_id")
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
        return filtered
    selected = tickers if tickers is not None else load_value_tickers(1000)
    ds = build_value_dataset(selected, start_date, end_date, params["horizon"], factor)
    filtered, _ = apply_value_filter(ds, registry_item.get("filter", {}))
    return filtered


def run_cost_scenarios(dataset: pd.DataFrame, registry_item: dict) -> list[dict]:
    factor = registry_item["factor"]
    params = registry_item["params"]
    results = []
    for scenario in COST_SCENARIOS:
        bt = run_topn_backtest(
            dataset=dataset,
            factor_col=factor_column(factor),
            top_n=params["top_n"],
            rebalance_frequency=params["rebalance_frequency"],
            weighting=params["weighting"],
            benchmark=params["benchmark"],
            commission_bps=scenario["commission_bps"],
            slippage_bps=scenario["slippage_bps"],
            horizon=params["horizon"],
        ).payload
        results.append({
            "label": scenario["label"],
            "annual_return": bt["annual_return"],
            "sharpe": bt["sharpe"],
            "turnover": bt["turnover"],
            "cost_paid": bt["cost_paid"],
            "holdings_by_rebalance_date": bt["holdings_by_rebalance_date"],
            "execution_diagnostics": bt.get("execution_diagnostics", {}),
            "execution_by_rebalance_date": bt.get("execution_by_rebalance_date", {}),
            "impact_cost_paid": bt.get("impact_cost_paid", 0.0),
        })
    return results


def derive_cost_status(scenarios: list[dict]) -> dict:
    base = scenarios[0]
    worst = scenarios[-1]
    if worst["annual_return"] < 0 or worst["sharpe"] < 0:
        status = "elevated"
        note = "Strategy becomes weak or negative under harsher cost assumptions."
    elif worst["annual_return"] < base["annual_return"] * 0.6 or worst["sharpe"] < base["sharpe"] * 0.6:
        status = "warning"
        note = "Performance degrades materially under modestly harsher cost assumptions."
    else:
        status = "acceptable"
        note = "Performance remains directionally intact under stressed transaction-cost assumptions."
    return {
        "status": status,
        "note": note,
        "scenario_comparison": [{k: v for k, v in x.items() if k != "holdings_by_rebalance_date"} for x in scenarios],
    }


def concentration_snapshot_from_holdings(holdings_by_date: dict[str, list[str]]) -> dict:
    if not holdings_by_date:
        return {"avg_single_name_weight": 0.0, "avg_top3_weight": 0.0, "avg_top5_weight": 0.0}
    single = []
    top3 = []
    top5 = []
    for holdings in holdings_by_date.values():
        n = max(len(holdings), 1)
        w = 1.0 / n
        single.append(w)
        top3.append(min(3, n) * w)
        top5.append(min(5, n) * w)
    return {
        "avg_single_name_weight": float(sum(single) / len(single)),
        "avg_top3_weight": float(sum(top3) / len(top3)),
        "avg_top5_weight": float(sum(top5) / len(top5)),
    }


def derive_concentration_status(snapshot: dict) -> dict:
    top3 = snapshot["avg_top3_weight"]
    top5 = snapshot["avg_top5_weight"]
    single = snapshot["avg_single_name_weight"]
    if top5 > CONCENTRATION_THRESHOLDS["top5_weight_warn"] or top3 > CONCENTRATION_THRESHOLDS["top3_weight_warn"] * 1.2:
        status = "elevated"
        note = "Portfolio concentration is persistently high relative to simple production-style comfort thresholds."
    elif (
        single > CONCENTRATION_THRESHOLDS["single_name_weight_warn"]
        or top3 > CONCENTRATION_THRESHOLDS["top3_weight_warn"]
        or top5 > CONCENTRATION_THRESHOLDS["top5_weight_warn"]
    ):
        status = "warning"
        note = "Portfolio concentration repeatedly approaches or exceeds warning thresholds."
    else:
        status = "acceptable"
        note = "Portfolio concentration remains within simple warning thresholds."
    return {"status": status, "note": note, "snapshot": snapshot}


def build_placeholder_liquidity(dataset: pd.DataFrame) -> dict:
    if "amount" in dataset.columns:
        return {
            "status": "unknown",
            "note": "Turnover data exists but position-size calibration is not yet wired in v1.",
            "snapshot": {"median_position_to_daily_turnover": None, "p90_position_to_daily_turnover": None},
        }
    return {
        "status": "unknown",
        "note": "Liquidity proxy not yet connected in v1.",
        "snapshot": {"median_position_to_daily_turnover": None, "p90_position_to_daily_turnover": None},
    }


def build_liquidity_risk(dataset: pd.DataFrame, holdings_by_date: dict[str, list[str]]) -> dict:
    if "amount" not in dataset.columns or not holdings_by_date:
        return {
            "status": "unknown",
            "note": "Liquidity proxy not available for the candidate holdings in v1.",
            "snapshot": {
                "median_holding_amount": None,
                "p10_holding_amount": None,
                "low_liquidity_exposure_ratio": None,
            },
        }

    frame = dataset[["date", "ticker", "amount"]].copy()
    frame["date"] = pd.to_datetime(frame["date"].astype(str), errors="coerce").astype("string")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    rows = []
    for dt, tickers in holdings_by_date.items():
        sub = frame.loc[(frame["date"] == dt) & (frame["ticker"].isin(tickers)), ["ticker", "amount"]].copy()
        if sub.empty:
            continue
        rows.extend(sub["amount"].dropna().tolist())
    if not rows:
        return {
            "status": "unknown",
            "note": "Holdings-level liquidity values could not be resolved from the current dataset window.",
            "snapshot": {
                "median_holding_amount": None,
                "p10_holding_amount": None,
                "low_liquidity_exposure_ratio": None,
            },
        }

    amounts = pd.Series(rows, dtype="float64")
    median_amount = float(amounts.median())
    p10_amount = float(amounts.quantile(0.10))
    low_liquidity_exposure_ratio = float((amounts < 300000).mean())

    if p10_amount < 150000 or low_liquidity_exposure_ratio > 0.30:
        status = "elevated"
        note = "A meaningful share of selected holdings falls into low traded-amount buckets on rebalance dates."
    elif p10_amount < 300000 or low_liquidity_exposure_ratio > 0.10:
        status = "warning"
        note = "Selected holdings show some meaningful low-liquidity exposure on rebalance dates."
    else:
        status = "acceptable"
        note = "Holdings-level traded-amount distribution looks acceptable for a first-pass liquidity screen."

    return {
        "status": status,
        "note": note,
        "snapshot": {
            "median_holding_amount": median_amount,
            "p10_holding_amount": p10_amount,
            "low_liquidity_exposure_ratio": low_liquidity_exposure_ratio,
        },
    }


def build_execution_realism(dataset: pd.DataFrame, scenarios: list[dict], registry_item: dict) -> dict:
    turnover = scenarios[0]["turnover"]
    active_dates = int(dataset["date"].nunique()) if "date" in dataset.columns else 0
    status = "acceptable"
    note = "Weekly rebalancing and observed turnover appear operationally sane for a first-pass realism check."
    if turnover > 0.5 or active_dates < 20:
        status = "warning"
        note = "Turnover or small sample size creates execution-realism caution."
    return {
        "status": status,
        "note": note,
        "checks": {
            "weekly_rebalance_feasible": str(registry_item["params"].get("rebalance_frequency", "")).upper() == "W",
            "extreme_turnover_warning": bool(turnover > 0.5),
            "small_sample_caution": bool(active_dates < 20),
        },
    }


def build_impact_realism(scenarios: list[dict]) -> dict:
    base = scenarios[0] if scenarios else {}
    diagnostics = base.get("execution_diagnostics", {})
    avg_bps = diagnostics.get("avg_dynamic_impact_bps")
    p90_rate = diagnostics.get("p90_participation_rate")
    bucket_counts = diagnostics.get("bucket_counts", {}) or {}
    total = sum(int(v) for v in bucket_counts.values()) if bucket_counts else 0
    extreme_ratio = float(bucket_counts.get("extreme", 0) / total) if total else 0.0

    if avg_bps is None:
        return {
            "status": "unknown",
            "note": "Execution impact diagnostics are not available in the current backtest payload.",
            "snapshot": {
                "avg_participation_rate": None,
                "p90_participation_rate": None,
                "avg_dynamic_impact_bps": None,
                "extreme_bucket_ratio": None,
            },
        }

    if avg_bps > 25 or extreme_ratio > 0.05:
        status = "elevated"
        note = "Dynamic impact diagnostics imply that execution friction is too large to treat research returns as clean."
    elif avg_bps > 10 or (p90_rate is not None and p90_rate > 0.01):
        status = "warning"
        note = "Dynamic impact diagnostics show meaningful execution friction that should constrain confidence."
    else:
        status = "acceptable"
        note = "Dynamic impact diagnostics remain within the current first-pass tolerance band."

    return {
        "status": status,
        "note": note,
        "snapshot": {
            "avg_participation_rate": diagnostics.get("avg_participation_rate"),
            "p90_participation_rate": p90_rate,
            "avg_dynamic_impact_bps": avg_bps,
            "extreme_bucket_ratio": extreme_ratio,
        },
    }


def overall_status(*statuses: str) -> str:
    order = {"acceptable": 0, "unknown": 1, "warning": 2, "elevated": 3}
    return max(statuses, key=lambda s: order.get(s, 1))


def overall_note(status: str) -> str:
    if status == "elevated":
        return "At least one realism dimension is materially stressed and should constrain confidence." 
    if status == "warning":
        return "One or more realism dimensions require caution before treating research results as production-like."
    if status == "acceptable":
        return "The first-pass realism checks are acceptable, though still simplified."
    return "Some realism dimensions remain unimplemented or unknown in v1."


def build_candidate_realism(line: str, strategy_id: str, tickers: list[str] | None = None) -> tuple[dict, dict]:
    registry, reviews, _, _ = load_registry_and_reviews(line)
    registry_item = find_registry_item(registry, strategy_id)
    review_row = latest_review(reviews, strategy_id)
    dataset = build_candidate_dataset(line, registry_item, review_row, tickers=tickers)
    scenarios = run_cost_scenarios(dataset, registry_item)
    cost = derive_cost_status(scenarios)
    concentration = derive_concentration_status(concentration_snapshot_from_holdings(scenarios[0]["holdings_by_rebalance_date"]))
    liquidity = build_liquidity_risk(dataset, scenarios[0]["holdings_by_rebalance_date"])
    execution = build_execution_realism(dataset, scenarios, registry_item)
    impact = build_impact_realism(scenarios)
    overall = overall_status(cost["status"], concentration["status"], liquidity["status"], execution["status"], impact["status"])
    payload = {
        "strategy_id": strategy_id,
        "line": line,
        "operating_params": dict(registry_item.get("params", {})),
        "cost_sensitivity": cost,
        "concentration_risk": concentration,
        "liquidity_risk": liquidity,
        "execution_realism": execution,
        "impact_realism": impact,
        "overall_realism": {"status": overall, "note": overall_note(overall)},
    }
    trace = {"review_id": review_row.get("review_id"), "window_label": review_row.get("window_label")}
    return payload, trace


def build_report(tickers_file: str | None = None, label: str = "base") -> dict[str, Any]:
    decision_summary_path = latest_matching_file("research_decision_summary_*.json", REPORTS_DIR)
    decision_summary = load_json(decision_summary_path)
    tickers = load_tickers_from_file(tickers_file) if tickers_file else None
    candidate_realism = []
    selection_trace = {}
    mappings = [
        ("growth_line", TRACKED_CANDIDATES["growth_primary"]),
        ("valuation_line", TRACKED_CANDIDATES["value_primary"]),
        ("valuation_line", TRACKED_CANDIDATES["value_baseline_reference"]),
    ]
    for line, strategy_id in mappings:
        realism, trace = build_candidate_realism(line, strategy_id, tickers=tickers)
        candidate_realism.append(realism)
        selection_trace[strategy_id] = trace
    return {
        "report_type": "research_realism_stress",
        "run_label": label,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "as_of_date": decision_summary.get("as_of_date"),
        "tracked_candidates": dict(TRACKED_CANDIDATES),
        "assumptions": {
            "cost_scenarios": COST_SCENARIOS,
            "concentration_thresholds": CONCENTRATION_THRESHOLDS,
            "liquidity_thresholds": LIQUIDITY_THRESHOLDS,
        },
        "candidate_realism": candidate_realism,
        "source_artifacts": {
            "decision_summary": str(decision_summary_path),
            "selection_trace": selection_trace,
            "tickers_file": tickers_file,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Research Realism Stress Summary",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- As of date: {report['as_of_date']}",
        "",
        "## Executive takeaway",
        "- First-pass realism outputs now distinguish cost/concentration risks from still-partial liquidity/execution realism.",
        "",
        "## Candidate realism table",
        "| strategy | cost sensitivity | concentration | liquidity | execution | overall |",
        "|---|---|---|---|---|---|",
    ]
    for item in report["candidate_realism"]:
        lines.append(
            f"| {item['strategy_id']} | {item['cost_sensitivity']['status']} | {item['concentration_risk']['status']} | {item['liquidity_risk']['status']} | {item['execution_realism']['status']} | {item['overall_realism']['status']} |"
        )
    lines += ["", "## Cost sensitivity details"]
    for item in report["candidate_realism"]:
        lines.append(f"### {item['strategy_id']}")
        for scenario in item["cost_sensitivity"]["scenario_comparison"]:
            lines.append(f"- {scenario['label']}: annual_return={scenario['annual_return']}, sharpe={scenario['sharpe']}")
        lines.append("")
    lines += ["## Concentration risk details"]
    for item in report["candidate_realism"]:
        snap = item["concentration_risk"]["snapshot"]
        lines.append(f"### {item['strategy_id']}")
        lines.append(f"- avg_single_name_weight: {snap['avg_single_name_weight']}")
        lines.append(f"- avg_top3_weight: {snap['avg_top3_weight']}")
        lines.append(f"- avg_top5_weight: {snap['avg_top5_weight']}")
        lines.append("")
    lines += ["## Liquidity & execution notes"]
    for item in report["candidate_realism"]:
        lines.append(f"- {item['strategy_id']}: liquidity={item['liquidity_risk']['note']} execution={item['execution_realism']['note']}")
    lines += ["", "## Recommended realism actions", "1. Prioritize cost/concentration interpretation first; treat liquidity/execution as partial in v1.", "2. Feed these realism outputs into the decision-summary layer before adding allocation logic."]
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path, label: str = "base") -> None:
    suffix = "" if label == "base" else f"_{label}"
    (REPORTS_DIR / f"research_realism_stress{suffix}_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / f"research_realism_stress{suffix}_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers-file", default=None)
    parser.add_argument("--label", default="base")
    args = parser.parse_args()
    report = build_report(tickers_file=args.tickers_file, label=args.label)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    suffix = "" if args.label == "base" else f"_{args.label}"
    json_path = REPORTS_DIR / f"research_realism_stress{suffix}_{timestamp}.json"
    md_path = REPORTS_DIR / f"research_realism_stress{suffix}_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path, label=args.label)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
