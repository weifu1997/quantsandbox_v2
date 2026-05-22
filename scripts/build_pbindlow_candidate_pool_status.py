from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

REGISTRY_PATH = Path('data/reports/pbindlow_candidate_registry.json')
REVIEWS_PATH = Path('data/reports/pbindlow_candidate_reviews.json')
OUTPUT = Path('data/reports/pbindlow_candidate_pool_status_20260517.json')


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> Path:
    registry = load_json(REGISTRY_PATH)
    reviews = load_json(REVIEWS_PATH)
    reviews_df = pd.DataFrame(reviews)

    summary_rows = []
    normalized_registry = []
    for item in registry:
        sid = item['strategy_id']
        role = item['role']
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

        status = item.get('status', 'watch')
        if latest_result == 'watch':
            status = 'watch'
        elif trend == 'persistent_watch':
            status = 'watch'
        elif latest_result == 'keep' and trend in {'stable_keep', 'recent_stable'} and role != 'primary_candidate':
            status = 'active'
        elif latest_result == 'keep' and trend == 'stable_keep':
            status = 'active'

        suggested_action = 'continue_tracking'
        if status == 'watch':
            suggested_action = 'watch_closely'
        if trend == 'persistent_watch':
            suggested_action = 'prepare_downgrade_if_next_review_fails'
        if role == 'enhanced_candidate' and status == 'watch' and trend == 'persistent_watch':
            suggested_action = 'keep_as_optional_enhancement_only'
        if sid == 'pbindlow_downtrend_only_v1' and trend in {'persistent_watch', 'recent_weakening'}:
            suggested_action = 'keep_as_legacy_baseline_or_prepare_retirement'

        updated_item = dict(item)
        updated_item['status'] = status
        normalized_registry.append(updated_item)

        summary_rows.append({
            'strategy_id': sid,
            'strategy_name': item['strategy_name'],
            'role': role,
            'status': status,
            'review_count': review_count,
            'last_review_at': item.get('last_review_at'),
            'latest_result': latest_result,
            'latest_comment': latest_comment,
            'recent_review_trend': trend,
            'suggested_action': suggested_action,
            'recent_reviews': recent_reviews,
        })

    REGISTRY_PATH.write_text(json.dumps(normalized_registry, ensure_ascii=False, indent=2), encoding='utf-8')

    pool_state = {
        'primary_candidate': next((x['strategy_id'] for x in normalized_registry if x['role'] == 'primary_candidate'), None),
        'enhanced_candidate': next((x['strategy_id'] for x in normalized_registry if x['role'] == 'enhanced_candidate'), None),
        'active_count': sum(1 for x in normalized_registry if x['status'] == 'active'),
        'watch_count': sum(1 for x in normalized_registry if x['status'] == 'watch'),
        'downgraded_count': sum(1 for x in normalized_registry if x['status'] == 'downgraded'),
        'retired_count': sum(1 for x in normalized_registry if x['status'] == 'retired'),
    }

    report = {
        'report_type': 'pbindlow_candidate_pool_status',
        'generated_at': pd.Timestamp.now('UTC').isoformat(),
        'registry_path': str(REGISTRY_PATH),
        'reviews_path': str(REVIEWS_PATH),
        'pool_state': pool_state,
        'strategies': summary_rows,
        'next_step_hint': 'Run run_pbindlow_candidate_review.py on each new review window, then rebuild this status summary.',
    }

    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    main()
