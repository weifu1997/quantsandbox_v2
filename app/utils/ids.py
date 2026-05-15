from __future__ import annotations

import uuid


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex}"


def new_experiment_id() -> str:
    return f"exp_{uuid.uuid4().hex}"


def new_report_id() -> str:
    return f"rep_{uuid.uuid4().hex}"
