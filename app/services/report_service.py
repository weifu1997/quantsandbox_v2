from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.settings import get_settings
from app.reports.json_report import render_json_report
from app.reports.markdown_report import render_markdown_report
from app.repositories.report_repository import create_report as repo_create_report
from app.repositories.report_repository import get_report as repo_get_report


def build_experiment_report(
    *,
    experiment_id: str,
    task_id: str | None,
    config: dict[str, Any],
    dataset_summary: dict[str, Any],
    factor_results: dict[str, Any],
    backtest_results: dict[str, Any],
    report_format: str,
) -> dict[str, Any]:
    settings = get_settings()
    normalized = str(report_format or "json").lower()

    json_payload = render_json_report(
        config=config,
        dataset_summary=dataset_summary,
        factor_results=factor_results,
        backtest_results=backtest_results,
    )
    diagnostics = json_payload.get("factor_diagnostics", [])
    warnings = json_payload.get("warnings", [])

    if normalized == "markdown":
        content = render_markdown_report(
            config=config,
            dataset_summary=dataset_summary,
            factor_results=factor_results,
            backtest_results=backtest_results,
            factor_diagnostics=diagnostics,
            warnings=warnings,
        )
        suffix = "md"
        summary = json_payload["summary"] | {
            "title": json_payload["title"],
            "output_format": "markdown",
            "experiment_id": experiment_id,
        }
    else:
        content = json.dumps(json_payload, ensure_ascii=False, indent=2)
        suffix = "json"
        summary = json_payload["summary"] | {
            "title": json_payload["title"],
            "output_format": json_payload["output_format"],
            "experiment_id": experiment_id,
        }

    report_path = settings.reports_dir / f"{experiment_id}.{suffix}"
    Path(report_path).write_text(content, encoding="utf-8")

    return repo_create_report(
        {
            "experiment_id": experiment_id,
            "task_id": task_id,
            "report_format": normalized,
            "report_path": str(report_path),
            "summary": summary,
        }
    )


def get_report(report_id: str) -> dict[str, Any] | None:
    return repo_get_report(report_id)


def resolve_report_content(report: dict[str, Any]) -> str | None:
    path = report.get("report_path")
    if not path:
        return None
    report_file = Path(path)
    if not report_file.exists():
        return None
    return report_file.read_text(encoding="utf-8")
