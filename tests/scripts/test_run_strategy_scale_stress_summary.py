from __future__ import annotations

import json
from pathlib import Path

from scripts.run_strategy_scale_stress_summary import build_report, render_markdown


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_fixture_reports(tmp_path: Path) -> Path:
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_json(reports / "revgrowth_candidate_registry.json", [{"strategy_id": "revgrowth_always_on_v1", "factor": "revenue_growth", "filter": {}, "params": {"top_n": 2, "rebalance_frequency": "W", "horizon": 10, "weighting": "equal", "benchmark": "equal_weight_universe", "commission_bps": 10.0, "slippage_bps": 5.0}}])
    write_json(reports / "revgrowth_candidate_reviews.json", [{"review_id": "review_growth", "strategy_id": "revgrowth_always_on_v1", "window_label": "2025H2", "start_date": "20250701", "end_date": "20251231"}])
    write_json(reports / "pbindlow_candidate_registry.json", [
        {"strategy_id": "pbindlow_downtrend_narrow_quality_v1", "factor": "pb_industry_lowpb_score", "filter": {}, "params": {"top_n": 2, "rebalance_frequency": "W", "horizon": 10, "weighting": "equal", "benchmark": "equal_weight_universe", "commission_bps": 10.0, "slippage_bps": 5.0}},
        {"strategy_id": "pbindlow_downtrend_only_v1", "factor": "pb_industry_lowpb_score", "filter": {}, "params": {"top_n": 2, "rebalance_frequency": "W", "horizon": 10, "weighting": "equal", "benchmark": "equal_weight_universe", "commission_bps": 10.0, "slippage_bps": 5.0}},
    ])
    write_json(reports / "pbindlow_candidate_reviews.json", [
        {"review_id": "review_value_primary", "strategy_id": "pbindlow_downtrend_narrow_quality_v1", "window_label": "2025H2", "start_date": "20250701", "end_date": "20251231"},
        {"review_id": "review_value_base", "strategy_id": "pbindlow_downtrend_only_v1", "window_label": "2025H2", "start_date": "20250701", "end_date": "20251231"},
    ])
    return reports


def test_build_report_runs_for_all_tracked_candidates(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import scripts.run_strategy_scale_stress_summary as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_candidate_dataset", lambda line, registry_item, review_row, tickers=None: __import__("pandas").DataFrame({
        "date": ["2025-07-04", "2025-07-04", "2025-07-11", "2025-07-11"],
        "ticker": ["AAA", "BBB", "AAA", "BBB"],
        f"factor:{registry_item['factor']}": [2.0, 1.0, 1.5, 0.5],
        "future_return_10d": [0.04, 0.01, 0.03, 0.0],
        "amount": [100000.0, 100000.0, 100000.0, 100000.0],
        "is_valid_sample": [True, True, True, True],
    }))
    monkeypatch.setattr(mod, "select_rebalance_dates", lambda dates, freq: sorted(set(dates)))

    report = build_report()
    assert report["report_type"] == "strategy_scale_stress_summary"
    ids = [x["strategy_id"] for x in report["candidate_scale_stress"]]
    assert ids == ["revgrowth_always_on_v1", "pbindlow_downtrend_narrow_quality_v1", "pbindlow_downtrend_only_v1"]
    assert all("stress_cases" in x for x in report["candidate_scale_stress"])
    assert all("deployability" in x for x in report["candidate_scale_stress"])


def test_render_markdown_mentions_all_strategies(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import scripts.run_strategy_scale_stress_summary as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_candidate_dataset", lambda line, registry_item, review_row, tickers=None: __import__("pandas").DataFrame({
        "date": ["2025-07-04", "2025-07-04", "2025-07-11", "2025-07-11"],
        "ticker": ["AAA", "BBB", "AAA", "BBB"],
        f"factor:{registry_item['factor']}": [2.0, 1.0, 1.5, 0.5],
        "future_return_10d": [0.04, 0.01, 0.03, 0.0],
        "amount": [100000.0, 100000.0, 100000.0, 100000.0],
        "is_valid_sample": [True, True, True, True],
    }))
    monkeypatch.setattr(mod, "select_rebalance_dates", lambda dates, freq: sorted(set(dates)))

    report = build_report()
    md = render_markdown(report)
    assert "# Strategy Scale Stress Summary" in md
    assert "deployable_aum_floor" in md
    assert "recommended_max_aum" in md
    assert "deployment_blocked" in md
    assert "## revgrowth_always_on_v1" in md
    assert "## pbindlow_downtrend_narrow_quality_v1" in md
    assert "## pbindlow_downtrend_only_v1" in md
