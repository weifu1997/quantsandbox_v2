from __future__ import annotations

from typing import Any

from app.adapters.universe_adapter import resolve_universe
from app.domain.models import ExperimentConfig
from app.repositories.experiment_repository import create_experiment as repo_create_experiment
from app.repositories.experiment_repository import get_experiment as repo_get_experiment
from app.services.backtest_service import run_strategy_backtest
from app.services.dataset_service import build_research_dataset
from app.services.factor_research_service import run_factor_research
from app.services.report_service import build_experiment_report
from app.services.task_service import (
    create_task,
    get_task,
    mark_task_completed,
    mark_task_failed,
    mark_task_running,
    update_task_progress,
)
from app.tasks.runner import submit_background


def _resolve_tickers_from_config(config: ExperimentConfig) -> list[str]:
    if config.tickers:
        return config.tickers
    if config.universe:
        return resolve_universe(config.universe, asof_date=config.end_date)
    return []


def _config_to_dict(config: ExperimentConfig) -> dict[str, Any]:
    return {
        "start_date": config.start_date,
        "end_date": config.end_date,
        "tickers": config.tickers,
        "universe": config.universe,
        "factors": config.factors,
        "horizons": config.horizons,
        "rebalance_frequency": config.rebalance_frequency,
        "top_n": config.top_n,
        "weighting": config.weighting,
        "benchmark": config.benchmark,
        "commission_bps": config.commission_bps,
        "slippage_bps": config.slippage_bps,
        "report_format": config.report_format,
    }


def run_experiment(task_id: str, experiment_id: str, config: ExperimentConfig) -> dict[str, Any]:
    try:
        tickers = _resolve_tickers_from_config(config)
        update_task_progress(task_id, 1, 4, "dataset", "building research dataset")
        dataset, dataset_summary, dataset_metadata = build_research_dataset(
            tickers=tickers,
            start_date=config.start_date,
            end_date=config.end_date,
            factor_names=config.factors,
            horizons=config.horizons,
            experiment_id=experiment_id,
        )

        update_task_progress(task_id, 2, 4, "factor_research", "running factor validation")
        split_date = None
        unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
        if unique_dates:
            split_date = unique_dates[len(unique_dates) // 2]
        factor_results = run_factor_research(
            dataset,
            config.factors,
            config.horizons,
            groups=5,
            split_date=str(split_date.date()) if split_date is not None else None,
        )

        update_task_progress(task_id, 3, 4, "backtest", "running topn backtests")
        backtest_results: dict[str, Any] = {}
        horizon = int(config.horizons[0]) if config.horizons else 20
        for factor_name in config.factors:
            report = run_strategy_backtest(
                dataset=dataset,
                factor_name=factor_name,
                top_n=config.top_n,
                rebalance_frequency=config.rebalance_frequency,
                weighting=config.weighting,
                benchmark=config.benchmark,
                commission_bps=config.commission_bps,
                slippage_bps=config.slippage_bps,
                horizon=horizon,
            )
            backtest_results[factor_name] = report.payload

        update_task_progress(task_id, 4, 4, "report", "building report")
        report = build_experiment_report(
            experiment_id=experiment_id,
            task_id=task_id,
            config={**_config_to_dict(config), "tickers": tickers},
            dataset_summary=dataset_summary,
            factor_results=factor_results,
            backtest_results=backtest_results,
            report_format=config.report_format,
        )
        mark_task_completed(task_id, result_ref=report["report_id"], message="experiment completed")
        return {
            "dataset_summary": dataset_summary,
            "dataset_metadata": dataset_metadata,
            "factor_results": factor_results,
            "backtest_results": backtest_results,
            "report": report,
        }
    except Exception as exc:
        mark_task_failed(task_id, str(exc))
        raise


def _run_experiment_background(task_id: str, experiment_id: str, config: ExperimentConfig) -> None:
    run_experiment(task_id, experiment_id, config)


def submit_experiment(config: ExperimentConfig) -> dict[str, Any]:
    experiment = repo_create_experiment(
        {
            "name": None,
            "universe": config.universe,
            "start_date": config.start_date,
            "end_date": config.end_date,
            "factors": config.factors,
            "horizons": config.horizons,
            "rebalance_frequency": config.rebalance_frequency,
            "top_n": config.top_n,
            "weighting": config.weighting,
            "benchmark": config.benchmark,
        }
    )
    task = create_task(experiment_id=experiment["experiment_id"])
    mark_task_running(task["task_id"], stage="accepted", message="experiment accepted")
    submit_background(_run_experiment_background, task["task_id"], experiment["experiment_id"], config)
    return {
        "experiment": experiment,
        "task": get_task(task["task_id"]),
    }


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    return repo_get_experiment(experiment_id)
