from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

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
        allowed = {"equal", "score"}
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


@router.get("/{experiment_id}")
def read_experiment(experiment_id: str):
    result = get_experiment(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"status": "success", "data": result}
