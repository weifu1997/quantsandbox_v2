from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.domain.models import ExperimentConfig
from app.services import experiment_service
from app.services import backtest_service
from app.services import dataset_service
from app.services import report_service
from app.services import task_service


class DummyBacktestResult:
    def __init__(self, payload):
        self.payload = payload


def test_backtest_service_uses_factor_column(monkeypatch) -> None:
    captured = {}

    def fake_run_topn_backtest(**kwargs):
        captured.update(kwargs)
        return DummyBacktestResult({'ok': True})

    monkeypatch.setattr(backtest_service, 'run_topn_backtest', fake_run_topn_backtest)

    result = backtest_service.run_strategy_backtest(
        dataset=pd.DataFrame(),
        factor_name='momentum_20d',
        top_n=10,
        rebalance_frequency='W',
        weighting='equal',
        benchmark='equal_weight_universe',
        commission_bps=10.0,
        slippage_bps=5.0,
        horizon=20,
    )

    assert captured['factor_col'] == 'factor:momentum_20d'
    assert result.payload == {'ok': True}


def test_task_service_marks_interrupted_running_tasks(monkeypatch) -> None:
    updated = []

    monkeypatch.setattr(task_service, 'repo_list_running_tasks', lambda: [
        {'task_id': 'task_1'},
        {'task_id': 'task_2'},
    ])
    monkeypatch.setattr(task_service, 'repo_update_task', lambda task_id, **kwargs: updated.append((task_id, kwargs)))

    task_service.mark_interrupted_running_tasks()

    assert len(updated) == 2
    assert updated[0][1]['status'] == 'interrupted'
    assert updated[0][1]['stage'] == 'interrupted'


def test_task_service_state_transitions_delegate_expected_payloads(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(task_service, 'repo_create_task', lambda experiment_id=None, status=None: {'task_id': 'task_1', 'experiment_id': experiment_id, 'status': status})
    monkeypatch.setattr(task_service, 'repo_update_task', lambda task_id, **kwargs: calls.append((task_id, kwargs)) or {'task_id': task_id, **kwargs})
    monkeypatch.setattr(task_service, 'repo_get_task', lambda task_id: {'task_id': task_id, 'status': 'completed'})

    created = task_service.create_task('exp_1')
    assert created['status'] == 'pending'

    task_service.mark_task_running('task_1', stage='accepted', message='accepted')
    task_service.update_task_progress('task_1', 2, 4, 'backtest', 'running')
    task_service.mark_task_completed('task_1', result_ref='rep_1', message='done')
    task_service.mark_task_failed('task_1', 'boom')
    fetched = task_service.get_task('task_1')

    assert fetched == {'task_id': 'task_1', 'status': 'completed'}
    assert calls[0][1]['status'] == 'running'
    assert calls[0][1]['stage'] == 'accepted'
    assert calls[1][1]['progress_current'] == 2
    assert calls[1][1]['progress_total'] == 4
    assert calls[2][1]['status'] == 'completed'
    assert calls[2][1]['result_ref'] == 'rep_1'
    assert calls[3][1]['status'] == 'failed'
    assert calls[3][1]['error'] == 'boom'


def test_dataset_service_build_dataset_summary_includes_invalid_reason_counts() -> None:
    df = pd.DataFrame([
        {'is_valid_sample': True, 'missing_reason': ''},
        {'is_valid_sample': False, 'missing_reason': 'missing_future_return_20d'},
        {'is_valid_sample': False, 'missing_reason': 'missing_future_return_20d'},
    ])
    summary = dataset_service.build_dataset_summary(
        df,
        tickers=['sh600519'],
        factors=['momentum_20d'],
        horizons=[20],
        warnings=['warn_a'],
        data_mode='simulated',
    )
    assert summary['rows'] == 3
    assert summary['invalid_reasons']['missing_future_return_20d'] == 2
    assert summary['warnings'] == ['warn_a']
    assert summary['data_mode'] == 'simulated'


def test_dataset_service_build_research_dataset_uses_configurable_sample_thresholds(monkeypatch) -> None:
    class SettingsStub:
        market_data_mode = 'memory'
        min_sample_trading_days = 2
        min_sample_listed_days = 30
        data_dir = Path('/tmp/quantsandbox-test-data')

    market = pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600519', 'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2, 'volume': 1000, 'amount': 10200},
        {'date': '2024-01-03', 'ticker': 'sh600519', 'open': 10.2, 'high': 10.4, 'low': 10.0, 'close': 10.3, 'volume': 1100, 'amount': 11330},
    ])
    fundamentals = pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600519', 'pe': 10.0, 'pb': 1.5, 'roe': 0.12, 'roa': 0.08, 'gross_margin': 0.35, 'revenue_growth': 0.1, 'profit_growth': 0.12},
        {'date': '2024-01-03', 'ticker': 'sh600519', 'pe': 10.1, 'pb': 1.52, 'roe': 0.121, 'roa': 0.081, 'gross_margin': 0.351, 'revenue_growth': 0.101, 'profit_growth': 0.121},
    ])

    class MarketAdapterStub:
        warnings = []
        def fetch_daily_bars(self, tickers, start_date, end_date):
            return market.copy()

    class FundamentalAdapterStub:
        warnings = []
        def fetch_fundamentals(self, tickers, start_date, end_date):
            return fundamentals.copy()

    monkeypatch.setattr(dataset_service, 'get_settings', lambda: SettingsStub())
    monkeypatch.setattr(dataset_service, 'build_default_factor_registry', lambda: type('Registry', (), {'compute': lambda self, name, dataset: pd.Series([0.1, 0.2])})())
    monkeypatch.setattr(dataset_service, 'persist_dataset', lambda dataset, experiment_id, summary: {'dataset_id': 'ds_test'})
    monkeypatch.setattr(dataset_service, 'attach_listing_days', lambda dataset, reference_path: (dataset.assign(listed_days=[20, 40]), {'listing_days_attached': 2}))

    dataset, summary, metadata = dataset_service.build_research_dataset(
        tickers=['sh600519'],
        start_date='2024-01-02',
        end_date='2024-01-03',
        factor_names=['momentum_20d'],
        horizons=[1],
        market_adapter=MarketAdapterStub(),
        fundamental_adapter=FundamentalAdapterStub(),
        experiment_id='exp_cfg_thresholds',
    )

    assert metadata['dataset_id'] == 'ds_test'
    assert summary['data_mode'] == 'simulated'
    assert dataset.loc[0, 'missing_reason'] == 'too_few_listed_days_min_30'

