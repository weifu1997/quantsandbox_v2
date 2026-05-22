from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.backtest.engine import run_topn_backtest
from app.domain.data_contracts import factor_column
from scripts.build_research_realism_stress import load_registry_and_reviews, find_registry_item, latest_review, build_candidate_dataset

REPORTS_DIR = Path('data/reports')
CONFIG_PATH = REPORTS_DIR / 'current_working_strategy_config_personal_100k.json'
OUT_PATH = REPORTS_DIR / 'growth_personal_100k_long_window_turnover_v2_1_boardlot_engine_latest.json'


def main() -> None:
    cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    registry, reviews, *_ = load_registry_and_reviews('growth_line')
    strategy_id = cfg['growth_core']
    registry_item = find_registry_item(registry, strategy_id)
    review = latest_review(reviews, strategy_id)

    dataset = build_candidate_dataset('growth_line', registry_item, review)
    dataset = dataset.copy()
    dataset.attrs['initial_aum'] = float(cfg['target_aum'])
    dataset.attrs['board_lot_enabled'] = True
    dataset.attrs['board_lot_size'] = 100

    params = cfg['operating_params']
    result = run_topn_backtest(
        dataset=dataset,
        factor_col=factor_column(registry_item['factor']),
        top_n=int(params['top_n']),
        rebalance_frequency=str(params['rebalance_frequency']),
        weighting=str(cfg['weighting_policy']),
        benchmark='equal_weight_universe',
        commission_bps=float(params['commission_bps']),
        slippage_bps=float(params['slippage_bps']),
        horizon=int(registry_item['params']['horizon']),
    ).payload

    payload = {
        'summary': {
            'label': 'turnover_limit_v2_1_boardlot_engine_long_window',
            'result': result,
        }
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(str(OUT_PATH))
    print(json.dumps({
        'annual_return': result['annual_return'],
        'total_return': result['total_return'],
        'aum_end_on_100k': 100000 * (1.0 + result['total_return']),
        'turnover': result['turnover'],
        'rebalance_count': len(result['equity_curve']),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
