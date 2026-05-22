from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

REPORTS_DIR = Path("data/reports")

TRACKED_CANDIDATES = {
    "growth_primary": "revgrowth_always_on_v1",
    "value_primary": "pbindlow_downtrend_narrow_quality_v1",
    "value_baseline_reference": "pbindlow_downtrend_only_v1",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_matching_file(pattern: str, reports_dir: Path = REPORTS_DIR) -> Path:
    matches = sorted(reports_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No files matched pattern: {pattern}")
    return matches[0]


def select_latest_review(reviews: list[dict], strategy_id: str) -> dict:
    candidates = [r for r in reviews if r.get("strategy_id") == strategy_id]
    if not candidates:
        raise ValueError(f"No reviews found for strategy_id={strategy_id}")

    def sort_key(item: dict) -> tuple[str, str, str]:
        return (
            str(item.get("end_date", "")),
            str(item.get("start_date", "")),
            str(item.get("review_id", "")),
        )

    return sorted(candidates, key=sort_key)[-1]


def find_registry_item(registry: list[dict], strategy_id: str) -> dict:
    for item in registry:
        if item.get("strategy_id") == strategy_id:
            return item
    raise ValueError(f"No registry item found for strategy_id={strategy_id}")


def find_status_item(status_payload: dict, strategy_id: str) -> dict:
    for item in status_payload.get("strategies", []):
        if item.get("strategy_id") == strategy_id:
            return item
    raise ValueError(f"No status item found for strategy_id={strategy_id}")


def formal_review_count(reviews: list[dict], strategy_id: str) -> int:
    return sum(1 for r in reviews if r.get("strategy_id") == strategy_id)


def metrics_snapshot_from_review(review: dict) -> dict:
    metrics = review.get("metrics", {})
    return {
        "annual_return": metrics.get("annual_return"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("max_drawdown"),
        "top_bottom_spread": metrics.get("top_bottom_spread"),
        "active_ratio": metrics.get("active_ratio"),
        "rank_ic_mean": metrics.get("rank_ic_mean"),
        "positive_ic_ratio": metrics.get("positive_ic_ratio"),
        "monotonicity_score": metrics.get("monotonicity_score"),
    }


def default_realism_flags() -> dict:
    def item() -> dict:
        return {"status": "unknown", "note": ""}

    return {
        "liquidity_risk": item(),
        "cost_sensitivity": item(),
        "concentration_risk": item(),
        "execution_realism": item(),
        "impact_realism": item(),
    }


def build_candidate_state(
    *,
    line: str,
    strategy_id: str,
    registry: list[dict],
    reviews: list[dict],
    status_payload: dict,
    realism_by_strategy: dict[str, dict] | None = None,
) -> tuple[dict, dict]:
    registry_item = find_registry_item(registry, strategy_id)
    status_item = find_status_item(status_payload, strategy_id)
    latest_review = select_latest_review(reviews, strategy_id)
    review_count = formal_review_count(reviews, strategy_id)

    latest_review_payload = {
        "review_id": latest_review.get("review_id"),
        "window_label": latest_review.get("window_label"),
        "review_result": latest_review.get("review_result"),
        "comment": latest_review.get("comment"),
    }

    realism_payload = (realism_by_strategy or {}).get(strategy_id, {})
    candidate_state = {
        "line": line,
        "strategy_id": strategy_id,
        "role": registry_item.get("role"),
        "status": status_item.get("status", registry_item.get("status")),
        "latest_review": latest_review_payload,
        "evidence_summary": {
            "formal_review_count": review_count,
            "recent_review_count_used": min(review_count, 3),
            "latest_window_label": latest_review.get("window_label"),
            "latest_start_date": latest_review.get("start_date"),
            "latest_end_date": latest_review.get("end_date"),
        },
        "recent_review_trend": status_item.get("recent_review_trend"),
        "suggested_action": status_item.get("suggested_action"),
        "operating_params": dict(registry_item.get("params", {})),
        "metrics_snapshot": metrics_snapshot_from_review(latest_review),
        "realism_flags": {
            "liquidity_risk": realism_payload.get("liquidity_risk", default_realism_flags()["liquidity_risk"]),
            "cost_sensitivity": realism_payload.get("cost_sensitivity", default_realism_flags()["cost_sensitivity"]),
            "concentration_risk": realism_payload.get("concentration_risk", default_realism_flags()["concentration_risk"]),
            "execution_realism": realism_payload.get("execution_realism", default_realism_flags()["execution_realism"]),
            "impact_realism": realism_payload.get("impact_realism", default_realism_flags()["impact_realism"]),
        },
    }

    selection_trace = {
        "review_id": latest_review.get("review_id"),
        "window_label": latest_review.get("window_label"),
    }
    return candidate_state, selection_trace


def derive_value_posture(value_primary_state: dict) -> str:
    status = value_primary_state.get("status")
    if status == "active":
        return "primary_active"
    if status == "watch":
        return "primary_watch"
    return "reference_only"


def derive_confidence(candidate_states: list[dict]) -> str:
    growth = next((x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["growth_primary"]), None)
    value = next((x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["value_primary"]), None)
    if not growth or not value:
        return "low"

    if (
        growth.get("status") == "active"
        and value.get("status") == "active"
        and growth.get("recent_review_trend") == "stable_keep"
        and value.get("recent_review_trend") == "stable_keep"
        and growth.get("evidence_summary", {}).get("formal_review_count", 0) >= 2
        and value.get("evidence_summary", {}).get("formal_review_count", 0) >= 2
    ):
        return "high"

    if growth.get("status") == "active" or value.get("status") == "active":
        return "medium"

    return "low"


def build_line_view(candidate_states: list[dict]) -> dict:
    value_primary = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["value_primary"])
    return {
        "growth_line": {
            "posture": "core",
            "headline_action": "Keep growth core as the main tracked allocation anchor.",
        },
        "valuation_line": {
            "posture": derive_value_posture(value_primary),
            "headline_action": "Treat value primary as a secondary line whose conviction should continue to be updated by forward reviews.",
        },
    }


def build_decision_actions(
    candidate_states: list[dict],
    working_config_recommendation: dict | None = None,
    additive_eligibility: dict | None = None,
    promotion_blockers: dict | None = None,
) -> dict:
    value_primary = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["value_primary"])
    growth_primary = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["growth_primary"])
    value_params = value_primary.get("operating_params", {})
    rec_status = (working_config_recommendation or {}).get("status", "needs_revision")
    growth_elig = (additive_eligibility or {}).get(growth_primary["strategy_id"], "ineligible")
    value_elig = (additive_eligibility or {}).get(value_primary["strategy_id"], "ineligible")
    value_blockers = (promotion_blockers or {}).get(value_primary["strategy_id"], [])
    scale_impact = (working_config_recommendation or {}).get("scale_stress_impact") or {}

    research_actions = [
        "Continue forward review accumulation for the tracked growth/value candidates.",
        f"Keep the value primary on current registry params (top_n={value_params.get('top_n')}) unless new evidence justifies another parameter decision.",
    ]
    if value_elig == "ineligible":
        research_actions.append("Do not promote the value line until its explicit promotion blockers are cleared in both realism, capacity, and scale stress.")
    if rec_status == "keep_with_caution":
        research_actions.append("Prioritize realism/capacity remediation work on the growth line before attempting any additive expansion.")
    elif rec_status in {"needs_revision", "stop_using"}:
        research_actions.append("Rework the current working configuration before treating it as a normal operating baseline again.")
    if scale_impact.get("growth", {}).get("status") in {"needs_revision", "stop_using"}:
        research_actions.append("Capital-scale executable-alpha stress now indicates that growth executability breaks under realistic AUM assumptions; remediation must happen before allocator expansion.")
    if scale_impact.get("value_primary", {}).get("status") in {"needs_revision", "stop_using"}:
        research_actions.append("Value-line scale stress now blocks treating the current value candidate as a normal additive sleeve until tradability is improved.")

    portfolio_actions = [
        "Keep growth core as the main tracked allocation anchor." if growth_elig in {"eligible", "conditional"} else "Do not treat growth as a normal allocation anchor until its gating status improves.",
    ]
    if value_elig == "eligible":
        portfolio_actions.append("Treat value primary as an additive sleeve that now clears review, realism, capacity, and scale-stress gates.")
    elif value_elig == "conditional":
        portfolio_actions.append("Treat value primary only as a tightly constrained additive sleeve, not a normal secondary line.")
    else:
        blocker_text = ", ".join(value_blockers) if value_blockers else "promotion blockers remain unresolved"
        portfolio_actions.append(f"Keep value primary in observe-only mode because {blocker_text}.")
    if rec_status == "keep_with_caution":
        portfolio_actions.append("Run the current working config in cautious mode rather than treating it as a clean keep.")
    elif rec_status in {"needs_revision", "stop_using"}:
        portfolio_actions.append("Do not treat the current working config as fully deployable until the gating recommendation improves.")
    if scale_impact.get("growth", {}).get("status") == "stop_using":
        portfolio_actions.append("Capital-scale stress shows growth already enters extreme execution buckets at the tested AUM floor, so the current working config should not be treated as deployable at that scale.")
    elif scale_impact.get("growth", {}).get("status") == "needs_revision":
        portfolio_actions.append("Capital-scale stress shows the current working config needs a revised tradability regime before production-scale deployment.")
    if scale_impact.get("value_primary", {}).get("status") == "stop_using":
        portfolio_actions.append("Value primary also fails scale-stress deployability at the tested AUM floor, so it should remain blocked as an additive line.")
    return {
        "research_actions": research_actions,
        "portfolio_actions": portfolio_actions,
    }


