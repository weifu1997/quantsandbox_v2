from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from app.db.session import get_db_session
from app.db.tables import DatasetMetadataTable
from app.utils.ids import new_report_id


def _to_dict(row: DatasetMetadataTable) -> dict[str, Any]:
    return {
        "dataset_id": row.dataset_id,
        "experiment_id": row.experiment_id,
        "dataset_path": row.dataset_path,
        "summary": row.summary_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def create_dataset_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    row = DatasetMetadataTable(
        dataset_id=payload.get("dataset_id") or new_report_id().replace("rep_", "ds_"),
        experiment_id=payload.get("experiment_id"),
        dataset_path=payload["dataset_path"],
        summary_json=payload.get("summary_json"),
    )
    with get_db_session() as session:
        session.add(row)
        session.flush()
        session.refresh(row)
        return _to_dict(row)


def get_dataset_metadata(dataset_id: str) -> dict[str, Any] | None:
    with get_db_session() as session:
        row = session.get(DatasetMetadataTable, dataset_id)
        return _to_dict(row) if row else None


def list_dataset_metadata_by_experiment(experiment_id: str) -> list[dict[str, Any]]:
    with get_db_session() as session:
        stmt = select(DatasetMetadataTable).where(DatasetMetadataTable.experiment_id == experiment_id)
        return [_to_dict(row) for row in session.scalars(stmt).all()]


def delete_dataset_metadata_by_experiment(experiment_id: str) -> int:
    with get_db_session() as session:
        result = session.execute(delete(DatasetMetadataTable).where(DatasetMetadataTable.experiment_id == experiment_id))
        return int(result.rowcount or 0)
