from __future__ import annotations

from pydantic import BaseModel, Field


class ReportSummaryModel(BaseModel):
    title: str
    output_format: str
    experiment_id: str
    factor_count: int = 0
    best_factor: str | None = None
    warning_count: int = 0


class DeployabilityItemModel(BaseModel):
    deployable_aum_floor: str | None = None
    first_light_aum: str | None = None
    first_medium_aum: str | None = None
    first_heavy_aum: str | None = None
    first_extreme_aum: str | None = None
    recommended_max_aum: str | None = None
    deployment_blocked: bool | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


class DeployabilitySummaryModel(BaseModel):
    growth: DeployabilityItemModel | None = None
    value_primary: DeployabilityItemModel | None = None
    value_baseline_reference: DeployabilityItemModel | None = None


class ReportResponseModel(BaseModel):
    report_id: str
    experiment_id: str
    task_id: str | None = None
    report_format: str
    report_path: str
    summary: ReportSummaryModel | dict | None = None
    content_type: str
    content: str | None = None
    structured: dict | None = None
    deployability: DeployabilitySummaryModel | dict | None = None


class ApiEnvelope(BaseModel):
    status: str = Field(default="success")
    data: dict | ReportResponseModel
