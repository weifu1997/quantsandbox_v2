from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from app.domain.models import BacktestResult
from app.domain.backtest.benchmark import run_benchmark
from app.domain.backtest.cost_model import estimate_transaction_cost
from app.domain.backtest.performance_metrics import (
    annual_return,
    max_drawdown,
    periods_per_year,
    sharpe_ratio,
    total_return,
    turnover_from_holdings,
    win_rate,
)
from app.domain.backtest.portfolio_construction import (
    build_topn_equal_weight_portfolio,
    build_topn_score_weight_portfolio,
)
from app.domain.backtest.rebalance_calendar import select_rebalance_dates


def run_topn_backtest(
    dataset: pd.DataFrame,
    factor_col: str,
    top_n: int,
    rebalance_frequency: str,
    weighting: str,
    benchmark: str,
    commission_bps: float,
    slippage_bps: float,
    horizon: int,
) -> BacktestResult:
    return_col = f"future_return_{horizon}d"
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col])

    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), rebalance_frequency)
    returns: list[float] = []
    equity_curve: list[float] = []
    holdings_by_date: dict[str, list[str]] = {}
    previous_holdings: dict[str, float] = {}
    turnover_values: list[float] = []
    cost_paid = 0.0
    equity = 1.0

    for dt in rebalance_dates:
        cross_section = sample.loc[sample["date"] == dt].copy()
        if cross_section.empty:
            continue
        if weighting == "score":
            holdings = build_topn_score_weight_portfolio(cross_section, factor_col, top_n)
        else:
            holdings = build_topn_equal_weight_portfolio(cross_section, factor_col, top_n)
        if not holdings:
            continue
        cross_section = cross_section.set_index("ticker")
        gross = 0.0
        for ticker, weight in holdings.items():
            if ticker in cross_section.index:
                gross += float(weight) * float(cross_section.loc[ticker, return_col])
        turnover = turnover_from_holdings(previous_holdings, holdings)
        turnover_values.append(turnover)
        cost = estimate_transaction_cost(turnover, commission_bps, slippage_bps)
        net = gross - cost
        returns.append(float(net))
        cost_paid += cost
        equity *= (1.0 + float(net))
        equity_curve.append(float(equity))
        holdings_by_date[pd.Timestamp(dt).strftime("%Y-%m-%d")] = list(holdings.keys())
        previous_holdings = holdings

    bm = run_benchmark(sample, return_col, benchmark, rebalance_frequency)
    ppy = periods_per_year(rebalance_frequency)
    payload = {
        "factor_name": factor_col.replace("factor:", ""),
        "horizon": horizon,
        "top_n": top_n,
        "rebalance_frequency": rebalance_frequency,
        "weighting": weighting,
        "benchmark_name": bm["name"],
        "annual_return": annual_return(returns, ppy),
        "total_return": total_return(equity_curve),
        "max_drawdown": max_drawdown(equity_curve),
        "sharpe": sharpe_ratio(returns, ppy),
        "turnover": float(sum(turnover_values) / len(turnover_values)) if turnover_values else 0.0,
        "win_rate": win_rate(returns),
        "cost_paid": float(cost_paid),
        "holdings_by_rebalance_date": holdings_by_date,
        "equity_curve": equity_curve,
        "benchmark_equity_curve": bm["equity_curve"],
        "benchmark_returns": bm["returns"],
        "excess_return_vs_benchmark": total_return(equity_curve) - total_return(bm["equity_curve"]),
    }
    return BacktestResult(factor_name=payload["factor_name"], payload=payload)
