from __future__ import annotations

import json
from typing import Any

from app.db.session import get_db_session
from app.db.tables import ReportTable
from app.utils.ids import new_report_id


def _to_dict(row: ReportTable) -> dict[str, Any]:
    return {
        "report_id": row.report_id,
        "experiment_id": row.experiment_id,
        "task_id": row.task_id,
        "report_format": row.report_format,
        "report_path": row.report_path,
        "summary": json.loads(row.summary_json) if row.summary_json else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def create_report(payload: dict[str, Any]) -> dict[str, Any]:
    row = ReportTable(
        report_id=new_report_id(),
        experiment_id=payload["experiment_id"],
        task_id=payload.get("task_id"),
        report_format=payload.get("report_format", "json"),
        report_path=payload["report_path"],
        summary_json=json.dumps(payload.get("summary"), ensure_ascii=False) if payload.get("summary") is not None else None,
    )
    with get_db_session() as session:
        session.add(row)
        session.flush()
        session.refresh(row)
        return _to_dict(row)


def get_report(report_id: str) -> dict[str, Any] | None:
    with get_db_session() as session:
        row = session.get(ReportTable, report_id)
        return _to_dict(row) if row else None
