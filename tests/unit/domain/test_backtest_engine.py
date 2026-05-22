import pandas as pd
import pytest

from app.domain.backtest.dynamic_impact_model import estimate_dynamic_impact_bps
from app.domain.backtest.engine import _apply_turnover_limit, run_topn_backtest, validate_frequency_horizon_pair, _apply_board_lot_constraints
from app.domain.backtest.portfolio_construction import (
    build_topn_equal_weight_portfolio,
    build_topn_liquidity_tilted_score_weight_portfolio,
    build_topn_score_weight_portfolio,
)


def test_build_topn_equal_weight_portfolio() -> None:
    cross_section = pd.DataFrame([
        {"ticker": "a", "factor:score": 3.0},
        {"ticker": "b", "factor:score": 2.0},
        {"ticker": "c", "factor:score": 1.0},
    ])
    holdings = build_topn_equal_weight_portfolio(cross_section, "factor:score", top_n=2)
    assert holdings == {"a": 0.5, "b": 0.5}


def test_build_topn_score_weight_portfolio() -> None:
    cross_section = pd.DataFrame([
        {"ticker": "a", "factor:score": 3.0},
        {"ticker": "b", "factor:score": 1.0},
        {"ticker": "c", "factor:score": -1.0},
    ])
    holdings = build_topn_score_weight_portfolio(cross_section, "factor:score", top_n=2)
    assert holdings["a"] == 0.75
    assert holdings["b"] == 0.25


def test_build_topn_liquidity_tilted_score_weight_portfolio() -> None:
    cross_section = pd.DataFrame([
        {"ticker": "a", "factor:score": 3.0, "amount": 100.0},
        {"ticker": "b", "factor:score": 2.0, "amount": 1000.0},
        {"ticker": "c", "factor:score": 1.0, "amount": 10000.0},
    ])
    holdings = build_topn_liquidity_tilted_score_weight_portfolio(cross_section, "factor:score", top_n=3)
    assert set(holdings) == {"a", "b", "c"}
    assert abs(sum(holdings.values()) - 1.0) < 1e-9
    assert holdings["a"] > holdings["b"] > holdings["c"]


def test_validate_frequency_horizon_pair_accepts_aligned_weekly() -> None:
    validate_frequency_horizon_pair("W", 10)


def test_validate_frequency_horizon_pair_rejects_overlapping_weekly_60d() -> None:
    with pytest.raises(ValueError, match="overlapping-forward-return distortion"):
        validate_frequency_horizon_pair("W", 60)


def test_estimate_dynamic_impact_bps_bucket_boundaries() -> None:
    assert estimate_dynamic_impact_bps(0.0, 1000.0).impact_bps == 0.0
    assert estimate_dynamic_impact_bps(5.0, 1000.0).bucket_label == "very_light"
    assert estimate_dynamic_impact_bps(7.0, 1000.0).bucket_label == "light"
    assert estimate_dynamic_impact_bps(15.0, 1000.0).bucket_label == "medium"
    assert estimate_dynamic_impact_bps(25.0, 1000.0).bucket_label == "heavy"
    assert estimate_dynamic_impact_bps(35.0, 1000.0).bucket_label == "extreme"
    assert estimate_dynamic_impact_bps(10.0, 0.0).impact_bps == 100.0


def test_run_topn_backtest_basic_flow() -> None:
    dataset = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.10, "is_valid_sample": True, "amount": 50.0, "next_open_price": 1.0, "open": 1.0},
        {"date": "2024-01-02", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.05, "is_valid_sample": True, "amount": 50.0, "next_open_price": 1.0, "open": 1.0},
        {"date": "2024-01-02", "ticker": "c", "factor:score": 1.0, "future_return_5d": -0.02, "is_valid_sample": True, "amount": 50.0, "next_open_price": 1.0, "open": 1.0},
        {"date": "2024-01-03", "ticker": "a", "factor:score": 1.0, "future_return_5d": 0.01, "is_valid_sample": True, "amount": 50.0, "next_open_price": 1.0, "open": 1.0},
        {"date": "2024-01-03", "ticker": "b", "factor:score": 4.0, "future_return_5d": 0.03, "is_valid_sample": True, "amount": 50.0, "next_open_price": 1.0, "open": 1.0},
        {"date": "2024-01-03", "ticker": "c", "factor:score": 2.0, "future_return_5d": 0.02, "is_valid_sample": True, "amount": 50.0, "next_open_price": 1.0, "open": 1.0},
    ])
    result = run_topn_backtest(
        dataset=dataset,
        factor_col="factor:score",
        top_n=2,
        rebalance_frequency="D",
        weighting="equal",
        benchmark="equal_weight_universe",
        commission_bps=0.0,
        slippage_bps=0.0,
        horizon=5,
    )
    payload = result.payload
    assert payload["factor_name"] == "score"
    assert len(payload["equity_curve"]) == 2
    assert payload["holdings_by_rebalance_date"]["2024-01-02"] == ["a", "b"]
    assert payload["holdings_by_rebalance_date"]["2024-01-03"] == ["b", "c"]
    assert abs(payload["gross_return_by_rebalance_date"]["2024-01-02"] - 0.075) < 1e-9
    assert abs(payload["gross_return_by_rebalance_date"]["2024-01-03"] - 0.025) < 1e-9
    assert payload["cost_by_rebalance_date"]["2024-01-02"] == 0.001
    assert payload["impact_cost_paid"] > 0.0
    assert payload["base_cost_paid"] == 0.0
    assert payload["execution_diagnostics"]["impact_model"] == "dynamic_impact_v1"
    assert payload["execution_diagnostics"]["bucket_counts"]["light"] >= 1
    assert payload["benchmark_name"] == "equal_weight_universe"


