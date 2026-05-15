from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.domain.models import ExperimentConfig
from app.services.experiment_service import get_experiment, submit_experiment

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class ExperimentRequest(BaseModel):
    start_date: str
    end_date: str
    tickers: list[str] = Field(default_factory=list)
    universe: str | None = None
    factors: list[str] = Field(default_factory=list)
    horizons: list[int] = Field(default_factory=lambda: [5, 20, 60])
    rebalance_frequency: str = "W"
    top_n: int = 10
    weighting: str = "equal"
    benchmark: str = "equal_weight_universe"
    commission_bps: float = 10.0
    slippage_bps: float = 5.0
    report_format: str = "json"


@router.post("")
def create_experiment(payload: ExperimentRequest):
    if not payload.tickers and not payload.universe:
        raise HTTPException(status_code=400, detail="either tickers or universe is required")
    result = submit_experiment(ExperimentConfig(**payload.model_dump()))
    return {"status": "accepted", "data": result}


@router.get("/{experiment_id}")
def read_experiment(experiment_id: str):
    result = get_experiment(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"status": "success", "data": result}
