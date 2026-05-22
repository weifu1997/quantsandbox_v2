from __future__ import annotations

import json
from pathlib import Path

from scripts.run_growth_executable_alpha_validation import build_report, render_markdown


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_fixture_reports(tmp_path: Path) -> Path:
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    growth_registry = [
        {
            "strategy_id": "revgrowth_always_on_v1",
            "factor": "revenue_growth",
            "filter": {},
            "role": "primary_candidate",
            "status": "active",
            "params": {
                "top_n": 2,
                "rebalance_frequency": "W",
                "horizon": 10,
                "weighting": "equal",
                "benchmark": "equal_weight_universe",
            },
        }
    ]
    growth_reviews = [
        {
            "review_id": "review_growth_2025H2",
            "strategy_id": "revgrowth_always_on_v1",
            "window_label": "2025H2",
            "start_date": "20250701",
            "end_date": "20251231",
            "review_result": "keep",
            "comment": "review ok",
        }
    ]
    write_json(reports / "revgrowth_candidate_registry.json", growth_registry)
    write_json(reports / "revgrowth_candidate_reviews.json", growth_reviews)
    write_json(reports / "research_realism_stress_20260518T000000Z.json", {"report_type": "research_realism_stress"})
    write_json(reports / "research_capacity_constraints_20260518T000000Z.json", {"report_type": "research_capacity_constraints"})
    write_json(reports / "research_decision_summary_20260518T000000Z.json", {"report_type": "research_decision_summary"})
    return reports


def sample_dataset():
    return {
        "date": ["2025-07-04", "2025-07-04", "2025-07-11", "2025-07-11"],
        "ticker": ["AAA", "BBB", "AAA", "BBB"],
        "factor:revenue_growth": [2.0, 1.0, 1.5, 0.5],
        "future_return_10d": [0.04, 0.01, 0.03, 0.0],
        "is_valid_sample": [True, True, True, True],
        "amount": [500000.0, 400000.0, 500000.0, 400000.0],
    }


def test_build_report_contains_required_cost_breakdown_and_erosion(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import scripts.run_growth_executable_alpha_validation as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_growth_dataset", lambda tickers, start_date, end_date, horizon, factor_name: __import__("pandas").DataFrame(sample_dataset()))
    monkeypatch.setattr(mod, "apply_growth_filter", lambda dataset, filt: (dataset.copy(), {"active_dates": 2, "total_dates": 2, "active_ratio": 1.0}))
    monkeypatch.setattr(mod, "load_expanded_tickers", lambda limit: ["AAA", "BBB"])

    class Result:
        def __init__(self, payload):
            self.payload = payload

    responses = [
        Result({
            "annual_return": 0.20,
            "total_return": 0.15,
            "sharpe": 1.8,
            "max_drawdown": 0.10,
            "turnover": 0.30,
            "base_cost_paid": 0.015,
            "impact_cost_paid": 0.005,
            "total_cost_paid_with_impact": 0.020,
            "cost_paid": 0.020,
            "execution_diagnostics": {
                "avg_participation_rate": 0.008,
                "p90_participation_rate": 0.012,
                "avg_dynamic_impact_bps": 12.0,
                "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0},
            },
        }),
        Result({
            "annual_return": 0.15,
            "total_return": 0.11,
            "sharpe": 1.5,
            "max_drawdown": 0.10,
            "turnover": 0.30,
            "base_cost_paid": 0.015,
            "impact_cost_paid": 0.010,
            "total_cost_paid_with_impact": 0.025,
            "cost_paid": 0.025,
            "execution_diagnostics": {
                "avg_participation_rate": 0.008,
                "p90_participation_rate": 0.012,
                "avg_dynamic_impact_bps": 12.0,
                "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0},
            },
        }),
    ]
    monkeypatch.setattr(mod, "run_topn_backtest", lambda *args, **kwargs: responses.pop(0))

    report = build_report(reports_dir=reports)
    assert report["report_type"] == "growth_executable_alpha_validation"
    assert report["comparison_discipline"]["same_strategy"] is True
    assert report["comparison_discipline"]["same_window"] is True
    assert report["comparison_discipline"]["same_universe"] is True
    assert report["comparison_discipline"]["same_params"] is True
    assert report["cost_breakdown"]["base_cost_paid"] == 0.015
    assert report["cost_breakdown"]["impact_cost_paid"] == 0.010
    assert report["cost_breakdown"]["total_cost_paid_with_impact"] == 0.025
    assert report["executable_alpha_erosion"]["annual_return_delta"] == -0.05000000000000002
    assert report["executable_alpha_erosion"]["sharpe_delta"] == -0.30000000000000004
    assert report["executable_alpha_erosion"]["annual_return_erosion_rate"] == 0.25000000000000006
    assert report["executable_alpha_erosion"]["status"] == "elevated"


def test_render_markdown_mentions_required_sections(monkeypatch, tmp_path: Path):
    reports = make_fixture_reports(tmp_path)
    import scripts.run_growth_executable_alpha_validation as mod

    monkeypatch.setattr(mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(mod, "build_growth_dataset", lambda tickers, start_date, end_date, horizon, factor_name: __import__("pandas").DataFrame(sample_dataset()))
    monkeypatch.setattr(mod, "apply_growth_filter", lambda dataset, filt: (dataset.copy(), {"active_dates": 2, "total_dates": 2, "active_ratio": 1.0}))
    monkeypatch.setattr(mod, "load_expanded_tickers", lambda limit: ["AAA", "BBB"])

    class Result:
        def __init__(self, annual_return, sharpe, impact_cost_paid, total_cost_paid_with_impact):
            self.payload = {
                "annual_return": annual_return,
                "total_return": 0.10,
                "sharpe": sharpe,
                "max_drawdown": 0.10,
                "turnover": 0.30,
                "base_cost_paid": 0.015,
                "impact_cost_paid": impact_cost_paid,
                "total_cost_paid_with_impact": total_cost_paid_with_impact,
                "cost_paid": total_cost_paid_with_impact,
                "execution_diagnostics": {
                    "avg_participation_rate": 0.008,
                    "p90_participation_rate": 0.012,
                    "avg_dynamic_impact_bps": 12.0,
                    "bucket_counts": {"very_light": 0, "light": 2, "medium": 0, "heavy": 0, "extreme": 0},
                },
            }

    responses = [Result(0.20, 1.8, 0.005, 0.020), Result(0.18, 1.7, 0.009, 0.024)]
    monkeypatch.setattr(mod, "run_topn_backtest", lambda *args, **kwargs: responses.pop(0))

    report = build_report(reports_dir=reports)
    md = render_markdown(report)
    assert "# Growth Executable Alpha Validation" in md
    assert "## Before vs after" in md
    assert "## Executable alpha erosion" in md
    assert "base_cost_paid" in md
    assert "impact_cost_paid" in md
    assert "total_cost_paid_with_impact" in md
