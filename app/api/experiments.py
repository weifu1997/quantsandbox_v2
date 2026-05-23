from __future__ import annotations

import json
from datetime import datetime

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.models import ExperimentConfig
from app.db.session import get_db_session
from app.db.tables import DatasetMetadataTable, ReportTable, TaskTable
from app.repositories.dataset_metadata_repository import delete_dataset_metadata_by_experiment
from app.repositories.dataset_metadata_repository import list_dataset_metadata_by_experiment
from app.repositories.experiment_repository import delete_experiment as repo_delete_experiment
from app.repositories.report_repository import delete_reports_by_experiment
from app.repositories.report_repository import list_reports_by_experiment
from app.repositories.task_repository import delete_tasks_by_experiment
from app.services.experiment_service import get_experiment, submit_experiment

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

from app.config.settings import get_settings


def _get_tickers_file() -> str:
    settings = get_settings()
    return str(settings.reports_dir / "filtered_universe_growth_amount_bottom_50pct_latest.json")


@router.get("/tickers")
def read_growth_tickers():
    """Return the pre-filtered growth-universe ticker list."""
    import json
    from pathlib import Path
    path = Path(_get_tickers_file())
    if not path.exists():
        raise HTTPException(status_code=404, detail="ticker file not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "filtered_universe" in data:
        tickers = [str(x) for x in data["filtered_universe"].get("tickers", [])]
    elif isinstance(data, list):
        tickers = [str(x) for x in data]
    else:
        tickers = []
    return {"status": "success", "data": {"tickers": sorted(tickers), "count": len(tickers)}}


@router.get("/stock-names")
def read_stock_names():
    """Return ticker-to-name mapping for all reference stocks."""
    import pandas as pd
    from pathlib import Path
    from app.config.settings import get_settings
    settings = get_settings()
    ref_path = settings.data_dir / "raw" / "reference" / "stock_basic_main_board.parquet"
    if not ref_path.exists():
        raise HTTPException(status_code=404, detail="reference file not found")
    df = pd.read_parquet(ref_path)
    mapping = dict(zip(df["ticker"], df["name"]))
    return {"status": "success", "data": mapping}


class ExperimentRequest(BaseModel):
    start_date: str
    end_date: str
    tickers: list[str] = Field(default_factory=list)
    universe: str | None = None
    factors: list[str] = Field(default_factory=list)
    horizons: list[int] = Field(default_factory=lambda: [5, 20, 60])
    rebalance_frequency: str = "W"
    top_n: int = 20
    weighting: str = "liquidity_tilted_score"
    benchmark: str = "equal_weight_universe"
    commission_bps: float = 10.0
    slippage_bps: float = 5.0
    report_format: str = "json"
    annual_turnover_limit: float | None = None
    initial_aum: float = 1.0
    board_lot_enabled: bool = False
    board_lot_size: int = 100
    execution_assumptions: dict | None = None

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y%m%d")
        except ValueError as exc:
            raise ValueError("date must be in YYYYMMDD format") from exc
        return value

    @field_validator("horizons")
    @classmethod
    def validate_horizons(cls, value: list[int]) -> list[int]:
        if any(v <= 0 for v in value):
            raise ValueError("horizons must be positive integers")
        return value

    @field_validator("rebalance_frequency")
    @classmethod
    def validate_rebalance_frequency(cls, value: str) -> str:
        allowed = {"D", "W", "M"}
        if value not in allowed:
            raise ValueError(f"rebalance_frequency must be one of {sorted(allowed)}")
        return value

    @field_validator("weighting")
    @classmethod
    def validate_weighting(cls, value: str) -> str:
        allowed = {"equal", "score", "liquidity_tilted_score"}
        if value not in allowed:
            raise ValueError(f"weighting must be one of {sorted(allowed)}")
        return value

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("top_n must be > 0")
        return value

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "ExperimentRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        if not self.tickers and not self.universe:
            raise ValueError("either tickers or universe is required")
        return self


@router.post("")
def create_experiment(payload: ExperimentRequest):
    result = submit_experiment(ExperimentConfig(**payload.model_dump()))
    return {"status": "accepted", "data": result}


@router.get("/latest/report")
def latest_report():
    """Return the most recent experiment report ID."""
    import sqlite3
    from pathlib import Path
    from app.config.settings import get_settings
    settings = get_settings()
    db_path = settings.db_path
    if not db_path or not Path(db_path).exists():
        raise HTTPException(status_code=404, detail="no database found")
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT report_id FROM reports ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="no reports found")
        return {"status": "success", "data": {"report_id": row[0]}}
    finally:
        conn.close()


