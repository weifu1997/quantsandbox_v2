from app.repositories.dataset_metadata_repository import get_dataset_metadata
from app.services.dataset_service import build_research_dataset


def test_dataset_service_persists_dataset_metadata() -> None:
    dataset, summary, metadata = build_research_dataset(
        tickers=["sh600519", "sz000858", "sz300750"],
        start_date="2024-01-01",
        end_date="2024-03-31",
        factor_names=["momentum_20d", "pe"],
        horizons=[20],
        experiment_id="exp_test_dataset_meta",
    )
    assert not dataset.empty
    assert summary["rows"] > 0
    assert metadata["dataset_id"].startswith("ds_")
    stored = get_dataset_metadata(metadata["dataset_id"])
    assert stored is not None
    assert stored["experiment_id"] == "exp_test_dataset_meta"
