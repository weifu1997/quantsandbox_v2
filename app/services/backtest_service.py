from __future__ import annotations

from app.domain.backtest.engine import run_topn_backtest


def run_strategy_backtest(
    dataset,
    factor_name: str,
    top_n: int,
    rebalance_frequency: str,
    weighting: str,
    benchmark: str,
    commission_bps: float,
    slippage_bps: float,
    horizon: int,
):
    return run_topn_backtest(
        dataset=dataset,
        factor_col=f"factor:{factor_name}",
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        weighting=weighting,
        benchmark=benchmark,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        horizon=horizon,
    )