def build_executive_summary(
    candidate_states: list[dict],
    working_configuration: dict | None = None,
    working_config_recommendation: dict | None = None,
    additive_eligibility: dict | None = None,
) -> dict:
    growth = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["growth_primary"])
    value = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["value_primary"])
    rec_status = (working_config_recommendation or {}).get("status", (working_configuration or {}).get("working_config_review", {}).get("status", "needs_review"))
    growth_elig = (additive_eligibility or {}).get(growth["strategy_id"], "ineligible")
    value_elig = (additive_eligibility or {}).get(value["strategy_id"], "ineligible")
    scale_impact = (working_config_recommendation or {}).get("scale_stress_impact") or {}
    if growth.get("status") == "active" and value_elig == "eligible":
        takeaway = "Growth remains the core line, and value has now cleared the main additive gates."
        posture = "growth core + additive value sleeve"
    elif growth.get("status") == "active":
        takeaway = "Growth remains the core line, while value should continue under tighter forward observation."
        posture = "growth core + cautious value tracking"
    else:
        takeaway = "Tracked candidates need renewed forward evidence before stronger allocation confidence is justified."
        posture = "cautious multi-line tracking"
    if scale_impact.get("growth", {}).get("status") == "stop_using":
        takeaway = "Growth review evidence remains live, but capital-scale executable-alpha stress now blocks treating the current working config as deployable."
        posture = "research-valid but scale-blocked growth core"
    elif scale_impact.get("growth", {}).get("status") == "needs_revision":
        takeaway = "Growth still leads on review evidence, but capital-scale executable-alpha stress now forces a revised deployment stance."
        posture = "growth core with scale-stress revision"
    elif scale_impact.get("value_primary", {}).get("status") == "stop_using":
        takeaway = "Growth remains the cleaner line, but value fails capital-scale deployability and cannot be treated as a normal additive sleeve."
        posture = "growth core with scale-blocked value overlay"
    return {
        "primary_takeaway": takeaway,
        "recommended_posture": posture,
        "allocator_priority": "deprioritized",
        "confidence": derive_confidence(candidate_states),
        "real_return_priority": "high",
        "single_line_dependency_risk": "elevated" if growth_elig == "conditional" and value_elig != "eligible" else "moderate",
        "working_config_recommendation": rec_status,
    }


