
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.domain.backtest.portfolio_construction import build_topn_liquidity_tilted_score_weight_portfolio
from app.domain.backtest.rebalance_calendar import select_rebalance_dates
from app.domain.data_contracts import factor_column
from scripts.build_research_realism_stress import load_registry_and_reviews, find_registry_item, latest_review, build_candidate_dataset

AUM = 100_000.0
TOP_N = 20
STRATEGY_ID = 'revgrowth_always_on_v1'
REPORTS_DIR = Path('data/reports')

registry, reviews, *_ = load_registry_and_reviews('growth_line')
registry_item = find_registry_item(registry, STRATEGY_ID)
review = latest_review(reviews, STRATEGY_ID)
dataset = build_candidate_dataset('growth_line', registry_item, review)

dataset = dataset.copy()
dataset['date'] = pd.to_datetime(dataset['date'])
if 'is_valid_sample' in dataset.columns:
    dataset = dataset.loc[dataset['is_valid_sample'] == True].copy()

factor_col = factor_column(registry_item['factor'])
dataset[factor_col] = pd.to_numeric(dataset[factor_col], errors='coerce')
dataset['close'] = pd.to_numeric(dataset['close'], errors='coerce')
dataset['amount'] = pd.to_numeric(dataset['amount'], errors='coerce')
dataset = dataset.dropna(subset=[factor_col, 'close', 'amount'])
rebalance_dates = select_rebalance_dates(dataset['date'].tolist(), str(registry_item['params']['rebalance_frequency']))

rows = []
per_date = []
for dt in rebalance_dates:
    cross = dataset.loc[dataset['date'] == dt].copy()
    if cross.empty:
        continue
    holdings = build_topn_liquidity_tilted_score_weight_portfolio(cross, factor_col, TOP_N)
    if not holdings:
        continue
    cross = cross.set_index('ticker')
    infeasible = 0
    for ticker, weight in holdings.items():
        if ticker not in cross.index:
            continue
        row = cross.loc[ticker]
        if hasattr(row, 'iloc') and getattr(row, 'ndim', 1) > 1:
            row = row.iloc[0]
        close = float(row['close'])
        amount = float(row['amount'])
        position_notional = AUM * float(weight)
        min_lot_notional = close * 100.0
        shares_float = position_notional / close if close > 0 else 0.0
        round_lots_affordable = int(position_notional // min_lot_notional) if min_lot_notional > 0 else 0
        is_feasible = position_notional >= min_lot_notional and round_lots_affordable >= 1
        if not is_feasible:
            infeasible += 1
        rows.append({
            'date': pd.Timestamp(dt).strftime('%Y-%m-%d'),
            'ticker': str(ticker),
            'weight': float(weight),
            'close': close,
            'amount': amount,
            'position_notional': position_notional,
            'min_lot_notional': min_lot_notional,
            'shares_float': shares_float,
            'round_lots_affordable': round_lots_affordable,
            'is_board_lot_feasible': bool(is_feasible),
        })
    per_date.append({
        'date': pd.Timestamp(dt).strftime('%Y-%m-%d'),
        'holding_count': len(holdings),
        'infeasible_count': infeasible,
        'feasible_ratio': (len(holdings) - infeasible) / len(holdings) if holdings else 0.0,
    })

frame = pd.DataFrame(rows)
per_date_df = pd.DataFrame(per_date)
summary = {
    'aum': AUM,
    'top_n': TOP_N,
    'dates_checked': int(per_date_df.shape[0]),
    'positions_checked': int(frame.shape[0]),
    'infeasible_positions': int((~frame['is_board_lot_feasible']).sum()),
    'infeasible_ratio': float((~frame['is_board_lot_feasible']).mean()) if not frame.empty else None,
    'dates_with_any_infeasible': int((per_date_df['infeasible_count'] > 0).sum()) if not per_date_df.empty else 0,
    'worst_date': None,
    'median_feasible_ratio_by_date': float(per_date_df['feasible_ratio'].median()) if not per_date_df.empty else None,
    'p10_feasible_ratio_by_date': float(per_date_df['feasible_ratio'].quantile(0.10)) if not per_date_df.empty else None,
    'weight_stats': {
        'min_weight': float(frame['weight'].min()) if not frame.empty else None,
        'median_weight': float(frame['weight'].median()) if not frame.empty else None,
        'max_weight': float(frame['weight'].max()) if not frame.empty else None,
    },
    'min_lot_notional_stats': {
        'median': float(frame['min_lot_notional'].median()) if not frame.empty else None,
        'p90': float(frame['min_lot_notional'].quantile(0.90)) if not frame.empty else None,
        'max': float(frame['min_lot_notional'].max()) if not frame.empty else None,
    },
}
if not per_date_df.empty:
    worst = per_date_df.sort_values(['feasible_ratio', 'infeasible_count'], ascending=[True, False]).iloc[0].to_dict()
    summary['worst_date'] = worst

payload = {
    'summary': summary,
    'per_date': per_date,
    'sample_infeasible_positions': frame.loc[~frame['is_board_lot_feasible']].sort_values(['date', 'position_notional']).head(30).to_dict(orient='records'),
    'sample_feasible_positions': frame.loc[frame['is_board_lot_feasible']].sort_values(['date', 'position_notional']).head(10).to_dict(orient='records'),
}

out = REPORTS_DIR / 'growth_personal_100k_board_lot_check_latest.json'
out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(out)
print(json.dumps(summary, indent=2, ensure_ascii=False))
