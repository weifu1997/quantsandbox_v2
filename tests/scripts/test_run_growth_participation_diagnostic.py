from __future__ import annotations

import json
from pathlib import Path

from scripts.run_growth_participation_diagnostic import build_report, render_markdown


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
                "status": "active",
                "params": {
                    "top_n": 2,
                    "rebalance_frequency": "W",
                    "horizon": 10,
                    "weighting": "equal",
                    "benchmark": "equal_weight_universe",
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
    write_json(
        reports / "growth_executable_alpha_validation_latest.json",
        {
            "before_after": {
                "dynamic_impact_v1": {
                    "turnover": 0.08,
                    "execution_diagnostics": {
                        "avg_participation_rate": 0.000001,
                        "p90_participation_rate": 0.000002,
                        "max_participation_rate": 0.000003,
                        "avg_dynamic_impact_bps": 0.0,
                        "bucket_counts": {"very_light": 10, "light": 0, "medium": 0, "heavy": 0, "extreme": 0},
                    },
                }
            },
            "operating_params": {"top_n": 20},
        },
    )
    return reports


def sample_dataset():
    return {
        "date": ["2025-07-04", "2025-07-04", "2025-07-11", "2025-07-11"],
        "ticker": ["AAA", "BBB", "AAA", "BBB"],
        "factor:revenue_growth": [2.0, 1.0, 1.5, 0.5],
        "amount": [2_000_000.0, 1_800_000.0, 2_100_000.0, 1_900_000.0],
        "is_valid_sample": [True, True, True, True],
    }


def test_build_report_explains_very_light_root_cause(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import pandas as pd
    import scripts.run_growth_participation_diagnostic as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(
        mod,
        "build_growth_sample",
        lambda strategy_id, tickers_file=None, sample_limit=1000, reports_dir=None: (
            pd.DataFrame(sample_dataset()),
            {
                "factor": "revenue_growth",
                "params": {
                    "top_n": 2,
                    "rebalance_frequency": "W",
                    "horizon": 10,
                    "weighting": "equal",
                    "benchmark": "equal_weight_universe",
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
    assert report["report_type"] == "growth_participation_diagnostic"
    assert report["actual_validation_snapshot"]["avg_dynamic_impact_bps"] == 0.0
    assert report["root_cause_assessment"]["very_light_threshold"] == 0.005
    assert len(report["aum_scale_analysis"]) == 4
    actual = next(x for x in report["aum_scale_analysis"] if x["label"] == "actual_equity_curve_start")
    assert actual["bucket_ratio"]["very_light"] == 1.0
    assert report["root_cause_assessment"]["dominant_driver"]


def test_render_markdown_contains_root_cause_sections(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import pandas as pd
    import scripts.run_growth_participation_diagnostic as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(
        mod,
        "build_growth_sample",
        lambda strategy_id, tickers_file=None, sample_limit=1000, reports_dir=None: (
            pd.DataFrame(sample_dataset()),
            {
                "factor": "revenue_growth",
                "params": {
                    "top_n": 2,
                    "rebalance_frequency": "W",
                    "horizon": 10,
                    "weighting": "equal",
                    "benchmark": "equal_weight_universe",
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
    assert "# Growth Participation / Impact Bucket Diagnostic" in md
    assert "## Root-cause assessment" in md
    assert "## AUM scale analysis" in md
    assert "## Sensitivity check" in md
