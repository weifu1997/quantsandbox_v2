from __future__ import annotations

from pathlib import Path

from scripts.run_relative_liquidity_tail_pruning import (
    build_report,
    derive_recommendation,
    prune_bottom_liquidity_tail,
    render_markdown,
    universe_effect,
)


def test_universe_effect_basic():
    ue = universe_effect(100, 90)
    assert ue["retained_fraction"] == 0.9
    assert abs(ue["coverage_change_vs_base"] + 0.1) < 1e-12


def test_derive_recommendation():
    assert derive_recommendation(0.9) == "promising"
    assert derive_recommendation(0.7) == "needs_more_review"
    assert derive_recommendation(0.5) == "too_weak"


def test_prune_bottom_liquidity_tail(tmp_path: Path, monkeypatch):
    import pandas as pd
    import scripts.run_relative_liquidity_tail_pruning as mod
    market_dir = tmp_path / "market"
    market_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"amount": [100, 100, 100]}).to_parquet(market_dir / "a.parquet")
    pd.DataFrame({"amount": [200, 200, 200]}).to_parquet(market_dir / "b.parquet")
    pd.DataFrame({"amount": [300, 300, 300]}).to_parquet(market_dir / "c.parquet")
    monkeypatch.setattr(mod, "MARKET_DIR", market_dir)
    kept = prune_bottom_liquidity_tail(["a", "b", "c"], "amount", 1/3)
    assert kept == ["b", "c"]


def test_build_report_contains_results(monkeypatch):
    import scripts.run_relative_liquidity_tail_pruning as mod
    monkeypatch.setattr(mod, "load_base_universe", lambda limit=1000: [f"t{i}" for i in range(10)])
    sizes = {
        0.10: [f"t{i}" for i in range(9)],
        0.20: [f"t{i}" for i in range(8)],
        0.30: [f"t{i}" for i in range(7)],
    }
    monkeypatch.setattr(mod, "prune_bottom_liquidity_tail", lambda base_tickers, field, tail_cut: sizes[tail_cut])
    report = build_report()
    assert report["report_type"] == "relative_liquidity_tail_pruning"
    assert len(report["tested_methods"]) == 3
    assert len(report["results"]) == 3
    assert report["results"][0]["recommendation"] == "promising"


def test_markdown_contains_required_sections(monkeypatch):
    import scripts.run_relative_liquidity_tail_pruning as mod
    monkeypatch.setattr(mod, "load_base_universe", lambda limit=1000: [f"t{i}" for i in range(10)])
    sizes = {
        0.10: [f"t{i}" for i in range(9)],
        0.20: [f"t{i}" for i in range(8)],
        0.30: [f"t{i}" for i in range(7)],
    }
    monkeypatch.setattr(mod, "prune_bottom_liquidity_tail", lambda base_tickers, field, tail_cut: sizes[tail_cut])
    md = render_markdown(build_report())
    assert "# Relative Liquidity Tail-Pruning Summary" in md
    assert "## Tested methods" in md
    assert "## Universe effect" in md
    assert "## Recommendation" in md
