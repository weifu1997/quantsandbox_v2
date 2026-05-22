from __future__ import annotations

import json
from pathlib import Path

from scripts.run_high_liquidity_filter_refactor import (
    build_report,
    derive_recommendation,
    filter_high_liquidity_tickers,
    render_markdown,
    universe_effect,
)


def test_universe_effect_basic():
    ue = universe_effect(100, 60)
    assert ue["eligible_ticker_count"] == 60
    assert ue["coverage_change_vs_base"] == -0.4


def test_derive_recommendation():
    assert derive_recommendation(80, 100) == "promising"
    assert derive_recommendation(50, 100) == "needs_more_review"
    assert derive_recommendation(20, 100) == "too_destructive"


def test_filter_high_liquidity_tickers(tmp_path: Path, monkeypatch):
    import pandas as pd
    import scripts.run_high_liquidity_filter_refactor as mod
    market_dir = tmp_path / "market"
    market_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"amount": [400000, 450000, 500000]}).to_parquet(market_dir / "a.parquet")
    pd.DataFrame({"amount": [100000, 120000, 150000]}).to_parquet(market_dir / "b.parquet")
    monkeypatch.setattr(mod, "MARKET_DIR", market_dir)
    eligible = filter_high_liquidity_tickers(["a", "b"], 300000, 0.7)
    assert eligible == ["a"]


def test_build_report_contains_results(tmp_path: Path, monkeypatch):
    import scripts.run_high_liquidity_filter_refactor as mod
    monkeypatch.setattr(mod, "load_base_universe", lambda limit=1000: [f"t{i}" for i in range(10)])
    coverage_map = {
        (300000, 0.7): [f"t{i}" for i in range(8)],
        (500000, 0.7): [f"t{i}" for i in range(5)],
        (1000000, 0.7): [f"t{i}" for i in range(2)],
    }
    monkeypatch.setattr(mod, "filter_high_liquidity_tickers", lambda base_tickers, amount_floor, coverage_ratio_min: coverage_map[(amount_floor, coverage_ratio_min)])
    report = build_report()
    assert report["report_type"] == "high_liquidity_filter_refactor"
    assert len(report["tested_filters"]) == 3
    assert len(report["results"]) == 3
    assert report["results"][0]["recommendation"] == "promising"


def test_markdown_contains_required_sections(tmp_path: Path, monkeypatch):
    import scripts.run_high_liquidity_filter_refactor as mod
    monkeypatch.setattr(mod, "load_base_universe", lambda limit=1000: [f"t{i}" for i in range(10)])
    coverage_map = {
        (300000, 0.7): [f"t{i}" for i in range(8)],
        (500000, 0.7): [f"t{i}" for i in range(5)],
        (1000000, 0.7): [f"t{i}" for i in range(2)],
    }
    monkeypatch.setattr(mod, "filter_high_liquidity_tickers", lambda base_tickers, amount_floor, coverage_ratio_min: coverage_map[(amount_floor, coverage_ratio_min)])
    md = render_markdown(build_report())
    assert "# High-Liquidity Filter Refactor Summary" in md
    assert "## Tested liquidity filters" in md
    assert "## Universe effect" in md
    assert "## Recommendation" in md