def test_apply_turnover_limit_bounds_final_name_count() -> None:
    previous = {f"old{i}": 0.05 for i in range(20)}
    target = {f"new{i}": 0.05 for i in range(20)}

    blended = _apply_turnover_limit(previous, target, turnover_limit=3.0 / 52.0)

    assert len(blended) <= 25


def test_apply_turnover_limit_does_not_accumulate_unbounded_stale_names() -> None:
    turnover_limit = 3.0 / 52.0
    previous = {f"name{i}": 0.05 for i in range(20)}
    last_target = previous

    for step in range(20):
        target = {f"name{step + i}": 0.05 for i in range(20)}
        last_target = target
        previous = _apply_turnover_limit(previous, target, turnover_limit=turnover_limit)

    stale_names = {k for k in previous if k not in last_target}
    assert len(previous) <= 30
    assert len(stale_names) <= 10


def test_apply_turnover_limit_respects_turnover_budget_after_initial_build() -> None:
    previous = {f"old{i}": 0.05 for i in range(20)}
    target = {f"new{i}": 0.05 for i in range(20)}
    turnover_limit = 3.0 / 52.0

    final = _apply_turnover_limit(previous, target, turnover_limit=turnover_limit)

    from app.domain.backtest.performance_metrics import turnover_from_holdings
    assert turnover_from_holdings(previous, final) <= turnover_limit + 1e-9


def test_apply_board_lot_constraints_rounds_to_100_share_lots_and_skips_infeasible_positions() -> None:
    cross_section = pd.DataFrame([
        {"ticker": "a", "next_open_price": 10.0, "open": 10.0},
        {"ticker": "b", "next_open_price": 55.0, "open": 55.0},
    ]).set_index("ticker")
    holdings = {"a": 0.06, "b": 0.04}

    adjusted, meta = _apply_board_lot_constraints(
        holdings=holdings,
        cross_section=cross_section,
        equity=100_000.0,
        board_lot_size=100,
    )

    assert set(adjusted) == {"a"}
    assert adjusted["a"] == 600 * 10.0 / 100_000.0
    assert meta["a"]["shares"] == 600
    assert meta["b"]["shares"] == 0
    assert meta["b"]["skipped"] is True


def test_run_topn_backtest_with_board_lot_enabled_keeps_equity_curve() -> None:
    dataset = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.10, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-02", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.05, "is_valid_sample": True, "amount": 50.0, "next_open_price": 55.0, "open": 55.0},
        {"date": "2024-01-03", "ticker": "a", "factor:score": 1.0, "future_return_5d": 0.01, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-03", "ticker": "b", "factor:score": 4.0, "future_return_5d": 0.03, "is_valid_sample": True, "amount": 50.0, "next_open_price": 55.0, "open": 55.0},
    ])
    dataset.attrs['initial_aum'] = 100_000.0
    dataset.attrs['board_lot_enabled'] = True
    dataset.attrs['board_lot_size'] = 100

    result = run_topn_backtest(
        dataset=dataset,
        factor_col="factor:score",
        top_n=2,
        rebalance_frequency="D",
        weighting="equal",
        benchmark="equal_weight_universe",
        commission_bps=0.0,
        slippage_bps=0.0,
        horizon=5,
    )
    payload = result.payload
    assert len(payload['equity_curve']) == 2
    assert 'position_details_by_rebalance_date' in payload
    first = payload['position_details_by_rebalance_date']['2024-01-02']
    assert first['a']['shares'] % 100 == 0
    assert first['b']['shares'] % 100 == 0
    assert first['a']['actual_notional'] == 50000.0
    assert first['b']['actual_notional'] == 49500.0


