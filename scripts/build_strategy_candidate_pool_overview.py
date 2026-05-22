from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

PB_REGISTRY = Path('data/reports/pbindlow_candidate_registry.json')
PB_REVIEWS = Path('data/reports/pbindlow_candidate_reviews.json')
PB_STATUS = Path('data/reports/pbindlow_candidate_pool_status_20260517.json')

GROWTH_REGISTRY = Path('data/reports/revgrowth_candidate_registry.json')
GROWTH_REVIEWS = Path('data/reports/revgrowth_candidate_reviews.json')
GROWTH_STATUS = Path('data/reports/revgrowth_candidate_pool_status_20260517.json')

OUTPUT = Path('data/reports/strategy_candidate_pool_overview_20260517.json')


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def summarize_line(name: str, registry_path: Path, reviews_path: Path, status_path: Path) -> dict:
    registry = load_json(registry_path)
    reviews = load_json(reviews_path)
    status = load_json(status_path)
    reviews_df = pd.DataFrame(reviews)

    review_count = int(len(reviews_df)) if not reviews_df.empty else 0
    latest_review_ids = []
    if not reviews_df.empty and 'review_id' in reviews_df.columns:
        latest_review_ids = reviews_df['review_id'].dropna().astype(str).tail(5).tolist()

    return {
        'line_name': name,
        'registry_path': str(registry_path),
        'reviews_path': str(reviews_path),
        'status_path': str(status_path),
        'candidate_count': len(registry),
        'review_count': review_count,
        'latest_review_ids': latest_review_ids,
        'pool_state': status.get('pool_state', {}),
        'strategies': status.get('strategies', []),
    }


def main() -> Path:
    pb_line = summarize_line('valuation_line', PB_REGISTRY, PB_REVIEWS, PB_STATUS)
    growth_line = summarize_line('growth_line', GROWTH_REGISTRY, GROWTH_REVIEWS, GROWTH_STATUS)

    total_candidates = pb_line['candidate_count'] + growth_line['candidate_count']
    total_reviews = pb_line['review_count'] + growth_line['review_count']

    report = {
        'report_type': 'strategy_candidate_pool_overview',
        'generated_at': pd.Timestamp.now('UTC').isoformat(),
        'summary': {
            'line_count': 2,
            'total_candidates': total_candidates,
            'total_reviews': total_reviews,
            'active_count': pb_line['pool_state'].get('active_count', 0) + growth_line['pool_state'].get('active_count', 0),
            'watch_count': pb_line['pool_state'].get('watch_count', 0) + growth_line['pool_state'].get('watch_count', 0),
            'downgraded_count': pb_line['pool_state'].get('downgraded_count', 0) + growth_line['pool_state'].get('downgraded_count', 0),
            'retired_count': pb_line['pool_state'].get('retired_count', 0) + growth_line['pool_state'].get('retired_count', 0),
        },
        'lines': [pb_line, growth_line],
        'operating_guidance': [
            'Treat valuation_line and growth_line as separate candidate pools with independent review windows and state transitions.',
            'Use each line\'s quarterly review wrapper to append new review rows before rebuilding this global overview.',
            'Only consider engineering promotion after a candidate remains acceptable across multiple future review windows, not from one-off backtests.',
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    main()
