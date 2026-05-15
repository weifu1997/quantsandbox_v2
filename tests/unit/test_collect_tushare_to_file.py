from pathlib import Path
import json
import pandas as pd

from scripts.collect_tushare_to_file import (
    _build_precheck_report,
    _checkpoint_path,
    _completed_tickers,
    _failed_tickers,
    _group_tickers_by_start_date,
    _iter_chunks,
    _load_checkpoint,
    _load_manifest,
    _manifest_path,
    _merge_ticker_partition,
    _next_start_date_from_manifest,
    _partition_file_path,
    _precheck_report_path,
    _resolve_tickers,
    _save_checkpoint,
    _save_precheck_report,
    _save_validation_report,
    _classify_existing_tickers,
    _validate_collection,
    _validate_partition_dir,
    _validation_report_path,
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


def test_group_tickers_by_start_date() -> None:
    grouped = _group_tickers_by_start_date(
        ['a', 'b', 'c'],
        {'a': '20240103', 'c': '20240105'},
        '20240101',
    )
    assert grouped == [
        ('20240101', ['b']),
        ('20240103', ['a']),
        ('20240105', ['c']),
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


def test_checkpoint_path_and_load_save(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    checkpoint = _load_checkpoint(settings)
    assert checkpoint['market_completed_tickers'] == []
    assert checkpoint['fundamental_completed_tickers'] == []
    assert checkpoint['market_failed_tickers'] == []
    assert checkpoint['fundamental_failed_tickers'] == []

    custom_path = tmp_path / 'state.json'
    saved = _save_checkpoint(settings, {
        'market_completed_tickers': ['sh600000'],
        'fundamental_completed_tickers': ['sz000001'],
        'market_failed_tickers': ['sh600519'],
        'fundamental_failed_tickers': ['sz000002'],
        'stage': 'fundamental',
    }, checkpoint_path=custom_path)
    assert saved == custom_path
    loaded = _load_checkpoint(settings, checkpoint_path=custom_path)
    assert loaded['market_completed_tickers'] == ['sh600000']
    assert loaded['fundamental_completed_tickers'] == ['sz000001']
    assert loaded['market_failed_tickers'] == ['sh600519']
    assert loaded['fundamental_failed_tickers'] == ['sz000002']
    assert loaded['stage'] == 'fundamental'


def test_completed_tickers() -> None:
    df = pd.DataFrame([
        {'ticker': 'sh600000'},
        {'ticker': 'sh600000'},
        {'ticker': 'sz000001'},
    ])
    assert _completed_tickers(df) == ['sh600000', 'sz000001']


def test_failed_tickers() -> None:
    df = pd.DataFrame([
        {'ticker': 'sh600000'},
        {'ticker': 'sz000001'},
    ])
    assert _failed_tickers(['sh600000', 'sz000001', 'sh600519'], df) == ['sh600519']


def test_classify_existing_tickers_and_precheck(tmp_path) -> None:
    market_dir = tmp_path / 'market'
    fund_dir = tmp_path / 'fund'
    market_dir.mkdir()
    fund_dir.mkdir()

    pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
        {'date': '2024-01-03', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
        {'date': '2024-01-04', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
    ]).to_parquet(market_dir / 'sh600000.parquet', index=False)
    pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sz000001', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
    ]).to_parquet(market_dir / 'sz000001.parquet', index=False)
    pd.DataFrame([{'ticker': 'bad'}]).to_parquet(market_dir / 'sh600519.parquet', index=False)

    classified = _classify_existing_tickers(market_dir, ['sh600000', 'sz000001', 'sh600519', 'sz000002'], '20240104')
    assert classified['covered_tickers'] == ['sh600000']
    assert classified['incremental_tickers'] == ['sz000001']
    assert classified['invalid_tickers'] == ['sh600519']
    assert classified['missing_tickers'] == ['sz000002']
    assert classified['incremental_start_dates']['sz000001'] == '20240103'

    precheck = _build_precheck_report(market_dir, fund_dir, ['sh600000', 'sz000001', 'sh600519', 'sz000002'], '20240104', True, False)
    assert precheck['market']['covered_count'] == 1
    assert precheck['market']['incremental_count'] == 1
    assert precheck['market']['invalid_count'] == 1
    assert precheck['market']['missing_count'] == 1


def test_precheck_report_path_and_save(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    manifest_path = tmp_path / 'custom-manifest.json'
    path = _precheck_report_path(settings, manifest_path)
    assert path == tmp_path / 'custom-manifest.precheck.json'
    saved = _save_precheck_report(settings, {'market': {'covered_count': 1}}, manifest_path)
    assert saved == path
    assert json.loads(saved.read_text())['market']['covered_count'] == 1


def test_validate_partition_dir_and_collection(tmp_path) -> None:
    market_dir = tmp_path / 'market'
    fund_dir = tmp_path / 'fund'
    market_dir.mkdir()
    fund_dir.mkdir()

    pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
        {'date': '2024-01-03', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
        {'date': '2024-01-04', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
    ]).to_parquet(market_dir / 'sh600000.parquet', index=False)

    pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600000', 'pe': 1, 'pb': 1, 'roe': 1},
    ]).to_parquet(fund_dir / 'sh600000.parquet', index=False)

    tickers = ['sh600000', 'sz000001']
    market_report = _validate_partition_dir(market_dir, tickers, '20240102', '20240104')
    assert market_report['missing_count'] == 1
    assert 'sz000001' in market_report['missing_tickers']

    report = _validate_collection(market_dir, fund_dir, tickers, '20240102', '20240104', True, True)
    assert report['market']['missing_count'] == 1
    assert report['fundamental']['missing_count'] == 1
    assert report['acceptable'] is False


def test_validation_report_path_and_save(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    manifest_path = tmp_path / 'custom-manifest.json'
    path = _validation_report_path(settings, manifest_path)
    assert path == tmp_path / 'custom-manifest.validation.json'
    saved = _save_validation_report(settings, {'acceptable': True}, manifest_path)
    assert saved == path
    assert json.loads(saved.read_text())['acceptable'] is True
