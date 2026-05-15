from pathlib import Path
import json
import pandas as pd

from scripts.collect_tushare_to_file import (
    _iter_chunks,
    _load_manifest,
    _manifest_path,
    _merge_ticker_partition,
    _next_start_date_from_manifest,
    _partition_file_path,
    _resolve_tickers,
)


def test_merge_ticker_partition(tmp_path):
    base_dir = tmp_path / 'market'
    base_dir.mkdir()
    existing = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "sh600519", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000, "amount": 10500},
    ])
    incoming = pd.DataFrame([
        {"date": "2024-01-03", "ticker": "sh600519", "open": 10.5, "high": 11.2, "low": 10.2, "close": 11.0, "volume": 1200, "amount": 13200},
    ])
    existing.to_parquet(_partition_file_path(base_dir, 'sh600519'), index=False)
    merged = _merge_ticker_partition(base_dir, 'sh600519', incoming)
    assert len(merged) == 2


def test_next_start_date_from_manifest() -> None:
    manifest = {'last_end_date': '20240131'}
    assert _next_start_date_from_manifest(manifest) == '20240201'


def test_resolve_tickers_append() -> None:
    manifest = {'tickers': ['sh600519', 'sz000858']}
    tickers = _resolve_tickers(['sz300750'], manifest, append_tickers=True)
    assert set(tickers) == {'sh600519', 'sz000858', 'sz300750'}


def test_resolve_tickers_fallback_manifest() -> None:
    manifest = {'tickers': ['sh600519', 'sz000858']}
    tickers = _resolve_tickers([], manifest, append_tickers=False)
    assert tickers == ['sh600519', 'sz000858']


def test_resolve_tickers_from_file(tmp_path) -> None:
    manifest = {'tickers': ['sh600519']}
    tickers_file = tmp_path / 'tickers.txt'
    tickers_file.write_text('sh600000 sz000001', encoding='utf-8')
    tickers = _resolve_tickers([], manifest, append_tickers=False, tickers_file=tickers_file)
    assert tickers == ['sh600000', 'sz000001']


def test_resolve_tickers_from_json_file(tmp_path) -> None:
    manifest = {'tickers': ['sh600519']}
    tickers_file = tmp_path / 'tickers.json'
    tickers_file.write_text(json.dumps(['sh600000', 'sz000001']), encoding='utf-8')
    tickers = _resolve_tickers([], manifest, append_tickers=False, tickers_file=tickers_file)
    assert tickers == ['sh600000', 'sz000001']


def test_iter_chunks() -> None:
    chunks = list(_iter_chunks(['a', 'b', 'c', 'd', 'e'], 2))
    assert chunks == [
        (0, ['a', 'b']),
        (2, ['c', 'd']),
        (4, ['e']),
    ]


def test_manifest_path_override_and_load(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    default_path = _manifest_path(settings)
    assert default_path == settings.data_dir / 'raw' / 'tushare_manifest.json'

    custom_path = tmp_path / 'custom-manifest.json'
    custom_payload = {'tickers': ['sh600519'], 'last_end_date': '20240131'}
    custom_path.write_text(json.dumps(custom_payload), encoding='utf-8')

    assert _manifest_path(settings, custom_path) == custom_path
    assert _load_manifest(settings, custom_path) == custom_payload