def build_open_risks(candidate_states: list[dict], working_config_recommendation: dict | None = None) -> list[str]:
    value_primary = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["value_primary"])
    growth_primary = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["growth_primary"])
    value_realism = value_primary.get("realism_flags", {})
    growth_realism = growth_primary.get("realism_flags", {})
    scale_impact = (working_config_recommendation or {}).get("scale_stress_impact") or {}
    risks = [
        "Liquidity realism is still partial: cost/concentration/execution first-pass checks are now connected, but capacity calibration is not yet wired.",
        f"Value primary remains dependent on continued forward evidence under current registry params (top_n={value_primary.get('operating_params', {}).get('top_n')}).",
    ]
    if value_realism.get("cost_sensitivity", {}).get("status") in {"warning", "elevated"}:
        risks.append("Value-line cost sensitivity is already elevated enough to constrain confidence, even before fuller liquidity realism is added.")
    if growth_realism.get("cost_sensitivity", {}).get("status") == "acceptable":
        risks.append("The current cross-line balance still leans heavily on growth being the cleaner realism-adjusted line.")
    else:
        risks.append("Allocator work should stay deprioritized while candidate-level evidence remains the main bottleneck.")
    if scale_impact.get("growth", {}).get("status") in {"needs_revision", "stop_using"}:
        risks.append("Capital-scale executable-alpha stress now shows that tradability can fail even while research returns remain positive, so deployability must be governed separately from pure alpha evidence.")
    if scale_impact.get("value_primary", {}).get("status") in {"needs_revision", "stop_using"}:
        risks.append("Value primary also fails scale-stress deployability at the tested AUM floor, so additive eligibility must remain blocked until tradability improves.")
    return risks


def build_what_changed(candidate_states: list[dict], working_config_recommendation: dict | None = None) -> list[str]:
    value_primary = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["value_primary"])
    value_reference = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["value_baseline_reference"])
    growth = next(x for x in candidate_states if x["strategy_id"] == TRACKED_CANDIDATES["growth_primary"])
    items = [
        f"Growth core latest state: {growth.get('status')} / {growth.get('recent_review_trend')}.",
        f"Value primary latest state: {value_primary.get('status')} / {value_primary.get('recent_review_trend')} under registry params top_n={value_primary.get('operating_params', {}).get('top_n')}.",
        f"Legacy value baseline remains {value_reference.get('status')} and should stay reference-oriented rather than becoming the main line.",
    ]
    scale_impact = (working_config_recommendation or {}).get("scale_stress_impact") or {}
    if scale_impact.get("growth", {}).get("status"):
        items.append(f"Capital-scale executable-alpha stress impact on growth: {scale_impact['growth'].get('status')} (first extreme bucket at {scale_impact['growth'].get('first_extreme_aum')}).")
    if scale_impact.get("value_primary", {}).get("status"):
        items.append(f"Capital-scale executable-alpha stress impact on value primary: {scale_impact['value_primary'].get('status')} (first extreme bucket at {scale_impact['value_primary'].get('first_extreme_aum')}).")
    return items


def classify_review_signal(candidate_state: dict) -> str:
    status = candidate_state.get("status")
    latest = candidate_state.get("latest_review", {})
    trend = candidate_state.get("recent_review_trend")
    review_result = latest.get("review_result")
    if status == "active" and review_result == "keep" and trend == "stable_keep":
        return "pass"
    if status == "watch" or trend in {"recent_weakening", "persistent_watch"} or review_result == "watch":
        return "warn"
    return "fail"


def classify_realism_signal(candidate_state: dict) -> str:
    realism = candidate_state.get("realism_flags", {})
    statuses = {
        "cost": realism.get("cost_sensitivity", {}).get("status", "unknown"),
        "liquidity": realism.get("liquidity_risk", {}).get("status", "unknown"),
        "concentration": realism.get("concentration_risk", {}).get("status", "unknown"),
        "execution": realism.get("execution_realism", {}).get("status", "unknown"),
        "impact": realism.get("impact_realism", {}).get("status", "unknown"),
    }
    if statuses["cost"] == "elevated" or statuses["liquidity"] == "elevated" or statuses["execution"] == "elevated" or statuses["impact"] == "elevated":
        return "fail"
    if "warning" in statuses.values() or "unknown" in statuses.values():
        return "warn"
    return "pass"


def load_capacity_map(reports_dir: Path) -> tuple[dict[str, dict], Path | None]:
    try:
        path = latest_matching_file("research_capacity_constraints_*.json", reports_dir)
    except FileNotFoundError:
        return {}, None
    payload = load_json(path)
    out: dict[str, dict] = {}
    for item in payload.get("candidate_capacity", []):
        if item.get("capital_label") != "model_micro":
            continue
        strategy_id = item.get("strategy_id")
        if strategy_id:
            out[strategy_id] = item
    return out, path


