from __future__ import annotations

from pydantic import BaseModel, Field


class ReportSummaryModel(BaseModel):
    title: str
    output_format: str
    experiment_id: str
    factor_count: int = 0
    best_factor: str | None = None
    warning_count: int = 0


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


class ApiEnvelope(BaseModel):
    status: str = Field(default="success")
    data: dict | ReportResponseModel
