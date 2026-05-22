from __future__ import annotations

import json
from pathlib import Path

from scripts.build_research_realism_stress import (
    build_report,
    concentration_snapshot_from_holdings,
    default_status_note,
    derive_concentration_status,
    derive_cost_status,
    render_markdown,
)

from tests.scripts.test_build_research_decision_summary import make_fixture_reports


def test_default_status_note_shape():
    assert default_status_note() == {"status": "unknown", "note": ""}


def test_concentration_snapshot_from_holdings():
    snap = concentration_snapshot_from_holdings({
        "2026-01-01": ["a", "b", "c", "d", "e"],
        "2026-01-08": ["a", "b", "c", "d", "e"],
    })
    assert round(snap["avg_single_name_weight"], 4) == 0.2
    assert round(snap["avg_top3_weight"], 4) == 0.6
    assert round(snap["avg_top5_weight"], 4) == 1.0


def test_derive_concentration_status_elevated():
    payload = derive_concentration_status({
        "avg_single_name_weight": 0.2,
        "avg_top3_weight": 0.7,
        "avg_top5_weight": 1.0,
    })
    assert payload["status"] == "elevated"


def test_derive_cost_status_warning_or_elevated():
    scenarios = [
        {"label": "base", "annual_return": 1.0, "sharpe": 2.0, "turnover": 0.2, "cost_paid": 0.01, "holdings_by_rebalance_date": {}},
        {"label": "stress_1", "annual_return": 0.7, "sharpe": 1.2, "turnover": 0.2, "cost_paid": 0.02, "holdings_by_rebalance_date": {}},
        {"label": "stress_2", "annual_return": 0.4, "sharpe": 0.9, "turnover": 0.2, "cost_paid": 0.03, "holdings_by_rebalance_date": {}},
    ]
    payload = derive_cost_status(scenarios)
    assert payload["status"] in {"warning", "elevated", "acceptable"}
    assert len(payload["scenario_comparison"]) == 3


