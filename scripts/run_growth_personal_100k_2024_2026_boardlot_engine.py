from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.backtest.engine import run_topn_backtest
from app.domain.data_contracts import factor_column
from scripts.run_revgrowth_candidate_review import load_tickers_from_file, build_dataset, apply_filter

REPORTS_DIR = Path('data/reports')
CONFIG_PATH = REPORTS_DIR / 'current_working_strategy_config_personal_100k.json'
REGISTRY_PATH = REPORTS_DIR / 'revgrowth_candidate_registry.json'
TICKERS_FILE = Path(os.environ.get('TICKERS_FILE', str(REPORTS_DIR / 'filtered_universe_growth_amount_bottom_50pct_latest.json')))
OUT_PATH = REPORTS_DIR / 'growth_personal_100k_2024_2026_boardlot_engine_latest.json'

START_DATE = '20240102'
END_DATE = os.environ.get('END_DATE', '20260514')


def main() -> None:
    cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    strategy_id = cfg['growth_core']
    registry_item = next(x for x in registry if x.get('strategy_id') == strategy_id)

    tickers = load_tickers_from_file(str(TICKERS_FILE))
    factor = registry_item['factor']
    params = dict(registry_item['params'])
    params['top_n'] = int(cfg['operating_params']['top_n'])
    params['rebalance_frequency'] = str(cfg['operating_params']['rebalance_frequency'])
    params['annual_turnover_limit'] = float(cfg['operating_params']['annual_turnover_limit'])
    params['commission_bps'] = float(cfg['operating_params']['commission_bps'])
    params['slippage_bps'] = float(cfg['operating_params']['slippage_bps'])

    ds = build_dataset(tickers, START_DATE, END_DATE, int(params['horizon']), factor)
    filtered, coverage = apply_filter(ds, registry_item.get('filter', {}))
    filtered.attrs['growth_strategy_id'] = registry_item.get('strategy_id')
    filtered.attrs['growth_turnover_annual_limit'] = params.get('annual_turnover_limit')
    filtered.attrs['initial_aum'] = float(cfg['target_aum'])
    filtered.attrs['board_lot_enabled'] = True
    filtered.attrs['board_lot_size'] = 100
    if params.get('execution_assumptions'):
        execution = params.get('execution_assumptions', {})
        filtered.attrs['execution_config_enabled'] = True
        filtered.attrs['execution_bar_delay'] = execution.get('bar_delay', 1)
        filtered.attrs['execution_tick_size'] = execution.get('tick_size', 0.01)
        filtered.attrs['execution_base_tick_slippage_ticks'] = execution.get('base_tick_slippage_ticks', 1.0)
        filtered.attrs['execution_high_vol_extra_tick_slippage_ticks'] = execution.get('high_vol_extra_tick_slippage_ticks', 1.0)
        filtered.attrs['execution_high_vol_quantile'] = execution.get('high_vol_quantile', 0.8)
        filtered.attrs['execution_minimum_roundtrip_ticks'] = execution.get('minimum_roundtrip_ticks', 2.0)
        filtered.attrs['execution_commission_bps_override'] = execution.get('commission_bps', params.get('commission_bps'))

    result = run_topn_backtest(
        dataset=filtered,
        factor_col=factor_column(factor),
        top_n=int(params['top_n']),
        rebalance_frequency=str(params['rebalance_frequency']),
        weighting=str(cfg['weighting_policy']),
        benchmark='equal_weight_universe',
        commission_bps=float(params['commission_bps']),
        slippage_bps=float(params['slippage_bps']),
        horizon=int(params['horizon']),
    ).payload

    out = {
        'summary': {
            'label': 'growth_personal_100k_2024_2026_boardlot_engine',
            'window': {'start': START_DATE, 'end': END_DATE},
            'coverage': coverage,
            'target_aum': cfg['target_aum'],
            'result': result,
        }
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(str(OUT_PATH))
    print(json.dumps({
        'aum_end_on_100k': 100000 * (1 + result['total_return']),
        'annual_return': result['annual_return'],
        'total_return': result['total_return'],
        'rebalance_count': len(result['equity_curve']),
        'coverage': coverage,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
