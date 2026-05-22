import pandas as pd

from scripts.run_strategy_line_allocator import merge_strategy_returns


def _strategy_result(strategy_id: str, returns_by_date: dict[str, float], rebalance_frequency: str = "W") -> dict:
    equity = 1.0
    equity_curve = []
    for dt in sorted(returns_by_date):
        equity *= 1.0 + returns_by_date[dt]
        equity_curve.append(equity)
    return {
        "strategy_id": strategy_id,
        "backtest": {
            "rebalance_frequency": rebalance_frequency,
            "returns_by_rebalance_date": returns_by_date,
            "equity_curve": equity_curve,
        },
    }


def test_merge_strategy_returns_matches_growth_baseline_when_value_weight_zero() -> None:
    growth = _strategy_result("growth", {"2024-01-05": 0.10, "2024-01-12": -0.05})
    value = _strategy_result("value", {"2024-01-05": 0.90, "2024-01-12": 0.90})
    regimes = pd.DataFrame([
        {"date": pd.Timestamp("2024-01-05"), "regime_trend_20d": "uptrend", "regime_vol_20d": "low_vol", "trend_20d": "uptrend", "breadth_regime": "broad_strength"},
        {"date": pd.Timestamp("2024-01-12"), "regime_trend_20d": "uptrend", "regime_vol_20d": "low_vol", "trend_20d": "uptrend", "breadth_regime": "broad_strength"},
    ])

    merged = merge_strategy_returns(growth, value, regimes, "baseline_growth_only")
    assert merged["returns_by_rebalance_date"] == {"2024-01-05": 0.10, "2024-01-12": -0.05}
    assert abs(merged["equity_curve"][0] - 1.10) < 1e-9
    assert abs(merged["equity_curve"][1] - 1.045) < 1e-9


def test_merge_strategy_returns_uses_rule_weights() -> None:
    growth = _strategy_result("growth", {"2024-01-05": 0.10, "2024-01-12": 0.10})
    value = _strategy_result("value", {"2024-01-05": -0.10, "2024-01-12": 0.20})
    regimes = pd.DataFrame([
        {"date": pd.Timestamp("2024-01-05"), "regime_trend_20d": "downtrend", "regime_vol_20d": "high_vol", "trend_20d": "downtrend", "breadth_regime": "narrow_weakness"},
        {"date": pd.Timestamp("2024-01-12"), "regime_trend_20d": "downtrend", "regime_vol_20d": "high_vol", "trend_20d": "downtrend", "breadth_regime": "broad_strength"},
    ])

    merged = merge_strategy_returns(growth, value, regimes, "simple_regime_allocator")
    assert abs(merged["returns_by_rebalance_date"]["2024-01-05"] - 0.02) < 1e-9
    assert abs(merged["returns_by_rebalance_date"]["2024-01-12"] - 0.12) < 1e-9
    assert merged["allocation_trace"][0]["growth_weight"] == 0.6
    assert merged["allocation_trace"][0]["value_weight"] == 0.4
    assert merged["allocation_trace"][1]["growth_weight"] == 0.8
    assert merged["allocation_trace"][1]["value_weight"] == 0.2
