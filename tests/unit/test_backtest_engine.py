import pandas as pd

from app.domain.backtest.engine import run_topn_backtest
from app.domain.backtest.portfolio_construction import (
    build_topn_equal_weight_portfolio,
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


def test_run_topn_backtest_basic_flow() -> None:
    dataset = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "a", "factor:score": 3.0, "future_return_5d": 0.10, "is_valid_sample": True},
        {"date": "2024-01-02", "ticker": "b", "factor:score": 2.0, "future_return_5d": 0.05, "is_valid_sample": True},
        {"date": "2024-01-02", "ticker": "c", "factor:score": 1.0, "future_return_5d": -0.02, "is_valid_sample": True},
        {"date": "2024-01-03", "ticker": "a", "factor:score": 1.0, "future_return_5d": 0.01, "is_valid_sample": True},
        {"date": "2024-01-03", "ticker": "b", "factor:score": 4.0, "future_return_5d": 0.03, "is_valid_sample": True},
        {"date": "2024-01-03", "ticker": "c", "factor:score": 2.0, "future_return_5d": 0.02, "is_valid_sample": True},
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
    assert payload["cost_paid"] == 0.0
    assert payload["benchmark_name"] == "equal_weight_universe"