def test_experiment_service_helpers_are_thin_and_deterministic() -> None:
    config = ExperimentConfig(
        start_date='20240101',
        end_date='20241231',
        factors=['momentum_20d', 'pe'],
        horizons=[20],
        tickers=['sh600519'],
        report_format='json',
    )

    payload = experiment_service._build_report_payload(config, ['sh600519', 'sz000858'])
    assert payload['tickers'] == ['sh600519', 'sz000858']
    assert payload['factors'] == ['momentum_20d', 'pe']

    dataset = pd.DataFrame({'date': pd.to_datetime(['2024-01-02', '2024-01-03', '2024-01-04'])})
    split_date = experiment_service._resolve_split_date(dataset)
    assert split_date == '2024-01-03'


def test_experiment_service_submit_and_backtest_helpers(monkeypatch) -> None:
    config = ExperimentConfig(
        start_date='20240101',
        end_date='20241231',
        factors=['momentum_20d', 'pe'],
        horizons=[20],
        tickers=['sh600519'],
        top_n=15,
        rebalance_frequency='W',
        weighting='equal',
        benchmark='equal_weight_universe',
        commission_bps=10.0,
        slippage_bps=5.0,
        report_format='json',
    )

    created_payload = {}
    monkeypatch.setattr(experiment_service, 'repo_create_experiment', lambda payload: (created_payload.setdefault('payload', payload), {'experiment_id': 'exp_1'})[1])
    monkeypatch.setattr(experiment_service, 'create_task', lambda experiment_id=None: {'task_id': 'task_1', 'experiment_id': experiment_id})
    mark_calls = []
    monkeypatch.setattr(experiment_service, 'mark_task_running', lambda task_id, stage='', message='': mark_calls.append((task_id, stage, message)))
    submitted = []
    monkeypatch.setattr(experiment_service, 'submit_background', lambda fn, *args: submitted.append((fn, args)))
    monkeypatch.setattr(experiment_service, 'get_task', lambda task_id: {'task_id': task_id, 'status': 'running'})

    response = experiment_service.submit_experiment(config)
    assert created_payload['payload']['factors'] == ['momentum_20d', 'pe']
    assert response['task']['task_id'] == 'task_1'
    assert mark_calls[0] == ('task_1', 'accepted', 'experiment accepted')
    assert submitted[0][1] == ('task_1', 'exp_1', config)

    class DummyBacktestResult:
        def __init__(self, payload):
            self.payload = payload

    captured = []
    monkeypatch.setattr(experiment_service, 'run_strategy_backtest', lambda **kwargs: captured.append(kwargs) or DummyBacktestResult({'factor_name': kwargs['factor_name']}))
    dataset = pd.DataFrame({'date': pd.to_datetime(['2024-01-02'])})
    backtest_results = experiment_service._build_backtest_results(dataset, config)
    assert set(backtest_results.keys()) == {'momentum_20d', 'pe'}
    assert captured[0]['top_n'] == 15
    assert captured[0]['horizon'] == 20


