from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

OUT1 = Path("data/reports/pbindlow_downtrend_window_summary_20260517.json")
OUT2 = Path("data/reports/pbindlow_downtrend_regime_profile_20260517.json")
OUT3 = Path("data/reports/pbindlow_downtrend_industry_attribution_20260517.json")
OUTPUT = Path("data/reports/pbindlow_downtrend_failure_report_20260517.json")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> Path:
    s1 = load_json(OUT1)
    s2 = load_json(OUT2)
    s3 = load_json(OUT3)

    summary_by_label = {x['label']: x for x in s1['results']}
    regime_by_label = {x['label']: x for x in s2['results']}
    industry_by_label = {x['label']: x for x in s3['results']}

    labels = ['2024H2','2025H1','2025H2']
    merged = []
    for label in labels:
        a = summary_by_label[label]
        r = regime_by_label[label]
        i = industry_by_label[label]
        diag = a['validation']['full_sample']['60']['diagnostics']['summary']
        bt = a['backtest']
        merged.append({
            'label': label,
            'active_ratio': a['coverage']['active_ratio'],
            'rank_ic_mean': diag['rank_ic_mean'],
            'positive_ic_ratio': diag['positive_ic_ratio'],
            'monotonicity_score': diag['monotonicity_score'],
            'top_bottom_spread': diag['top_bottom_spread'],
            'annual_return': bt['annual_return'],
            'sharpe': bt['sharpe'],
            'max_drawdown': bt['max_drawdown'],
            'mean_market_ret_60d': r['mean_market_ret_60d'],
            'mean_breadth_20d': r['mean_breadth_20d'],
            'breadth_below_50_ratio': r['breadth_below_50_ratio'],
            'mean_vol_20d': r['mean_vol_20d'],
            'top3_industry_share_mean': i['top3_industry_share_mean'],
            'avg_industry_count_per_rebalance': i['avg_industry_count_per_rebalance'],
            'industry_counts_top10': i['industry_counts_top10'],
        })

    candidate_filters = [
        {
            'name': 'downtrend_plus_narrow_weakness',
            'logic': 'trend_60d = downtrend AND breadth_20d < 0.5',
            'why': 'If 2025 failure windows show weaker breadth structure than 2024H2, this should remove low-quality downtrend dates.'
        },
        {
            'name': 'downtrend_plus_exclude_low_vol_drift',
            'logic': 'trend_60d = downtrend AND vol_20d above threshold',
            'why': 'If failure windows are dominated by low-vol drift downtrends, exclude them.'
        },
        {
            'name': 'downtrend_plus_industry_concentration_cap',
            'logic': 'skip/reduce trades when top3 industry share exceeds threshold',
            'why': 'If failure is driven by industry traps and excessive concentration, cap industry exposure.'
        }
    ]

    report = {
        'report_type': 'pbindlow_downtrend_failure_report',
        'generated_at': pd.Timestamp.now('UTC').isoformat(),
        'window_comparison': merged,
        'provisional_root_cause_hypothesis': 'Compare 2024H2 vs 2025H1/H2 on breadth, volatility, and industry concentration to identify whether the 2025 failure comes from weak breadth quality, low-vol drift, or concentrated value-trap industries.',
        'candidate_filters': candidate_filters,
        'source_reports': [str(OUT1), str(OUT2), str(OUT3)],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    main()
