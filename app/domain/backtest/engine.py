from __future__ import annotations
from dataclasses import asdict

import pandas as pd

from app.config.settings import get_settings
from app.domain.data_contracts import BacktestCoverageSummary, BacktestWindow, validate_backtest_dataset
from app.domain.models import BacktestResult
from app.domain.backtest.benchmark import run_benchmark
from app.domain.backtest.cost_model import estimate_transaction_cost
from app.domain.backtest.dynamic_impact_model import estimate_dynamic_impact_bps
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
    build_topn_liquidity_tilted_score_weight_portfolio,
    build_topn_score_weight_portfolio,
)
from app.domain.backtest.rebalance_calendar import select_rebalance_dates

MAX_HORIZON_BY_FREQUENCY = {
    "D": 5,
    "W": 10,
    "M": 20,
}


def validate_frequency_horizon_pair(rebalance_frequency: str, horizon: int) -> None:
    freq = str(rebalance_frequency).upper()
    horizon_int = int(horizon)
    max_allowed = MAX_HORIZON_BY_FREQUENCY.get(freq)
    if max_allowed is None:
        return
    if horizon_int > max_allowed:
        raise ValueError(
            f"unsupported backtest configuration: rebalance_frequency={freq} with horizon={horizon_int}d. "
            f"Maximum supported horizon for {freq} is {max_allowed}d to avoid overlapping-forward-return distortion."
        )


def _execution_config(dataset: pd.DataFrame) -> dict:
    enabled = bool(dataset.attrs.get("execution_config_enabled", False))
    return {
        "enabled": enabled,
        "bar_delay": int(dataset.attrs.get("execution_bar_delay", 0)),
        "tick_size": float(dataset.attrs.get("execution_tick_size", 0.01)),
        "base_tick_slippage_ticks": float(dataset.attrs.get("execution_base_tick_slippage_ticks", 0.0)),
        "high_vol_extra_tick_slippage_ticks": float(dataset.attrs.get("execution_high_vol_extra_tick_slippage_ticks", 0.0)),
        "high_vol_quantile": float(dataset.attrs.get("execution_high_vol_quantile", 0.8)),
        "minimum_roundtrip_ticks": float(dataset.attrs.get("execution_minimum_roundtrip_ticks", 0.0)),
        "commission_bps_override": dataset.attrs.get("execution_commission_bps_override"),
    }


def _turnover_limit(dataset: pd.DataFrame, rebalance_frequency: str) -> float | None:
    annual_limit = dataset.attrs.get("growth_turnover_annual_limit")
    if annual_limit in (None, ""):
        return None
    ppy = periods_per_year(rebalance_frequency)
    if ppy <= 0:
        return None
    return float(annual_limit) / float(ppy)


