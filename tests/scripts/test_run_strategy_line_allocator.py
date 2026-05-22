from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_strategy_line_allocator import (
    allocator_overlay_blocked,
    choose_allocator_rule,
    merge_strategy_returns,
    strategy_deployability_key,
)


def test_strategy_deployability_key_maps_known_ids():
    assert strategy_deployability_key("revgrowth_always_on_v1") == "growth"
    assert strategy_deployability_key("pbindlow_downtrend_narrow_quality_v1") == "value_primary"
    assert strategy_deployability_key("pbindlow_downtrend_only_v1") == "value_baseline_reference"


def test_allocator_overlay_blocked_reads_deployability_schema():
    deployability = {
        "value_primary": {"deployment_blocked": True},
        "growth": {"deployment_blocked": False},
    }
    assert allocator_overlay_blocked("pbindlow_downtrend_narrow_quality_v1", deployability) is True
    assert allocator_overlay_blocked("revgrowth_always_on_v1", deployability) is False


def test_choose_allocator_rule_zeroes_value_when_blocked():
    row = __import__("pandas").Series({"trend_20d": "downtrend", "breadth_regime": "narrow_weakness"})
    rules = [
        {"when": {"trend_20d": "downtrend", "breadth_regime": "narrow_weakness"}, "growth": 0.6, "value": 0.4},
        {"when": {}, "growth": 0.9, "value": 0.0},
    ]
    rule = choose_allocator_rule(row, rules, value_blocked=True)
    assert rule["growth"] == 1.0
    assert rule["value"] == 0.0
    assert rule["deployability_override"] == "value_blocked"


def test_merge_strategy_returns_raises_when_growth_blocked():
    growth = {"strategy_id": "revgrowth_always_on_v1", "backtest": {"returns_by_rebalance_date": {"2025-01-01": 0.01}, "rebalance_frequency": "W"}}
    value = {"strategy_id": "pbindlow_downtrend_narrow_quality_v1", "backtest": {"returns_by_rebalance_date": {"2025-01-01": 0.02}, "rebalance_frequency": "W"}}
    regime = __import__("pandas").DataFrame({"date": __import__("pandas").to_datetime(["2025-01-01"]), "regime_trend_20d": ["uptrend"], "regime_vol_20d": ["low_vol"], "trend_20d": ["uptrend"], "breadth_regime": ["broad_strength"]})
    deployability = {"growth": {"deployment_blocked": True}}
    with pytest.raises(ValueError, match="growth core .* deployment_blocked"):
        merge_strategy_returns(growth, value, regime, "baseline_growth_only", deployability)


def test_allocator_script_should_block_when_growth_core_blocked(monkeypatch, tmp_path: Path):
    import json as _json
    import scripts.run_strategy_line_allocator as mod
    monkeypatch.setattr(mod, "load_deployability_map", lambda reports_dir=None: {"growth": {"deployment_blocked": True}, "value_primary": {"deployment_blocked": True}})
    monkeypatch.setattr(mod, "load_expanded_tickers", lambda limit: ["AAA", "BBB"])
    monkeypatch.setattr(mod, "build_base_dataset", lambda tickers, start_date, end_date: (__import__("pandas").DataFrame({"date": __import__("pandas").to_datetime(["2025-01-01"]), "ticker": ["AAA"], "factor:revenue_growth": [1.0], "factor:pb_industry_lowpb_score": [1.0], "future_return_10d": [0.01], "close": [10.0], "pb": [1.0], "roe": [0.1], "profit_growth": [0.1], "industry": ["bank"], "amount": [100000.0], "is_valid_sample": [True]}), {"rows": 1}))
    monkeypatch.setattr(mod, "build_market_regimes", lambda dataset: __import__("pandas").DataFrame({"date": __import__("pandas").to_datetime(["2025-01-01"]), "regime_trend_20d": ["uptrend"], "regime_vol_20d": ["low_vol"], "trend_20d": ["uptrend"], "breadth_regime": ["broad_strength"]}))
    monkeypatch.setattr(mod, "run_strategy", lambda ds, strategy: {"strategy_id": strategy["strategy_id"], "coverage": {"active_ratio": 1.0}, "backtest": {"annual_return": 0.1, "total_return": 0.1, "sharpe": 1.0, "max_drawdown": 0.1, "returns_by_rebalance_date": {"2025-01-01": 0.01}, "rebalance_frequency": "W"}})
    report_dir = tmp_path / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "REPORTS_DIR", report_dir)
    mod.main()
    files = list(report_dir.glob("strategy_line_allocator_*.json"))
    assert files
    payload = _json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["allocator_status"]["status"] == "blocked"
    assert payload["portfolio_constraints"]["growth_blocked"] is True
    assert payload["allocator_reports"] == []


def test_merge_strategy_returns_consumes_value_block_and_emits_trace():
    import pandas as pd
    growth = {"strategy_id": "revgrowth_always_on_v1", "backtest": {"returns_by_rebalance_date": {"2025-01-01": 0.01}, "rebalance_frequency": "W"}}
    value = {"strategy_id": "pbindlow_downtrend_narrow_quality_v1", "backtest": {"returns_by_rebalance_date": {"2025-01-01": 0.05}, "rebalance_frequency": "W"}}
    regime = pd.DataFrame({"date": pd.to_datetime(["2025-01-01"]), "regime_trend_20d": ["downtrend"], "regime_vol_20d": ["low_vol"], "trend_20d": ["downtrend"], "breadth_regime": ["narrow_weakness"]})
    deployability = {
        "growth": {"deployment_blocked": False},
        "value_primary": {"deployment_blocked": True, "recommended_max_aum": None},
    }
    result = merge_strategy_returns(growth, value, regime, "simple_regime_allocator", deployability)
    trace = result["allocation_trace"][0]
    assert trace["growth_weight"] == 1.0
    assert trace["value_weight"] == 0.0
    assert trace["deployability_override"] == "value_blocked"
    assert result["deployability_consumed"]["value"]["deployment_blocked"] is True
