from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from app.db.session import get_db_session
from app.db.tables import TaskTable
from app.domain.enums import TaskStatus
from app.utils.ids import new_task_id


def _to_dict(row: TaskTable) -> dict[str, Any]:
    return {
        "task_id": row.task_id,
        "experiment_id": row.experiment_id,
        "status": row.status,
        "progress": {
            "current": row.progress_current,
            "total": row.progress_total,
            "message": row.message or "",
        },
        "stage": row.stage,
        "error": row.error,
        "result_ref": row.result_ref,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create_task(experiment_id: str | None = None, status: str = TaskStatus.PENDING.value) -> dict[str, Any]:
    task = TaskTable(
        task_id=new_task_id(),
        experiment_id=experiment_id,
        status=status,
        progress_current=0.0,
        progress_total=0.0,
    )
    with get_db_session() as session:
        session.add(task)
        session.flush()
        session.refresh(task)
        return _to_dict(task)


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_db_session() as session:
        row = session.get(TaskTable, task_id)
        return _to_dict(row) if row else None


def update_task(
    task_id: str,
    *,
    status: str | None = None,
    progress_current: float | None = None,
    progress_total: float | None = None,
    stage: str | None = None,
    message: str | None = None,
    error: str | None = None,
    result_ref: str | None = None,
) -> dict[str, Any] | None:
    with get_db_session() as session:
        row = session.get(TaskTable, task_id)
        if row is None:
            return None
        if status is not None:
            row.status = status
        if progress_current is not None:
            row.progress_current = progress_current
        if progress_total is not None:
            row.progress_total = progress_total
        if stage is not None:
            row.stage = stage
        if message is not None:
            row.message = message
        if error is not None:
            row.error = error
        if result_ref is not None:
            row.result_ref = result_ref
        session.add(row)
        session.flush()
        session.refresh(row)
        return _to_dict(row)


def list_running_tasks() -> list[dict[str, Any]]:
    with get_db_session() as session:
        stmt = select(TaskTable).where(TaskTable.status == TaskStatus.RUNNING.value)
        return [_to_dict(row) for row in session.scalars(stmt).all()]


def delete_tasks_by_experiment(experiment_id: str) -> int:
    with get_db_session() as session:
        result = session.execute(delete(TaskTable).where(TaskTable.experiment_id == experiment_id))
        return int(result.rowcount or 0)
