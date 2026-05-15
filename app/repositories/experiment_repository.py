from __future__ import annotations

import json
from typing import Any

from app.db.session import get_db_session
from app.db.tables import ExperimentTable
from app.utils.ids import new_experiment_id


def _to_dict(row: ExperimentTable) -> dict[str, Any]:
    return {
        "experiment_id": row.experiment_id,
        "name": row.name,
        "universe": row.universe,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "factors": json.loads(row.factors or "[]"),
        "horizons": json.loads(row.horizons or "[]"),
        "rebalance_frequency": row.rebalance_frequency,
        "top_n": row.top_n,
        "weighting": row.weighting,
        "benchmark": row.benchmark,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def create_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    row = ExperimentTable(
        experiment_id=new_experiment_id(),
        name=payload.get("name"),
        universe=payload.get("universe"),
        start_date=payload["start_date"],
        end_date=payload["end_date"],
        factors=json.dumps(payload.get("factors", []), ensure_ascii=False),
        horizons=json.dumps(payload.get("horizons", []), ensure_ascii=False),
        rebalance_frequency=payload.get("rebalance_frequency", "W"),
        top_n=int(payload.get("top_n", 10)),
        weighting=payload.get("weighting", "equal"),
        benchmark=payload.get("benchmark", "equal_weight_universe"),
    )
    with get_db_session() as session:
        session.add(row)
        session.flush()
        session.refresh(row)
        return _to_dict(row)


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    with get_db_session() as session:
        row = session.get(ExperimentTable, experiment_id)
        return _to_dict(row) if row else None
