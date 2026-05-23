from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPORTS_DIR = Path('data/reports')
ENGINE_PATH = REPORTS_DIR / 'growth_personal_100k_2024_2026_boardlot_engine_latest.json'
PERIOD_PATH = REPORTS_DIR / 'growth_personal_100k_2024_2026_boardlot_rebalance_detail_latest.json'
LEDGER_OUT = REPORTS_DIR / 'growth_personal_100k_2024_2026_boardlot_stock_ledger_closed_latest.json'
SUMMARY_OUT = REPORTS_DIR / 'growth_personal_100k_2024_2026_boardlot_stock_summary_closed_latest.json'
INITIAL_AUM = 100_000.0
REFERENCE_PATH = Path('data/raw/reference/stock_basic_main_board.parquet')


def main() -> None:
    engine = json.loads(ENGINE_PATH.read_text(encoding='utf-8'))['summary']['result']
    period = json.loads(PERIOD_PATH.read_text(encoding='utf-8'))
    rows = period['rebalances']
    details = engine['position_details_by_rebalance_date']
    accounting = engine['per_name_accounting_by_rebalance_date']
    cash_by_date = engine['cash_accounting_by_rebalance_date']

    name_map: dict[str, str] = {}
    if REFERENCE_PATH.exists():
        try:
            ref_df = pd.read_parquet(REFERENCE_PATH)
            if 'ticker' in ref_df.columns and 'name' in ref_df.columns:
                ref_df = ref_df[['ticker', 'name']].copy()
                ref_df['ticker'] = ref_df['ticker'].astype(str).str.lower().str.strip()
                ref_df['name'] = ref_df['name'].astype('string').str.strip()
                name_map = {
                    str(row['ticker']): str(row['name'])
                    for _, row in ref_df.dropna(subset=['ticker']).drop_duplicates(subset=['ticker'], keep='last').iterrows()
                }
        except Exception:
            name_map = {}

    trades = []
    snapshots = []
    closed_trades = []
    per_ticker = defaultdict(lambda: {
        'ticker': '',
        'name': '',
        'buy_count': 0,
        'sell_count': 0,
        'buy_shares_total': 0,
        'sell_shares_total': 0,
        'buy_notional_total': 0.0,
        'sell_notional_total': 0.0,
        'realized_pnl_total': 0.0,
        'latest_shares_held': 0,
        'latest_avg_cost': 0.0,
        'latest_reference_price': 0.0,
        'latest_position_notional': 0.0,
        'latest_snapshot_date': '',
        'unrealized_pnl': 0.0,
        'total_pnl': 0.0,
        'cumulative_end_notional': 0.0,
        'cumulative_cost_allocated': 0.0,
    })
    inventory = defaultdict(lambda: {'shares': 0, 'avg_cost': 0.0})
    prev_positions: dict[str, int] = {}

    for row in rows:
        d = row['date']
        start_equity = float(row['start_equity'])
        day_details = details.get(d, {})
        day_acc = accounting.get(d, {})
        current_positions = {t: int(v.get('shares', 0)) for t, v in day_details.items() if int(v.get('shares', 0)) > 0}
        tickers = sorted(set(prev_positions) | set(current_positions))

        for t in tickers:
            prev_shares = int(prev_positions.get(t, 0))
            new_shares = int(current_positions.get(t, 0))
            meta = day_details.get(t, {})
            price = float(meta.get('price', 0.0) or 0.0)
            row_acc = per_ticker[t]
            row_acc['ticker'] = t
            row_acc['name'] = name_map.get(t, '')
            inv = inventory[t]

            if new_shares > prev_shares:
                buy_shares = new_shares - prev_shares
                if buy_shares > 0 and price > 0:
                    total_cost = inv['shares'] * inv['avg_cost'] + buy_shares * price
                    inv['shares'] += buy_shares
                    inv['avg_cost'] = total_cost / inv['shares'] if inv['shares'] > 0 else 0.0
                    trade_notional = buy_shares * price
                    trades.append({
                        'date': d,
                        'ticker': t,
                        'name': name_map.get(t, ''),
                        'side': 'BUY',
                        'price': price,
                        'shares': buy_shares,
                        'trade_notional': round(trade_notional, 6),
                        'prev_weight': (prev_shares * price / start_equity) if start_equity > 0 else 0.0,
                        'new_weight': (new_shares * price / start_equity) if start_equity > 0 else 0.0,
                        'delta_weight': ((new_shares - prev_shares) * price / start_equity) if start_equity > 0 else 0.0,
                        'realized_pnl': '',
                    })
                    row_acc['buy_count'] += 1
                    row_acc['buy_shares_total'] += buy_shares
                    row_acc['buy_notional_total'] += trade_notional
            elif prev_shares > new_shares:
                sell_shares = prev_shares - new_shares
                if sell_shares > 0 and price > 0:
                    avg_cost = float(inv['avg_cost'])
                    trade_notional = sell_shares * price
                    realized_cash_pnl = (price - avg_cost) * sell_shares
                    inv['shares'] -= sell_shares
                    if inv['shares'] <= 0:
                        inv['shares'] = 0
                        inv['avg_cost'] = 0.0
                    trades.append({
                        'date': d,
                        'ticker': t,
                        'side': 'SELL',
                        'price': price,
                        'shares': sell_shares,
                        'trade_notional': round(trade_notional, 6),
                        'prev_weight': (prev_shares * price / start_equity) if start_equity > 0 else 0.0,
                        'new_weight': (new_shares * price / start_equity) if start_equity > 0 else 0.0,
                        'delta_weight': ((new_shares - prev_shares) * price / start_equity) if start_equity > 0 else 0.0,
                        'realized_pnl': round(realized_cash_pnl, 6),
                    })
                    closed_trades.append({
                        'date': d,
                        'ticker': t,
                        'name': name_map.get(t, ''),
                        'sell_price': price,
                        'sell_shares': sell_shares,
                        'avg_cost': round(avg_cost, 6),
                        'realized_pnl': round(realized_cash_pnl, 6),
                    })
                    row_acc['sell_count'] += 1
                    row_acc['sell_shares_total'] += sell_shares
                    row_acc['sell_notional_total'] += trade_notional
                    row_acc['realized_pnl_total'] += realized_cash_pnl

        prev_positions = current_positions
        end_equity = float(row['end_equity'])
        for t, shares in current_positions.items():
            acc = day_acc[t]
            end_notional = float(acc.get('end_notional', 0.0) or 0.0)
            end_price = end_notional / shares if shares > 0 else 0.0
            snapshots.append({
                'date': d,
                'ticker': t,
                'name': name_map.get(t, ''),
                'weight': end_notional / end_equity if end_equity > 0 else 0.0,
                'position_notional': round(end_notional, 6),
                'reference_price': round(end_price, 6),
                'shares_held': shares,
                'avg_cost': round(inventory[t]['avg_cost'], 6),
                'gross_pnl_cny': round(float(acc.get('gross_pnl_cny', 0.0) or 0.0), 6),
                'allocated_cost_cny': round(float(acc.get('allocated_cost_cny', 0.0) or 0.0), 6),
                'net_pnl_cny': round(float(acc.get('net_pnl_cny', 0.0) or 0.0), 6),
            })
            row_acc = per_ticker[t]
            row_acc['latest_shares_held'] = shares
            row_acc['latest_avg_cost'] = round(inventory[t]['avg_cost'], 6)
            row_acc['latest_reference_price'] = round(end_price, 6)
            row_acc['latest_position_notional'] = round(end_notional, 6)
            row_acc['latest_snapshot_date'] = d
            row_acc['cumulative_end_notional'] = round(end_notional, 6)
            row_acc['cumulative_cost_allocated'] += float(acc.get('allocated_cost_cny', 0.0) or 0.0)

    final_cash = float(cash_by_date[rows[-1]['date']]['cash_end'])
    final_date = rows[-1]['date']
    final_accounting = accounting.get(final_date, {})
    final_details = details.get(final_date, {})

    for t, row_acc in per_ticker.items():
        if t in final_accounting:
            final_end_notional = float(final_accounting[t].get('end_notional', 0.0) or 0.0)
            final_shares = int(final_details.get(t, {}).get('shares', 0) or 0)
            final_price = final_end_notional / final_shares if final_shares > 0 else 0.0
            row_acc['latest_shares_held'] = final_shares
            row_acc['latest_reference_price'] = round(final_price, 6)
            row_acc['latest_position_notional'] = round(final_end_notional, 6)
            row_acc['latest_snapshot_date'] = final_date
        else:
            row_acc['latest_shares_held'] = 0
            row_acc['latest_reference_price'] = 0.0
            row_acc['latest_position_notional'] = 0.0
        remaining_cost_basis = row_acc['latest_shares_held'] * row_acc['latest_avg_cost']
        row_acc['unrealized_pnl'] = round(row_acc['latest_position_notional'] - remaining_cost_basis, 6)
        row_acc['realized_pnl_total'] = round(float(row_acc['realized_pnl_total']), 6)
        row_acc['total_pnl'] = round(
            float(row_acc['realized_pnl_total']) + float(row_acc['unrealized_pnl']),
            6,
        )
        row_acc['buy_notional_total'] = round(row_acc['buy_notional_total'], 6)
        row_acc['sell_notional_total'] = round(row_acc['sell_notional_total'], 6)
        row_acc['cumulative_end_notional'] = round(row_acc['cumulative_end_notional'], 6)
        row_acc['cumulative_cost_allocated'] = round(row_acc['cumulative_cost_allocated'], 6)

    rows_out = sorted(per_ticker.values(), key=lambda x: x['cumulative_end_notional'], reverse=True)
    stocks_total_end_notional = sum(x['latest_position_notional'] for x in rows_out)
    reconstructed_end = stocks_total_end_notional + final_cash
    period_end = float(period['summary']['aum_end'])

    ledger = {
        'summary': {
            'strategy_id': 'revgrowth_always_on_v1',
            'window': period['summary']['window'],
            'aum_start': INITIAL_AUM,
            'aum_end': period_end,
            'cash_end': round(final_cash, 6),
            'rebalance_count': period['summary']['rebalance_count'],
            'trade_row_count': len(trades),
            'position_snapshot_row_count': len(snapshots),
            'closed_trade_row_count': len(closed_trades),
            'note': '基于引擎直接输出的 per_name_accounting_by_rebalance_date 重建的闭合单股账本。',
        },
        'trades': trades,
        'position_snapshots': snapshots,
        'closed_trades': closed_trades,
        'cash_end': round(final_cash, 6),
    }
    LEDGER_OUT.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    summary = {
        'summary': {
            'ticker_count': len(rows_out),
            'cash_end': round(final_cash, 6),
            'note': '基于引擎直接输出的 per_name_accounting_by_rebalance_date 重建的闭合股票汇总表。',
        },
        'rows': rows_out,
    }
    SUMMARY_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(str(LEDGER_OUT))
    print(str(SUMMARY_OUT))
    print(json.dumps({
        'stocks_total_end_notional': round(stocks_total_end_notional, 6),
        'cash_end': round(final_cash, 6),
        'reconstructed_end': round(reconstructed_end, 6),
        'period_end': round(period_end, 6),
        'gap': round(reconstructed_end - period_end, 6),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
