from app.repositories.dataset_metadata_repository import get_dataset_metadata
from app.services.backtest_service import run_strategy_backtest
from app.services.dataset_service import build_research_dataset
from app.services.factor_research_service import run_factor_research


def test_dataset_service_builds_minimal_dataset() -> None:
    dataset, summary, metadata = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750"],
        start_date="2024-01-01",
        end_date="2024-04-30",
        factor_names=["momentum_20d", "reversal_5d"],
        horizons=[5, 20],
        experiment_id="exp_flow_dataset_1",
    )
    assert not dataset.empty
    assert "factor:momentum_20d" in dataset.columns
    assert "factor:reversal_5d" in dataset.columns
    assert "future_return_5d" in dataset.columns
    assert summary["rows"] > 0
    assert set(summary["factors"]) == {"momentum_20d", "reversal_5d"}
    assert metadata["dataset_id"].startswith("ds_")
    assert get_dataset_metadata(metadata["dataset_id"]) is not None


def test_factor_research_returns_expected_shape() -> None:
    dataset, _, _ = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
        start_date="2024-01-01",
        end_date="2024-06-30",
        factor_names=["momentum_20d"],
        horizons=[5, 20],
        experiment_id="exp_flow_dataset_2",
    )
    result = run_factor_research(dataset, ["momentum_20d"], [5, 20], groups=5, split_date="2024-04-01")
    assert "momentum_20d" in result
    assert "full_sample" in result["momentum_20d"]
    assert "in_sample" in result["momentum_20d"]
    assert "out_sample" in result["momentum_20d"]
    assert "5" in result["momentum_20d"]["full_sample"]
    assert "ic" in result["momentum_20d"]["full_sample"]["5"]
    assert "group_returns" in result["momentum_20d"]["full_sample"]["5"]


def test_topn_backtest_returns_metrics() -> None:
    dataset, _, _ = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
        start_date="2024-01-01",
        end_date="2024-06-30",
        factor_names=["momentum_20d"],
        horizons=[20],
        experiment_id="exp_flow_dataset_3",
    )
    report = run_strategy_backtest(
        dataset=dataset,
        factor_name="momentum_20d",
        top_n=2,
        rebalance_frequency="W",
        weighting="equal",
        benchmark="equal_weight_universe",
        commission_bps=10.0,
        slippage_bps=5.0,
        horizon=20,
    )
    assert report.factor_name == "momentum_20d"
    assert "annual_return" in report.payload
    assert "total_return" in report.payload
    assert "equity_curve" in report.payload
    assert "benchmark_equity_curve" in report.payload
