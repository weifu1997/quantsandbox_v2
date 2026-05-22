from pathlib import Path
import json
import os
import pandas as pd
import pytest
import sqlite3

from scripts.collect_tushare_to_file import (
    _acquire_or_recover_run_lock,
    _acquire_run_lock,
    _build_precheck_report,
    _build_quick_result,
    _build_result_payload,
    _build_run_report,
    _checkpoint_path,
    _checkpoint_status_payload,
    _classify_ticker_outcomes,
    _completed_tickers,
    _compute_manifest_dates,
    _create_run_state,
    _decision_summary_from_classification,
    _derive_cli_stage,
    _derive_collection_status,
    _failed_tickers,
    _group_tickers_by_start_date,
    _is_lock_stale,
    _iter_chunks,
    _latest_partition_dates,
    _latest_run_state,
    _load_checkpoint,
    _load_manifest,
    _load_reference_names,
    _load_reference_records,
    _load_run_lock,
    _manifest_path,
    _mark_stale_runs_interrupted,
    _merge_ticker_partition,
    _next_start_date_from_manifest,
    _partition_file_path,
    _pid_is_alive,
    _precheck_report_path,
    _release_run_lock,
    _resolve_tickers,
    _run_lock_path,
    _run_metrics_payload,
    _run_report_path,
    _run_state_db_path,
    _save_checkpoint,
    _save_precheck_report,
    _save_run_report,
    _save_validation_report,
    _update_manifest,
    _update_run_state,
    _write_json_atomic,
    _classification_summary,
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
    assert checkpoint['market_true_failed_tickers'] == []
    assert checkpoint['fundamental_true_failed_tickers'] == []
    assert checkpoint['market_acceptable_gap_tickers'] == []
    assert checkpoint['fundamental_acceptable_gap_tickers'] == []

    custom_path = tmp_path / 'state.json'
    saved = _save_checkpoint(settings, {
        'market_completed_tickers': ['sh600000'],
        'fundamental_completed_tickers': ['sz000001'],
        'market_failed_tickers': ['sh600519'],
        'fundamental_failed_tickers': ['sz000002'],
        'market_true_failed_tickers': ['sh600519'],
        'market_acceptable_gap_tickers': ['sh600193'],
        'market_manual_review_tickers': ['sz000003'],
        'fundamental_true_failed_tickers': ['sz000002'],
        'fundamental_acceptable_gap_tickers': ['sh600421'],
        'fundamental_manual_review_tickers': ['sz000004'],
        'stage': 'fundamental',
    }, checkpoint_path=custom_path)
    assert saved == custom_path
    loaded = _load_checkpoint(settings, checkpoint_path=custom_path)
    assert loaded['market_completed_tickers'] == ['sh600000']
    assert loaded['fundamental_completed_tickers'] == ['sz000001']
    assert loaded['market_failed_tickers'] == ['sh600519']
    assert loaded['fundamental_failed_tickers'] == ['sz000002']
    assert loaded['market_true_failed_tickers'] == ['sh600519']
    assert loaded['market_acceptable_gap_tickers'] == ['sh600193']
    assert loaded['market_manual_review_tickers'] == ['sz000003']
    assert loaded['fundamental_true_failed_tickers'] == ['sz000002']
    assert loaded['fundamental_acceptable_gap_tickers'] == ['sh600421']
    assert loaded['fundamental_manual_review_tickers'] == ['sz000004']
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
    missing = _failed_tickers(['sh600000', 'sz000001', 'sh600519'], df)
    assert missing == ['sh600519']


def test_classify_ticker_outcomes() -> None:
    outcome = _classify_ticker_outcomes(
        requested=['sh600000', 'sz000001', 'sh600519', 'sz000002', 'sz000003', 'sz000004', 'sz000005', 'sz000006'],
        completed_tickers=['sh600000'],
        missing_tickers=['sz000001', 'sh600519', 'sz000002', 'sz000003', 'sz000004', 'sz000005', 'sz000006'],
        reference_names={
            'sz000001': '平安银行',
            'sh600519': '*ST样例',
            'sz000003': '普通股票',
            'sz000004': '普通股票B',
            'sz000005': '退市样例',
            'sz000006': '未来上市样例',
        },
        reference_records={
            'sh600519': {'name': '*ST样例', 'list_status': 'L', 'list_date': '20010827', 'delist_date': ''},
            'sz000001': {'name': '平安银行', 'list_status': 'L', 'list_date': '19910403', 'delist_date': ''},
            'sz000003': {'name': '普通股票', 'list_status': 'L', 'list_date': '20000101', 'delist_date': ''},
            'sz000004': {'name': '普通股票B', 'list_status': 'L', 'list_date': '20000101', 'delist_date': ''},
            'sz000005': {'name': '退市样例', 'list_status': 'L', 'list_date': '20000101', 'delist_date': '20240103'},
            'sz000006': {'name': '未来上市样例', 'list_status': 'L', 'list_date': '20240110', 'delist_date': ''},
        },
        latest_local_dates={
            'sz000001': '20231220',
            'sh600519': '20240101',
            'sz000003': '20240103',
            'sz000004': '20240101',
            'sz000005': '20240103',
        },
        target_end_date='20240104',
        warning_messages=[
            'daily_basic returned empty for sz000004',
            'daily_basic failed for sz000001: timeout',
        ],
    )
    assert outcome['true_failed_tickers'] == ['sz000001']
    assert outcome['acceptable_gap_tickers'] == ['sh600519', 'sz000004', 'sz000005']
    assert outcome['manual_review_tickers'] == ['sz000002', 'sz000003', 'sz000006']


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


def test_load_reference_names(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    manifest_path = tmp_path / 'custom-manifest.json'
    reference_dir = tmp_path / 'reference'
    reference_dir.mkdir()
    pd.DataFrame([
        {'ticker': 'sh600519', 'name': '*ST样例', 'list_status': 'L'},
        {'ticker': 'sz000001', 'name': '平安银行', 'list_status': 'L'},
    ]).to_parquet(reference_dir / 'stock_basic_main_board.parquet', index=False)

    names = _load_reference_names(settings, manifest_path)
    assert names == {'sh600519': '*ST样例', 'sz000001': '平安银行'}


def test_load_reference_records(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    manifest_path = tmp_path / 'custom-manifest.json'
    reference_dir = tmp_path / 'reference'
    reference_dir.mkdir()
    pd.DataFrame([
        {'ticker': 'sh600519', 'name': '*ST样例', 'list_status': 'D', 'list_date': '20010827', 'delist_date': '20240102'},
    ]).to_parquet(reference_dir / 'stock_basic_main_board.parquet', index=False)

    records = _load_reference_records(settings, manifest_path)
    assert records == {
        'sh600519': {
            'name': '*ST样例',
            'list_status': 'D',
            'list_date': '20010827',
            'delist_date': '20240102',
        }
    }


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

    report = _validate_collection(
        market_dir,
        fund_dir,
        tickers,
        '20240102',
        '20240104',
        True,
        True,
        true_failed_tickers=['sz000001'],
        acceptable_gap_tickers=[],
        manual_review_tickers=[],
    )
    assert report['market']['missing_count'] == 1
    assert report['fundamental']['missing_count'] == 1
    assert report['acceptable'] is False
    assert report['true_failed_tickers'] == ['sz000001']
    assert report['review_required'] is False


def test_validate_collection_accepts_acceptable_gaps_and_flags_manual_review(tmp_path) -> None:
    market_dir = tmp_path / 'market'
    fund_dir = tmp_path / 'fund'
    market_dir.mkdir()
    fund_dir.mkdir()

    tickers = ['sh600000']
    report_gap = _validate_collection(
        market_dir,
        fund_dir,
        tickers,
        '20240102',
        '20240104',
        False,
        False,
        true_failed_tickers=[],
        acceptable_gap_tickers=['sh600000'],
        manual_review_tickers=[],
    )
    assert report_gap['acceptable'] is True
    assert report_gap['warnings'] == ['acceptable_gap_tickers=sh600000']
    assert report_gap['review_required'] is False

    report_manual = _validate_collection(
        market_dir,
        fund_dir,
        tickers,
        '20240102',
        '20240104',
        False,
        False,
        true_failed_tickers=[],
        acceptable_gap_tickers=[],
        manual_review_tickers=['sh600000'],
    )
    assert report_manual['acceptable'] is False
    assert report_manual['review_required'] is True


def test_latest_partition_dates(tmp_path) -> None:
    market_dir = tmp_path / 'market'
    fund_dir = tmp_path / 'fund'
    market_dir.mkdir()
    fund_dir.mkdir()

    pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
        {'date': '2024-01-04', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
    ]).to_parquet(market_dir / 'sh600000.parquet', index=False)
    pd.DataFrame([
        {'date': '2024-01-03', 'ticker': 'sh600000', 'pe': 1, 'pb': 1, 'roe': 1},
    ]).to_parquet(fund_dir / 'sh600000.parquet', index=False)

    latest = _latest_partition_dates(market_dir, fund_dir, ['sh600000'], True, True)
    assert latest == {'sh600000': '20240104'}


def test_compute_manifest_dates(tmp_path) -> None:
    market_dir = tmp_path / 'market'
    fund_dir = tmp_path / 'fund'
    market_dir.mkdir()
    fund_dir.mkdir()

    pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
        {'date': '2024-01-04', 'ticker': 'sh600000', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
    ]).to_parquet(market_dir / 'sh600000.parquet', index=False)
    pd.DataFrame([
        {'date': '2024-01-03', 'ticker': 'sz000001', 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'amount': 1},
    ]).to_parquet(market_dir / 'sz000001.parquet', index=False)

    pd.DataFrame([
        {'date': '2024-01-04', 'ticker': 'sh600000', 'pe': 1, 'pb': 1, 'roe': 1},
    ]).to_parquet(fund_dir / 'sh600000.parquet', index=False)
    pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sz000001', 'pe': 1, 'pb': 1, 'roe': 1},
    ]).to_parquet(fund_dir / 'sz000001.parquet', index=False)

    dataset_max_date, latest_complete_end_date = _compute_manifest_dates(
        market_dir,
        fund_dir,
        ['sh600000', 'sz000001'],
        '20240104',
        True,
        True,
    )
    assert dataset_max_date == '20240104'
    assert latest_complete_end_date == '20240102'


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


