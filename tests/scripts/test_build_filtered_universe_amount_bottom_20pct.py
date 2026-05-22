from __future__ import annotations

from scripts.build_filtered_universe_amount_bottom_20pct import build_filtered_universe


def test_build_filtered_universe(monkeypatch):
    import scripts.build_filtered_universe_amount_bottom_20pct as mod
    monkeypatch.setattr(mod, "load_base_universe", lambda limit=1000: [f"t{i}" for i in range(10)])
    monkeypatch.setattr(mod, "prune_bottom_liquidity_tail", lambda base_tickers, field, tail_cut: [f"t{i}" for i in range(8)])
    payload = build_filtered_universe()
    assert payload["report_type"] == "filtered_universe"
    assert payload["base_universe"]["ticker_count"] == 10
    assert payload["filtered_universe"]["ticker_count"] == 8
    assert payload["filtered_universe"]["retained_fraction"] == 0.8
    assert len(payload["filtered_universe"]["tickers"]) == 8
