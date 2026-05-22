from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

REPORTS_DIR = Path("data/reports")
INPUT_LEDGER = REPORTS_DIR / "growth_personal_100k_turnover_v2_1_stock_ledger_latest.json"
OUTPUT_LEDGER = REPORTS_DIR / "growth_personal_100k_turnover_v2_1_stock_ledger_boardlot_latest.json"
OUTPUT_SUMMARY = REPORTS_DIR / "growth_personal_100k_turnover_v2_1_stock_summary_boardlot_latest.json"
BOARD_LOT = 100


def floor_board_lot(shares: float) -> int:
    if not shares or shares <= 0:
        return 0
    return int(math.floor(shares / BOARD_LOT) * BOARD_LOT)


def main() -> None:
    payload = json.loads(INPUT_LEDGER.read_text(encoding="utf-8"))
    trades: list[dict[str, Any]] = payload.get("trades", [])
    original_snapshots: list[dict[str, Any]] = payload.get("position_snapshots", [])

    inventory: dict[str, dict[str, float]] = defaultdict(lambda: {"shares": 0.0, "avg_cost": 0.0})
    adjusted_trades: list[dict[str, Any]] = []
    closed_trades: list[dict[str, Any]] = []
    trades_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in trades:
        date = str(row["date"])
        ticker = str(row["ticker"])
        side = str(row["side"]).upper()
        price = float(row["price"])
        raw_shares = float(row["shares"])
        board_shares = floor_board_lot(raw_shares)
        if board_shares <= 0:
            continue

        pos = inventory[ticker]
        realized = ""

        if side == "BUY":
            prev_shares = float(pos["shares"])
            prev_cost = float(pos["avg_cost"])
            new_notional = board_shares * price
            total_notional = prev_shares * prev_cost + new_notional
            new_shares = prev_shares + board_shares
            pos["shares"] = new_shares
            pos["avg_cost"] = (total_notional / new_shares) if new_shares > 0 else 0.0
        else:
            sellable = min(board_shares, floor_board_lot(float(pos["shares"])))
            if sellable <= 0:
                continue
            board_shares = sellable
            avg_cost = float(pos["avg_cost"])
            realized_value = (price - avg_cost) * board_shares
            realized = round(realized_value, 6)
            pos["shares"] = max(float(pos["shares"]) - board_shares, 0.0)
            if pos["shares"] <= 1e-12:
                pos["shares"] = 0.0
                pos["avg_cost"] = 0.0
            closed_trades.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "sell_price": price,
                    "sell_shares": board_shares,
                    "avg_cost": round(avg_cost, 6),
                    "estimated_realized_pnl": realized,
                }
            )

        trade_row = {
            "date": date,
            "ticker": ticker,
            "side": side,
            "price": price,
            "shares": board_shares,
            "trade_notional": round(board_shares * price, 6),
            "prev_weight": row.get("prev_weight", 0.0),
            "new_weight": row.get("new_weight", 0.0),
            "delta_weight": row.get("delta_weight", 0.0),
            "estimated_realized_pnl": realized,
        }
        adjusted_trades.append(trade_row)
        trades_by_date[date].append(trade_row)

    snapshot_price_lookup: dict[tuple[str, str], tuple[float, float]] = {}
    for row in original_snapshots:
        key = (str(row.get("date")), str(row.get("ticker")))
        snapshot_price_lookup[key] = (
            float(row.get("reference_price") or 0.0),
            float(row.get("weight") or 0.0),
        )

    position_snapshots: list[dict[str, Any]] = []
    running_inventory: dict[str, dict[str, float]] = defaultdict(lambda: {"shares": 0.0, "avg_cost": 0.0})
    seen_dates = sorted(trades_by_date.keys())
    for date in seen_dates:
        for tr in trades_by_date[date]:
            pos = running_inventory[tr["ticker"]]
            side = tr["side"]
            shares = float(tr["shares"])
            price = float(tr["price"])
            if side == "BUY":
                prev_shares = float(pos["shares"])
                prev_cost = float(pos["avg_cost"])
                total_cost = prev_shares * prev_cost + shares * price
                new_shares = prev_shares + shares
                pos["shares"] = new_shares
                pos["avg_cost"] = total_cost / new_shares if new_shares > 0 else 0.0
            else:
                pos["shares"] = max(float(pos["shares"]) - shares, 0.0)
                if pos["shares"] <= 1e-12:
                    pos["shares"] = 0.0
                    pos["avg_cost"] = 0.0
        for ticker, pos in sorted(running_inventory.items()):
            if float(pos["shares"]) <= 0:
                continue
            ref_price, weight = snapshot_price_lookup.get((date, ticker), (0.0, 0.0))
            position_snapshots.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "weight": weight,
                    "position_notional_est": round(float(pos["shares"]) * ref_price, 6) if ref_price > 0 else 0.0,
                    "reference_price": ref_price,
                    "estimated_shares_held": int(pos["shares"]),
                    "estimated_avg_cost": round(float(pos["avg_cost"]), 6),
                }
            )

    by_ticker: dict[str, dict[str, Any]] = {}
    for tr in adjusted_trades:
        ticker = tr["ticker"]
        row = by_ticker.setdefault(
            ticker,
            {
                "ticker": ticker,
                "buy_count": 0,
                "sell_count": 0,
                "buy_shares_total": 0,
                "sell_shares_total": 0,
                "buy_notional_total": 0.0,
                "sell_notional_total": 0.0,
                "estimated_realized_pnl_total": 0.0,
                "latest_estimated_shares_held": 0,
                "latest_estimated_avg_cost": 0.0,
                "latest_reference_price": 0.0,
                "latest_position_notional_est": 0.0,
                "latest_snapshot_date": "",
                "estimated_unrealized_pnl": 0.0,
                "estimated_total_pnl": 0.0,
            },
        )
        shares = int(tr["shares"])
        notional = float(tr["trade_notional"])
        if tr["side"] == "BUY":
            row["buy_count"] += 1
            row["buy_shares_total"] += shares
            row["buy_notional_total"] += notional
        else:
            row["sell_count"] += 1
            row["sell_shares_total"] += shares
            row["sell_notional_total"] += notional
            pnl = tr.get("estimated_realized_pnl", "")
            if pnl != "":
                row["estimated_realized_pnl_total"] += float(pnl)

    latest_snap_by_ticker: dict[str, dict[str, Any]] = {}
    for snap in position_snapshots:
        latest_snap_by_ticker[snap["ticker"]] = snap
    for ticker, row in by_ticker.items():
        snap = latest_snap_by_ticker.get(ticker)
        if snap:
            row["latest_estimated_shares_held"] = int(snap["estimated_shares_held"])
            row["latest_estimated_avg_cost"] = round(float(snap["estimated_avg_cost"]), 6)
            row["latest_reference_price"] = float(snap["reference_price"])
            row["latest_position_notional_est"] = round(float(snap["position_notional_est"]), 6)
            row["latest_snapshot_date"] = str(snap["date"])
            row["estimated_unrealized_pnl"] = round(
                (float(snap["reference_price"]) - float(snap["estimated_avg_cost"]))
                * float(snap["estimated_shares_held"]),
                6,
            )
        row["estimated_realized_pnl_total"] = round(float(row["estimated_realized_pnl_total"]), 6)
        row["estimated_total_pnl"] = round(
            float(row["estimated_realized_pnl_total"]) + float(row["estimated_unrealized_pnl"]),
            6,
        )

    ledger_out = {
        "summary": {
            **payload.get("summary", {}),
            "trade_row_count": len(adjusted_trades),
            "position_snapshot_row_count": len(position_snapshots),
            "closed_trade_row_count": len(closed_trades),
            "note": "按原 v2.1 回测执行口径重建，并额外应用 A 股 100 股一手约束；股票层账本用于人工核算核查，组合层最终资金仍以 period-level 报告为准。",
        },
        "trades": adjusted_trades,
        "position_snapshots": position_snapshots,
        "closed_trades": closed_trades,
    }
    OUTPUT_LEDGER.write_text(json.dumps(ledger_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary_out = {
        "summary": {
            "ticker_count": len(by_ticker),
            "note": "按 100 股一手约束重建的股票汇总表。",
        },
        "rows": sorted(by_ticker.values(), key=lambda x: x["estimated_total_pnl"], reverse=True),
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(str(OUTPUT_LEDGER))
    print(str(OUTPUT_SUMMARY))
    print(json.dumps({
        "trade_rows": len(adjusted_trades),
        "closed_trade_rows": len(closed_trades),
        "position_snapshot_rows": len(position_snapshots),
        "ticker_count": len(by_ticker),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
