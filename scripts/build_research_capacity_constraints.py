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

from scripts.build_research_decision_summary import TRACKED_CANDIDATES, latest_matching_file, load_json
from scripts.build_research_realism_stress import build_candidate_dataset, find_registry_item, load_registry_and_reviews
from scripts.run_pbindlow_candidate_review import load_tickers_from_file

REPORTS_DIR = Path("data/reports")
CAPITAL_ASSUMPTIONS = [
    {"label": "model_micro", "aum": 100_000},
    {"label": "model_small", "aum": 1_000_000},
    {"label": "model_medium", "aum": 5_000_000},
    {"label": "model_large", "aum": 10_000_000},
]
LIQUIDITY_THRESHOLDS = {
    "single_position_ratio_warn": 0.01,
    "single_position_ratio_elevated": 0.15,
    "low_liquidity_exposure_warn": 0.10,
    "low_liquidity_exposure_elevated": 0.75,
}


def select_latest_review(reviews: list[dict], strategy_id: str) -> dict:
    candidates = [r for r in reviews if r.get("strategy_id") == strategy_id]
    if not candidates:
        raise ValueError(f"No review rows found for {strategy_id}")
    return sorted(candidates, key=lambda x: (str(x.get("end_date", "")), str(x.get("review_id", ""))))[-1]


def candidate_line(strategy_id: str) -> str:
    if strategy_id == TRACKED_CANDIDATES["growth_primary"]:
        return "growth_line"
    return "valuation_line"


def target_weight_from_params(params: dict) -> float:
    top_n = max(int(params.get("top_n", 1)), 1)
    return 1.0 / top_n


def compute_capacity_snapshot(dataset: pd.DataFrame, holdings_by_date: dict[str, list[str]], model_capital: float, target_weight: float, weights_by_date: dict[str, dict[str, float]] | None = None) -> dict:
    if "amount" not in dataset.columns or "ticker" not in dataset.columns or not holdings_by_date:
        return {
            "median_position_to_amount_ratio": None,
            "p90_position_to_amount_ratio": None,
            "max_position_to_amount_ratio": None,
            "low_liquidity_exposure_ratio": None,
        }
    frame = dataset[["date", "ticker", "amount"]].copy()
    frame["date"] = pd.to_datetime(frame["date"].astype(str), errors="coerce").astype("string")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    ratios: list[float] = []
    for dt, tickers in holdings_by_date.items():
        sub = frame.loc[(frame["date"] == dt) & (frame["ticker"].isin(tickers)), ["ticker", "amount"]].copy()
        if sub.empty:
            continue
        dt_weights = (weights_by_date or {}).get(dt)
        for _, row in sub.iterrows():
            amount = row["amount"]
            if pd.isna(amount) or amount <= 0:
                continue
            ticker = str(row["ticker"])
            w = float(dt_weights.get(ticker, target_weight)) if dt_weights else target_weight
            position_notional = float(model_capital) * w
            ratios.append(float(position_notional / amount))
    if not ratios:
        return {
            "median_position_to_amount_ratio": None,
            "p90_position_to_amount_ratio": None,
            "max_position_to_amount_ratio": None,
            "low_liquidity_exposure_ratio": None,
        }
    series = pd.Series(ratios, dtype="float64")
    return {
        "median_position_to_amount_ratio": float(series.median()),
        "p90_position_to_amount_ratio": float(series.quantile(0.90)),
        "max_position_to_amount_ratio": float(series.max()),
        "low_liquidity_exposure_ratio": float((series > LIQUIDITY_THRESHOLDS["single_position_ratio_warn"]).mean()),
    }


def derive_capacity_status(snapshot: dict) -> tuple[str, bool, str]:
    p90 = snapshot.get("p90_position_to_amount_ratio")
    exposure = snapshot.get("low_liquidity_exposure_ratio")
    if p90 is None or exposure is None:
        return "unknown", False, "Capacity snapshot could not be resolved from the current candidate dataset."
    if p90 > LIQUIDITY_THRESHOLDS["single_position_ratio_elevated"] or exposure > LIQUIDITY_THRESHOLDS["low_liquidity_exposure_elevated"]:
        return "elevated", True, "The candidate breaches first-pass capacity thresholds at the current model capital."
    if p90 > LIQUIDITY_THRESHOLDS["single_position_ratio_warn"] or exposure > LIQUIDITY_THRESHOLDS["low_liquidity_exposure_warn"]:
        return "warning", False, "The candidate approaches first-pass capacity limits and likely needs downweighting or tighter filters."
    return "acceptable", False, "The candidate stays within first-pass capacity thresholds at the current model capital."


