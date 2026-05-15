from __future__ import annotations

import math


def total_return(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    return float(equity_curve[-1] - 1.0)


def annual_return(period_returns: list[float], periods_per_year: int) -> float:
    """Annualize a sequence of already-aggregated per-period returns.

    `period_returns` must match the effective rebalance/evaluation frequency used by
    the strategy or benchmark. For example, weekly backtests should pass weekly
    returns with `periods_per_year=52`, not raw daily returns. Under that contract,
    `years = len(period_returns) / periods_per_year` is the intended holding span.
    """
    if not period_returns or periods_per_year <= 0:
        return 0.0
    equity = 1.0
    for value in period_returns:
        equity *= (1.0 + float(value))
    years = len(period_returns) / periods_per_year
    if years <= 0:
        return 0.0
    return float(equity ** (1 / years) - 1.0)


def annual_volatility(period_returns: list[float], periods_per_year: int) -> float:
    if len(period_returns) < 2 or periods_per_year <= 0:
        return 0.0
    mean = sum(period_returns) / len(period_returns)
    variance = sum((x - mean) ** 2 for x in period_returns) / len(period_returns)
    return float(math.sqrt(variance) * math.sqrt(periods_per_year))


def sharpe_ratio(period_returns: list[float], periods_per_year: int, risk_free_rate: float = 0.0) -> float:
    vol = annual_volatility(period_returns, periods_per_year)
    if vol <= 1e-12:
        return 0.0
    ann = annual_return(period_returns, periods_per_year)
    return float((ann - risk_free_rate) / vol)


def max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        dd = (value / peak) - 1.0 if peak > 0 else 0.0
        worst = min(worst, dd)
    return float(abs(worst))


def win_rate(period_returns: list[float]) -> float:
    if not period_returns:
        return 0.0
    return float(sum(1 for x in period_returns if x > 0) / len(period_returns))


def turnover_from_holdings(previous: dict[str, float], current: dict[str, float]) -> float:
    all_names = set(previous) | set(current)
    total_change = 0.0
    for name in all_names:
        total_change += abs(current.get(name, 0.0) - previous.get(name, 0.0))
    return float(total_change)


def periods_per_year(freq: str) -> int:
    mapping = {"D": 252, "W": 52, "M": 12}
    return mapping.get(str(freq).upper(), 52)