def test_experiment_service_run_experiment_marks_failed_on_dataset_error(monkeypatch) -> None:
    config = ExperimentConfig(
        start_date='20240101',
        end_date='20241231',
        factors=['momentum_20d'],
        horizons=[20],
        tickers=['sh600519'],
        report_format='json',
    )

    monkeypatch.setattr(experiment_service, 'build_research_dataset', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('dataset boom')))
    progress_calls = []
    monkeypatch.setattr(experiment_service, 'update_task_progress', lambda *args: progress_calls.append(args))
    failed = []
    monkeypatch.setattr(experiment_service, 'mark_task_failed', lambda task_id, error: failed.append((task_id, error)))

    try:
        experiment_service.run_experiment('task_1', 'exp_1', config)
        assert False, 'expected RuntimeError'
    except RuntimeError as exc:
        assert str(exc) == 'dataset boom'

    assert progress_calls[0] == ('task_1', 1, 4, 'dataset', 'building research dataset')
    assert failed == [('task_1', 'dataset boom')]


def test_experiment_service_run_experiment_marks_failed_on_report_error(monkeypatch) -> None:
    config = ExperimentConfig(
        start_date='20240101',
        end_date='20241231',
        factors=['momentum_20d'],
        horizons=[20],
        tickers=['sh600519'],
        report_format='json',
    )

    dataset = pd.DataFrame({'date': pd.to_datetime(['2024-01-02', '2024-01-03']), 'ticker': ['sh600519', 'sh600519']})
    monkeypatch.setattr(experiment_service, 'build_research_dataset', lambda **kwargs: (dataset, {'rows': 2}, {'dataset_id': 'ds_1'}))
    monkeypatch.setattr(experiment_service, 'run_factor_research', lambda *args, **kwargs: {'momentum_20d': {'full_sample': {}}})
    monkeypatch.setattr(experiment_service, '_build_backtest_results', lambda *args, **kwargs: {'momentum_20d': {'total_return': 0.1}})
    monkeypatch.setattr(experiment_service, 'build_experiment_report', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('report boom')))
    progress_calls = []
    monkeypatch.setattr(experiment_service, 'update_task_progress', lambda *args: progress_calls.append(args))
    failed = []
    monkeypatch.setattr(experiment_service, 'mark_task_failed', lambda task_id, error: failed.append((task_id, error)))

    try:
        experiment_service.run_experiment('task_1', 'exp_1', config)
        assert False, 'expected RuntimeError'
    except RuntimeError as exc:
        assert str(exc) == 'report boom'

    assert progress_calls[-1] == ('task_1', 4, 4, 'report', 'building report')
    assert failed == [('task_1', 'report boom')]


def test_report_service_helpers_compose_cleanly(tmp_path, monkeypatch) -> None:
    class SettingsStub:
        reports_dir = tmp_path / 'reports'

    monkeypatch.setattr(report_service, 'get_settings', lambda: SettingsStub())

    json_payload = {
        'title': 'QuantSandbox v2 Research Report',
        'output_format': 'json',
        'summary': {'factor_count': 2, 'best_factor': 'momentum_20d', 'warning_count': 1, 'data_mode': 'simulated'},
        'factor_diagnostics': [{'factor_name': 'momentum_20d'}],
        'warnings': ['warn_a'],
    }

    summary = report_service._build_report_summary(json_payload, 'exp_1', 'markdown')
    assert summary['output_format'] == 'markdown'
    assert summary['experiment_id'] == 'exp_1'

    monkeypatch.setattr(report_service, 'render_markdown_report', lambda **kwargs: '# report')
    content, suffix = report_service._render_report_content(
        normalized_format='markdown',
        json_payload=json_payload,
        config={'factors': ['momentum_20d']},
        dataset_summary={'rows': 10, 'data_mode': 'simulated'},
        factor_results={},
        backtest_results={},
    )
    assert suffix == 'md'
    assert content == '# report'

    report_path = report_service._persist_report_file('exp_1', suffix, content)
    assert report_path == tmp_path / 'reports' / 'exp_1.md'
    assert report_path.read_text(encoding='utf-8') == '# report'

    captured = {}
    monkeypatch.setattr(report_service, 'repo_create_report', lambda payload: captured.setdefault('payload', payload) or {'report_id': 'rep_1'})
    report_service._create_report_record(
        experiment_id='exp_1',
        task_id='task_1',
        normalized_format='markdown',
        report_path=report_path,
        summary=summary,
    )
    assert captured['payload']['report_format'] == 'markdown'
    assert captured['payload']['report_path'] == str(report_path)
    assert captured['payload']['summary']['experiment_id'] == 'exp_1'
