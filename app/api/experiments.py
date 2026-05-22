from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.models import ExperimentConfig
from app.services.experiment_service import get_experiment, submit_experiment

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

TICKERS_FILE = "data/reports/filtered_universe_growth_amount_bottom_50pct_latest.json"


@router.get("/tickers")
def read_growth_tickers():
    """Return the pre-filtered growth-universe ticker list."""
    import json
    from pathlib import Path
    path = Path(TICKERS_FILE)
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


@router.get("/{experiment_id}")
def read_experiment(experiment_id: str):
    result = get_experiment(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"status": "success", "data": result}
