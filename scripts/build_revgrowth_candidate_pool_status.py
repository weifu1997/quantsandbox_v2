from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

REGISTRY_PATH = Path('data/reports/revgrowth_candidate_registry.json')
REVIEWS_PATH = Path('data/reports/revgrowth_candidate_reviews.json')
OUTPUT = Path('data/reports/revgrowth_candidate_pool_status_20260517.json')


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> Path:
    registry = load_json(REGISTRY_PATH)
    reviews = load_json(REVIEWS_PATH)
    reviews_df = pd.DataFrame(reviews)

    summary_rows = []
    for item in registry:
        sid = item['strategy_id']
        strat_reviews = reviews_df.loc[reviews_df['strategy_id'] == sid].copy() if not reviews_df.empty else pd.DataFrame()
        recent_reviews = []
        trend = 'no_reviews'
        latest_result = None
        latest_comment = None
        review_count = 0
        if not strat_reviews.empty:
            review_count = int(len(strat_reviews))
            strat_reviews = strat_reviews.sort_values(['start_date', 'end_date', 'review_id'])
            tail = strat_reviews.tail(3)
            recent_reviews = tail[['review_id', 'window_label', 'review_result', 'comment']].to_dict(orient='records')
            latest = tail.iloc[-1]
            latest_result = latest['review_result']
            latest_comment = latest['comment']
            results = tail['review_result'].tolist()
            if all(r == 'keep' for r in results):
                trend = 'stable_keep'
            elif all(r == 'watch' for r in results):
                trend = 'persistent_watch'
            elif results[-1] == 'watch':
                trend = 'recent_weakening'
            elif results[-1] == 'keep':
                trend = 'recent_stable'
            else:
                trend = 'mixed'

        suggested_action = 'continue_tracking'
        if item['status'] == 'watch':
            suggested_action = 'watch_closely'
        if trend == 'persistent_watch':
            suggested_action = 'prepare_downgrade_if_next_review_fails'
        if item['role'] == 'enhanced_candidate' and item['status'] == 'watch' and trend == 'persistent_watch':
            suggested_action = 'keep_as_optional_enhancement_only'

        summary_rows.append({
            'strategy_id': sid,
            'strategy_name': item['strategy_name'],
            'role': item['role'],
            'status': item['status'],
            'review_count': review_count,
            'last_review_at': item.get('last_review_at'),
            'latest_result': latest_result,
            'latest_comment': latest_comment,
            'recent_review_trend': trend,
            'suggested_action': suggested_action,
            'recent_reviews': recent_reviews,
        })

    pool_state = {
        'primary_candidate': next((x['strategy_id'] for x in registry if x['role'] == 'primary_candidate'), None),
        'enhanced_candidate': next((x['strategy_id'] for x in registry if x['role'] == 'enhanced_candidate'), None),
        'active_count': sum(1 for x in registry if x['status'] == 'active'),
        'watch_count': sum(1 for x in registry if x['status'] == 'watch'),
        'downgraded_count': sum(1 for x in registry if x['status'] == 'downgraded'),
        'retired_count': sum(1 for x in registry if x['status'] == 'retired'),
    }

    report = {
        'report_type': 'revgrowth_candidate_pool_status',
        'generated_at': pd.Timestamp.now('UTC').isoformat(),
        'registry_path': str(REGISTRY_PATH),
        'reviews_path': str(REVIEWS_PATH),
        'pool_state': pool_state,
        'strategies': summary_rows,
        'next_step_hint': 'Build a matching review runner for growth-line candidates, then start accumulating review windows.',
    }

    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    main()
