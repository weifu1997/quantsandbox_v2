from __future__ import annotations

from scripts.build_filtered_universe_growth_amount_bottom import build_filtered_universe


def test_filtered_universe_payload_includes_as_of_date():
    payload = build_filtered_universe(limit=10)
    assert 'generated_at' in payload
    assert payload['filter_config']['label'].startswith('growth_amount_bottom_')
    assert 'as_of_date' in payload['filtered_universe']
