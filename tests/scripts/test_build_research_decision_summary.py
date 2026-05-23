from __future__ import annotations

import json
from pathlib import Path

from scripts.build_research_decision_summary import (
    build_summary,
    default_realism_flags,
    render_markdown,
    select_latest_review,
)


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_fixture_reports(tmp_path: Path) -> Path:
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    growth_registry = [
        {
            "strategy_id": "revgrowth_always_on_v1",
            "factor": "revenue_growth_raw",
            "filter": {},
            "role": "primary_candidate",
            "status": "active",
            "params": {"top_n": 10, "rebalance_frequency": "W", "horizon": 10, "weighting": "equal", "benchmark": "equal_weight_universe"},
        },
        {
            "strategy_id": "revgrowth_uptrend_lowvol_v1",
            "factor": "revenue_growth_raw",
            "filter": {"regime_trend_60d": "uptrend", "regime_vol_20d": "low_vol"},
            "role": "enhanced_candidate",
            "status": "active",
            "params": {"top_n": 10},
        },
    ]
    value_registry = [
        {
            "strategy_id": "pbindlow_downtrend_only_v1",
            "factor": "pb_industry_lowpb_score",
            "filter": {"trend_20d": "downtrend"},
            "role": "enhanced_candidate",
            "status": "watch",
            "params": {"top_n": 10, "rebalance_frequency": "W", "horizon": 10, "weighting": "equal", "benchmark": "equal_weight_universe"},
        },
        {
            "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
            "factor": "pb_industry_lowpb_score",
            "filter": {"trend_20d": "downtrend", "breadth_regime": "narrow_weakness", "quality_refined": "true"},
            "role": "primary_candidate",
            "status": "active",
            "params": {"top_n": 20, "rebalance_frequency": "W", "horizon": 10, "weighting": "equal", "benchmark": "equal_weight_universe"},
        },
    ]

    growth_reviews = [
        {
            "review_id": "review_growth_2025H2",
            "strategy_id": "revgrowth_always_on_v1",
            "window_label": "2025H2",
            "start_date": "20250701",
            "end_date": "20251231",
            "review_result": "keep",
            "comment": "review window still acceptable",
            "metrics": {
                "annual_return": 0.8,
                "sharpe": 1.9,
                "max_drawdown": 0.2,
                "top_bottom_spread": 0.03,
                "active_ratio": 1.0,
                "rank_ic_mean": 0.05,
                "positive_ic_ratio": 0.6,
                "monotonicity_score": 0.75,
            },
        },
        {
            "review_id": "review_growth_2025H1",
            "strategy_id": "revgrowth_always_on_v1",
            "window_label": "2025H1",
            "start_date": "20250101",
            "end_date": "20250630",
            "review_result": "keep",
            "comment": "older review",
            "metrics": {
                "annual_return": 0.7,
                "sharpe": 1.7,
                "max_drawdown": 0.25,
                "top_bottom_spread": 0.02,
                "active_ratio": 1.0,
                "rank_ic_mean": 0.04,
                "positive_ic_ratio": 0.58,
                "monotonicity_score": 0.5,
            },
        },
    ]
    value_reviews = [
        {
            "review_id": "review_quality_2025H2",
            "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
            "window_label": "2025H2",
            "start_date": "20250701",
            "end_date": "20251231",
            "review_result": "keep",
            "comment": "review window still acceptable",
            "metrics": {
                "annual_return": 1.0,
                "sharpe": 2.1,
                "max_drawdown": 0.17,
                "top_bottom_spread": 0.01,
                "active_ratio": 0.36,
                "rank_ic_mean": 0.02,
                "positive_ic_ratio": 0.81,
                "monotonicity_score": 0.75,
            },
        },
        {
            "review_id": "review_quality_2025H1",
            "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
            "window_label": "2025H1",
            "start_date": "20250101",
            "end_date": "20250630",
            "review_result": "keep",
            "comment": "older review",
            "metrics": {
                "annual_return": 0.9,
                "sharpe": 1.8,
                "max_drawdown": 0.2,
                "top_bottom_spread": 0.02,
                "active_ratio": 0.35,
                "rank_ic_mean": 0.01,
                "positive_ic_ratio": 0.75,
                "monotonicity_score": 0.5,
            },
        },
        {
            "review_id": "review_baseline_2025H2",
            "strategy_id": "pbindlow_downtrend_only_v1",
            "window_label": "2025H2",
            "start_date": "20250701",
            "end_date": "20251231",
            "review_result": "watch",
            "comment": "negative return",
            "metrics": {
                "annual_return": -0.2,
                "sharpe": -0.7,
                "max_drawdown": 0.18,
                "top_bottom_spread": -0.01,
                "active_ratio": 0.4,
                "rank_ic_mean": 0.01,
                "positive_ic_ratio": 0.45,
                "monotonicity_score": 0.25,
            },
        },
    ]

    growth_status = {
        "pool_state": {"primary_candidate": "revgrowth_always_on_v1", "enhanced_candidate": "revgrowth_uptrend_lowvol_v1", "active_count": 2, "watch_count": 0},
        "strategies": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "status": "active",
                "recent_review_trend": "stable_keep",
                "suggested_action": "continue_tracking",
            }
        ],
    }
    value_status = {
        "pool_state": {"primary_candidate": "pbindlow_downtrend_narrow_quality_v1", "enhanced_candidate": "pbindlow_downtrend_only_v1", "active_count": 1, "watch_count": 1},
        "strategies": [
            {
                "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
                "status": "active",
                "recent_review_trend": "stable_keep",
                "suggested_action": "continue_tracking",
            },
            {
                "strategy_id": "pbindlow_downtrend_only_v1",
                "status": "watch",
                "recent_review_trend": "persistent_watch",
                "suggested_action": "reference_only",
            },
        ],
    }
    overview = {"report_type": "strategy_candidate_pool_overview"}
    realism_report = {
        "report_type": "research_realism_stress",
        "candidate_realism": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "cost_sensitivity": {"status": "acceptable", "note": "growth ok"},
                "concentration_risk": {"status": "acceptable", "note": "growth conc ok"},
                "liquidity_risk": {"status": "unknown", "note": "growth liquidity pending"},
                "execution_realism": {"status": "acceptable", "note": "growth exec ok"},
                "impact_realism": {"status": "warning", "note": "growth impact caution"},
            },
            {
                "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
                "cost_sensitivity": {"status": "elevated", "note": "value cost weak"},
                "concentration_risk": {"status": "acceptable", "note": "value conc ok"},
                "liquidity_risk": {"status": "unknown", "note": "value liquidity pending"},
                "execution_realism": {"status": "acceptable", "note": "value exec ok"},
                "impact_realism": {"status": "elevated", "note": "value impact bad"},
            },
            {
                "strategy_id": "pbindlow_downtrend_only_v1",
                "cost_sensitivity": {"status": "elevated", "note": "baseline weak"},
                "concentration_risk": {"status": "acceptable", "note": "baseline conc ok"},
                "liquidity_risk": {"status": "unknown", "note": "baseline liquidity pending"},
                "execution_realism": {"status": "acceptable", "note": "baseline exec ok"},
                "impact_realism": {"status": "warning", "note": "baseline impact caution"},
            },
        ],
    }

    write_json(reports / "revgrowth_candidate_registry.json", growth_registry)
    write_json(reports / "revgrowth_candidate_reviews.json", growth_reviews)
    write_json(reports / "revgrowth_candidate_pool_status_20260517.json", growth_status)
    write_json(reports / "pbindlow_candidate_registry.json", value_registry)
    write_json(reports / "pbindlow_candidate_reviews.json", value_reviews)
    write_json(reports / "pbindlow_candidate_pool_status_20260517.json", value_status)
    write_json(reports / "strategy_candidate_pool_overview_20260517.json", overview)
    write_json(reports / "research_realism_stress_20260518T000000Z.json", realism_report)
    write_json(reports / "current_working_strategy_config.json", {
        "as_of": "2026-05-18",
        "working_universe_policy": "amount_bottom_30pct",
        "weighting_policy": "equal_weight",
        "growth_core": "revgrowth_always_on_v1",
        "value_primary": "pbindlow_downtrend_narrow_quality_v1",
        "value_status": "watch",
        "operating_mode": "growth_mainline_with_value_watch",
        "mainline_thesis": "growth remains the execution anchor while value stays optional until it proves additive under realism and capacity constraints",
        "keep_rule_status": "keep",
        "decision_basis": "data/reports/research_decision_summary_latest.json",
        "realism_basis": "data/reports/research_realism_stress_latest.json",
        "capacity_basis": "data/reports/research_capacity_constraints_latest.json",
        "promotion_ruleset_version": "p0",
        "demotion_ruleset_version": "p0",
        "notes": ["tail30 + equal-weight is the current working configuration"]
    })
    return reports


