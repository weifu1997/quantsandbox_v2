from app.domain.backtest.performance_metrics import (
    annual_return,
    annual_volatility,
    max_drawdown,
    sharpe_ratio,
    total_return,
    turnover_from_holdings,
    win_rate,
)


def test_total_return() -> None:
    assert abs(total_return([1.1, 1.21]) - 0.21) < 1e-9


def test_annual_return_weekly_single_year() -> None:
    returns = [0.01] * 52
    value = annual_return(returns, 52)
    assert value > 0.67 and value < 0.69


def test_annual_volatility_zero_when_flat() -> None:
    assert annual_volatility([0.01, 0.01, 0.01], 52) == 0.0


def test_sharpe_zero_when_no_volatility() -> None:
    assert sharpe_ratio([0.01, 0.01, 0.01], 52) == 0.0


def test_max_drawdown() -> None:
    assert abs(max_drawdown([1.0, 1.2, 0.9, 1.1]) - 0.25) < 1e-9


def test_win_rate() -> None:
    assert win_rate([0.1, -0.2, 0.3, 0.0]) == 0.5


def test_turnover_from_holdings() -> None:
    previous = {"A": 0.5, "B": 0.5}
    current = {"A": 0.2, "C": 0.8}
    assert abs(turnover_from_holdings(previous, current) - 1.6) < 1e-9
