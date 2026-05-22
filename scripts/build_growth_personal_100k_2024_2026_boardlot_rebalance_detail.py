from __future__ import annotations

import json
from pathlib import Path

REPORTS_DIR = Path('data/reports')
INPUT_PATH = REPORTS_DIR / 'growth_personal_100k_2024_2026_boardlot_engine_latest.json'
OUT_PATH = REPORTS_DIR / 'growth_personal_100k_2024_2026_boardlot_rebalance_detail_latest.json'
INITIAL_AUM = 100_000.0


def main() -> None:
    payload = json.loads(INPUT_PATH.read_text(encoding='utf-8'))['summary']
    result = payload['result']

    dates = list(result['returns_by_rebalance_date'].keys())
    equity = INITIAL_AUM
    rows = []
    for i, d in enumerate(dates):
        start_equity = equity
        net = float(result['returns_by_rebalance_date'][d])
        gross = float(result['gross_return_by_rebalance_date'][d])
        turnover = float(result['turnover_by_rebalance_date'][d])
        cost = float(result['cost_by_rebalance_date'][d]) * start_equity
        equity = start_equity * (1.0 + net)
        holds = result['holdings_by_rebalance_date'].get(d, [])
        exec_diag = result['execution_by_rebalance_date'].get(d, {})
        prev_holds = result['holdings_by_rebalance_date'].get(dates[i-1], []) if i > 0 else []
        buy = [x for x in holds if x not in prev_holds]
        sell = [x for x in prev_holds if x not in holds]
        rows.append({
            'date': d,
            'start_equity': round(start_equity, 6),
            'gross_return_pct': round(gross * 100.0, 6),
            'net_return_pct': round(net * 100.0, 6),
            'turnover_pct': round(turnover * 100.0, 6),
            'cost_cny': round(cost, 6),
            'end_equity': round(equity, 6),
            'hold_count': len(holds),
            'buy_count': len(buy),
            'sell_count': len(sell),
            'buy': ', '.join(buy),
            'sell': ', '.join(sell),
            'holdings': ', '.join(holds),
            'avg_participation_rate': exec_diag.get('avg_participation_rate'),
            'max_participation_rate': exec_diag.get('max_participation_rate'),
            'impact_cost_bps': exec_diag.get('impact_cost_bps'),
            'extreme_count': exec_diag.get('extreme_count'),
        })

    out = {
        'summary': {
            'strategy_id': 'revgrowth_always_on_v1',
            'window': payload['window'],
            'aum_start': INITIAL_AUM,
            'aum_end': round(equity, 6),
            'total_return_pct': round((equity / INITIAL_AUM - 1.0) * 100.0, 6),
            'annual_return': result['annual_return'],
            'sharpe': result['sharpe'],
            'max_drawdown': result['max_drawdown'],
            'win_rate': result['win_rate'],
            'rebalance_count': len(rows),
            'note': '真正基于 2024-2026 全窗口 + 10万 + 100股一手约束引擎结果生成的组合层调仓报告。',
        },
        'rebalances': rows,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(str(OUT_PATH))
    print(json.dumps(out['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
