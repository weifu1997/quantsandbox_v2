from __future__ import annotations

from typing import Any

from app.domain.enums import TaskStatus
from app.repositories.task_repository import create_task as repo_create_task
from app.repositories.task_repository import get_task as repo_get_task
from app.repositories.task_repository import list_running_tasks as repo_list_running_tasks
from app.repositories.task_repository import update_task as repo_update_task


def create_task(experiment_id: str | None = None) -> dict[str, Any]:
    return repo_create_task(experiment_id=experiment_id, status=TaskStatus.PENDING.value)


def mark_task_running(task_id: str, stage: str = "queued", message: str = "") -> dict[str, Any] | None:
    return repo_update_task(
        task_id,
        status=TaskStatus.RUNNING.value,
        stage=stage,
        message=message,
    )


def update_task_progress(task_id: str, current: float, total: float, stage: str, message: str) -> dict[str, Any] | None:
    return repo_update_task(
        task_id,
        progress_current=current,
        progress_total=total,
        stage=stage,
        message=message,
    )


def mark_task_completed(task_id: str, result_ref: str | None = None, message: str = "completed") -> dict[str, Any] | None:
    return repo_update_task(
        task_id,
        status=TaskStatus.COMPLETED.value,
        stage="completed",
        message=message,
        result_ref=result_ref,
    )


def mark_task_failed(task_id: str, error: str) -> dict[str, Any] | None:
    return repo_update_task(
        task_id,
        status=TaskStatus.FAILED.value,
        stage="failed",
        error=error,
        message=error,
    )


def mark_interrupted_running_tasks() -> None:
    running = repo_list_running_tasks()
    for item in running:
        repo_update_task(
            item["task_id"],
            status=TaskStatus.INTERRUPTED.value,
            stage="interrupted",
            error="service restarted before task completion",
            message="service restarted before task completion",
        )


def get_task(task_id: str) -> dict[str, Any] | None:
    return repo_get_task(task_id)
