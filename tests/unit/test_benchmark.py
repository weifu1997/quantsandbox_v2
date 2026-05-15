from app.domain.backtest.benchmark import run_equal_weight_universe_benchmark
from app.services.dataset_service import build_research_dataset


def test_benchmark_respects_rebalance_frequency_weekly() -> None:
    dataset, _, _ = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
        start_date="2024-01-01",
        end_date="2024-03-31",
        factor_names=["momentum_20d"],
        horizons=[20],
        experiment_id="exp_benchmark_weekly",
    )
    benchmark = run_equal_weight_universe_benchmark(dataset, "future_return_20d", "W")
    full_dates = sorted(dataset.loc[dataset["is_valid_sample"] == True, "date"].drop_duplicates())
    assert len(benchmark["dates"]) < len(full_dates)
    assert len(benchmark["dates"]) == len(benchmark["returns"]) == len(benchmark["equity_curve"])
