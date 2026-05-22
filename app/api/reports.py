from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import ReportResponseModel
from app.services.report_service import get_report, resolve_report_content

router = APIRouter(prefix="/api/reports", tags=["reports"])


def extract_deployability(structured: dict | None) -> dict | None:
    if not structured:
        return None
    if isinstance(structured.get("deployability"), dict):
        return structured.get("deployability")
    return None


@router.get("/{report_id}", response_model=ReportResponseModel)
def read_report(report_id: str):
    result = get_report(report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="report not found")
    content = resolve_report_content(result)
    structured = None
    if result.get("report_format") == "json" and content:
        import json
        try:
            structured = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            structured = None
    return {
        **result,
        "content": content,
        "content_type": result.get("report_format"),
        "structured": structured,
        "deployability": extract_deployability(structured),
    }
