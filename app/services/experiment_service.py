from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.domain.backtest.engine import run_topn_backtest
from app.domain.data_contracts import factor_column
from app.domain.models import ExperimentConfig
from app.repositories.experiment_repository import create_experiment as repo_create_experiment
from app.repositories.experiment_repository import get_experiment as repo_get_experiment
from app.services.factor_research_service import run_factor_research
from app.services.report_service import build_experiment_report
from scripts.run_revgrowth_candidate_review import load_tickers_from_file, build_dataset, apply_filter
from app.services.task_service import (
    create_task,
    get_task,
    mark_task_completed,
    mark_task_failed,
    mark_task_running,
    update_task_progress,
)
from app.tasks.runner import submit_background


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
        "annual_turnover_limit": config.annual_turnover_limit,
        "initial_aum": config.initial_aum,
        "board_lot_enabled": config.board_lot_enabled,
        "board_lot_size": config.board_lot_size,
        "execution_assumptions": config.execution_assumptions,
    }


def _resolve_split_date(dataset) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(split_date.date())


REPORTS_DIR = Path("data/reports")
CONFIG_PATH = REPORTS_DIR / "current_working_strategy_config_personal_100k.json"
REGISTRY_PATH = REPORTS_DIR / "revgrowth_candidate_registry.json"
TICKERS_FILE = REPORTS_DIR / "filtered_universe_growth_amount_bottom_50pct_latest.json"


def _load_growth_config() -> tuple[dict, dict]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    strategy_id = cfg["growth_core"]
    registry_item = next(x for x in registry if x.get("strategy_id") == strategy_id)
    return cfg, registry_item


def _run_growth_backtest(start_date: str, end_date: str) -> tuple[dict[str, Any], pd.DataFrame]:
    """Replicate the production growth-line backtest pipeline.

    Uses the same pre-filtered tickers, strategy config, registry params,
    market-regime features, filter, and execution assumptions as
    run_growth_personal_100k_2024_2026_boardlot_engine.py.

    Returns (backtest_results_dict, filtered_dataset).
    """
    cfg, registry_item = _load_growth_config()
    factor = registry_item["factor"]
    params = dict(registry_item["params"])
    params["top_n"] = int(cfg["operating_params"]["top_n"])
    params["rebalance_frequency"] = str(cfg["operating_params"]["rebalance_frequency"])
    params["annual_turnover_limit"] = float(cfg["operating_params"]["annual_turnover_limit"])
    params["commission_bps"] = float(cfg["operating_params"]["commission_bps"])
    params["slippage_bps"] = float(cfg["operating_params"]["slippage_bps"])
    params["horizon"] = int(params.get("horizon", 10))

    tickers = load_tickers_from_file(str(TICKERS_FILE))
    ds = build_dataset(tickers, start_date, end_date, params["horizon"], factor)
    filtered, coverage = apply_filter(ds, registry_item.get("filter", {}))

    filtered.attrs["growth_strategy_id"] = registry_item.get("strategy_id")
    filtered.attrs["growth_turnover_annual_limit"] = params.get("annual_turnover_limit")
    filtered.attrs["initial_aum"] = float(cfg["target_aum"])
    filtered.attrs["board_lot_enabled"] = True
    filtered.attrs["board_lot_size"] = 100
    if params.get("execution_assumptions"):
        execution = params["execution_assumptions"]
        filtered.attrs["execution_config_enabled"] = True
        for k, v in {
            "bar_delay": execution.get("bar_delay", 1),
            "tick_size": execution.get("tick_size", 0.01),
            "base_tick_slippage_ticks": execution.get("base_tick_slippage_ticks", 1.0),
            "high_vol_extra_tick_slippage_ticks": execution.get("high_vol_extra_tick_slippage_ticks", 1.0),
            "high_vol_quantile": execution.get("high_vol_quantile", 0.8),
            "minimum_roundtrip_ticks": execution.get("minimum_roundtrip_ticks", 2.0),
            "commission_bps_override": execution.get("commission_bps", params.get("commission_bps")),
        }.items():
            filtered.attrs[f"execution_{k}"] = v

    result = run_topn_backtest(
        dataset=filtered,
        factor_col=factor_column(factor),
        top_n=int(params["top_n"]),
        rebalance_frequency=str(params["rebalance_frequency"]),
        weighting=str(cfg["weighting_policy"]),
        benchmark="equal_weight_universe",
        commission_bps=float(params["commission_bps"]),
        slippage_bps=float(params["slippage_bps"]),
        horizon=int(params["horizon"]),
    ).payload

    result["_growth_config"] = {
        "strategy_id": registry_item.get("strategy_id"),
        "strategy_name": registry_item.get("strategy_name"),
        "filter_applied": bool(registry_item.get("filter", {})),
        "filter_rules": registry_item.get("filter", {}),
        "tickers_used": len(tickers),
        "tickers": sorted(tickers),
        "ticker_source": "filtered_universe_growth_amount_bottom_50pct",
        "coverage": coverage,
        "target_aum": cfg["target_aum"],
        "weighting_policy": cfg["weighting_policy"],
        "actual_params": {
            "top_n": params["top_n"],
            "rebalance_frequency": params["rebalance_frequency"],
            "horizon": params["horizon"],
            "annual_turnover_limit": params["annual_turnover_limit"],
            "commission_bps": params["commission_bps"],
            "slippage_bps": params["slippage_bps"],
            "board_lot_enabled": True,
            "board_lot_size": 100,
            "bar_delay": params.get("execution_assumptions", {}).get("bar_delay", 1),
            "base_tick_slippage_ticks": params.get("execution_assumptions", {}).get("base_tick_slippage_ticks", 1.0),
            "high_vol_extra_tick_slippage_ticks": params.get("execution_assumptions", {}).get("high_vol_extra_tick_slippage_ticks", 1.0),
        },
    }
    return {factor: result}, filtered