def test_default_realism_flags_shape():
    flags = default_realism_flags()
    assert flags["liquidity_risk"] == {"status": "unknown", "note": ""}
    assert flags["execution_realism"]["status"] == "unknown"


def test_select_latest_review_prefers_latest_end_date():
    reviews = [
        {"strategy_id": "s1", "review_id": "old", "start_date": "20240101", "end_date": "20240630"},
        {"strategy_id": "s1", "review_id": "new", "start_date": "20240701", "end_date": "20241231"},
    ]
    latest = select_latest_review(reviews, "s1")
    assert latest["review_id"] == "new"


def test_build_summary_contains_expected_top_level_keys(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    assert summary["report_type"] == "research_decision_summary"
    assert "candidate_states" in summary
    assert "decision_actions" in summary
    assert "source_artifacts" in summary
    assert summary["tracked_candidates"]["value_primary"] == "pbindlow_downtrend_narrow_quality_v1"
    assert "deployability" in summary


def test_build_summary_tracks_exactly_three_candidates(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    ids = [x["strategy_id"] for x in summary["candidate_states"]]
    assert ids == [
        "revgrowth_always_on_v1",
        "pbindlow_downtrend_narrow_quality_v1",
        "pbindlow_downtrend_only_v1",
    ]


def test_value_primary_reads_registry_operating_params(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    value_primary = next(x for x in summary["candidate_states"] if x["strategy_id"] == "pbindlow_downtrend_narrow_quality_v1")
    assert value_primary["operating_params"]["top_n"] == 20
    assert value_primary["operating_params"]["benchmark"] == "equal_weight_universe"
    assert value_primary["realism_flags"]["cost_sensitivity"]["status"] == "elevated"
    assert value_primary["realism_flags"]["execution_realism"]["status"] == "acceptable"
    assert value_primary["realism_flags"]["impact_realism"]["status"] == "elevated"


def test_role_switch_compatibility_uses_true_primary(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    value_primary = next(x for x in summary["candidate_states"] if x["strategy_id"] == "pbindlow_downtrend_narrow_quality_v1")
    value_reference = next(x for x in summary["candidate_states"] if x["strategy_id"] == "pbindlow_downtrend_only_v1")
    assert value_primary["role"] == "primary_candidate"
    assert value_primary["status"] == "active"
    assert value_reference["role"] == "enhanced_candidate"
    assert summary["line_view"]["valuation_line"]["posture"] == "primary_active"


def test_status_payload_overrides_registry_status(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    status_path = reports / "pbindlow_candidate_pool_status_20260517.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    for item in payload["strategies"]:
        if item["strategy_id"] == "pbindlow_downtrend_narrow_quality_v1":
            item["status"] = "watch"
            item["recent_review_trend"] = "recent_weakening"
    write_json(status_path, payload)

    summary = build_summary(reports)
    value_primary = next(x for x in summary["candidate_states"] if x["strategy_id"] == "pbindlow_downtrend_narrow_quality_v1")
    assert value_primary["status"] == "watch"
    assert summary["line_view"]["valuation_line"]["posture"] == "primary_watch"


def test_decision_actions_are_split(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    assert "research_actions" in summary["decision_actions"]
    assert "portfolio_actions" in summary["decision_actions"]
    assert len(summary["decision_actions"]["research_actions"]) > 0
    assert len(summary["decision_actions"]["portfolio_actions"]) > 0


def test_selection_trace_is_populated(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    trace = summary["source_artifacts"]["selection_trace"]
    assert trace["pbindlow_downtrend_narrow_quality_v1"]["review_id"] == "review_quality_2025H2"
    assert trace["revgrowth_always_on_v1"]["window_label"] == "2025H2"


def test_markdown_contains_required_sections(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    write_json(reports / "strategy_scale_stress_summary_20260519T000000Z.json", {
        "report_type": "strategy_scale_stress_summary",
        "candidate_scale_stress": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "bucket_entry_thresholds": {"light": "model_small", "medium": "model_small", "heavy": None, "extreme": "model_small"},
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": "model_small",
                    "first_medium_aum": "model_small",
                    "first_heavy_aum": None,
                    "first_extreme_aum": "model_small",
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_small:stop_using"],
                },
                "stress_cases": [],
            }
        ],
    })
    summary = build_summary(reports)
    md = render_markdown(summary)
    assert "# Research Decision Summary" in md
    assert "## What changed since last summary" in md
    assert "## Realism flags" in md
    assert "impact realism" in md
    assert "## Deployability summary" in md


def test_summary_includes_working_configuration(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    wc = summary["working_configuration"]
    assert wc["universe_policy"] == "amount_bottom_30pct"
    assert wc["weighting_policy"] == "equal_weight"
    assert wc["operating_mode"] == "growth_mainline_with_value_watch"
    assert wc["keep_rule_status"] == "keep"
    assert wc["decision_basis"].endswith("research_decision_summary_latest.json")
    assert wc["capacity_basis"].endswith("research_capacity_constraints_latest.json")
    assert wc["observed_value_status"] == "active"
    assert wc["mainline_role"] == "growth_core"
    assert wc["true_return_thesis"] == wc["mainline_thesis"]
    assert wc["config_alignment"] == "drifted"
    assert wc["working_config_review"]["status"] == "needs_review"
    assert wc["additive_eligibility"] in {"eligible", "blocked"}
    assert "promotion_blockers" in wc
    assert "demotion_triggers" in wc
    assert wc["working_config_review"]["status"] in {"keep", "needs_review", "stop_using", "needs_revision"}
    assert summary["source_artifacts"]["working_config"].endswith("current_working_strategy_config.json")


def test_markdown_includes_current_working_configuration(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    md = render_markdown(summary)
    assert "## Current working configuration" in md
    assert "Universe policy: amount_bottom_30pct" in md
    assert "Operating mode: growth_mainline_with_value_watch" in md
    assert "Observed value status: active" in md
    assert "Config alignment: drifted" in md
    assert "Decision basis: data/reports/research_decision_summary_latest.json" in md
    assert "Promotion blockers:" in md


def test_executive_summary_includes_real_return_governance_fields(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    summary = build_summary(reports)
    executive = summary["executive_summary"]
    assert executive["real_return_priority"] == "high"
    assert executive["single_line_dependency_risk"] in {"moderate", "elevated"}
    assert executive["working_config_recommendation"] in {"keep", "keep_with_caution", "needs_revision", "stop_using"}


def test_growth_realism_and_capacity_fail_force_top_level_deployment_block(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    write_json(reports / "research_capacity_constraints_latest.json", {
        "report_type": "research_capacity_constraints",
        "strategy_capacity": [
            {"strategy_id": "revgrowth_always_on_v1", "capacity_status": "failed", "note": "real-return capacity breach"},
            {"strategy_id": "pbindlow_downtrend_narrow_quality_v1", "capacity_status": "acceptable", "note": "value ok"},
            {"strategy_id": "pbindlow_downtrend_only_v1", "capacity_status": "acceptable", "note": "baseline ok"},
        ],
    })
    write_json(reports / "research_realism_stress_latest.json", {
        "report_type": "research_realism_stress",
        "candidate_realism": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "cost_sensitivity": {"status": "elevated", "note": "growth cost fail"},
                "concentration_risk": {"status": "acceptable", "note": "ok"},
                "liquidity_risk": {"status": "elevated", "note": "growth liquidity fail"},
                "execution_realism": {"status": "elevated", "note": "growth execution fail"},
                "impact_realism": {"status": "elevated", "note": "growth impact fail"},
            },
            {
                "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
                "cost_sensitivity": {"status": "acceptable", "note": "ok"},
                "concentration_risk": {"status": "acceptable", "note": "ok"},
                "liquidity_risk": {"status": "acceptable", "note": "ok"},
                "execution_realism": {"status": "acceptable", "note": "ok"},
                "impact_realism": {"status": "acceptable", "note": "ok"},
            },
            {
                "strategy_id": "pbindlow_downtrend_only_v1",
                "cost_sensitivity": {"status": "acceptable", "note": "ok"},
                "concentration_risk": {"status": "acceptable", "note": "ok"},
                "liquidity_risk": {"status": "acceptable", "note": "ok"},
                "execution_realism": {"status": "acceptable", "note": "ok"},
                "impact_realism": {"status": "acceptable", "note": "ok"},
            },
        ],
    })
    write_json(reports / "strategy_scale_stress_summary_latest.json", {
        "report_type": "strategy_scale_stress_summary",
        "candidate_scale_stress": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "deployability": {
                    "deployable_aum_floor": "model_micro",
                    "first_light_aum": "model_small",
                    "first_medium_aum": None,
                    "first_heavy_aum": None,
                    "first_extreme_aum": None,
                    "recommended_max_aum": "model_micro",
                    "deployment_blocked": False,
                    "blocking_reasons": [],
                },
                "stress_cases": [
                    {
                        "capital_label": "model_micro",
                        "aum": 100000.0,
                        "working_config_recommendation_impact": {"status": "keep", "reason": "micro still tradable"},
                    }
                ],
            },
            {
                "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": None,
                    "first_medium_aum": None,
                    "first_heavy_aum": None,
                    "first_extreme_aum": None,
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_micro:value_blocked"],
                },
                "stress_cases": [],
            },
            {
                "strategy_id": "pbindlow_downtrend_only_v1",
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": None,
                    "first_medium_aum": None,
                    "first_heavy_aum": None,
                    "first_extreme_aum": None,
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_micro:value_blocked"],
                },
                "stress_cases": [],
            },
        ],
    })
    summary = build_summary(reports)
    growth = summary["deployability"]["growth"]
    assert summary["working_config_recommendation"]["status"] == "stop_using"
    assert summary["working_config_recommendation"]["decision_inputs"]["growth_realism"] == "fail"
    assert summary["working_config_recommendation"]["decision_inputs"]["growth_capacity"] == "fail"
    assert growth["deployment_blocked"] is True
    assert growth["recommended_max_aum"] is None
    assert "model_micro:realism_fail" in growth["blocking_reasons"]
    assert "model_micro:capacity_fail" in growth["blocking_reasons"]


def test_scale_stress_report_is_consumed_into_summary(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    write_json(reports / "strategy_scale_stress_summary_20260519T000000Z.json", {
        "report_type": "strategy_scale_stress_summary",
        "candidate_scale_stress": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "bucket_entry_thresholds": {"light": "model_small", "medium": "model_small", "heavy": None, "extreme": "model_small"},
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": "model_small",
                    "first_medium_aum": "model_small",
                    "first_heavy_aum": None,
                    "first_extreme_aum": "model_small",
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_small:stop_using"],
                },
                "stress_cases": [
                    {
                        "capital_label": "model_small",
                        "aum": 1000000.0,
                        "working_config_recommendation_impact": {
                            "status": "stop_using",
                            "reason": "capital-scaled dynamic impact pushes growth into extreme execution buckets or negative executable return",
                        },
                        "executable_alpha_erosion": {
                            "annual_return_erosion_rate": 0.08,
                            "sharpe_erosion_rate": 0.07,
                            "impact_cost_paid": 25000.0,
                        },
                        "dynamic_impact_v1": {
                            "execution_diagnostics": {
                                "bucket_counts": {"very_light": 10, "light": 1, "medium": 1, "heavy": 0, "extreme": 2},
                            }
                        },
                    }
                ],
            },
            {
                "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
                "bucket_entry_thresholds": {"light": "model_small", "medium": None, "heavy": None, "extreme": "model_small"},
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": "model_small",
                    "first_medium_aum": None,
                    "first_heavy_aum": None,
                    "first_extreme_aum": "model_small",
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_small:stop_using"],
                },
                "stress_cases": [
                    {
                        "capital_label": "model_small",
                        "aum": 1000000.0,
                        "working_config_recommendation_impact": {
                            "status": "stop_using",
                            "reason": "capital-scaled dynamic impact pushes value into extreme execution buckets",
                        },
                        "executable_alpha_erosion": {
                            "annual_return_erosion_rate": 0.11,
                            "sharpe_erosion_rate": 0.09,
                            "impact_cost_paid": 18000.0,
                        },
                        "dynamic_impact_v1": {
                            "execution_diagnostics": {
                                "bucket_counts": {"very_light": 8, "light": 1, "medium": 0, "heavy": 0, "extreme": 3},
                            }
                        },
                    }
                ],
            },
            {
                "strategy_id": "pbindlow_downtrend_only_v1",
                "bucket_entry_thresholds": {"light": "model_small", "medium": None, "heavy": None, "extreme": None},
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": "model_small",
                    "first_medium_aum": None,
                    "first_heavy_aum": None,
                    "first_extreme_aum": None,
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_small:needs_revision"],
                },
                "stress_cases": [
                    {
                        "capital_label": "model_small",
                        "aum": 1000000.0,
                        "working_config_recommendation_impact": {
                            "status": "needs_revision",
                            "reason": "baseline value has material scale friction",
                        },
                        "executable_alpha_erosion": {
                            "annual_return_erosion_rate": 0.05,
                            "sharpe_erosion_rate": 0.04,
                            "impact_cost_paid": 9000.0,
                        },
                        "dynamic_impact_v1": {
                            "execution_diagnostics": {
                                "bucket_counts": {"very_light": 9, "light": 2, "medium": 0, "heavy": 0, "extreme": 0},
                            }
                        },
                    }
                ],
            },
        ],
    })
    summary = build_summary(reports)
    assert summary["working_config_recommendation"]["status"] == "stop_using"
    assert summary["working_config_recommendation"]["decision_inputs"]["growth_scale_stress"] == "fail"
    assert summary["working_config_recommendation"]["decision_inputs"]["value_scale_stress"] == "fail"
    assert summary["working_config_recommendation"]["scale_stress_impact"]["growth"]["first_extreme_aum"] == "model_small"
    assert summary["working_config_recommendation"]["scale_stress_impact"]["value_primary"]["first_extreme_aum"] == "model_small"
    assert summary["additive_eligibility"]["revgrowth_always_on_v1"] == "ineligible"
    assert summary["additive_eligibility"]["pbindlow_downtrend_narrow_quality_v1"] == "ineligible"
    assert any("scale stress gating failed" in x for x in summary["promotion_blockers"]["pbindlow_downtrend_narrow_quality_v1"])
    assert any("capital-scale stress enters extreme at model_small" in x for x in summary["demotion_triggers"]["pbindlow_downtrend_narrow_quality_v1"])
    assert summary["deployability"]["growth"]["deployment_blocked"] is True
    assert summary["deployability"]["value_primary"]["first_extreme_aum"] == "model_small"
    assert summary["source_artifacts"]["scale_stress_report"].endswith("strategy_scale_stress_summary_20260519T000000Z.json")