def load_scale_stress_map(reports_dir: Path) -> tuple[dict[str, Any], Path | None]:
    try:
        path = latest_matching_file("strategy_scale_stress_summary_*.json", reports_dir)
    except FileNotFoundError:
        return {}, None
    payload = load_json(path)
    by_strategy: dict[str, Any] = {}
    for item in payload.get("candidate_scale_stress", []):
        cases_by_capital = {str(case.get("capital_label")): case for case in item.get("stress_cases", []) if case.get("capital_label")}
        deployability = item.get("deployability")
        if not deployability:
            thresholds = item.get("bucket_entry_thresholds", {}) or {}
            deployability = {
                "deployable_aum_floor": None,
                "first_light_aum": thresholds.get("light"),
                "first_medium_aum": thresholds.get("medium"),
                "first_heavy_aum": thresholds.get("heavy"),
                "first_extreme_aum": thresholds.get("extreme"),
                "recommended_max_aum": None,
                "deployment_blocked": True,
                "blocking_reasons": [],
            }
        by_strategy[str(item.get("strategy_id"))] = {
            "stress_cases_by_capital": cases_by_capital,
            "bucket_entry_thresholds": item.get("bucket_entry_thresholds", {}) or {},
            "deployability": deployability,
        }
    return by_strategy, path


def classify_capacity_signal(strategy_id: str, capacity_map: dict[str, dict]) -> str:
    item = capacity_map.get(strategy_id)
    if not item:
        return "warn"
    lc = item.get("liquidity_capacity", {})
    status = lc.get("status")
    breach = bool(lc.get("constraint_breach"))
    if status == "elevated" or breach:
        return "fail"
    if status == "warning" or status == "unknown":
        return "warn"
    return "pass"


def classify_scale_stress_signal(strategy_id: str, scale_stress_map: dict[str, Any]) -> str:
    strategy_block = scale_stress_map.get(strategy_id, {})
    cases = strategy_block.get("stress_cases_by_capital", {})
    item = cases.get("model_micro") or cases.get("model_small")
    if not item:
        return "warn"
    status = ((item.get("working_config_recommendation_impact") or {}).get("status") or "keep").strip()
    if status == "stop_using":
        return "fail"
    if status in {"needs_revision", "keep_with_caution"}:
        return "warn"
    return "pass"


def build_scale_stress_impact(strategy_id: str, scale_stress_map: dict[str, Any]) -> dict | None:
    strategy_block = scale_stress_map.get(strategy_id, {})
    cases = strategy_block.get("stress_cases_by_capital", {})
    item = cases.get("model_micro") or cases.get("model_small")
    if not item:
        return None
    recommendation = item.get("working_config_recommendation_impact", {})
    thresholds = strategy_block.get("bucket_entry_thresholds", {}) or {}
    erosion = item.get("executable_alpha_erosion", {}) or {}
    diagnostics = ((item.get("dynamic_impact_v1") or {}).get("execution_diagnostics") or {})
    deployability = strategy_block.get("deployability", {}) or {}
    return {
        "status": recommendation.get("status"),
        "reason": recommendation.get("reason"),
        "capital_label": item.get("capital_label"),
        "aum": item.get("aum"),
        "annual_return_erosion_rate": erosion.get("annual_return_erosion_rate"),
        "sharpe_erosion_rate": erosion.get("sharpe_erosion_rate"),
        "impact_cost_paid": erosion.get("impact_cost_paid"),
        "bucket_counts": diagnostics.get("bucket_counts"),
        "first_light_aum": thresholds.get("light"),
        "first_medium_aum": thresholds.get("medium"),
        "first_heavy_aum": thresholds.get("heavy"),
        "first_extreme_aum": thresholds.get("extreme"),
        "deployable_aum_floor": deployability.get("deployable_aum_floor"),
        "recommended_max_aum": deployability.get("recommended_max_aum"),
        "deployment_blocked": deployability.get("deployment_blocked"),
    }


def build_promotion_blockers(candidate_state: dict, realism_signal: str, capacity_signal: str, scale_stress_signal: str = "pass", scale_stress_impact: dict | None = None) -> list[str]:
    blockers: list[str] = []
    latest = candidate_state.get("latest_review", {})
    trend = candidate_state.get("recent_review_trend")
    if latest.get("review_result") == "watch":
        blockers.append("latest review_result=watch")
    if trend in {"recent_weakening", "persistent_watch"}:
        blockers.append(f"recent_review_trend={trend}")
    realism = candidate_state.get("realism_flags", {})
    if realism.get("cost_sensitivity", {}).get("status") == "elevated":
        blockers.append("cost_sensitivity=elevated")
    if realism.get("liquidity_risk", {}).get("status") == "elevated":
        blockers.append("liquidity_risk=elevated")
    if realism.get("impact_realism", {}).get("status") == "elevated":
        blockers.append("impact_realism=elevated")
    if realism_signal == "fail":
        blockers.append("realism gating failed")
    if capacity_signal == "fail":
        blockers.append("capacity constraint breach present")
    if scale_stress_signal == "fail":
        blockers.append("scale stress gating failed")
    if scale_stress_impact and scale_stress_impact.get("first_extreme_aum"):
        blockers.append(f"scale_stress_extreme_at={scale_stress_impact.get('first_extreme_aum')}")
    return blockers


def build_demotion_triggers(candidate_state: dict, scale_stress_impact: dict | None = None) -> list[str]:
    triggers = [
        "latest review_result becomes watch",
        "recent_review_trend leaves stable_keep",
        "cost_sensitivity turns elevated",
        "capacity status turns elevated",
        "working config alignment becomes needs_review",
    ]
    if scale_stress_impact and scale_stress_impact.get("first_extreme_aum"):
        triggers.append(f"capital-scale stress enters extreme at {scale_stress_impact.get('first_extreme_aum')}")
    return triggers


