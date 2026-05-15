from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.task_service import get_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}")
def read_task(task_id: str):
    result = get_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"status": "success", "data": result}