def derive_constraint_action(status: str) -> str:
    if status == "acceptable":
        return "keep"
    if status == "warning":
        return "downweight"
    if status == "elevated":
        return "filter"
    return "downweight"


def build_candidate_capacity(strategy_id: str, capital_label: str, aum: float, tickers: list[str] | None = None, realism_by_strategy: dict[str, dict] | None = None) -> tuple[dict, dict]:
    line = candidate_line(strategy_id)
    registry, reviews, _, _ = load_registry_and_reviews(line)
    registry_item = find_registry_item(registry, strategy_id)
    latest_review = select_latest_review(reviews, strategy_id)
    dataset = build_candidate_dataset(line, registry_item, latest_review, tickers=tickers)

    factor_col = f"factor:{registry_item['factor']}"
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"].astype(str), errors="coerce")
    holdings_by_date: dict[str, list[str]] = {}
    weights_by_date: dict[str, dict[str, float]] = {}
    top_n = int(registry_item["params"]["top_n"])
    weighting = str(registry_item["params"].get("weighting", "equal")).lower()

    for dt in sorted(sample["date"].dropna().unique()):
        cross = sample.loc[sample["date"] == dt].copy()
        if cross.empty or factor_col not in cross.columns:
            continue
        cross[factor_col] = pd.to_numeric(cross[factor_col], errors="coerce")
        cross["amount"] = pd.to_numeric(cross["amount"], errors="coerce") if "amount" in cross.columns else 0.0
        cross = cross.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).head(top_n)
        date_key = pd.Timestamp(dt).strftime("%Y-%m-%d")
        ticker_list = cross["ticker"].astype(str).tolist()
        holdings_by_date[date_key] = ticker_list

        if weighting == "liquidity_tilted_score":
            import math
            scores = cross[factor_col].clip(lower=0)
            liq = cross["amount"].clip(lower=0).apply(lambda x: math.log1p(float(x)))
            combined = scores * liq
            total = float(combined.sum())
            if total > 1e-12:
                weights_by_date[date_key] = {str(row["ticker"]): float(c / total) for (_, row), c in zip(cross.iterrows(), combined)}
            else:
                w = 1.0 / len(ticker_list) if ticker_list else 0.0
                weights_by_date[date_key] = {t: w for t in ticker_list}
        else:
            w = 1.0 / len(ticker_list) if ticker_list else 0.0
            weights_by_date[date_key] = {t: w for t in ticker_list}

    snapshot = compute_capacity_snapshot(dataset, holdings_by_date, aum, target_weight_from_params(registry_item["params"]), weights_by_date=weights_by_date)
    impact_realism = ((realism_by_strategy or {}).get(strategy_id, {}) or {}).get("impact_realism", {"status": "unknown", "note": "impact realism not wired", "snapshot": {}})
    status, breach, note = derive_capacity_status(snapshot)
    if impact_realism.get("status") == "elevated" and status != "elevated":
        status = "warning"
        note = "Dynamic impact realism is already elevated, so capacity should be treated with additional caution even before a direct breach."
    payload = {
        "strategy_id": strategy_id,
        "line": line,
        "capital_label": capital_label,
        "operating_params": {
            "top_n": registry_item["params"].get("top_n"),
            "rebalance_frequency": registry_item["params"].get("rebalance_frequency"),
            "weighting": registry_item["params"].get("weighting"),
        },
        "liquidity_capacity": {
            "status": status,
            "note": note,
            "snapshot": snapshot,
            "constraint_breach": breach,
        },
        "impact_capacity_overlay": impact_realism,
        "suggested_constraint": {
            "max_position_to_amount_ratio": LIQUIDITY_THRESHOLDS["single_position_ratio_warn"],
            "action": derive_constraint_action(status),
        },
    }
    trace = {"review_id": latest_review.get("review_id"), "window_label": latest_review.get("window_label")}
    return payload, trace