def build_gating_decision(candidate_states: list[dict], capacity_map: dict[str, dict], scale_stress_map: dict[str, Any] | None = None) -> tuple[dict, dict, dict, dict]:
    scale_stress_map = scale_stress_map or {}
    by_id = {x["strategy_id"]: x for x in candidate_states}
    growth = by_id[TRACKED_CANDIDATES["growth_primary"]]
    value = by_id[TRACKED_CANDIDATES["value_primary"]]
    value_baseline = by_id[TRACKED_CANDIDATES["value_baseline_reference"]]

    growth_review = classify_review_signal(growth)
    value_review = classify_review_signal(value)
    baseline_review = classify_review_signal(value_baseline)
    growth_realism = classify_realism_signal(growth)
    value_realism = classify_realism_signal(value)
    baseline_realism = classify_realism_signal(value_baseline)
    growth_capacity = classify_capacity_signal(growth["strategy_id"], capacity_map)
    value_capacity = classify_capacity_signal(value["strategy_id"], capacity_map)
    baseline_capacity = classify_capacity_signal(value_baseline["strategy_id"], capacity_map)
    growth_scale_stress = classify_scale_stress_signal(growth["strategy_id"], scale_stress_map)
    value_scale_stress = classify_scale_stress_signal(value["strategy_id"], scale_stress_map)
    baseline_scale_stress = classify_scale_stress_signal(value_baseline["strategy_id"], scale_stress_map)
    growth_scale_stress_impact = build_scale_stress_impact(growth["strategy_id"], scale_stress_map)
    value_scale_stress_impact = build_scale_stress_impact(value["strategy_id"], scale_stress_map)
    baseline_scale_stress_impact = build_scale_stress_impact(value_baseline["strategy_id"], scale_stress_map)

    if growth_review == "fail":
        wc_status = "stop_using"
        wc_reason = "growth review itself has failed, so the current working config can no longer stay active"
    elif growth_scale_stress == "fail":
        wc_status = "stop_using"
        wc_reason = "capital-scale executable-alpha stress now shows that growth is not deployable at the tested AUM floor"
    elif growth_review == "warn":
        wc_status = "needs_revision"
        wc_reason = "growth forward evidence has weakened enough that the working config now needs revision"
    elif growth_scale_stress == "warn":
        wc_status = "needs_revision"
        wc_reason = "capital-scale executable-alpha stress now requires a revised working config before production-scale use"
    elif growth_realism == "fail" or growth_capacity == "fail":
        wc_status = "keep_with_caution"
        wc_reason = "growth still leads on review evidence, but realism/capacity blockers now force a cautious operating stance rather than normal keep"
    elif growth_realism == "warn" or growth_capacity == "warn" or value_review != "pass":
        wc_status = "keep_with_caution"
        wc_reason = "growth remains usable, but realism/capacity friction and weak additive lines require caution"
    else:
        wc_status = "keep"
        wc_reason = "growth line remains stable and no realism/capacity blocker currently invalidates the working config"

    def eligibility(strategy_id: str, review: str, realism: str, capacity: str, scale_stress: str = "pass") -> str:
        if review == "fail":
            return "ineligible"
        if scale_stress == "fail":
            return "ineligible"
        if strategy_id == TRACKED_CANDIDATES["growth_primary"]:
            if review == "pass" and realism == "pass" and capacity == "pass" and scale_stress == "pass":
                return "eligible"
            if review == "pass":
                return "conditional"
            return "ineligible"
        if review == "pass" and realism == "pass" and capacity == "pass" and scale_stress == "pass":
            return "eligible"
        if review == "pass" and realism != "fail" and capacity != "fail" and scale_stress != "fail":
            return "conditional"
        return "ineligible"

    additive_eligibility = {
        growth["strategy_id"]: eligibility(growth["strategy_id"], growth_review, growth_realism, growth_capacity, growth_scale_stress),
        value["strategy_id"]: eligibility(value["strategy_id"], value_review, value_realism, value_capacity, value_scale_stress),
        value_baseline["strategy_id"]: eligibility(value_baseline["strategy_id"], baseline_review, baseline_realism, baseline_capacity, baseline_scale_stress),
    }
    promotion_blockers = {
        value["strategy_id"]: build_promotion_blockers(value, value_realism, value_capacity, value_scale_stress, value_scale_stress_impact),
        value_baseline["strategy_id"]: build_promotion_blockers(value_baseline, baseline_realism, baseline_capacity, baseline_scale_stress, baseline_scale_stress_impact),
    }
    demotion_triggers = {
        growth["strategy_id"]: build_demotion_triggers(growth, growth_scale_stress_impact),
        value["strategy_id"]: build_demotion_triggers(value, value_scale_stress_impact),
    }
    working_config_recommendation = {
        "status": wc_status,
        "reason": wc_reason,
        "decision_inputs": {
            "growth_review": growth_review,
            "value_review": value_review,
            "growth_realism": growth_realism,
            "value_realism": value_realism,
            "growth_capacity": growth_capacity,
            "value_capacity": value_capacity,
            "growth_scale_stress": growth_scale_stress,
            "value_scale_stress": value_scale_stress,
            "value_baseline_scale_stress": baseline_scale_stress,
        },
        "scale_stress_impact": {
            "growth": growth_scale_stress_impact or {},
            "value_primary": value_scale_stress_impact or {},
            "value_baseline_reference": baseline_scale_stress_impact or {},
        },
    }
    return working_config_recommendation, additive_eligibility, promotion_blockers, demotion_triggers


