from app.domain.factors.registry import build_default_factor_registry
from app.domain.research.sample_split import rolling_time_splits, split_in_sample_out_sample
from app.domain.research.validation import run_factor_validation
from app.services.dataset_service import build_research_dataset


def test_split_in_sample_out_sample() -> None:
    dataset, _, _ = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750"],
        start_date="2024-01-01",
        end_date="2024-04-30",
        factor_names=["momentum_20d"],
        horizons=[20],
        experiment_id="exp_split_test",
    )
    in_sample, out_sample = split_in_sample_out_sample(dataset, "2024-03-01")
    assert not in_sample.empty
    assert not out_sample.empty
    assert in_sample["date"].max() <= out_sample["date"].min()


def test_rolling_time_splits() -> None:
    dataset, _, _ = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750"],
        start_date="2024-01-01",
        end_date="2024-05-31",
        factor_names=["momentum_20d"],
        horizons=[20],
        experiment_id="exp_roll_test",
    )
    splits = rolling_time_splits(dataset, train_window=20, test_window=10)
    assert len(splits) >= 1


def test_validation_structure() -> None:
    dataset, _, _ = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
        start_date="2024-01-01",
        end_date="2024-06-30",
        factor_names=["momentum_20d"],
        horizons=[20],
        experiment_id="exp_validation_test",
    )
    result = run_factor_validation(dataset, "factor:momentum_20d", [20], groups=5, split_date="2024-04-01")
    assert "full_sample" in result
    assert "20" in result["full_sample"]
    assert "ic" in result["full_sample"]["20"]


def test_factor_registry_contains_phase1_factors() -> None:
    registry = build_default_factor_registry()
    names = set(registry.list_names())
    assert {"momentum_20d", "momentum_60d", "reversal_5d", "pe", "pb", "roe"}.issubset(names)
