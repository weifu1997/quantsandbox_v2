from pathlib import Path

import pandas as pd

from scripts.collect_stock_basic import ts_to_ticker


def test_ts_to_ticker() -> None:
    assert ts_to_ticker('600519.SH') == 'sh600519'
    assert ts_to_ticker('000858.SZ') == 'sz000858'


def test_reference_path_convention(tmp_path) -> None:
    output = tmp_path / 'reference' / 'stock_basic_main_board.parquet'
    output.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([
        {
            'ts_code': '600519.SH',
            'symbol': '600519',
            'name': '贵州茅台',
            'area': '贵州',
            'industry': '酿酒',
            'market': '主板',
            'list_status': 'L',
            'list_date': '20010827',
            'delist_date': None,
            'ticker': 'sh600519',
            'updated_at': '2026-05-15T00:00:00+00:00',
        }
    ])
    df.to_parquet(output, index=False)
    assert output.exists()