def build_deployability_summary(scale_stress_map: dict[str, Any], reports_dir: Path = REPORTS_DIR) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for strategy_id, strategy_block in scale_stress_map.items():
        deployability = strategy_block.get("deployability", {}) or {}
        if not deployability:
            continue
        if strategy_id == TRACKED_CANDIDATES["growth_primary"]:
            key = "growth"
        elif strategy_id == TRACKED_CANDIDATES["value_primary"]:
            key = "value_primary"
        elif strategy_id == TRACKED_CANDIDATES["value_baseline_reference"]:
            key = "value_baseline_reference"
        else:
            key = str(strategy_id)
        out[key] = dict(deployability)
    return out


def render_markdown(summary: dict) -> str:
    lines: list[str] = []
    lines.append("# Research Decision Summary")
    lines.append("")
    lines.append(f"- Generated at: {summary['generated_at']}")
    lines.append(f"- As of date: {summary['as_of_date']}")
    lines.append("")
    lines.append("## Executive summary")
    exec_summary = summary["executive_summary"]
    lines.append(f"- Primary takeaway: {exec_summary['primary_takeaway']}")
    lines.append(f"- Recommended posture: {exec_summary['recommended_posture']}")
    lines.append(f"- Allocator priority: {exec_summary['allocator_priority']}")
    lines.append(f"- Confidence: {exec_summary['confidence']}")
    lines.append(f"- Real return priority: {exec_summary['real_return_priority']}")
    lines.append(f"- Single-line dependency risk: {exec_summary['single_line_dependency_risk']}")
    lines.append(f"- Working config recommendation: {exec_summary['working_config_recommendation']}")
    lines.append("")
    lines.append("## What changed since last summary")
    for item in summary["what_changed_since_last_summary"]:
        lines.append(f"- {item}")
    lines.append("")
    if summary.get("working_configuration"):
        wc = summary["working_configuration"]
        lines.append("## Current working configuration")
        lines.append(f"- Universe policy: {wc['universe_policy']}")
        lines.append(f"- Weighting policy: {wc['weighting_policy']}")
        lines.append(f"- Growth core: {wc['growth_core']}")
        lines.append(f"- Value primary: {wc['value_primary']} ({wc['value_status']})")
        lines.append(f"- Observed value status: {wc['observed_value_status']}")
        lines.append(f"- Config alignment: {wc['config_alignment']}")
        lines.append(f"- Operating mode: {wc['operating_mode']}")
        lines.append(f"- Mainline thesis: {wc['mainline_thesis']}")
        lines.append(f"- Keep rule status: {wc['keep_rule_status']}")
        lines.append(f"- Decision basis: {wc['decision_basis']}")
        lines.append(f"- Realism basis: {wc['realism_basis']}")
        lines.append(f"- Capacity basis: {wc['capacity_basis']}")
        lines.append(f"- Scale-stress basis: {wc.get('scale_stress_basis')}")
        lines.append(f"- Additive eligibility: {wc['additive_eligibility']}")
        lines.append(f"- Promotion blockers: {', '.join(wc['promotion_blockers']) if wc['promotion_blockers'] else 'none'}")
        lines.append(f"- Demotion triggers: {', '.join(wc['demotion_triggers']) if wc['demotion_triggers'] else 'none'}")
        lines.append(f"- Working config review: {wc['working_config_review']['status']} — {wc['working_config_review']['reason']}")
        lines.append("")
    if summary.get("working_config_recommendation", {}).get("scale_stress_impact"):
        ssi = summary["working_config_recommendation"]["scale_stress_impact"]
        lines.append("## Capital-scale executable-alpha stress impact")
        for label, item in [("growth", ssi.get("growth")), ("value_primary", ssi.get("value_primary")), ("value_baseline_reference", ssi.get("value_baseline_reference"))]:
            if not item:
                continue
            lines.append(f"### {label}")
            lines.append(f"- Status: {item.get('status')}")
            lines.append(f"- Reason: {item.get('reason')}")
            lines.append(f"- Capital label: {item.get('capital_label')} (aum={item.get('aum')})")
            lines.append(f"- Annual return erosion rate: {item.get('annual_return_erosion_rate')}")
            lines.append(f"- Sharpe erosion rate: {item.get('sharpe_erosion_rate')}")
            lines.append(f"- Impact cost paid: {item.get('impact_cost_paid')}")
            lines.append(f"- Bucket counts: {item.get('bucket_counts')}")
            lines.append(f"- First light AUM: {item.get('first_light_aum')}")
            lines.append(f"- First medium AUM: {item.get('first_medium_aum')}")
            lines.append(f"- First heavy AUM: {item.get('first_heavy_aum')}")
            lines.append(f"- First extreme AUM: {item.get('first_extreme_aum')}")
            lines.append(f"- Deployable AUM floor: {item.get('deployable_aum_floor')}")
            lines.append(f"- Recommended max AUM: {item.get('recommended_max_aum')}")
            lines.append(f"- Deployment blocked: {item.get('deployment_blocked')}")
            lines.append("")
    if summary.get("deployability"):
        lines.append("## Deployability summary")
        for label, item in summary["deployability"].items():
            lines.append(f"### {label}")
            lines.append(f"- deployable_aum_floor: {item.get('deployable_aum_floor')}")
            lines.append(f"- first_light_aum: {item.get('first_light_aum')}")
            lines.append(f"- first_medium_aum: {item.get('first_medium_aum')}")
            lines.append(f"- first_heavy_aum: {item.get('first_heavy_aum')}")
            lines.append(f"- first_extreme_aum: {item.get('first_extreme_aum')}")
            lines.append(f"- recommended_max_aum: {item.get('recommended_max_aum')}")
            lines.append(f"- deployment_blocked: {item.get('deployment_blocked')}")
            lines.append(f"- blocking_reasons: {item.get('blocking_reasons')}")
            lines.append("")
    lines.append("## Candidate state table")
    lines.append("| line | strategy | role | status | latest review | trend | suggested action |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in summary["candidate_states"]:
        latest = item.get("latest_review", {})
        latest_text = f"{latest.get('window_label')} / {latest.get('review_result')}"
        lines.append(
            f"| {item['line']} | {item['strategy_id']} | {item['role']} | {item['status']} | {latest_text} | {item.get('recent_review_trend')} | {item.get('suggested_action')} |"
        )
    lines.append("")
    lines.append("## Evidence snapshot")
    for item in summary["candidate_states"]:
        lines.append(f"### {item['strategy_id']}")
        for key, value in item["metrics_snapshot"].items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    lines.append("## Realism flags")
    lines.append("| strategy | liquidity | cost sensitivity | concentration | execution realism | impact realism |")
    lines.append("|---|---|---|---|---|---|")
    for item in summary["candidate_states"]:
        rf = item["realism_flags"]
        lines.append(
            f"| {item['strategy_id']} | {rf['liquidity_risk']['status']} | {rf['cost_sensitivity']['status']} | {rf['concentration_risk']['status']} | {rf['execution_realism']['status']} | {rf['impact_realism']['status']} |"
        )
    lines.append("")
    lines.append("## Suggested research actions")
    for idx, action in enumerate(summary["decision_actions"]["research_actions"], start=1):
        lines.append(f"{idx}. {action}")
    lines.append("")
    lines.append("## Suggested portfolio actions")
    for idx, action in enumerate(summary["decision_actions"]["portfolio_actions"], start=1):
        lines.append(f"{idx}. {action}")
    lines.append("")
    lines.append("## Open risks")
    for risk in summary["open_risks"]:
        lines.append(f"- {risk}")
    lines.append("")
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, markdown_path: Path) -> None:
    latest_json = REPORTS_DIR / "research_decision_summary_latest.json"
    latest_md = REPORTS_DIR / "research_decision_summary_latest.md"
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")


