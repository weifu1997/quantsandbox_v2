from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

SOURCE_REPORTS = [
    Path('data/reports/pbindlow_final_confirm_20260517T105550Z.json'),
    Path('data/reports/pbindlow_longreview_20260517T110337Z.json'),
    Path('data/reports/pbindlow_batch2_large_20260517T111814Z.json'),
]
OUTPUT = Path('data/reports/pbindlow_candidate_pool_validation_20260517.json')


VARIANT_ALIASES = {
    'downtrend_only': 'default_candidate',
    'downtrend_plus_narrow_weakness': 'enhanced_candidate',
}


def variant_key(label: str) -> str:
    if label.startswith('downtrend_only'):
        return 'downtrend_only'
    if label.startswith('downtrend_plus_narrow_weakness'):
        return 'downtrend_plus_narrow_weakness'
    raise ValueError(f'unknown label: {label}')


def load_rows() -> list[dict]:
    rows = []
    for path in SOURCE_REPORTS:
        data = json.loads(path.read_text(encoding='utf-8'))
        for item in data['results']:
            fs = item['validation']['full_sample']['60']
            diag = fs['diagnostics']['summary']
            bt = item['backtest']
            key = variant_key(item['label'])
            rows.append({
                'source_report': str(path),
                'variant': key,
                'label': item['label'],
                'active_ratio': item['coverage']['active_ratio'],
                'rank_ic_mean': diag['rank_ic_mean'],
                'positive_ic_ratio': diag['positive_ic_ratio'],
                'monotonicity_score': diag['monotonicity_score'],
                'top_bottom_spread': diag['top_bottom_spread'],
                'annual_return': bt['annual_return'],
                'sharpe': bt['sharpe'],
                'max_drawdown': bt['max_drawdown'],
                'turnover': bt['turnover'],
            })
    return rows


def summarize(rows: list[dict]) -> dict:
    df = pd.DataFrame(rows)
    out = {}
    for variant, g in df.groupby('variant'):
        out[variant] = {
            'alias': VARIANT_ALIASES[variant],
            'run_count': int(len(g)),
            'mean_active_ratio': float(g['active_ratio'].mean()),
            'mean_rank_ic_mean': float(g['rank_ic_mean'].mean()),
            'mean_positive_ic_ratio': float(g['positive_ic_ratio'].mean()),
            'mean_monotonicity_score': float(g['monotonicity_score'].mean()),
            'mean_top_bottom_spread': float(g['top_bottom_spread'].mean()),
            'mean_annual_return': float(g['annual_return'].mean()),
            'mean_sharpe': float(g['sharpe'].mean()),
            'mean_max_drawdown': float(g['max_drawdown'].mean()),
            'mean_turnover': float(g['turnover'].mean()),
            'positive_sharpe_ratio': float((g['sharpe'] > 0).mean()),
            'positive_annual_return_ratio': float((g['annual_return'] > 0).mean()),
            'non_negative_spread_ratio': float((g['top_bottom_spread'] >= 0).mean()),
            'labels': g['label'].tolist(),
        }
    return out


def main() -> Path:
    rows = load_rows()
    summary = summarize(rows)

    decision = {
        'downtrend_only': {
            'admit_to_pool': True,
            'role': 'primary_candidate',
            'reason': 'Higher coverage, simpler rule set, and more balanced default behavior across prior validation batches.',
        },
        'downtrend_plus_narrow_weakness': {
            'admit_to_pool': True,
            'role': 'enhanced_candidate',
            'reason': 'Lower coverage but persistently stronger purity/performance in favorable environments; suitable as parallel enhancement mode.',
        },
    }

    report = {
        'report_type': 'pbindlow_candidate_pool_validation',
        'generated_at': pd.Timestamp.now('UTC').isoformat(),
        'source_reports': [str(p) for p in SOURCE_REPORTS],
        'row_count': len(rows),
        'summary_by_variant': summary,
        'pool_decision': decision,
        'pool_policy': {
            'primary_candidate_definition': 'Default strategy candidate with better balance of coverage, simplicity, and robustness.',
            'enhanced_candidate_definition': 'Higher-purity lower-coverage strategy retained as parallel enhancement mode.',
        },
        'next_step_recommendation': 'Continue long-horizon tracking with downtrend_only as default candidate and downtrend_plus_narrow_weakness as enhanced candidate; defer engineering promotion until further live-like review confirms persistence.',
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    main()