def test_markdown_includes_scale_stress_section(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    write_json(reports / "strategy_scale_stress_summary_20260519T000000Z.json", {
        "report_type": "strategy_scale_stress_summary",
        "candidate_scale_stress": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "bucket_entry_thresholds": {"light": "model_small", "medium": "model_small", "heavy": None, "extreme": "model_small"},
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": "model_small",
                    "first_medium_aum": "model_small",
                    "first_heavy_aum": None,
                    "first_extreme_aum": "model_small",
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_small:stop_using"],
                },
                "stress_cases": [
                    {
                        "capital_label": "model_small",
                        "aum": 1000000.0,
                        "working_config_recommendation_impact": {
                            "status": "stop_using",
                            "reason": "capital-scaled dynamic impact pushes growth into extreme execution buckets or negative executable return",
                        },
                        "executable_alpha_erosion": {
                            "annual_return_erosion_rate": 0.08,
                            "sharpe_erosion_rate": 0.07,
                            "impact_cost_paid": 25000.0,
                        },
                        "dynamic_impact_v1": {
                            "execution_diagnostics": {
                                "bucket_counts": {"very_light": 10, "light": 1, "medium": 1, "heavy": 0, "extreme": 2},
                            }
                        },
                    }
                ],
            },
            {
                "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
                "bucket_entry_thresholds": {"light": "model_small", "medium": None, "heavy": None, "extreme": "model_small"},
                "deployability": {
                    "deployable_aum_floor": None,
                    "first_light_aum": "model_small",
                    "first_medium_aum": None,
                    "first_heavy_aum": None,
                    "first_extreme_aum": "model_small",
                    "recommended_max_aum": None,
                    "deployment_blocked": True,
                    "blocking_reasons": ["model_small:stop_using"],
                },
                "stress_cases": [
                    {
                        "capital_label": "model_small",
                        "aum": 1000000.0,
                        "working_config_recommendation_impact": {
                            "status": "stop_using",
                            "reason": "capital-scaled dynamic impact pushes value into extreme execution buckets",
                        },
                        "executable_alpha_erosion": {
                            "annual_return_erosion_rate": 0.11,
                            "sharpe_erosion_rate": 0.09,
                            "impact_cost_paid": 18000.0,
                        },
                        "dynamic_impact_v1": {
                            "execution_diagnostics": {
                                "bucket_counts": {"very_light": 8, "light": 1, "medium": 0, "heavy": 0, "extreme": 3},
                            }
                        },
                    }
                ],
            },
        ],
    })
    summary = build_summary(reports)
    md = render_markdown(summary)
    assert "## Capital-scale executable-alpha stress impact" in md
    assert "### value_primary" in md
    assert "First extreme AUM: model_small" in md
    assert "## Deployability summary" in md
    assert "recommended_max_aum" in md