def load_working_config(reports_dir: Path) -> tuple[dict | None, Path | None]:
    path = reports_dir / "current_working_strategy_config.json"
    if not path.exists():
        return None, None
    return load_json(path), path


def build_working_configuration(candidate_states: list[dict], reports_dir: Path, scale_stress_map: dict[str, Any] | None = None) -> tuple[dict | None, Path | None]:
    scale_stress_map = scale_stress_map or {}
    config, path = load_working_config(reports_dir)
    if not config:
        return None, None
    growth = next(x for x in candidate_states if x["strategy_id"] == config.get("growth_core"))
    value = next(x for x in candidate_states if x["strategy_id"] == config.get("value_primary"))
    value_configured_status = config.get("value_status")
    value_observed_status = value.get("status")
    status = "keep" if growth.get("status") == "active" and value_observed_status in {"active", "watch"} else "needs_review"
    config_alignment = "aligned"
    if value_configured_status != value_observed_status:
        config_alignment = "drifted"
        status = "needs_review"
    reason = (
        "growth remains stable and no tested alternative has superseded the current working configuration"
        if status == "keep"
        else "candidate state drift suggests the current working configuration should be reviewed"
    )
    growth_scale_stress_impact = build_scale_stress_impact(str(config.get("growth_core")), scale_stress_map)
    value_scale_stress_impact = build_scale_stress_impact(str(config.get("value_primary")), scale_stress_map)
    if growth_scale_stress_impact and growth_scale_stress_impact.get("status") in {"needs_revision", "stop_using"}:
        status = str(growth_scale_stress_impact.get("status"))
        reason = str(growth_scale_stress_impact.get("reason"))
    value_additive_eligibility = "eligible" if value.get("status") == "active" else "blocked"
    promotion_blockers = []
    if value.get("status") != "active":
        promotion_blockers.append("value_primary_not_active")
    if value.get("realism_flags", {}).get("cost_sensitivity", {}).get("status") in {"warning", "elevated"}:
        promotion_blockers.append("value_cost_sensitivity_not_clean")
    if value.get("realism_flags", {}).get("liquidity_risk", {}).get("status") in {"warning", "elevated", "unknown"}:
        promotion_blockers.append("value_liquidity_not_cleared")
    if value_scale_stress_impact and value_scale_stress_impact.get("status") in {"needs_revision", "stop_using"}:
        promotion_blockers.append(f"value_scale_stress_{value_scale_stress_impact.get('status')}")
    demotion_triggers = []
    if growth.get("status") != "active":
        demotion_triggers.append("growth_not_active")
    if growth.get("realism_flags", {}).get("cost_sensitivity", {}).get("status") in {"warning", "elevated"}:
        demotion_triggers.append("growth_cost_sensitivity_deteriorated")
    if growth_scale_stress_impact and growth_scale_stress_impact.get("first_extreme_aum"):
        demotion_triggers.append(f"growth_scale_stress_extreme_at_{growth_scale_stress_impact.get('first_extreme_aum')}")
    return {
        "universe_policy": config.get("working_universe_policy"),
        "weighting_policy": config.get("weighting_policy"),
        "growth_core": config.get("growth_core"),
        "value_primary": config.get("value_primary"),
        "value_status": config.get("value_status"),
        "observed_value_status": value_observed_status,
        "operating_mode": config.get("operating_mode"),
        "mainline_thesis": config.get("mainline_thesis"),
        "keep_rule_status": config.get("keep_rule_status", status),
        "decision_basis": config.get("decision_basis"),
        "realism_basis": config.get("realism_basis"),
        "capacity_basis": config.get("capacity_basis"),
        "scale_stress_basis": config.get("scale_stress_basis", "data/reports/strategy_scale_stress_summary_latest.json"),
        "promotion_ruleset_version": config.get("promotion_ruleset_version"),
        "demotion_ruleset_version": config.get("demotion_ruleset_version"),
        "config_alignment": config_alignment,
        "working_config_review": {"status": status, "reason": reason},
        "mainline_role": "growth_core",
        "true_return_thesis": config.get("mainline_thesis"),
        "additive_eligibility": value_additive_eligibility,
        "promotion_blockers": promotion_blockers,
        "demotion_triggers": demotion_triggers,
    }, path


