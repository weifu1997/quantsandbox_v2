from __future__ import annotations

import json
from pathlib import Path

from scripts.run_current_working_config_pipeline import (
    build_pipeline_steps,
    build_result,
    resolve_tickers_file,
)
from scripts.sync_current_working_config import sync_config


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_reports(tmp_path: Path) -> tuple[Path, Path]:
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    config = {
        "as_of": "2026-05-18",
        "working_universe_policy": "amount_bottom_30pct",
        "weighting_policy": "equal_weight",
        "growth_core": "revgrowth_always_on_v1",
        "value_primary": "pbindlow_downtrend_narrow_quality_v1",
        "value_status": "watch",
        "review_start_date": "20250701",
        "review_end_date": "20251231",
        "operating_mode": "growth_mainline_with_value_watch",
        "keep_rule_status": "keep",
    }
    config_path = reports / "current_working_strategy_config.json"
    write_json(config_path, config)
    write_json(reports / "filtered_universe_amount_bottom_30pct_latest.json", {"filtered_universe": {"tickers": ["000001.SZ"]}})
    return reports, config_path


def test_resolve_tickers_file_uses_tail30_latest(tmp_path: Path):
    reports, config_path = make_reports(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    resolved = resolve_tickers_file(config, reports)
    assert resolved is not None
    assert resolved.endswith("filtered_universe_amount_bottom_30pct_latest.json")


def test_build_pipeline_steps_contains_expected_sequence(tmp_path: Path):
    reports, config_path = make_reports(tmp_path)
    steps = build_pipeline_steps(config_path, reports)
    assert [s["name"] for s in steps] == [
        "growth_review",
        "value_review",
        "realism",
        "capacity",
        "scale_stress",
        "decision_summary",
        "strategy_line_allocator",
        "sync_working_config",
    ]
    growth_cmd = steps[0]["command"]
    assert "scripts/run_revgrowth_candidate_review.py" in growth_cmd
    assert "--tickers-file" in growth_cmd
    assert "20250701" in growth_cmd
    assert "20251231" in growth_cmd


def test_build_result_points_to_latest_summary(tmp_path: Path):
    _, config_path = make_reports(tmp_path)
    payload = build_result(config_path, [{"name": "growth_review", "returncode": 0}])
    assert payload["status"] == "ok"
    assert payload["executed_steps"][0]["name"] == "growth_review"
    assert payload["latest_summary"].endswith("research_decision_summary_latest.json")


def test_sync_config_aligns_keep_rule_status_and_basis(tmp_path: Path):
    reports, config_path = make_reports(tmp_path)
    summary_path = reports / "research_decision_summary_latest.json"
    write_json(summary_path, {
        "working_config_recommendation": {"status": "stop_using"},
        "source_artifacts": {
            "realism_report": str(reports / "research_realism_stress_latest.json"),
            "capacity_report": str(reports / "research_capacity_constraints_latest.json"),
            "scale_stress_report": str(reports / "strategy_scale_stress_summary_latest.json"),
        },
        "working_configuration": {},
        "deployability": {
            "growth": {
                "deployable_aum_floor": None,
                "first_light_aum": "model_small",
                "first_extreme_aum": "model_small",
                "recommended_max_aum": None,
                "deployment_blocked": True,
            }
        },
    })
    result = sync_config(config_path, summary_path)
    synced = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["keep_rule_status"] == "stop_using"
    assert synced["keep_rule_status"] == "stop_using"
    assert synced["operating_mode"] == "governance_stop_using"
    assert synced["scale_stress_basis"] == "data/reports/strategy_scale_stress_summary_latest.json"
    assert synced["deployability"]["growth"]["deployment_blocked"] is True