def test_build_summary_blocks_growth_when_realism_and_capacity_fail_even_without_scale_stress_fail(tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    write_json(reports / "research_realism_stress_20260523T000000Z.json", {
        "report_type": "research_realism_stress",
        "candidate_realism": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "liquidity_risk": {"status": "elevated", "note": "thin tail"},
                "cost_sensitivity": {"status": "elevated", "note": "real mark-to-market return is negative"},
                "concentration_risk": {"status": "acceptable", "note": ""},
                "execution_realism": {"status": "elevated", "note": "execution path unstable"},
                "impact_realism": {"status": "elevated", "note": "impact path unstable"},
            }
        ],
    })
    write_json(reports / "research_capacity_constraints_20260523T000000Z.json", {
        "report_type": "research_capacity_constraints",
        "candidate_capacity": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "capital_label": "model_micro",
                "liquidity_capacity": {"status": "elevated", "constraint_breach": True},
            }
        ],
    })
    write_json(reports / "strategy_scale_stress_summary_20260523T000000Z.json", {
        "report_type": "strategy_scale_stress_summary",
        "candidate_scale_stress": [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "bucket_entry_thresholds": {"light": "model_micro", "medium": "model_micro", "heavy": "model_micro", "extreme": "model_micro"},
                "deployability": {
                    "deployable_aum_floor": "model_micro",
                    "first_light_aum": "model_micro",
                    "first_medium_aum": "model_micro",
                    "first_heavy_aum": "model_micro",
                    "first_extreme_aum": "model_micro",
                    "recommended_max_aum": "model_micro",
                    "deployment_blocked": False,
                    "blocking_reasons": [],
                },
                "stress_cases": [
                    {
                        "capital_label": "model_micro",
                        "aum": 100000.0,
                        "working_config_recommendation_impact": {"status": "needs_revision", "reason": "scale caution only"},
                        "executable_alpha_erosion": {"annual_return_erosion_rate": 0.01, "sharpe_erosion_rate": 0.01, "impact_cost_paid": 100.0},
                        "dynamic_impact_v1": {"execution_diagnostics": {"bucket_counts": {"very_light": 10, "light": 1, "medium": 0, "heavy": 0, "extreme": 0}}},
                    }
                ],
            }
        ],
    })
    summary = build_summary(reports)
    assert summary["working_config_recommendation"]["decision_inputs"]["growth_capacity"] == "fail"
    assert summary["working_config_recommendation"]["status"] in {"needs_revision", "stop_using"}
    assert summary["deployability"]["growth"]["deployment_blocked"] is True
    assert summary["deployability"]["growth"]["recommended_max_aum"] is None