def build_summary(reports_dir: Path = REPORTS_DIR) -> dict:
    growth_registry_path = reports_dir / "revgrowth_candidate_registry.json"
    growth_reviews_path = reports_dir / "revgrowth_candidate_reviews.json"
    value_registry_path = reports_dir / "pbindlow_candidate_registry.json"
    value_reviews_path = reports_dir / "pbindlow_candidate_reviews.json"

    growth_status_path = latest_matching_file("revgrowth_candidate_pool_status_*.json", reports_dir)
    value_status_path = latest_matching_file("pbindlow_candidate_pool_status_*.json", reports_dir)
    overview_path = latest_matching_file("strategy_candidate_pool_overview_*.json", reports_dir)

    growth_registry = load_json(growth_registry_path)
    growth_reviews = load_json(growth_reviews_path)
    value_registry = load_json(value_registry_path)
    value_reviews = load_json(value_reviews_path)
    growth_status = load_json(growth_status_path)
    value_status = load_json(value_status_path)

    realism_by_strategy: dict[str, dict] = {}
    realism_report_path: Path | None = None
    try:
        realism_report_path = latest_matching_file("research_realism_stress_*.json", reports_dir)
        realism_report = load_json(realism_report_path)
        realism_by_strategy = {
            item.get("strategy_id"): item
            for item in realism_report.get("candidate_realism", [])
            if item.get("strategy_id")
        }
    except FileNotFoundError:
        realism_report_path = None

    capacity_map, capacity_report_path = load_capacity_map(reports_dir)
    scale_stress_map, scale_stress_report_path = load_scale_stress_map(reports_dir)

    candidate_states: list[dict] = []
    selection_trace: dict[str, dict] = {}

    mappings = [
        ("growth_line", TRACKED_CANDIDATES["growth_primary"], growth_registry, growth_reviews, growth_status),
        ("valuation_line", TRACKED_CANDIDATES["value_primary"], value_registry, value_reviews, value_status),
        ("valuation_line", TRACKED_CANDIDATES["value_baseline_reference"], value_registry, value_reviews, value_status),
    ]
    for line, strategy_id, registry, reviews, status in mappings:
        state, trace = build_candidate_state(
            line=line,
            strategy_id=strategy_id,
            registry=registry,
            reviews=reviews,
            status_payload=status,
            realism_by_strategy=realism_by_strategy,
        )
        candidate_states.append(state)
        selection_trace[strategy_id] = trace

    working_configuration, working_config_path = build_working_configuration(candidate_states, reports_dir, scale_stress_map)
    working_config_recommendation, additive_eligibility, promotion_blockers, demotion_triggers = build_gating_decision(candidate_states, capacity_map, scale_stress_map)

    as_of_date = max(
        x["latest_review"]["window_label"] and x["evidence_summary"]["latest_end_date"] or ""
        for x in candidate_states
    )
    summary = {
        "report_type": "research_decision_summary",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "as_of_date": as_of_date,
        "tracked_candidates": dict(TRACKED_CANDIDATES),
        "deployability": build_deployability_summary(scale_stress_map, reports_dir),
        "working_configuration": working_configuration,
        "working_config_recommendation": working_config_recommendation,
        "additive_eligibility": additive_eligibility,
        "promotion_blockers": promotion_blockers,
        "demotion_triggers": demotion_triggers,
        "executive_summary": build_executive_summary(candidate_states, working_configuration, working_config_recommendation, additive_eligibility),
        "what_changed_since_last_summary": build_what_changed(candidate_states, working_config_recommendation),
        "candidate_states": candidate_states,
        "line_view": build_line_view(candidate_states),
        "decision_actions": build_decision_actions(candidate_states, working_config_recommendation, additive_eligibility, promotion_blockers),
        "open_risks": build_open_risks(candidate_states, working_config_recommendation),
        "source_artifacts": {
            "growth_status": str(growth_status_path),
            "value_status": str(value_status_path),
            "overview": str(overview_path),
            "growth_reviews": str(growth_reviews_path),
            "value_reviews": str(value_reviews_path),
            "realism_report": str(realism_report_path) if realism_report_path else None,
            "capacity_report": str(capacity_report_path) if capacity_report_path else None,
            "scale_stress_report": str(scale_stress_report_path) if scale_stress_report_path else None,
            "working_config": str(working_config_path) if working_config_path else None,
            "selection_trace": selection_trace,
        },
    }
    return summary


def main() -> tuple[Path, Path]:
    summary = build_summary(REPORTS_DIR)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"research_decision_summary_{timestamp}.json"
    md_path = REPORTS_DIR / f"research_decision_summary_{timestamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
