from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path('/root/project/quantsandbox_v2')
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.backtest.engine import run_topn_backtest
from app.domain.data_contracts import factor_column
from scripts.build_research_realism_stress import build_candidate_dataset, find_registry_item, load_registry_and_reviews

REPORTS_DIR = PROJECT_ROOT / 'data/reports'
OUT_PATH = PROJECT_ROOT / 'data/reports/growth_v3_long_window_backtest_2024_2026.json'

START_DATE = '20240101'
END_DATE = '20260520'
LINE = 'growth_line'
STRATEGY_ID = 'revgrowth_quality_v3'


def main() -> None:
    registry, reviews, *_ = load_registry_and_reviews(LINE)
    registry_item = find_registry_item(registry, STRATEGY_ID)
    params = dict(registry_item['params'])

    review_like = {
        'start_date': START_DATE,
        'end_date': END_DATE,
    }
    dataset = build_candidate_dataset(LINE, registry_item, review_like, tickers=None)

    payload = run_topn_backtest(
        dataset=dataset,
        factor_col=factor_column(registry_item['factor']),
        top_n=int(params['top_n']),
        rebalance_frequency=str(params['rebalance_frequency']),
        weighting=str(params['weighting']),
        benchmark=str(params['benchmark']),
        commission_bps=float(params['commission_bps']),
        slippage_bps=float(params['slippage_bps']),
        horizon=int(params['horizon']),
    ).payload

    rebalance_dates = list(payload.get('returns_by_rebalance_date', {}).keys())
    backtest_window = payload.get('backtest_window', {})
    backtest_coverage_summary = payload.get('backtest_coverage_summary', {})
    total_return = payload.get('total_return')
    benchmark_total_return = payload.get('benchmark_total_return')
    excess_total_return = None
    if total_return is not None and benchmark_total_return is not None:
        excess_total_return = float(total_return) - float(benchmark_total_return)
    result = {
        'strategy_id': STRATEGY_ID,
        'window': {
            'start_date': START_DATE,
            'end_date': END_DATE,
            'requested_start_date': backtest_window.get('requested_start_date', START_DATE),
            'requested_end_date': backtest_window.get('requested_end_date', END_DATE),
            'effective_first_rebalance_date': backtest_window.get('effective_first_rebalance_date'),
            'effective_last_rebalance_date': backtest_window.get('effective_last_rebalance_date'),
            'data_start_date': backtest_window.get('data_start_date'),
            'data_end_date': backtest_window.get('data_end_date'),
            'rebalance_count': backtest_window.get('rebalance_count', len(rebalance_dates)),
            'tail_truncated_rebalance_count': backtest_window.get('tail_truncated_rebalance_count', 0),
        },
        'backtest_coverage_summary': backtest_coverage_summary,
        'operating_params': {
            'top_n': int(params['top_n']),
            'rebalance_frequency': str(params['rebalance_frequency']),
            'weighting': str(params['weighting']),
            'benchmark': str(params['benchmark']),
            'commission_bps': float(params['commission_bps']),
            'slippage_bps': float(params['slippage_bps']),
            'annual_turnover_limit': float(params.get('annual_turnover_limit', 0.0)),
            'selection_hold_rank': int(params.get('selection_hold_rank', params['top_n'])),
            'selection_buy_rank': int(params.get('selection_buy_rank', params['top_n'])),
        },
        'metrics': {
            'total_return': payload.get('total_return'),
            'annual_return': payload.get('annual_return'),
            'sharpe': payload.get('sharpe'),
            'max_drawdown': payload.get('max_drawdown'),
            'turnover': payload.get('turnover'),
            'annualized_one_way_turnover': payload.get('annualized_one_way_turnover'),
            'win_rate': payload.get('win_rate'),
            'cost_paid': payload.get('cost_paid'),
            'base_cost_paid': payload.get('base_cost_paid'),
            'impact_cost_paid': payload.get('impact_cost_paid'),
            'total_cost_paid_with_impact': payload.get('total_cost_paid_with_impact'),
            'benchmark_total_return': payload.get('benchmark_total_return'),
            'benchmark_annual_return': payload.get('benchmark_annual_return'),
            'benchmark_sharpe': payload.get('benchmark_sharpe'),
            'excess_total_return': excess_total_return,
        },
        'rebalance': {
            'count': len(rebalance_dates),
            'first_rebalance_date': rebalance_dates[0] if rebalance_dates else None,
            'last_rebalance_date': rebalance_dates[-1] if rebalance_dates else None,
        },
    }

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(OUT_PATH))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
