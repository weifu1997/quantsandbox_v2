from app.domain.models import ExperimentConfig
from app.services.experiment_service import run_experiment
from app.services.task_service import create_task, get_task, mark_task_running


def test_run_experiment_end_to_end_sync() -> None:
    task = create_task(experiment_id="exp_sync_e2e")
    mark_task_running(task["task_id"], stage="accepted", message="accepted")
    result = run_experiment(
        task_id=task["task_id"],
        experiment_id="exp_sync_e2e",
        config=ExperimentConfig(
            start_date="20240101",
            end_date="20241231",
            factors=["momentum_20d", "pe"],
            horizons=[10],
            tickers=["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
            report_format="json",
        ),
    )
    assert "dataset_summary" in result
    assert "backtest_results" in result
    assert len(result["backtest_results"]["momentum_20d"]["equity_curve"]) > 0

    final_task = get_task(task["task_id"])
    assert final_task is not None
    assert final_task["status"] == "completed"
    assert final_task["result_ref"] == result["report"]["report_id"]
