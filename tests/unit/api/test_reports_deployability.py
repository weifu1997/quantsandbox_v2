from __future__ import annotations

import json
from pathlib import Path

from app.api.reports import extract_deployability, read_report


def test_extract_deployability_returns_top_level_schema():
    structured = {
        "report_type": "research_decision_summary",
        "deployability": {
            "growth": {
                "deployable_aum_floor": None,
                "first_light_aum": "model_small",
                "first_extreme_aum": "model_small",
                "recommended_max_aum": None,
                "deployment_blocked": True,
                "blocking_reasons": ["model_small:stop_using"],
            }
        },
    }
    deployability = extract_deployability(structured)
    assert deployability is not None
    assert deployability["growth"]["deployment_blocked"] is True
    assert deployability["growth"]["first_extreme_aum"] == "model_small"


def test_extract_deployability_returns_none_when_missing():
    assert extract_deployability({"report_type": "x"}) is None


def test_report_response_model_can_carry_deployability(tmp_path: Path, monkeypatch):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "deployability": {
            "growth": {
                "deployable_aum_floor": None,
                "first_light_aum": "model_small",
                "first_medium_aum": None,
                "first_heavy_aum": "model_small",
                "first_extreme_aum": "model_small",
                "recommended_max_aum": None,
                "deployment_blocked": True,
                "blocking_reasons": ["model_small:stop_using"],
            }
        }
    }), encoding="utf-8")

    monkeypatch.setattr("app.api.reports.get_report", lambda report_id: {
        "report_id": report_id,
        "experiment_id": "exp_1",
        "task_id": None,
        "report_format": "json",
        "report_path": str(report_path),
        "summary": None,
    })
    monkeypatch.setattr("app.api.reports.resolve_report_content", lambda result: report_path.read_text(encoding="utf-8"))

    payload = read_report("rep_1")
    assert payload["deployability"] is not None
    assert payload["deployability"]["growth"]["deployment_blocked"] is True