def test_build_report_contains_candidate_realism(tmp_path: Path, monkeypatch):
    reports = make_fixture_reports(tmp_path)
    # seed latest decision summary file expected by realism builder
    decision_summary = {
        "report_type": "research_decision_summary",
        "as_of_date": "20251231",
    }
    (reports / "research_decision_summary_20260518T000000Z.json").write_text(json.dumps(decision_summary), encoding="utf-8")

    import pandas as pd
    import scripts.build_research_realism_stress as mod
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_candidate_dataset", lambda line, registry_item, review_row, tickers=None: pd.DataFrame({"date": pd.to_datetime(["2025-12-31", "2025-12-24"]), "ticker": ["a", "b"], "amount": [500000.0, 600000.0]}))
    monkeypatch.setattr(mod, "run_cost_scenarios", lambda dataset, registry_item: [
        {"label": "base", "annual_return": 1.0, "sharpe": 2.0, "turnover": 0.2, "cost_paid": 0.01, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
        {"label": "stress_1", "annual_return": 0.8, "sharpe": 1.6, "turnover": 0.2, "cost_paid": 0.02, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
        {"label": "stress_2", "annual_return": 0.6, "sharpe": 1.2, "turnover": 0.2, "cost_paid": 0.03, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
    ])
    report = build_report()
    assert report["report_type"] == "research_realism_stress"
    assert len(report["candidate_realism"]) == 3
    ids = [x["strategy_id"] for x in report["candidate_realism"]]
    assert "revgrowth_always_on_v1" in ids
    assert "pbindlow_downtrend_narrow_quality_v1" in ids
    assert "pbindlow_downtrend_only_v1" in ids


def test_cost_and_concentration_keys_exist(tmp_path: Path, monkeypatch):
    reports = make_fixture_reports(tmp_path)
    (reports / "research_decision_summary_20260518T000000Z.json").write_text(json.dumps({"as_of_date": "20251231"}), encoding="utf-8")
    import pandas as pd
    import scripts.build_research_realism_stress as mod
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_candidate_dataset", lambda line, registry_item, review_row, tickers=None: pd.DataFrame({"date": pd.to_datetime(["2025-12-31", "2025-12-24"]), "ticker": ["a", "b"], "amount": [500000.0, 600000.0]}))
    monkeypatch.setattr(mod, "run_cost_scenarios", lambda dataset, registry_item: [
        {"label": "base", "annual_return": 1.0, "sharpe": 2.0, "turnover": 0.2, "cost_paid": 0.01, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
        {"label": "stress_1", "annual_return": 0.8, "sharpe": 1.6, "turnover": 0.2, "cost_paid": 0.02, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
        {"label": "stress_2", "annual_return": 0.6, "sharpe": 1.2, "turnover": 0.2, "cost_paid": 0.03, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
    ])
    report = build_report()
    item = next(x for x in report["candidate_realism"] if x["strategy_id"] == "pbindlow_downtrend_narrow_quality_v1")
    assert "scenario_comparison" in item["cost_sensitivity"]
    assert "snapshot" in item["concentration_risk"]
    assert "impact_realism" in item
    assert item["impact_realism"]["status"] in {"acceptable", "warning", "elevated", "unknown"}
    assert item["cost_sensitivity"]["status"] in {"acceptable", "warning", "elevated"}
    assert item["liquidity_risk"]["status"] in {"acceptable", "warning", "elevated", "unknown"}


def test_markdown_contains_required_sections(tmp_path: Path, monkeypatch):
    reports = make_fixture_reports(tmp_path)
    (reports / "research_decision_summary_20260518T000000Z.json").write_text(json.dumps({"as_of_date": "20251231"}), encoding="utf-8")
    import pandas as pd
    import scripts.build_research_realism_stress as mod
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_candidate_dataset", lambda line, registry_item, review_row, tickers=None: pd.DataFrame({"date": pd.to_datetime(["2025-12-31", "2025-12-24"]), "ticker": ["a", "b"], "amount": [500000.0, 600000.0]}))
    monkeypatch.setattr(mod, "run_cost_scenarios", lambda dataset, registry_item: [
        {"label": "base", "annual_return": 1.0, "sharpe": 2.0, "turnover": 0.2, "cost_paid": 0.01, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
        {"label": "stress_1", "annual_return": 0.8, "sharpe": 1.6, "turnover": 0.2, "cost_paid": 0.02, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
        {"label": "stress_2", "annual_return": 0.6, "sharpe": 1.2, "turnover": 0.2, "cost_paid": 0.03, "holdings_by_rebalance_date": {"2025-12-31": ["a"], "2025-12-24": ["b"]}, "execution_diagnostics": {"avg_participation_rate": 0.008, "p90_participation_rate": 0.012, "avg_dynamic_impact_bps": 12.0, "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0}}},
    ])
    report = build_report()
    md = render_markdown(report)
    assert "# Research Realism Stress Summary" in md
    assert "## Candidate realism table" in md
    assert "## Cost sensitivity details" in md
    assert "## Concentration risk details" in md


def test_build_report_supports_filtered_label_and_tickers_file(tmp_path: Path, monkeypatch):
    reports = make_fixture_reports(tmp_path)
    (reports / "research_decision_summary_20260518T000000Z.json").write_text(json.dumps({"as_of_date": "20251231"}), encoding="utf-8")
    tickers_file = reports / "filtered.json"
    tickers_file.write_text(json.dumps(["aaa", "bbb"]), encoding="utf-8")
    import pandas as pd
    import scripts.build_research_realism_stress as mod
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    seen = []
    def fake_dataset(line, registry_item, review_row, tickers=None):
        seen.append(list(tickers or []))
        return pd.DataFrame({"date": pd.to_datetime(["2025-12-31"]), "ticker": ["a"], "amount": [500000.0]})
    monkeypatch.setattr(mod, "build_candidate_dataset", fake_dataset)
    monkeypatch.setattr(mod, "run_cost_scenarios", lambda dataset, registry_item: [
        {"label": "base", "annual_return": 1.0, "sharpe": 2.0, "turnover": 0.2, "cost_paid": 0.01, "holdings_by_rebalance_date": {"2025-12-31": ["a"]}},
        {"label": "stress_1", "annual_return": 0.8, "sharpe": 1.6, "turnover": 0.2, "cost_paid": 0.02, "holdings_by_rebalance_date": {"2025-12-31": ["a"]}},
        {"label": "stress_2", "annual_return": 0.6, "sharpe": 1.2, "turnover": 0.2, "cost_paid": 0.03, "holdings_by_rebalance_date": {"2025-12-31": ["a"]}},
    ])
    report = build_report(tickers_file=str(tickers_file), label="filtered_tail20")
    assert report["run_label"] == "filtered_tail20"
    assert report["source_artifacts"]["tickers_file"] == str(tickers_file)
    assert seen and seen[0] == ["aaa", "bbb"]