def test_run_topn_backtest_board_lot_cash_drag_is_implicit_in_weights() -> None:
    dataset = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.10, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-02", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.05, "is_valid_sample": True, "amount": 50.0, "next_open_price": 600.0, "open": 600.0},
    ])
    dataset.attrs['initial_aum'] = 100_000.0
    dataset.attrs['board_lot_enabled'] = True
    dataset.attrs['board_lot_size'] = 100

    result = run_topn_backtest(
        dataset=dataset,
        factor_col='factor:score',
        top_n=2,
        rebalance_frequency='D',
        weighting='equal',
        benchmark='equal_weight_universe',
        commission_bps=0.0,
        slippage_bps=0.0,
        horizon=5,
    )
    payload = result.payload
    assert abs(payload['gross_return_by_rebalance_date']['2024-01-02'] - 0.05) < 1e-9


def test_run_topn_backtest_outputs_per_name_gross_contribution_details() -> None:
    dataset = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.10, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-02", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.05, "is_valid_sample": True, "amount": 50.0, "next_open_price": 600.0, "open": 600.0},
    ])
    dataset.attrs['initial_aum'] = 100_000.0
    dataset.attrs['board_lot_enabled'] = True
    dataset.attrs['board_lot_size'] = 100

    result = run_topn_backtest(
        dataset=dataset,
        factor_col='factor:score',
        top_n=2,
        rebalance_frequency='D',
        weighting='equal',
        benchmark='equal_weight_universe',
        commission_bps=0.0,
        slippage_bps=0.0,
        horizon=5,
    )
    payload = result.payload
    assert 'per_name_gross_contribution_by_rebalance_date' in payload
    contrib = payload['per_name_gross_contribution_by_rebalance_date']['2024-01-02']
    assert abs(sum(contrib.values()) - payload['gross_return_by_rebalance_date']['2024-01-02']) < 1e-12
    assert abs(contrib['a'] - 0.05) < 1e-9
    assert abs(contrib.get('b', 0.0) - 0.0) < 1e-12

    accounting = payload['per_name_accounting_by_rebalance_date']['2024-01-02']
    cash = payload['cash_accounting_by_rebalance_date']['2024-01-02']
    end_total = sum(float(x['end_notional']) for x in accounting.values()) + float(cash['cash_end'])
    expected_end = 100_000.0 * payload['equity_curve'][0]
    assert abs(end_total - expected_end) < 1e-6


def test_run_topn_backtest_outputs_per_name_accounting_closed_book() -> None:
    dataset = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.10, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-02", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.05, "is_valid_sample": True, "amount": 50.0, "next_open_price": 600.0, "open": 600.0},
        {"date": "2024-01-03", "ticker": "a", "factor:score": 1.0, "future_return_5d": 0.01, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-03", "ticker": "b", "factor:score": 4.0, "future_return_5d": 0.03, "is_valid_sample": True, "amount": 50.0, "next_open_price": 600.0, "open": 600.0},
    ])
    dataset.attrs['initial_aum'] = 100_000.0
    dataset.attrs['board_lot_enabled'] = True
    dataset.attrs['board_lot_size'] = 100

    result = run_topn_backtest(
        dataset=dataset,
        factor_col='factor:score',
        top_n=2,
        rebalance_frequency='D',
        weighting='equal',
        benchmark='equal_weight_universe',
        commission_bps=0.0,
        slippage_bps=0.0,
        horizon=5,
    )
    payload = result.payload
    acct = payload['per_name_accounting_by_rebalance_date']
    cash = payload['cash_accounting_by_rebalance_date']
    dates = list(payload['returns_by_rebalance_date'].keys())
    last = dates[-1]
    total = sum(float(v['end_notional']) for v in acct[last].values()) + float(cash[last]['cash_end'])
    assert abs(total - 100_000.0 * payload['equity_curve'][-1]) < 1e-6


def test_run_topn_backtest_per_name_accounting_carries_forward_previous_end_notional() -> None:
    dataset = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.10, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-02", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.00, "is_valid_sample": True, "amount": 50.0, "next_open_price": 600.0, "open": 600.0},
        {"date": "2024-01-03", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.20, "is_valid_sample": True, "amount": 50.0, "next_open_price": 10.0, "open": 10.0},
        {"date": "2024-01-03", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.00, "is_valid_sample": True, "amount": 50.0, "next_open_price": 600.0, "open": 600.0},
    ])
    dataset.attrs['initial_aum'] = 100_000.0
    dataset.attrs['board_lot_enabled'] = True
    dataset.attrs['board_lot_size'] = 100

    result = run_topn_backtest(
        dataset=dataset,
        factor_col='factor:score',
        top_n=2,
        rebalance_frequency='D',
        weighting='equal',
        benchmark='equal_weight_universe',
        commission_bps=0.0,
        slippage_bps=0.0,
        horizon=5,
    )

    acct = result.payload['per_name_accounting_by_rebalance_date']
    first_end = float(acct['2024-01-02']['a']['end_notional'])
    second_start = float(acct['2024-01-03']['a']['start_notional'])
    assert abs(second_start - first_end) < 1e-6
