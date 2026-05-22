from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.settings import get_settings
from app.reports.json_report import render_json_report
from app.reports.markdown_report import render_markdown_report
from app.repositories.report_repository import create_report as repo_create_report
from app.repositories.report_repository import get_report as repo_get_report


def _normalize_report_format(report_format: str | None) -> str:
    return str(report_format or "json").lower()


def _render_report_payload(
    *,
    config: dict[str, Any],
    dataset_summary: dict[str, Any],
    factor_results: dict[str, Any],
    backtest_results: dict[str, Any],
) -> dict[str, Any]:
    return render_json_report(
        config=config,
        dataset_summary=dataset_summary,
        factor_results=factor_results,
        backtest_results=backtest_results,
    )


def _build_report_summary(json_payload: dict[str, Any], experiment_id: str, normalized_format: str) -> dict[str, Any]:
    output_format = "markdown" if normalized_format == "markdown" else json_payload["output_format"]
    return json_payload["summary"] | {
        "title": json_payload["title"],
        "output_format": output_format,
        "experiment_id": experiment_id,
    }


def _render_report_content(
    *,
    normalized_format: str,
    json_payload: dict[str, Any],
    config: dict[str, Any],
    dataset_summary: dict[str, Any],
    factor_results: dict[str, Any],
    backtest_results: dict[str, Any],
) -> tuple[str, str]:
    diagnostics = json_payload.get("factor_diagnostics", [])
    warnings = json_payload.get("warnings", [])

    if normalized_format == "markdown":
        return (
            render_markdown_report(
                config=config,
                dataset_summary=dataset_summary,
                factor_results=factor_results,
                backtest_results=backtest_results,
                factor_diagnostics=diagnostics,
                warnings=warnings,
            ),
            "md",
        )
    return json.dumps(json_payload, ensure_ascii=False, indent=2), "json"


def _persist_report_file(experiment_id: str, suffix: str, content: str) -> Path:
    settings = get_settings()
    report_path = settings.reports_dir / f"{experiment_id}.{suffix}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(content, encoding="utf-8")
    return report_path


def _create_report_record(
    *,
    experiment_id: str,
    task_id: str | None,
    normalized_format: str,
    report_path: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    return repo_create_report(
        {
            "experiment_id": experiment_id,
            "task_id": task_id,
            "report_format": normalized_format,
            "report_path": str(report_path),
            "summary": summary,
        }
    )


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
    normalized = _normalize_report_format(report_format)
    json_payload = _render_report_payload(
        config=config,
        dataset_summary=dataset_summary,
        factor_results=factor_results,
        backtest_results=backtest_results,
    )
    summary = _build_report_summary(json_payload, experiment_id, normalized)
    content, suffix = _render_report_content(
        normalized_format=normalized,
        json_payload=json_payload,
        config=config,
        dataset_summary=dataset_summary,
        factor_results=factor_results,
        backtest_results=backtest_results,
    )
    report_path = _persist_report_file(experiment_id, suffix, content)
    return _create_report_record(
        experiment_id=experiment_id,
        task_id=task_id,
        normalized_format=normalized,
        report_path=report_path,
        summary=summary,
    )


def _latest_report_candidates(report_id: str) -> list[str]:
    candidates = [report_id]
    if report_id.endswith("_latest"):
        candidates.append(report_id.removesuffix("_latest"))
    else:
        candidates.append(f"{report_id}_latest")
    return list(dict.fromkeys(candidates))


def _find_report_file_by_id(report_id: str) -> Path | None:
    settings = get_settings()
    reports_dir = settings.reports_dir
    for candidate in _latest_report_candidates(report_id):
        for suffix in ("json", "md"):
            path = reports_dir / f"{candidate}.{suffix}"
            if path.exists():
                return path
    return None


def get_report(report_id: str) -> dict[str, Any] | None:
    result = repo_get_report(report_id)
    if result is not None:
        return result

    fallback_path = _find_report_file_by_id(report_id)
    if fallback_path is None:
        return None

    suffix = fallback_path.suffix.lstrip(".")
    experiment_id = fallback_path.stem
    summary = None
    structured = None
    if suffix == "json":
        try:
            structured = json.loads(fallback_path.read_text(encoding="utf-8"))
            summary = structured.get("summary") if isinstance(structured, dict) else None
        except Exception:
            structured = None
    return {
        "report_id": report_id,
        "experiment_id": experiment_id,
        "task_id": None,
        "report_format": suffix,
        "report_path": str(fallback_path),
        "summary": summary,
        "created_at": None,
    }


def resolve_report_content(report: dict[str, Any]) -> str | None:
    path = report.get("report_path")
    if not path:
        return None
    report_file = Path(path)
    if not report_file.exists():
        return None
    return report_file.read_text(encoding="utf-8")
