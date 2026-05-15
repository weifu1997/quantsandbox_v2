from __future__ import annotations


def estimate_transaction_cost(
    turnover: float,
    commission_bps: float,
    slippage_bps: float,
) -> float:
    total_bps = float(commission_bps) + float(slippage_bps)
    return float(turnover) * total_bps / 10000.0
