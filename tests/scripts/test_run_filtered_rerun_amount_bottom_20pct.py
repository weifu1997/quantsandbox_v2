from __future__ import annotations

from scripts.run_filtered_rerun_amount_bottom_20pct import (
    build_report,
    derive_net_assessment,
    render_markdown,
    universe_effect,
)


def test_universe_effect():
    ue = universe_effect(100, 80)
    assert ue["retained_fraction"] == 0.8
    assert ue["eligible_ticker_count"] == 80


def test_derive_net_assessment():
    assert derive_net_assessment(0.85) == "promising"
    assert derive_net_assessment(0.7) == "mixed"
    assert derive_net_assessment(0.5) == "not_enough"


def test_build_report_contains_required_keys(monkeypatch):
    import scripts.run_filtered_rerun_amount_bottom_20pct as mod
    monkeypatch.setattr(mod, "load_base_universe", lambda limit=1000: [f"t{i}" for i in range(10)])
    monkeypatch.setattr(mod, "prune_bottom_liquidity_tail", lambda base_tickers, field, tail_cut: [f"t{i}" for i in range(8)])
    report = build_report()
    assert report["report_type"] == "filtered_rerun_chain"
    assert report["filter_config"]["label"] == "amount_bottom_20pct"
    assert "comparison_summary" in report
    assert "growth_line" in report
    assert "valuation_line" in report


def test_markdown_contains_required_sections(monkeypatch):
    import scripts.run_filtered_rerun_amount_bottom_20pct as mod
    monkeypatch.setattr(mod, "load_base_universe", lambda limit=1000: [f"t{i}" for i in range(10)])
    monkeypatch.setattr(mod, "prune_bottom_liquidity_tail", lambda base_tickers, field, tail_cut: [f"t{i}" for i in range(8)])
    md = render_markdown(build_report())
    assert "# Filtered Rerun Chain Summary" in md
    assert "## Filter configuration" in md
    assert "## Universe retention" in md
    assert "## Net assessment" in md