def test_update_manifest_supports_dataset_and_target_dates(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    manifest_path = tmp_path / 'custom-manifest.json'
    saved = _update_manifest(
        settings,
        market_dir=tmp_path / 'market',
        fundamental_dir=tmp_path / 'fundamentals',
        tickers=['sh600000', 'sz000001'],
        start_date='20260515',
        end_date='20260520',
        market_rows=10,
        fundamental_rows=8,
        warnings=['w1'],
        modes={'market': True, 'fundamental': True},
        manifest_path=manifest_path,
        dataset_max_date='20260520',
        latest_complete_end_date='20260513',
        unified_status='partial_success',
        classification_summary={'true_failed_count': 1},
        market_classification_summary={'true_failed_count': 1, 'acceptable_gap_count': 2, 'manual_review_count': 0},
        fundamental_classification_summary={'true_failed_count': 0, 'acceptable_gap_count': 1, 'manual_review_count': 1},
        validation_report={'acceptable': False, 'review_required': True, 'warnings': []},
    )
    payload = json.loads(saved.read_text(encoding='utf-8'))
    assert payload['target_end_date'] == '20260520'
    assert payload['dataset_max_date'] == '20260520'
    assert payload['latest_complete_end_date'] == '20260513'
    assert payload['unified_status'] == 'partial_success'
    assert payload['classification_summary'] == {'true_failed_count': 1}
    assert payload['market_classification_summary'] == {'true_failed_count': 1, 'acceptable_gap_count': 2, 'manual_review_count': 0}
    assert payload['fundamental_classification_summary'] == {'true_failed_count': 0, 'acceptable_gap_count': 1, 'manual_review_count': 1}
    assert payload['retry_recommendation'] == 'retry_true_failed'
    assert payload['manual_review_required'] is True
    assert payload['downstream_readiness'] == 'blocked'
    assert payload['blocking_reasons'] == ['true_failed_tickers=1', 'manual_review_tickers=0']
    assert payload['last_end_date'] == '20260520'


def test_write_json_atomic_replaces_existing_file(tmp_path) -> None:
    path = tmp_path / 'state.json'
    path.write_text('{"old": true}', encoding='utf-8')

    saved = _write_json_atomic(path, {'new': True, 'items': [1, 2]})

    assert saved == path
    assert json.loads(path.read_text(encoding='utf-8')) == {'new': True, 'items': [1, 2]}
    assert not any(p.name.startswith('.state.json.tmp.') for p in tmp_path.iterdir())


def test_run_lock_acquire_and_release(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    manifest_path = tmp_path / 'custom-manifest.json'
    lock_path = _acquire_run_lock(settings, manifest_path)

    assert lock_path == _run_lock_path(settings, manifest_path)
    lock_payload = _load_run_lock(lock_path)
    assert lock_payload is not None
    assert lock_payload['pid'] == os.getpid()

    with pytest.raises(RuntimeError, match='collection lock already exists'):
        _acquire_run_lock(settings, manifest_path)

    _release_run_lock(lock_path)
    assert not lock_path.exists()


def test_run_state_db_path_and_persistence(tmp_path) -> None:
    class SettingsStub:
        db_path = tmp_path / 'db' / 'run_state.sqlite3'

    settings = SettingsStub()
    db_path = _run_state_db_path(settings)
    assert db_path == settings.db_path

    metrics = _run_metrics_payload(
        market_rows_fetched=10,
        fundamental_rows_fetched=5,
        market_rows_written=8,
        fundamental_rows_written=4,
        pending_market_ticker_count=2,
        pending_fundamental_ticker_count=1,
        failed_market_ticker_count=1,
        failed_fundamental_ticker_count=0,
    )
    _create_run_state(
        db_path,
        run_id='col_test_1',
        manifest_path=tmp_path / 'manifest.json',
        checkpoint_path=tmp_path / 'checkpoint.json',
        status='running',
        stage='market',
        start_date='20240101',
        end_date='20240131',
        tickers=['sh600000', 'sz000001'],
        modes={'market': True, 'fundamental': False},
        metrics=metrics,
        warning_count=2,
        error=None,
        lock_path=tmp_path / 'manifest.lock',
    )

    row = _latest_run_state(db_path, 'col_test_1')
    assert row is not None
    assert row['status'] == 'running'
    assert row['stage'] == 'market'
    assert json.loads(row['tickers_json']) == ['sh600000', 'sz000001']
    assert json.loads(row['metrics_json'])['market_rows_fetched'] == 10
    assert row['finished_at'] is None

    updated_metrics = _run_metrics_payload(
        market_rows_fetched=12,
        fundamental_rows_fetched=6,
        market_rows_written=10,
        fundamental_rows_written=5,
        pending_market_ticker_count=0,
        pending_fundamental_ticker_count=0,
        failed_market_ticker_count=1,
        failed_fundamental_ticker_count=1,
    )
    _update_run_state(
        db_path,
        run_id='col_test_1',
        status='failed',
        stage='fundamental',
        metrics=updated_metrics,
        warning_count=3,
        error='boom',
        finished=True,
    )

    updated = _latest_run_state(db_path, 'col_test_1')
    assert updated is not None
    assert updated['status'] == 'failed'
    assert updated['stage'] == 'fundamental'
    assert updated['warning_count'] == 3
    assert updated['error'] == 'boom'
    assert updated['finished_at'] is not None
    assert json.loads(updated['metrics_json'])['failed_fundamental_ticker_count'] == 1

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'collection_runs' in tables


def test_build_and_save_run_report(tmp_path) -> None:
    class SettingsStub:
        data_dir = tmp_path / 'data'

    settings = SettingsStub()
    run_row = {
        'run_id': 'col_test_2',
        'status': 'completed',
        'stage': 'completed',
        'start_date': '20240101',
        'end_date': '20240131',
        'manifest_path': str(tmp_path / 'manifest.json'),
        'checkpoint_path': str(tmp_path / 'checkpoint.json'),
        'lock_path': str(tmp_path / 'manifest.lock'),
        'tickers_json': json.dumps(['sh600000', 'sz000001']),
        'modes_json': json.dumps({'market': True, 'fundamental': True}),
        'metrics_json': json.dumps({'market_rows_fetched': 10, 'fundamental_rows_written': 8}),
        'error': None,
        'started_at': '2026-05-16T00:00:00+00:00',
        'updated_at': '2026-05-16T00:10:00+00:00',
        'finished_at': '2026-05-16T00:12:00+00:00',
    }
    validation = {'acceptable': True, 'market': {'missing_count': 0}, 'fundamental': {'missing_count': 0}}
    precheck = {'market': {'covered_count': 1}, 'fundamental': {'incremental_count': 1}}
    warnings = ['slow retry', 'partial empty chunk']

    report = _build_run_report(
        run_row=run_row,
        warnings=warnings,
        validation_report=validation,
        precheck_report=precheck,
        failed_market_tickers=['sz000001'],
        failed_fundamental_tickers=[],
        unified_status='partial_success',
        true_failed_tickers=['sz000001'],
        acceptable_gap_tickers=['sh600519'],
        manual_review_tickers=['sz000002'],
        market_true_failed_tickers=['sz000001'],
        market_acceptable_gap_tickers=['sh600519'],
        market_manual_review_tickers=[],
        fundamental_true_failed_tickers=[],
        fundamental_acceptable_gap_tickers=[],
        fundamental_manual_review_tickers=['sz000002'],
    )
    report['lifecycle_stage'] = 'finalizing'

    assert report['run_id'] == 'col_test_2'
    assert report['final_status'] == 'partial_success'
    assert report['unified_status'] == 'partial_success'
    assert report['validation_acceptable'] is True
    assert report['failed_ticker_count'] == 1
    assert report['warning_count'] == 2
    assert report['metrics']['market_rows_fetched'] == 10
    assert report['stage_timeline'][-1]['stage'] == 'completed'
    assert report['true_failed_tickers'] == ['sz000001']
    assert report['acceptable_gap_tickers'] == ['sh600519']
    assert report['manual_review_tickers'] == ['sz000002']
    assert report['classification_summary'] == {
        'true_failed_count': 1,
        'acceptable_gap_count': 1,
        'manual_review_count': 1,
    }
    assert report['retry_recommendation'] == 'retry_true_failed'
    assert report['manual_review_required'] is False
    assert report['downstream_readiness'] == 'blocked'
    assert report['blocking_reasons'] == ['true_failed_tickers=1', 'manual_review_tickers=1']
    assert report['market_classification'] == {
        'true_failed_tickers': ['sz000001'],
        'acceptable_gap_tickers': ['sh600519'],
        'manual_review_tickers': [],
    }
    assert report['fundamental_classification'] == {
        'true_failed_tickers': [],
        'acceptable_gap_tickers': [],
        'manual_review_tickers': ['sz000002'],
    }
    assert report['lifecycle_stage'] == 'finalizing'

    manifest_path = tmp_path / 'custom-manifest.json'
    saved = _save_run_report(settings, report, manifest_path)
    assert saved == _run_report_path(settings, manifest_path)
    saved_payload = json.loads(saved.read_text(encoding='utf-8'))
    assert saved_payload['run_id'] == 'col_test_2'
    assert saved_payload['validation_acceptable'] is True
    assert saved_payload['true_failed_tickers'] == ['sz000001']
    assert saved_payload['acceptable_gap_tickers'] == ['sh600519']
    assert saved_payload['manual_review_tickers'] == ['sz000002']
    assert saved_payload['classification_summary'] == {
        'true_failed_count': 1,
        'acceptable_gap_count': 1,
        'manual_review_count': 1,
    }
    assert saved_payload['lifecycle_stage'] == 'finalizing'


def test_build_result_payload_summary_first(tmp_path) -> None:
    payload = _build_result_payload(
        base_result={
            'manifest_path': str(tmp_path / 'manifest.json'),
            'checkpoint_path': str(tmp_path / 'checkpoint.json'),
            'precheck_report_path': str(tmp_path / 'precheck.json'),
            'validation_report_path': str(tmp_path / 'validation.json'),
            'run_report_path': str(tmp_path / 'run-report.json'),
            'failed_market_tickers': ['legacy-a'],
            'fundamental_failed_tickers': ['legacy-b'],
        },
        unified_status='partial_success',
        cli_stage='partial_success',
        validation_report={
            'acceptable': False,
            'review_required': True,
            'warnings': ['acceptable_gap_tickers=sh600519'],
        },
        run_report={'run_id': 'col_test'},
        manifest_output_path=tmp_path / 'manifest.json',
        checkpoint_path=tmp_path / 'checkpoint.json',
        run_state_db_path=tmp_path / 'run_state.sqlite3',
        run_id='col_test',
        classification_summary={
            'true_failed_count': 1,
            'acceptable_gap_count': 1,
            'manual_review_count': 1,
        },
        true_failed_tickers=['sz000001'],
        acceptable_gap_tickers=['sh600519'],
        manual_review_tickers=['sz000002'],
        raw_market_missing_tickers=['sz000001'],
        raw_fundamental_missing_tickers=['sz000001', 'sh600519'],
        market_true_failed_tickers=['sz000001'],
        market_acceptable_gap_tickers=[],
        market_manual_review_tickers=[],
        fundamental_true_failed_tickers=[],
        fundamental_acceptable_gap_tickers=['sh600519'],
        fundamental_manual_review_tickers=['sz000002'],
    )
    assert payload['summary']['unified_status'] == 'partial_success'
    assert payload['summary']['classification_summary']['true_failed_count'] == 1
    assert payload['summary']['market_classification_summary'] == {
        'true_failed_count': 1,
        'acceptable_gap_count': 0,
        'manual_review_count': 0,
    }
    assert payload['summary']['fundamental_classification_summary'] == {
        'true_failed_count': 0,
        'acceptable_gap_count': 1,
        'manual_review_count': 1,
    }
    assert payload['summary']['validation']['review_required'] is True
    assert payload['summary']['raw_fetch_missing_summary']['raw_fetch_missing_ticker_count'] == 2
    assert payload['summary']['retry_recommendation'] == 'retry_true_failed'
    assert payload['summary']['manual_review_required'] is True
    assert payload['summary']['downstream_readiness'] == 'blocked'
    assert payload['summary']['blocking_reasons'] == ['true_failed_tickers=1', 'manual_review_tickers=1']
    assert payload['details']['classification']['acceptable_gap_tickers'] == ['sh600519']
    assert payload['details']['classification']['market'] == {
        'true_failed_tickers': ['sz000001'],
        'acceptable_gap_tickers': [],
        'manual_review_tickers': [],
    }
    assert payload['details']['classification']['fundamental'] == {
        'true_failed_tickers': [],
        'acceptable_gap_tickers': ['sh600519'],
        'manual_review_tickers': ['sz000002'],
    }
    assert payload['details']['raw_fetch_missing']['raw_fetch_missing_tickers_union'] == ['sh600519', 'sz000001']
    assert 'failed_market_tickers' not in payload
    assert 'fundamental_failed_tickers' not in payload


def test_build_quick_result_summary_first() -> None:
    payload = _build_quick_result(
        base_result={'manifest_path': '/tmp/manifest.json'},
        unified_status='ready',
        cli_stage='ready',
    )
    assert payload['summary']['unified_status'] == 'ready'
    assert payload['summary']['classification_summary'] == {
        'true_failed_count': 0,
        'acceptable_gap_count': 0,
        'manual_review_count': 0,
    }
    assert payload['summary']['market_classification_summary'] == {
        'true_failed_count': 0,
        'acceptable_gap_count': 0,
        'manual_review_count': 0,
    }
    assert payload['summary']['fundamental_classification_summary'] == {
        'true_failed_count': 0,
        'acceptable_gap_count': 0,
        'manual_review_count': 0,
    }
    assert payload['summary']['retry_recommendation'] == 'no_retry_needed'
    assert payload['summary']['manual_review_required'] is False
    assert payload['summary']['downstream_readiness'] == 'ready'
    assert payload['summary']['blocking_reasons'] == []
    assert payload['details']['run']['run_id'] is None


def test_build_result_payload_decision_summary_variants(tmp_path) -> None:
    payload = _build_result_payload(
        base_result={'manifest_path': str(tmp_path / 'manifest.json')},
        unified_status='success_with_gaps',
        cli_stage='success_with_gaps',
        validation_report={
            'acceptable': True,
            'review_required': False,
            'warnings': ['acceptable_gap_tickers=sh600519'],
        },
        run_report=None,
        manifest_output_path=None,
        checkpoint_path=None,
        run_state_db_path=None,
        run_id=None,
        classification_summary={
            'true_failed_count': 0,
            'acceptable_gap_count': 2,
            'manual_review_count': 0,
        },
        true_failed_tickers=[],
        acceptable_gap_tickers=['sh600519', 'sh600193'],
        manual_review_tickers=[],
        raw_market_missing_tickers=['sh600519'],
        raw_fundamental_missing_tickers=['sh600193'],
    )
    assert payload['summary']['retry_recommendation'] == 'no_retry_acceptable_gaps'
    assert payload['summary']['manual_review_required'] is False
    assert payload['summary']['downstream_readiness'] == 'ready_with_gaps'
    assert payload['summary']['blocking_reasons'] == []


def test_decision_summary_from_classification() -> None:
    summary = _decision_summary_from_classification(
        classification_summary={
            'true_failed_count': 0,
            'acceptable_gap_count': 2,
            'manual_review_count': 1,
        },
        validation_report={
            'acceptable': False,
            'review_required': True,
            'warnings': ['acceptable_gap_tickers=sh600519'],
        },
    )
    assert summary['retry_recommendation'] == 'review_before_retry'
    assert summary['manual_review_required'] is True
    assert summary['downstream_readiness'] == 'blocked'
    assert summary['blocking_reasons'] == ['manual_review_tickers=1']
    assert summary['time_lag_review'] is False

    time_lag = _decision_summary_from_classification(
        classification_summary={
            'true_failed_count': 0,
            'acceptable_gap_count': 13,
            'manual_review_count': 1,
        },
        validation_report={
            'acceptable': False,
            'review_required': True,
            'warnings': [
                'acceptable_gap_tickers=sh600193,sz002629',
                'resume_day_tushare_not_updated=sz002629',
            ],
        },
    )
    assert time_lag['retry_recommendation'] == 'retry_after_data_refresh'
    assert time_lag['manual_review_required'] is True
    assert time_lag['downstream_readiness'] == 'ready_with_gaps'
    assert time_lag['blocking_reasons'] == []
    assert time_lag['time_lag_review'] is True


def test_classification_summary_helper() -> None:
    summary = _classification_summary(
        true_failed_tickers=['a', 'b'],
        acceptable_gap_tickers=['c'],
        manual_review_tickers=['d', 'e', 'f'],
    )
    assert summary == {
        'true_failed_count': 2,
        'acceptable_gap_count': 1,
        'manual_review_count': 3,
    }


def test_build_run_report_deduplicates_failed_ticker_count(tmp_path) -> None:
    run_row = {
        'run_id': 'col_test_dedupe',
        'status': 'partial_success',
        'stage': 'partial_success',
        'start_date': '20240101',
        'end_date': '20240131',
        'manifest_path': str(tmp_path / 'manifest.json'),
        'checkpoint_path': str(tmp_path / 'checkpoint.json'),
        'lock_path': None,
        'tickers_json': json.dumps(['sh600000', 'sz000001']),
        'modes_json': json.dumps({'market': True, 'fundamental': True}),
        'metrics_json': json.dumps({}),
        'error': None,
        'started_at': '2026-05-16T00:00:00+00:00',
        'updated_at': '2026-05-16T00:10:00+00:00',
        'finished_at': '2026-05-16T00:12:00+00:00',
    }

    report = _build_run_report(
        run_row=run_row,
        warnings=[],
        validation_report={'acceptable': True},
        precheck_report=None,
        failed_market_tickers=['sz000001'],
        failed_fundamental_tickers=['sz000001'],
        unified_status='partial_success',
        true_failed_tickers=['sz000001'],
    )

    assert report['failed_ticker_count'] == 1
    assert report['failed_tickers_union'] == ['sz000001']
    assert report['true_failed_ticker_count'] == 1


def test_unified_status_helpers() -> None:
    assert _derive_collection_status(
        check_only=True,
        precheck_only=False,
        blocked_by_lock=False,
        interrupted=False,
        failed=False,
        market_failed_tickers=[],
        fundamental_failed_tickers=[],
        validation_report=None,
    ) == 'ready'
    assert _derive_collection_status(
        check_only=False,
        precheck_only=True,
        blocked_by_lock=False,
        interrupted=False,
        failed=False,
        market_failed_tickers=[],
        fundamental_failed_tickers=[],
        validation_report=None,
    ) == 'precheck_only'
    assert _derive_collection_status(
        check_only=False,
        precheck_only=False,
        blocked_by_lock=True,
        interrupted=False,
        failed=False,
        market_failed_tickers=[],
        fundamental_failed_tickers=[],
        validation_report=None,
    ) == 'blocked_by_lock'
    assert _derive_collection_status(
        check_only=False,
        precheck_only=False,
        blocked_by_lock=False,
        interrupted=True,
        failed=False,
        market_failed_tickers=[],
        fundamental_failed_tickers=[],
        validation_report=None,
    ) == 'interrupted'
    assert _derive_collection_status(
        check_only=False,
        precheck_only=False,
        blocked_by_lock=False,
        interrupted=False,
        failed=False,
        market_failed_tickers=['sh600519'],
        fundamental_failed_tickers=[],
        validation_report={'acceptable': True},
        true_failed_tickers=['sh600519'],
    ) == 'partial_success'
    assert _derive_collection_status(
        check_only=False,
        precheck_only=False,
        blocked_by_lock=False,
        interrupted=False,
        failed=False,
        market_failed_tickers=[],
        fundamental_failed_tickers=[],
        validation_report={'acceptable': True},
        acceptable_gap_tickers=['sh600519'],
    ) == 'success_with_gaps'
    assert _derive_collection_status(
        check_only=False,
        precheck_only=False,
        blocked_by_lock=False,
        interrupted=False,
        failed=False,
        market_failed_tickers=[],
        fundamental_failed_tickers=[],
        validation_report={'acceptable': False},
    ) == 'partial_success'
    assert _derive_collection_status(
        check_only=False,
        precheck_only=False,
        blocked_by_lock=False,
        interrupted=False,
        failed=True,
        market_failed_tickers=[],
        fundamental_failed_tickers=[],
        validation_report=None,
    ) == 'failed'
    assert _derive_cli_stage('partial_success') == 'partial_success'
    assert _derive_cli_stage('success_with_gaps') == 'success_with_gaps'
    assert _derive_cli_stage('running', 'market') == 'market'
    assert _checkpoint_status_payload('failed', 'failed') == {'status': 'failed', 'stage': 'failed'}


def test_stale_lock_helpers_and_recovery(tmp_path) -> None:
    assert _pid_is_alive(os.getpid()) is True
    assert _is_lock_stale({'pid': 999999999}) is True
    assert _is_lock_stale({'invalid': True, 'path': '/tmp/x'}) is True

    class SettingsStub:
        data_dir = tmp_path / 'data'
        db_path = tmp_path / 'db' / 'run_state.sqlite3'

    settings = SettingsStub()
    manifest_path = tmp_path / 'custom-manifest.json'
    lock_path = _run_lock_path(settings, manifest_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({'pid': 999999999, 'hostname': 'dead', 'started_at': '2026-05-16T00:00:00+00:00'}), encoding='utf-8')

    metrics = _run_metrics_payload(
        market_rows_fetched=0,
        fundamental_rows_fetched=0,
        market_rows_written=0,
        fundamental_rows_written=0,
        pending_market_ticker_count=1,
        pending_fundamental_ticker_count=1,
        failed_market_ticker_count=0,
        failed_fundamental_ticker_count=0,
        market_retry_stats={},
        fundamental_retry_stats={},
    )
    _create_run_state(
        settings.db_path,
        run_id='col_stale_1',
        manifest_path=manifest_path,
        checkpoint_path=tmp_path / 'checkpoint.json',
        status='running',
        stage='locked',
        start_date='20240101',
        end_date='20240131',
        tickers=['sh600000'],
        modes={'market': True},
        metrics=metrics,
        warning_count=0,
        error=None,
        lock_path=lock_path,
    )

    recovered_lock_path, stale_payload = _acquire_or_recover_run_lock(settings, settings.db_path, manifest_path)
    assert recovered_lock_path == lock_path
    assert stale_payload is not None
    row = _latest_run_state(settings.db_path, 'col_stale_1')
    assert row is not None
    assert row['status'] == 'interrupted'
    assert row['stage'] == 'interrupted'
    assert 'stale lock recovered' in (row['error'] or '')
    _release_run_lock(recovered_lock_path)
    assert not recovered_lock_path.exists()