@router.get("/history")
def experiment_history(limit: int = 20):
    """Return recent experiment/backtest records for frontend history display."""
    import sqlite3
    from pathlib import Path

    settings = get_settings()
    db_path = settings.db_path
    if not db_path or not Path(db_path).exists():
        raise HTTPException(status_code=404, detail="no database found")

    limit = max(1, min(int(limit), 100))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                e.experiment_id,
                e.universe,
                e.start_date,
                e.end_date,
                e.factors,
                e.horizons,
                e.rebalance_frequency,
                e.top_n,
                e.weighting,
                e.benchmark,
                e.created_at AS experiment_created_at,
                t.task_id,
                t.status AS task_status,
                t.stage AS task_stage,
                t.error AS task_error,
                t.result_ref,
                t.updated_at AS task_updated_at,
                r.report_id,
                r.report_format,
                r.created_at AS report_created_at
            FROM experiments e
            LEFT JOIN tasks t
                ON t.task_id = (
                    SELECT task_id FROM tasks
                    WHERE experiment_id = e.experiment_id
                    ORDER BY created_at DESC
                    LIMIT 1
                )
            LEFT JOIN reports r
                ON r.report_id = (
                    SELECT report_id FROM reports
                    WHERE experiment_id = e.experiment_id
                    ORDER BY created_at DESC
                    LIMIT 1
                )
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = []
        for row in rows:
            items.append({
                "experiment_id": row["experiment_id"],
                "task_id": row["task_id"],
                "status": row["task_status"],
                "stage": row["task_stage"],
                "error": row["task_error"],
                "result_ref": row["result_ref"],
                "report_id": row["report_id"] or row["result_ref"],
                "report_format": row["report_format"],
                "universe": row["universe"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "factors": json.loads(row["factors"] or "[]"),
                "horizons": json.loads(row["horizons"] or "[]"),
                "rebalance_frequency": row["rebalance_frequency"],
                "top_n": row["top_n"],
                "weighting": row["weighting"],
                "benchmark": row["benchmark"],
                "created_at": row["experiment_created_at"],
                "task_updated_at": row["task_updated_at"],
                "report_created_at": row["report_created_at"],
            })
        return {"status": "success", "data": {"items": items, "count": len(items)}}
    finally:
        conn.close()


@router.get("/{experiment_id}")
def read_experiment(experiment_id: str):
    result = get_experiment(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"status": "success", "data": result}


@router.delete("/{experiment_id}")
def delete_experiment_record(experiment_id: str):
    result = get_experiment(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="experiment not found")

    report_rows = list_reports_by_experiment(experiment_id)
    dataset_rows = list_dataset_metadata_by_experiment(experiment_id)

    deleted_files: list[str] = []
    missing_files: list[str] = []

    def _cleanup_file(path_str: str | None):
        if not path_str:
            return
        path = Path(path_str)
        if path.exists() and path.is_file():
            path.unlink()
            deleted_files.append(str(path))
        else:
            missing_files.append(str(path))

    for row in report_rows:
        _cleanup_file(row.get("report_path"))

    for row in dataset_rows:
        _cleanup_file(row.get("dataset_path"))

    deleted_reports = delete_reports_by_experiment(experiment_id)
    deleted_tasks = delete_tasks_by_experiment(experiment_id)
    deleted_datasets = delete_dataset_metadata_by_experiment(experiment_id)
    deleted_experiment = repo_delete_experiment(experiment_id)

    return {
        "status": "success",
        "data": {
            "experiment_id": experiment_id,
            "deleted": bool(deleted_experiment),
            "deleted_reports": deleted_reports,
            "deleted_tasks": deleted_tasks,
            "deleted_dataset_metadata": deleted_datasets,
            "deleted_files": deleted_files,
            "missing_files": missing_files,
        },
    }
