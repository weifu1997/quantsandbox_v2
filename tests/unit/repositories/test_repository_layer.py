from __future__ import annotations

from app.domain.enums import TaskStatus
from app.repositories.experiment_repository import create_experiment, get_experiment
from app.repositories.report_repository import create_report, get_report
from app.repositories.task_repository import create_task, get_task, list_running_tasks, update_task


def test_task_repository_create_update_and_list_running() -> None:
    task = create_task(experiment_id='exp_repo_task_1')
    assert task['task_id'].startswith('task_')
    assert task['status'] == TaskStatus.PENDING.value

    updated = update_task(
        task['task_id'],
        status=TaskStatus.RUNNING.value,
        progress_current=1,
        progress_total=4,
        stage='dataset',
        message='building dataset',
    )
    assert updated is not None
    assert updated['status'] == TaskStatus.RUNNING.value
    assert updated['progress']['current'] == 1
    assert updated['progress']['total'] == 4
    assert updated['progress']['message'] == 'building dataset'
    assert updated['stage'] == 'dataset'

    running = list_running_tasks()
    assert any(item['task_id'] == task['task_id'] for item in running)

    stored = get_task(task['task_id'])
    assert stored is not None
    assert stored['experiment_id'] == 'exp_repo_task_1'


def test_experiment_repository_roundtrip() -> None:
    experiment = create_experiment(
        {
            'name': 'repo experiment',
            'universe': 'main_board',
            'start_date': '20240101',
            'end_date': '20241231',
            'factors': ['momentum_20d', 'pe'],
            'horizons': [20, 60],
            'rebalance_frequency': 'W',
            'top_n': 15,
            'weighting': 'equal',
            'benchmark': 'equal_weight_universe',
        }
    )
    assert experiment['experiment_id'].startswith('exp_')
    assert experiment['name'] == 'repo experiment'
    assert experiment['factors'] == ['momentum_20d', 'pe']
    assert experiment['horizons'] == [20, 60]

    stored = get_experiment(experiment['experiment_id'])
    assert stored is not None
    assert stored['universe'] == 'main_board'
    assert stored['top_n'] == 15


def test_report_repository_roundtrip() -> None:
    report = create_report(
        {
            'experiment_id': 'exp_repo_report_1',
            'task_id': 'task_repo_report_1',
            'report_format': 'json',
            'report_path': '/tmp/repo-report.json',
            'summary': {
                'title': 'Repository Report',
                'output_format': 'json',
                'experiment_id': 'exp_repo_report_1',
            },
        }
    )
    assert report['report_id'].startswith('rep_')
    assert report['report_format'] == 'json'
    assert report['summary']['title'] == 'Repository Report'

    stored = get_report(report['report_id'])
    assert stored is not None
    assert stored['task_id'] == 'task_repo_report_1'
    assert stored['summary']['experiment_id'] == 'exp_repo_report_1'