def build_report(tickers_file: str | None = None, label: str = "base") -> dict[str, Any]:
    realism_pattern = "research_realism_stress_*.json" if label == "base" else f"research_realism_stress_{label}_*.json"
    realism_report_path = latest_matching_file(realism_pattern, REPORTS_DIR)
    decision_summary_path = latest_matching_file("research_decision_summary_*.json", REPORTS_DIR)
    decision_summary = load_json(decision_summary_path)
    realism_report = load_json(realism_report_path)
    realism_by_strategy = {
        item.get("strategy_id"): item
        for item in realism_report.get("candidate_realism", [])
        if item.get("strategy_id")
    }
    tickers = load_tickers_from_file(tickers_file) if tickers_file else None
    candidate_capacity = []
    selection_trace = {}
    tracked_ids = [TRACKED_CANDIDATES["growth_primary"], TRACKED_CANDIDATES["value_primary"], TRACKED_CANDIDATES["value_baseline_reference"]]
    for capital in CAPITAL_ASSUMPTIONS:
        for strategy_id in tracked_ids:
            item, trace = build_candidate_capacity(strategy_id, capital["label"], capital["aum"], tickers=tickers, realism_by_strategy=realism_by_strategy)
            candidate_capacity.append(item)
            selection_trace[strategy_id] = trace
    return {
        "report_type": "research_capacity_constraints",
        "run_label": label,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "as_of_date": decision_summary.get("as_of_date"),
        "capital_assumptions": CAPITAL_ASSUMPTIONS,
        "liquidity_thresholds": dict(LIQUIDITY_THRESHOLDS),
        "candidate_capacity": candidate_capacity,
        "source_artifacts": {
            "realism_report": str(realism_report_path),
            "decision_summary": str(decision_summary_path),
            "selection_trace": selection_trace,
            "tickers_file": tickers_file,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    capital_lines = ", ".join(f"{c['label']}={c['aum']}" for c in report["capital_assumptions"])
    lines = [
        "# Research Capacity & Liquidity Constraint Summary",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- As of date: {report['as_of_date']}",
        f"- Capital assumptions: {capital_lines}",
        "",
        "## Executive takeaway",
        "- First-pass capacity constraints translate liquidity realism into explicit position-to-amount limits across multiple capital scales.",
        "",
        "## Candidate capacity table",
        "| strategy | capital | liquidity capacity | breach | suggested action |",
        "|---|---|---|---|---|",
    ]
    for item in report["candidate_capacity"]:
        cap = item["capital_label"]
        lc = item["liquidity_capacity"]
        lines.append(f"| {item['strategy_id']} | {cap} | {lc['status']} | {lc['constraint_breach']} | {item['suggested_constraint']['action']} |")
    lines += ["", "## Liquidity-capacity details"]
    for item in report["candidate_capacity"]:
        snap = item["liquidity_capacity"]["snapshot"]
        lines.append(f"### {item['strategy_id']}")
        lines.append(f"- median position/amount: {snap['median_position_to_amount_ratio']}")
        lines.append(f"- p90 position/amount: {snap['p90_position_to_amount_ratio']}")
        lines.append(f"- max position/amount: {snap['max_position_to_amount_ratio']}")
        lines.append(f"- low-liquidity exposure ratio: {snap['low_liquidity_exposure_ratio']}")
        lines.append("")
    lines += ["## Suggested liquidity constraints"]
    for idx, item in enumerate(report["candidate_capacity"], start=1):
        lines.append(f"{idx}. {item['strategy_id']}: {item['suggested_constraint']['action']} (max_position_to_amount_ratio <= {item['suggested_constraint']['max_position_to_amount_ratio']})")
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path, label: str = "base") -> None:
    suffix = "" if label == "base" else f"_{label}"
    (REPORTS_DIR / f"research_capacity_constraints{suffix}_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / f"research_capacity_constraints{suffix}_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers-file", default=None)
    parser.add_argument("--label", default="base")
    args = parser.parse_args()
    report = build_report(tickers_file=args.tickers_file, label=args.label)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    suffix = "" if args.label == "base" else f"_{args.label}"
    json_path = REPORTS_DIR / f"research_capacity_constraints{suffix}_{timestamp}.json"
    md_path = REPORTS_DIR / f"research_capacity_constraints{suffix}_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path, label=args.label)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
