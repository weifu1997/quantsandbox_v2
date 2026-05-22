from __future__ import annotations

import json
from pathlib import Path

from scripts.build_research_capacity_constraints import (
    build_report,
    compute_capacity_snapshot,
    derive_capacity_status,
    derive_constraint_action,
    render_markdown,
)
from tests.scripts.test_build_research_decision_summary import make_fixture_reports


def test_compute_capacity_snapshot_basic():
    import pandas as pd
    dataset = pd.DataFrame({
        "date": pd.to_datetime(["2025-12-31", "2025-12-24"]),
        "ticker": ["a", "b"],
        "amount": [1_000_000.0, 2_000_000.0],
    })
    snap = compute_capacity_snapshot(dataset, {"2025-12-31": ["a"], "2025-12-24": ["b"]}, 5_000_000, 0.05)
    assert snap["median_position_to_amount_ratio"] is not None
    assert snap["p90_position_to_amount_ratio"] is not None
    assert snap["low_liquidity_exposure_ratio"] >= 0.0


def test_derive_capacity_status_mapping():
    status, breach, _ = derive_capacity_status({
        "median_position_to_amount_ratio": 0.02,
        "p90_position_to_amount_ratio": 0.04,
        "max_position_to_amount_ratio": 0.05,
        "low_liquidity_exposure_ratio": 0.3,
    })
    assert status == "elevated"
    assert breach is True
    assert derive_constraint_action(status) == "filter"


def test_build_report_contains_candidate_capacity(tmp_path: Path, monkeypatch):
    reports = make_fixture_reports(tmp_path)
    (reports / "research_decision_summary_20260518T000000Z.json").write_text(json.dumps({"as_of_date": "20260514"}), encoding="utf-8")
    (reports / "research_realism_stress_20260518T000000Z.json").write_text(json.dumps({"report_type": "research_realism_stress", "candidate_realism": [{"strategy_id": "revgrowth_always_on_v1", "impact_realism": {"status": "warning", "note": "impact caution", "snapshot": {}}}, {"strategy_id": "pbindlow_downtrend_narrow_quality_v1", "impact_realism": {"status": "elevated", "note": "impact elevated", "snapshot": {}}}, {"strategy_id": "pbindlow_downtrend_only_v1", "impact_realism": {"status": "warning", "note": "impact caution", "snapshot": {}}}]}), encoding="utf-8")

    import pandas as pd
    import scripts.build_research_capacity_constraints as mod
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_candidate_dataset", lambda line, registry_item, review_row, tickers=None: pd.DataFrame({
        "date": pd.to_datetime(["2025-12-31", "2025-12-24"]),
        "ticker": ["a", "b"],
        "amount": [1_000_000.0, 2_000_000.0],
        f"factor:{registry_item['factor']}": [2.0, 1.0],
    }))
    report = build_report()
    assert report["report_type"] == "research_capacity_constraints"
    assert len(report["candidate_capacity"]) == 9
    item = next(x for x in report["candidate_capacity"] if x["strategy_id"] == "pbindlow_downtrend_narrow_quality_v1" and x["capital_label"] == "model_medium")
    assert "liquidity_capacity" in item
    assert "impact_capacity_overlay" in item
    assert item["impact_capacity_overlay"]["status"] in {"acceptable", "warning", "elevated", "unknown"}
    assert "suggested_constraint" in item


def test_markdown_contains_required_sections(tmp_path: Path, monkeypatch):
    reports = make_fixture_reports(tmp_path)
    (reports / "research_decision_summary_20260518T000000Z.json").write_text(json.dumps({"as_of_date": "20260514"}), encoding="utf-8")
    (reports / "research_realism_stress_20260518T000000Z.json").write_text(json.dumps({"report_type": "research_realism_stress", "candidate_realism": [{"strategy_id": "revgrowth_always_on_v1", "impact_realism": {"status": "warning", "note": "impact caution", "snapshot": {}}}, {"strategy_id": "pbindlow_downtrend_narrow_quality_v1", "impact_realism": {"status": "elevated", "note": "impact elevated", "snapshot": {}}}, {"strategy_id": "pbindlow_downtrend_only_v1", "impact_realism": {"status": "warning", "note": "impact caution", "snapshot": {}}}]}), encoding="utf-8")

    import pandas as pd
    import scripts.build_research_capacity_constraints as mod
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_candidate_dataset", lambda line, registry_item, review_row, tickers=None: pd.DataFrame({
        "date": pd.to_datetime(["2025-12-31", "2025-12-24"]),
        "ticker": ["a", "b"],
        "amount": [1_000_000.0, 2_000_000.0],
        f"factor:{registry_item['factor']}": [2.0, 1.0],
    }))
    report = build_report()
    md = render_markdown(report)
    assert "# Research Capacity & Liquidity Constraint Summary" in md
    assert "## Candidate capacity table" in md
    assert "## Suggested liquidity constraints" in md


def test_build_report_supports_filtered_label_and_tickers_file(tmp_path: Path, monkeypatch):
    reports = make_fixture_reports(tmp_path)
    (reports / "research_decision_summary_20260518T000000Z.json").write_text(json.dumps({"as_of_date": "20260514"}), encoding="utf-8")
    (reports / "research_realism_stress_filtered_tail20_20260518T000000Z.json").write_text(json.dumps({"report_type": "research_realism_stress", "run_label": "filtered_tail20"}), encoding="utf-8")
    tickers_file = reports / "filtered.json"
    tickers_file.write_text(json.dumps(["aaa", "bbb"]), encoding="utf-8")

    import pandas as pd
    import scripts.build_research_capacity_constraints as mod
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    seen = []
    def fake_dataset(line, registry_item, review_row, tickers=None):
        seen.append(list(tickers or []))
        return pd.DataFrame({
            "date": pd.to_datetime(["2025-12-31"]),
            "ticker": ["a"],
            "amount": [1_000_000.0],
            f"factor:{registry_item['factor']}": [2.0],
        })
    monkeypatch.setattr(mod, "build_candidate_dataset", fake_dataset)
    report = build_report(tickers_file=str(tickers_file), label="filtered_tail20")
    assert report["run_label"] == "filtered_tail20"
    assert report["source_artifacts"]["tickers_file"] == str(tickers_file)
    assert seen and seen[0] == ["aaa", "bbb"]
