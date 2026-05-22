from __future__ import annotations

import json
from pathlib import Path

from scripts.run_growth_executable_alpha_scale_stress import build_report, render_markdown


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_fixture_reports(tmp_path: Path) -> Path:
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_json(
        reports / "revgrowth_candidate_registry.json",
        [
            {
                "strategy_id": "revgrowth_always_on_v1",
                "factor": "revenue_growth",
                "filter": {},
                "params": {
                    "top_n": 2,
                    "rebalance_frequency": "W",
                    "horizon": 10,
                    "weighting": "equal",
                    "benchmark": "equal_weight_universe",
                    "commission_bps": 10.0,
                    "slippage_bps": 5.0,
                },
            }
        ],
    )
    write_json(
        reports / "revgrowth_candidate_reviews.json",
        [
            {
                "review_id": "review_growth_2025H2",
                "strategy_id": "revgrowth_always_on_v1",
                "window_label": "2025H2",
                "start_date": "20250701",
                "end_date": "20251231",
            }
        ],
    )
    write_json(reports / "growth_participation_diagnostic_latest.json", {"report_type": "growth_participation_diagnostic"})
    write_json(reports / "growth_executable_alpha_validation_latest.json", {"report_type": "growth_executable_alpha_validation"})
    return reports


def sample_dataset():
    return {
        "date": ["2025-07-04", "2025-07-04", "2025-07-11", "2025-07-11"],
        "ticker": ["AAA", "BBB", "AAA", "BBB"],
        "factor:revenue_growth": [2.0, 1.0, 1.5, 0.5],
        "future_return_10d": [0.04, 0.01, 0.03, 0.0],
        "amount": [100000.0, 100000.0, 100000.0, 100000.0],
        "is_valid_sample": [True, True, True, True],
    }


def test_build_report_contains_scale_stress_and_bucket_entries(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import pandas as pd
    import scripts.run_growth_executable_alpha_scale_stress as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(
        mod,
        "build_growth_sample",
        lambda strategy_id, tickers_file=None, sample_limit=1000, reports_dir=None: (
            pd.DataFrame(sample_dataset()),
            {
                "factor": "revenue_growth",
                "filter": {},
                "params": {
                    "top_n": 2,
                    "rebalance_frequency": "W",
                    "horizon": 10,
                    "weighting": "equal",
                    "benchmark": "equal_weight_universe",
                    "commission_bps": 10.0,
                    "slippage_bps": 5.0,
                },
            },
            {
                "review_id": "review_growth_2025H2",
                "window_label": "2025H2",
                "start_date": "20250701",
                "end_date": "20251231",
            },
            None,
        ),
    )
    monkeypatch.setattr(mod, "select_rebalance_dates", lambda dates, freq: sorted(set(dates)))

    report = build_report()
    assert report["report_type"] == "growth_executable_alpha_scale_stress"
    assert len(report["stress_cases"]) == 3
    first = report["stress_cases"][0]
    assert first["comparison_discipline"]["same_strategy"] is True
    assert first["comparison_discipline"]["capital_assumption_only_change"] is True
    assert "annual_return_delta" in first["executable_alpha_erosion"]
    assert "working_config_recommendation_impact" in first
    assert set(report["bucket_entry_thresholds"].keys()) == {"light", "medium", "heavy", "extreme"}


def test_render_markdown_mentions_working_config_recommendation(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import pandas as pd
    import scripts.run_growth_executable_alpha_scale_stress as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(
        mod,
        "build_growth_sample",
        lambda strategy_id, tickers_file=None, sample_limit=1000, reports_dir=None: (
            pd.DataFrame(sample_dataset()),
            {
                "factor": "revenue_growth",
                "filter": {},
                "params": {
                    "top_n": 2,
                    "rebalance_frequency": "W",
                    "horizon": 10,
                    "weighting": "equal",
                    "benchmark": "equal_weight_universe",
                    "commission_bps": 10.0,
                    "slippage_bps": 5.0,
                },
            },
            {
                "review_id": "review_growth_2025H2",
                "window_label": "2025H2",
                "start_date": "20250701",
                "end_date": "20251231",
            },
            None,
        ),
    )
    monkeypatch.setattr(mod, "select_rebalance_dates", lambda dates, freq: sorted(set(dates)))

    report = build_report()
    md = render_markdown(report)
    assert "# Growth Executable Alpha Scale Stress" in md
    assert "## Bucket entry thresholds" in md
    assert "working_config_recommendation" in md