def _initial_aum(dataset: pd.DataFrame) -> float:
    raw = dataset.attrs.get("initial_aum", 1.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 1.0
    return value if value > 0 else 1.0


def _board_lot_enabled(dataset: pd.DataFrame) -> bool:
    return bool(dataset.attrs.get("board_lot_enabled", False))


def _board_lot_size(dataset: pd.DataFrame) -> int:
    raw = dataset.attrs.get("board_lot_size", _DEFAULT_BOARD_LOT_SIZE)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = _DEFAULT_BOARD_LOT_SIZE
    return value if value > 0 else _DEFAULT_BOARD_LOT_SIZE


_TURNOVER_CARRY_BUFFER = 5
_DEFAULT_BOARD_LOT_SIZE = 100


def _apply_turnover_limit(previous_holdings: dict[str, float], target_holdings: dict[str, float], turnover_limit: float | None) -> dict[str, float]:
    if turnover_limit is None:
        return target_holdings
    if not previous_holdings:
        # First period: no previous holdings, but still respect turnover limit
        # by capping total allocation to turnover_limit (treat as max initial deployment).
        total = sum(target_holdings.values())
        if total <= turnover_limit + 1e-12:
            return target_holdings
        # Scale down proportionally so total allocation = turnover_limit
        scale = turnover_limit / total
        return {k: float(v) * scale for k, v in target_holdings.items()}
    realized = turnover_from_holdings(previous_holdings, target_holdings)
    if realized <= turnover_limit + 1e-12:
        return target_holdings

    final = {k: float(v) for k, v in previous_holdings.items() if float(v) > 1e-12}
    sell_budget = float(turnover_limit) / 2.0
    sold = 0.0

    stale = sorted(((k, float(v)) for k, v in final.items() if k not in target_holdings), key=lambda x: x[1], reverse=True)
    stale_keep = {k for k, _ in stale[:_TURNOVER_CARRY_BUFFER]}
    stale_drop = sorted(((k, w) for k, w in stale if k not in stale_keep), key=lambda x: x[1])

    def apply_sell(ticker: str, desired: float) -> float:
        nonlocal sold
        remaining = max(sell_budget - sold, 0.0)
        if remaining <= 1e-12 or desired <= 1e-12:
            return 0.0
        amt = min(desired, remaining)
        final[ticker] = max(final.get(ticker, 0.0) - amt, 0.0)
        sold += amt
        return amt

    for ticker, weight in stale_drop:
        apply_sell(ticker, weight)
    for ticker, weight in sorted(((k, w) for k, w in stale if k in stale_keep), key=lambda x: x[1]):
        if sold >= sell_budget - 1e-12:
            break
        apply_sell(ticker, weight)

    overweights = sorted(
        ((k, max(float(final.get(k, 0.0)) - float(target_holdings.get(k, 0.0)), 0.0)) for k in target_holdings),
        key=lambda x: x[1],
        reverse=True,
    )
    for ticker, excess in overweights:
        if sold >= sell_budget - 1e-12:
            break
        apply_sell(ticker, excess)

    buy_budget = sold
    bought = 0.0
    deficits = sorted(
        ((k, max(float(target_holdings.get(k, 0.0)) - float(final.get(k, 0.0)), 0.0)) for k in target_holdings),
        key=lambda x: x[1],
        reverse=True,
    )
    for ticker, deficit in deficits:
        remaining = max(buy_budget - bought, 0.0)
        if remaining <= 1e-12:
            break
        amt = min(deficit, remaining)
        if amt > 1e-12:
            final[ticker] = float(final.get(ticker, 0.0)) + amt
            bought += amt

    cleaned = {k: float(v) for k, v in final.items() if float(v) > 1e-12}
    total = sum(cleaned.values())
    if total > 0:
        cleaned = {k: float(v) / total for k, v in cleaned.items()}
    return cleaned


def _apply_board_lot_constraints(
    holdings: dict[str, float],
    cross_section: pd.DataFrame,
    equity: float,
    board_lot_size: int = _DEFAULT_BOARD_LOT_SIZE,
) -> tuple[dict[str, float], dict[str, dict[str, float | int | bool]]]:
    adjusted: dict[str, float] = {}
    meta: dict[str, dict[str, float | int | bool]] = {}
    if not holdings or equity <= 0:
        return adjusted, meta

    for ticker, weight in holdings.items():
        price = 0.0
        if ticker in cross_section.index:
            maybe = None
            if "next_open_price" in cross_section.columns:
                maybe = cross_section.loc[ticker, "next_open_price"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
            if maybe is None or pd.isna(maybe) or float(maybe) <= 0:
                maybe = cross_section.loc[ticker, "open"] if "open" in cross_section.columns else None
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
            if maybe is not None and pd.notna(maybe) and float(maybe) > 0:
                price = float(maybe)

        target_notional = float(weight) * float(equity)
        if price <= 0:
            meta[ticker] = {"shares": 0, "price": 0.0, "target_notional": target_notional, "actual_notional": 0.0, "skipped": True}
            continue

        raw_shares = target_notional / price
        shares = int(raw_shares // board_lot_size) * board_lot_size
        actual_notional = float(shares) * price
        skipped = shares <= 0
        meta[ticker] = {
            "shares": shares,
            "price": price,
            "target_notional": target_notional,
            "actual_notional": actual_notional,
            "skipped": skipped,
        }
        if shares > 0 and actual_notional > 0:
            adjusted[ticker] = actual_notional / float(equity)
    return adjusted, meta


def _extra_execution_cost_bps(cross_section: pd.DataFrame, holdings: dict[str, float], previous_holdings: dict[str, float], execution_cfg: dict) -> tuple[float, list[float]]:
    if not execution_cfg.get("enabled"):
        return 0.0, []
    tick_size = float(execution_cfg["tick_size"])
    base_ticks = float(execution_cfg["base_tick_slippage_ticks"])
    extra_ticks = float(execution_cfg["high_vol_extra_tick_slippage_ticks"])
    min_roundtrip_ticks = float(execution_cfg["minimum_roundtrip_ticks"])
    all_tickers = set(previous_holdings) | set(holdings)
    per_name_bps: list[float] = []
    for ticker in all_tickers:
        trade_weight = abs(float(holdings.get(ticker, 0.0)) - float(previous_holdings.get(ticker, 0.0)))
        if trade_weight <= 1e-12 or ticker not in cross_section.index:
            continue
        px = pd.to_numeric(pd.Series(cross_section.loc[ticker, "next_open_price"]), errors="coerce") if "next_open_price" in cross_section.columns else pd.Series(dtype="float64")
        if px.empty or pd.isna(px.iloc[0]) or float(px.iloc[0]) <= 0:
            px = pd.to_numeric(pd.Series(cross_section.loc[ticker, "open"]), errors="coerce")
        price = float(px.iloc[0]) if not px.empty and pd.notna(px.iloc[0]) and float(px.iloc[0]) > 0 else 0.0
        if price <= 0:
            continue
        vol = float(pd.to_numeric(pd.Series(cross_section.loc[ticker, "rolling_vol_20d"]), errors="coerce").iloc[0]) if "rolling_vol_20d" in cross_section.columns and ticker in cross_section.index else float("nan")
        vol_q80 = float(pd.to_numeric(pd.Series(cross_section.loc[ticker, "rolling_vol_20d_hist_q80"]), errors="coerce").iloc[0]) if "rolling_vol_20d_hist_q80" in cross_section.columns and ticker in cross_section.index else float("nan")
        ticks = base_ticks
        if pd.notna(vol) and pd.notna(vol_q80) and vol_q80 > 0 and vol >= vol_q80:
            ticks += extra_ticks
        ticks = max(ticks, min_roundtrip_ticks)
        bps = float((ticks * tick_size / price) * 10000.0)
        per_name_bps.append(bps)
    if not per_name_bps:
        return 0.0, []
    return float(sum(per_name_bps) / len(per_name_bps)), per_name_bps


def _format_date(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _dataset_attr_date(dataset: pd.DataFrame, key: str, fallback: str) -> str:
    value = dataset.attrs.get(key)
    if value in (None, ""):
        return fallback
    return _format_date(value)


def _build_backtest_coverage_summary(
    original_dataset: pd.DataFrame,
    rebalance_frequency: str,
    executed_rebalance_dates: list[str],
) -> BacktestCoverageSummary:
    original_dates = sorted(pd.to_datetime(original_dataset["date"]).dropna().drop_duplicates().tolist()) if "date" in original_dataset.columns else []
    data_start_date = _format_date(original_dates[0]) if original_dates else ""
    data_end_date = _format_date(original_dates[-1]) if original_dates else ""
    requested_start_date = _dataset_attr_date(original_dataset, "requested_start_date", data_start_date)
    requested_end_date = _dataset_attr_date(original_dataset, "requested_end_date", data_end_date)

    requested_start_ts = pd.to_datetime(requested_start_date) if requested_start_date else None
    requested_end_ts = pd.to_datetime(requested_end_date) if requested_end_date else None
    requested_dates = original_dates
    if requested_start_ts is not None:
        requested_dates = [dt for dt in requested_dates if pd.Timestamp(dt) >= requested_start_ts]
    if requested_end_ts is not None:
        requested_dates = [dt for dt in requested_dates if pd.Timestamp(dt) <= requested_end_ts]

    requested_rebalance_dates = select_rebalance_dates(requested_dates, rebalance_frequency)
    executed_keys = list(executed_rebalance_dates)
    effective_first = executed_keys[0] if executed_keys else ""
    effective_last = executed_keys[-1] if executed_keys else ""
    effective_last_ts = pd.to_datetime(effective_last) if effective_last else None
    dropped_tail_dates = [
        _format_date(dt)
        for dt in requested_rebalance_dates
        if effective_last_ts is None or pd.Timestamp(dt) > effective_last_ts
    ]

    window = BacktestWindow(
        requested_start_date=requested_start_date,
        requested_end_date=requested_end_date,
        effective_first_rebalance_date=effective_first,
        effective_last_rebalance_date=effective_last,
        data_start_date=_dataset_attr_date(original_dataset, "data_start_date", data_start_date),
        data_end_date=_dataset_attr_date(original_dataset, "data_end_date", data_end_date),
        rebalance_count=len(executed_keys),
        tail_truncated_rebalance_count=len(dropped_tail_dates),
    )
    return BacktestCoverageSummary(
        window=window,
        total_requested_days=len(requested_dates),
        total_valid_rebalance_dates=len(executed_keys),
        dropped_tail_dates=dropped_tail_dates,
    )


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
    validate_frequency_horizon_pair(rebalance_frequency, horizon)
    execution_cfg = _execution_config(dataset)
    return_col = f"delayed_future_return_{horizon}d" if execution_cfg.get("enabled") and f"delayed_future_return_{horizon}d" in dataset.columns else f"future_return_{horizon}d"
    validate_backtest_dataset(dataset, factor_col, return_col)
    original_dataset = dataset.copy()
    original_dataset.attrs = dict(getattr(dataset, "attrs", {}))
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col])

    turnover_limit = _turnover_limit(sample, rebalance_frequency)
    initial_aum = _initial_aum(sample)
    board_lot_enabled = _board_lot_enabled(sample)
    board_lot_size = _board_lot_size(sample)
    if execution_cfg.get("enabled") and execution_cfg.get("commission_bps_override") is not None:
        commission_bps = float(execution_cfg["commission_bps_override"])

    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), rebalance_frequency)
    returns: list[float] = []
    equity_curve: list[float] = []
    holdings_by_date: dict[str, list[str]] = {}
    position_details_by_date: dict[str, dict[str, dict[str, float | int | bool]]] = {}
    per_name_accounting_by_date: dict[str, dict[str, dict[str, float | int | bool]]] = {}
    cash_accounting_by_date: dict[str, dict[str, float]] = {}
    returns_by_date: dict[str, float] = {}
    turnover_by_date: dict[str, float] = {}
    cost_by_date: dict[str, float] = {}
    gross_return_by_date: dict[str, float] = {}
    previous_holdings: dict[str, float] = {}
    previous_end_notional_by_ticker: dict[str, float] = {}
    previous_cash_end_cny = initial_aum
    turnover_values: list[float] = []
    cost_paid = 0.0
    impact_cost_paid = 0.0
    equity = 1.0
    execution_bucket_counts: dict[str, int] = {"very_light": 0, "light": 0, "medium": 0, "heavy": 0, "extreme": 0}
    participation_rates: list[float] = []
    impact_bps_values: list[float] = []
    execution_by_rebalance_date: dict[str, dict[str, float | int | bool | None]] = {}

    for dt in rebalance_dates:
        cross_section = sample.loc[sample["date"] == dt].copy()
        if cross_section.empty:
            continue
        if weighting == "score":
            raw_holdings = build_topn_score_weight_portfolio(cross_section, factor_col, top_n)
        elif weighting == "liquidity_tilted_score":
            raw_holdings = build_topn_liquidity_tilted_score_weight_portfolio(cross_section, factor_col, top_n)
        else:
            raw_holdings = build_topn_equal_weight_portfolio(cross_section, factor_col, top_n)
        if not raw_holdings:
            continue
        holdings = _apply_turnover_limit(previous_holdings, raw_holdings, turnover_limit)
        if not holdings:
            continue
        cross_section = cross_section.set_index("ticker")
        board_lot_meta: dict[str, dict[str, float | int | bool]] = {}
        if board_lot_enabled:
            holdings, board_lot_meta = _apply_board_lot_constraints(holdings, cross_section, float(equity) * float(initial_aum), board_lot_size=board_lot_size)
            if not holdings:
                continue
        current_equity = float(equity)
        current_equity_cny = current_equity * float(initial_aum)
        all_tickers = set(previous_holdings.keys()) | set(holdings.keys())

        if "close" not in cross_section.columns:
            raise ValueError("backtest dataset missing required mark-to-market column: close")

        def _entry_price_for_ticker(ticker: str) -> float:
            if ticker not in cross_section.index:
                return 0.0
            maybe = None
            if "next_open_price" in cross_section.columns:
                maybe = cross_section.loc[ticker, "next_open_price"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
                if maybe is not None and pd.notna(maybe) and float(maybe) > 0:
                    return float(maybe)
            if "open" in cross_section.columns:
                maybe = cross_section.loc[ticker, "open"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
                if maybe is not None and pd.notna(maybe) and float(maybe) > 0:
                    return float(maybe)
            return 0.0

        def _mark_price_for_ticker(ticker: str) -> float:
            if ticker not in cross_section.index:
                return 0.0
            maybe = cross_section.loc[ticker, "close"]
            if hasattr(maybe, "iloc"):
                maybe = maybe.iloc[0]
            if maybe is not None and pd.notna(maybe) and float(maybe) > 0:
                return float(maybe)
            return 0.0

        marked_end_notional_by_ticker: dict[str, float] = {}
        gross_pnl_cny_by_ticker: dict[str, float] = {}
        per_name_gross: dict[str, float] = {}

        for ticker in all_tickers:
            target_notional = 0.0
            if board_lot_enabled and ticker in board_lot_meta:
                target_notional = float(board_lot_meta[ticker].get('actual_notional', 0.0) or 0.0)
            elif ticker in holdings:
                target_notional = float(holdings.get(ticker, 0.0)) * current_equity_cny

            entry_price = _entry_price_for_ticker(ticker)
            mark_price = _mark_price_for_ticker(ticker)
            if target_notional > 1e-12 and (entry_price <= 0 or mark_price <= 0):
                raise ValueError(f"backtest dataset missing valid execution/mark price for ticker {ticker} on {pd.Timestamp(dt).strftime('%Y-%m-%d')}")

            if board_lot_enabled and ticker in board_lot_meta:
                shares = int(board_lot_meta[ticker].get('shares', 0) or 0)
                mark_end_notional = float(shares) * mark_price if shares > 0 and mark_price > 0 else 0.0
                board_lot_meta[ticker]['mark_price'] = mark_price
            else:
                mark_end_notional = target_notional * (mark_price / entry_price) if target_notional > 0 and entry_price > 0 and mark_price > 0 else 0.0

            gross_pnl_cny = mark_end_notional - target_notional
            marked_end_notional_by_ticker[ticker] = mark_end_notional
            gross_pnl_cny_by_ticker[ticker] = gross_pnl_cny
            per_name_gross[ticker] = gross_pnl_cny / current_equity_cny if current_equity_cny > 0 else 0.0

        gross_pnl_total_cny = float(sum(gross_pnl_cny_by_ticker.values()))
        gross = gross_pnl_total_cny / current_equity_cny if current_equity_cny > 0 else 0.0
        turnover = turnover_from_holdings(previous_holdings, holdings)
        turnover_values.append(turnover)
        extra_slippage_bps, extra_slippage_per_name = _extra_execution_cost_bps(cross_section, holdings, previous_holdings, execution_cfg)
        base_cost = estimate_transaction_cost(turnover, commission_bps, slippage_bps + extra_slippage_bps)
        impact_cost = 0.0
        date_key = pd.Timestamp(dt).strftime("%Y-%m-%d")
        per_name_rates: list[float] = []
        per_name_bps: list[float] = list(extra_slippage_per_name)
        for ticker in all_tickers:
            target_weight = float(holdings.get(ticker, 0.0))
            current_weight = float(previous_holdings.get(ticker, 0.0))
            trade_notional = abs(target_weight - current_weight) * current_equity
            amount = None
            if ticker in cross_section.index and "amount" in cross_section.columns:
                maybe = cross_section.loc[ticker, "amount"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
                amount = maybe
            estimate = estimate_dynamic_impact_bps(trade_notional, float(amount) if amount is not None and pd.notna(amount) else 0.0)
            impact_cost += trade_notional * estimate.impact_bps / 10000.0
            per_name_rates.append(float(estimate.participation_rate))
            per_name_bps.append(float(estimate.impact_bps))
            participation_rates.append(float(estimate.participation_rate))
            impact_bps_values.append(float(estimate.impact_bps))
            execution_bucket_counts[estimate.bucket_label] = execution_bucket_counts.get(estimate.bucket_label, 0) + 1
        cost = base_cost + impact_cost
        net = gross - cost

        invested_start = 0.0
        if board_lot_enabled:
            invested_start = float(sum(float(meta.get("actual_notional", 0.0) or 0.0) for meta in board_lot_meta.values()))
        else:
            invested_start = float(sum(float(w) for w in holdings.values()) * current_equity_cny)
        cash_start = previous_cash_end_cny
        cost_cny = float(cost) * current_equity_cny
        net_pnl_total_cny = gross_pnl_total_cny - cost_cny

        accounting_for_date: dict[str, dict[str, float | int | bool]] = {}
        total_abs_trade = 0.0
        total_trade_net_notional = 0.0
        for ticker in all_tickers:
            start_notional = float(previous_end_notional_by_ticker.get(ticker, 0.0))
            target_notional = 0.0
            if board_lot_enabled and ticker in board_lot_meta:
                target_notional = float(board_lot_meta[ticker].get('actual_notional', 0.0) or 0.0)
            elif ticker in holdings:
                target_notional = float(holdings.get(ticker, 0.0)) * current_equity_cny
            gross_pnl_cny = float(gross_pnl_cny_by_ticker.get(ticker, 0.0))
            trade_abs = abs(target_notional - start_notional)
            trade_net_notional = target_notional - start_notional
            total_abs_trade += trade_abs
            total_trade_net_notional += trade_net_notional
            accounting_for_date[ticker] = {
                'start_notional': start_notional,
                'target_notional': target_notional,
                'gross_pnl_cny': gross_pnl_cny,
                'trade_abs_notional': trade_abs,
                'trade_net_notional': trade_net_notional,
            }

        for ticker, item in accounting_for_date.items():
            trade_abs = float(item['trade_abs_notional'])
            allocated_cost_cny = cost_cny * (trade_abs / total_abs_trade) if total_abs_trade > 1e-12 else 0.0
            post_trade_notional = float(item['start_notional']) + float(item['trade_net_notional'])
            end_notional = float(marked_end_notional_by_ticker.get(ticker, post_trade_notional + float(item['gross_pnl_cny'])))
            item['allocated_cost_cny'] = allocated_cost_cny
            item['post_trade_notional'] = post_trade_notional
            item['net_pnl_cny'] = float(item['gross_pnl_cny']) - allocated_cost_cny
            item['end_notional'] = end_notional

        cash_trade_flow = total_trade_net_notional
        cash_end = cash_start - cash_trade_flow - cost_cny
        cash_accounting_by_date[date_key] = {
            'cash_start': cash_start,
            'cash_trade_flow': cash_trade_flow,
            'cash_end': cash_end,
            'cost_cny': cost_cny,
            'gross_pnl_total_cny': gross_pnl_total_cny,
            'net_pnl_total_cny': net_pnl_total_cny,
        }
        returns.append(float(net))
        cost_paid += cost
        impact_cost_paid += impact_cost
        equity *= (1.0 + float(net))
        equity_curve.append(float(equity))
        holdings_by_date[date_key] = list(holdings.keys())
        if board_lot_enabled:
            position_details_by_date[date_key] = board_lot_meta
        per_name_accounting_by_date[date_key] = accounting_for_date
        returns_by_date[date_key] = float(net)
        turnover_by_date[date_key] = float(turnover)
        cost_by_date[date_key] = float(cost)
        gross_return_by_date[date_key] = float(gross)
        execution_by_rebalance_date[date_key] = {
            "avg_participation_rate": float(sum(per_name_rates) / len(per_name_rates)) if per_name_rates else 0.0,
            "max_participation_rate": float(max(per_name_rates)) if per_name_rates else 0.0,
            "impact_cost_bps": float(sum(per_name_bps) / len(per_name_bps)) if per_name_bps else 0.0,
            "extreme_count": int(sum(1 for x in per_name_bps if x >= 100.0)),
            "applied_turnover_limit": float(turnover_limit) if turnover_limit is not None else None,
            "used_delayed_execution": bool(execution_cfg.get("enabled")),
        }
        previous_holdings = holdings
        previous_end_notional_by_ticker = {
            ticker: float(item['end_notional'])
            for ticker, item in accounting_for_date.items()
            if abs(float(item['end_notional'])) > 1e-12
        }
        previous_cash_end_cny = float(cash_end)

    bm = run_benchmark(sample, return_col, benchmark, rebalance_frequency)
    ppy = periods_per_year(rebalance_frequency)
    coverage_summary = _build_backtest_coverage_summary(
        original_dataset=original_dataset,
        rebalance_frequency=rebalance_frequency,
        executed_rebalance_dates=list(returns_by_date.keys()),
    )
    coverage_payload = asdict(coverage_summary)
    payload = {
        "factor_name": factor_col.replace("factor:", ""),
        "horizon": horizon,
        "top_n": top_n,
        "rebalance_frequency": rebalance_frequency,
        "weighting": weighting,
        "benchmark_name": bm["name"],
        "accounting_method": "mark_to_market_close",
        "mark_price_field": "close",
        "research_label_return_column": return_col,
        "backtest_window": coverage_payload["window"],
        "backtest_coverage_summary": coverage_payload,
        "annual_return": annual_return(returns, ppy),
        "total_return": total_return(equity_curve),
        "max_drawdown": max_drawdown(equity_curve),
        "sharpe": sharpe_ratio(returns, ppy),
        "turnover": float(sum(turnover_values) / len(turnover_values)) if turnover_values else 0.0,
        "annualized_one_way_turnover": float((sum(turnover_values) / len(turnover_values)) * ppy) if turnover_values else 0.0,
        "win_rate": win_rate(returns),
        "cost_paid": float(cost_paid),
        "base_cost_paid": float(cost_paid - impact_cost_paid),
        "impact_cost_paid": float(impact_cost_paid),
        "total_cost_paid_with_impact": float(cost_paid),
        "holdings_by_rebalance_date": holdings_by_date,
        "position_details_by_rebalance_date": position_details_by_date,
        "per_name_accounting_by_rebalance_date": per_name_accounting_by_date,
        "cash_accounting_by_rebalance_date": cash_accounting_by_date,
        "returns_by_rebalance_date": returns_by_date,
        "gross_return_by_rebalance_date": gross_return_by_date,
        "turnover_by_rebalance_date": turnover_by_date,
        "cost_by_rebalance_date": cost_by_date,
        "execution_by_rebalance_date": execution_by_rebalance_date,
        "execution_diagnostics": {
            "impact_model": "dynamic_impact_v1",
            "assumed_fill_mode": "next_open_plus_tick" if execution_cfg.get("enabled") else "full_fill_with_impact_penalty",
            "bar_delay": execution_cfg.get("bar_delay"),
            "partial_fill_model_enabled": False,
            "avg_participation_rate": float(sum(participation_rates) / len(participation_rates)) if participation_rates else 0.0,
            "p90_participation_rate": float(pd.Series(participation_rates).quantile(0.90)) if participation_rates else 0.0,
            "max_participation_rate": float(max(participation_rates)) if participation_rates else 0.0,
            "avg_dynamic_impact_bps": float(sum(impact_bps_values) / len(impact_bps_values)) if impact_bps_values else 0.0,
            "p90_dynamic_impact_bps": float(pd.Series(impact_bps_values).quantile(0.90)) if impact_bps_values else 0.0,
            "max_dynamic_impact_bps": float(max(impact_bps_values)) if impact_bps_values else 0.0,
            "bucket_counts": execution_bucket_counts,
            "impact_cost_paid": float(impact_cost_paid),
            "total_cost_paid_with_impact": float(cost_paid),
            "turnover_limit_per_rebalance": turnover_limit,
        },
        "equity_curve": equity_curve,
        "benchmark_equity_curve": bm["equity_curve"],
        "benchmark_returns": bm["returns"],
        "excess_return_vs_benchmark": total_return(equity_curve) - total_return(bm["equity_curve"]),
    }
    return BacktestResult(factor_name=payload["factor_name"], payload=payload)