def _build_backtest_results(dataset, config: ExperimentConfig) -> dict[str, Any]:
    """Build backtest results using the growth-line pipeline."""
    bt_result, _ = _run_growth_backtest(config.start_date, config.end_date)
    return bt_result


def _build_report_payload(config: ExperimentConfig, tickers: list[str]) -> dict[str, Any]:
    return {
        **_config_to_dict(config),
        "tickers": tickers,
    }


def _create_experiment_record(config: ExperimentConfig) -> dict[str, Any]:
    return repo_create_experiment(
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


def _build_growth_dataset_summary(dataset: pd.DataFrame) -> dict[str, Any]:
    """Build a minimal dataset summary from the growth-pipeline filtered dataset."""
    invalid_reasons: dict[str, int] = {}
    if not dataset.empty and "missing_reason" in dataset.columns:
        counts = dataset.loc[dataset["is_valid_sample"] == False, "missing_reason"].value_counts(dropna=True)
        invalid_reasons = {str(k): int(v) for k, v in counts.items()}
    return {
        "rows": int(len(dataset)),
        "tickers": sorted(dataset["ticker"].unique().tolist()),
        "factors": list(dataset.columns[dataset.columns.str.startswith("factor_")]),
        "horizons": [int(c.split("_")[2].replace("d", "")) for c in dataset.columns if c.startswith("future_return_")],
        "valid_sample_ratio": float(dataset["is_valid_sample"].mean()) if not dataset.empty and "is_valid_sample" in dataset.columns else 0.0,
        "invalid_reasons": invalid_reasons,
        "warnings": [],
        "data_mode": "growth_pipeline",
    }


def run_experiment(task_id: str, experiment_id: str, config: ExperimentConfig) -> dict[str, Any]:
    try:
        update_task_progress(task_id, 1, 4, "dataset", "building research dataset")
        backtest_results, dataset = _run_growth_backtest(config.start_date, config.end_date)

        dataset_summary = _build_growth_dataset_summary(dataset)

        update_task_progress(task_id, 2, 4, "factor_research", "running factor validation")
        growth_horizons = dataset_summary["horizons"]
        factor_results = run_factor_research(
            dataset,
            config.factors,
            growth_horizons,
            groups=5,
            split_date=_resolve_split_date(dataset),
        )

        update_task_progress(task_id, 3, 4, "backtest", "running topn backtests")

        tickers_used = list(dataset["ticker"].unique())

        update_task_progress(task_id, 4, 4, "report", "building report")
        report = build_experiment_report(
            experiment_id=experiment_id,
            task_id=task_id,
            config=_build_report_payload(config, tickers_used),
            dataset_summary=dataset_summary,
            factor_results=factor_results,
            backtest_results=backtest_results,
            report_format=config.report_format,
        )

        mark_task_completed(task_id, result_ref=report["report_id"], message="experiment completed")
        return {
            "dataset_summary": dataset_summary,
            "dataset_metadata": {},
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
    experiment = _create_experiment_record(config)
    task = create_task(experiment_id=experiment["experiment_id"])
    mark_task_running(task["task_id"], stage="accepted", message="experiment accepted")
    submit_background(_run_experiment_background, task["task_id"], experiment["experiment_id"], config)
    return {
        "experiment": experiment,
        "task": get_task(task["task_id"]),
    }


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    return repo_get_experiment(experiment_id)
