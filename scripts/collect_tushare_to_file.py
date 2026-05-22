#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.adapters.fundamental_data_adapter import TushareFundamentalDataAdapter
from app.adapters.market_data_adapter import TushareMarketDataAdapter
from app.config.settings import get_settings


def _read_dataset(path: Path):
    if not path.exists():
        return None
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def _partition_file_path(base_dir: Path, ticker: str) -> Path:
    return base_dir / f"{ticker}.parquet"


def _merge_ticker_partition(base_dir: Path, ticker: str, incoming: pd.DataFrame) -> pd.DataFrame:
    path = _partition_file_path(base_dir, ticker)
    if path.exists():
        existing = _read_dataset(path)
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming.copy()
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values(["ticker", "date"]).drop_duplicates(subset=["ticker", "date"], keep="last")
    return combined.reset_index(drop=True)


def _write_dataset(path: Path, df: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
    else:
        df.to_parquet(path, index=False)


def _write_json_atomic(path: Path, payload: dict[str, Any] | list[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return path


def _run_lock_path(settings, manifest_path: str | Path | None = None) -> Path:
    manifest = _manifest_path(settings, manifest_path)
    return manifest.with_name(f"{manifest.stem}.lock")


def _load_run_lock(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"invalid": True, "path": str(path)}


def _pid_is_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_lock_stale(lock_payload: dict[str, Any] | None) -> bool:
    if not lock_payload:
        return False
    if lock_payload.get("invalid"):
        return True
    pid = lock_payload.get("pid")
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return True
    return not _pid_is_alive(pid_int)


def _mark_stale_runs_interrupted(db_path: Path, lock_path: Path, reason: str) -> int:
    _ensure_run_state_table(db_path)
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE collection_runs
            SET status = 'interrupted',
                stage = 'interrupted',
                error = ?,
                updated_at = ?,
                finished_at = COALESCE(finished_at, ?)
            WHERE lock_path = ?
              AND status = 'running'
            """,
            (reason, now, now, str(lock_path)),
        )
        conn.commit()
        return cursor.rowcount


def _acquire_or_recover_run_lock(settings, db_path: Path, manifest_path: str | Path | None = None) -> tuple[Path, dict[str, Any] | None]:
    path = _run_lock_path(settings, manifest_path)
    stale_lock_payload: dict[str, Any] | None = None
    while True:
        try:
            return _acquire_run_lock(settings, manifest_path), stale_lock_payload
        except RuntimeError:
            lock_payload = _load_run_lock(path)
            if not _is_lock_stale(lock_payload):
                raise
            stale_lock_payload = lock_payload or {"path": str(path)}
            reason = f"stale lock recovered: {path}"
            _mark_stale_runs_interrupted(db_path, path, reason)
            _release_run_lock(path)


def _acquire_run_lock(settings, manifest_path: str | Path | None = None) -> Path:
    path = _run_lock_path(settings, manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "started_at": datetime.now(UTC).isoformat(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise RuntimeError(f"collection lock already exists: {path}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def _release_run_lock(path: Path | None) -> None:
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _run_state_db_path(settings) -> Path:
    return Path(settings.db_path)


def _ensure_run_state_table(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_runs (
                run_id TEXT PRIMARY KEY,
                manifest_path TEXT NOT NULL,
                checkpoint_path TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT,
                start_date TEXT,
                end_date TEXT,
                tickers_json TEXT NOT NULL,
                modes_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                warning_count INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                lock_path TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_collection_runs_started_at ON collection_runs(started_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_collection_runs_status ON collection_runs(status)")
        conn.commit()


def _run_metrics_payload(
    *,
    market_rows_fetched: int,
    fundamental_rows_fetched: int,
    market_rows_written: int,
    fundamental_rows_written: int,
    pending_market_ticker_count: int,
    pending_fundamental_ticker_count: int,
    failed_market_ticker_count: int,
    failed_fundamental_ticker_count: int,
    market_retry_stats: dict[str, int] | None = None,
    fundamental_retry_stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "market_rows_fetched": market_rows_fetched,
        "fundamental_rows_fetched": fundamental_rows_fetched,
        "market_rows_written": market_rows_written,
        "fundamental_rows_written": fundamental_rows_written,
        "pending_market_ticker_count": pending_market_ticker_count,
        "pending_fundamental_ticker_count": pending_fundamental_ticker_count,
        "failed_market_ticker_count": failed_market_ticker_count,
        "failed_fundamental_ticker_count": failed_fundamental_ticker_count,
        "market_retry_stats": dict(market_retry_stats or {}),
        "fundamental_retry_stats": dict(fundamental_retry_stats or {}),
    }


def _derive_collection_status(
    *,
    check_only: bool,
    precheck_only: bool,
    blocked_by_lock: bool,
    interrupted: bool,
    failed: bool,
    market_failed_tickers: list[str],
    fundamental_failed_tickers: list[str],
    validation_report: dict[str, Any] | None,
    true_failed_tickers: list[str] | None = None,
    acceptable_gap_tickers: list[str] | None = None,
) -> str:
    if check_only:
        return "ready"
    if precheck_only:
        return "precheck_only"
    if blocked_by_lock:
        return "blocked_by_lock"
    if interrupted:
        return "interrupted"
    if failed:
        return "failed"
    if true_failed_tickers:
        return "partial_success"
    if acceptable_gap_tickers:
        return "success_with_gaps"
    if market_failed_tickers or fundamental_failed_tickers:
        return "partial_success"
    if validation_report is not None and validation_report.get("acceptable") is False:
        return "partial_success"
    return "completed"


def _derive_cli_stage(status: str, running_stage: str | None = None) -> str:
    if status in {"ready", "precheck_only", "blocked_by_lock", "completed", "partial_success", "success_with_gaps", "failed", "interrupted"}:
        return status
    return running_stage or "running"


def _checkpoint_status_payload(status: str, stage: str) -> dict[str, Any]:
    return {
        "status": status,
        "stage": stage,
    }


def _create_run_state(
    db_path: Path,
    *,
    run_id: str,
    manifest_path: Path,
    checkpoint_path: Path,
    status: str,
    stage: str,
    start_date: str,
    end_date: str,
    tickers: list[str],
    modes: dict[str, Any],
    metrics: dict[str, Any],
    warning_count: int,
    error: str | None,
    lock_path: Path | None,
) -> None:
    _ensure_run_state_table(db_path)
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO collection_runs (
                run_id, manifest_path, checkpoint_path, status, stage, start_date, end_date,
                tickers_json, modes_json, metrics_json, warning_count, error, lock_path,
                started_at, updated_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                str(manifest_path),
                str(checkpoint_path),
                status,
                stage,
                start_date,
                end_date,
                json.dumps(tickers, ensure_ascii=False),
                json.dumps(modes, ensure_ascii=False),
                json.dumps(metrics, ensure_ascii=False),
                warning_count,
                error,
                str(lock_path) if lock_path else None,
                now,
                now,
                now if status in {"completed", "failed", "interrupted"} else None,
            ),
        )
        conn.commit()


def _update_run_state(
    db_path: Path,
    *,
    run_id: str,
    status: str,
    stage: str,
    metrics: dict[str, Any],
    warning_count: int,
    error: str | None = None,
    finished: bool = False,
) -> None:
    _ensure_run_state_table(db_path)
    now = datetime.now(UTC).isoformat()
    finished_at = now if finished else None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE collection_runs
            SET status = ?,
                stage = ?,
                metrics_json = ?,
                warning_count = ?,
                error = ?,
                updated_at = ?,
                finished_at = COALESCE(?, finished_at)
            WHERE run_id = ?
            """,
            (
                status,
                stage,
                json.dumps(metrics, ensure_ascii=False),
                warning_count,
                error,
                now,
                finished_at,
                run_id,
            ),
        )
        conn.commit()


def _latest_run_state(db_path: Path, run_id: str) -> dict[str, Any] | None:
    _ensure_run_state_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM collection_runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def _run_report_path(settings, manifest_path: str | Path | None = None) -> Path:
    manifest = _manifest_path(settings, manifest_path)
    return manifest.with_name(f"{manifest.stem}.run-report.json")


def _decode_json_field(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _stage_timeline_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    started_at = row.get("started_at")
    updated_at = row.get("updated_at")
    finished_at = row.get("finished_at")
    stage = row.get("stage")
    timeline: list[dict[str, Any]] = []
    if started_at:
        timeline.append({"stage": "initializing", "at": started_at})
    if stage and updated_at and stage != "initializing":
        timeline.append({"stage": stage, "at": updated_at})
    if finished_at and row.get("status") in {"completed", "failed", "interrupted"}:
        timeline.append({"stage": row.get("status"), "at": finished_at})
    return timeline


def _classification_summary(*, true_failed_tickers: list[str] | None, acceptable_gap_tickers: list[str] | None, manual_review_tickers: list[str] | None) -> dict[str, int]:
    return {
        "true_failed_count": len(sorted(true_failed_tickers or [])),
        "acceptable_gap_count": len(sorted(acceptable_gap_tickers or [])),
        "manual_review_count": len(sorted(manual_review_tickers or [])),
    }


def _decision_summary_from_classification(
    *,
    classification_summary: dict[str, Any] | None,
    validation_report: dict[str, Any] | None,
) -> dict[str, Any]:
    classification_summary = classification_summary or {}
    validation_summary = {
        "acceptable": validation_report.get("acceptable") if validation_report else None,
        "review_required": validation_report.get("review_required") if validation_report else None,
        "warnings": validation_report.get("warnings", []) if validation_report else [],
    }
    manual_review_required = bool(validation_summary["review_required"])
    true_failed_count = int(classification_summary.get("true_failed_count", 0))
    acceptable_gap_count = int(classification_summary.get("acceptable_gap_count", 0))
    manual_review_count = int(classification_summary.get("manual_review_count", 0))

    warnings_text = "\n".join(str(item) for item in validation_summary["warnings"])
    time_lag_review = "resume_day_tushare_not_updated" in warnings_text

    blocking_reasons: list[str] = []
    if true_failed_count > 0:
        blocking_reasons.append(f"true_failed_tickers={true_failed_count}")
    if (manual_review_required or manual_review_count > 0) and not time_lag_review:
        blocking_reasons.append(f"manual_review_tickers={manual_review_count}")
    if validation_summary["acceptable"] is False and true_failed_count == 0 and manual_review_count == 0:
        blocking_reasons.append("validation_not_acceptable")

    if true_failed_count > 0:
        retry_recommendation = "retry_true_failed"
    elif time_lag_review:
        retry_recommendation = "retry_after_data_refresh"
    elif manual_review_required or manual_review_count > 0:
        retry_recommendation = "review_before_retry"
    elif acceptable_gap_count > 0:
        retry_recommendation = "no_retry_acceptable_gaps"
    else:
        retry_recommendation = "no_retry_needed"

    if true_failed_count > 0 or (manual_review_required and not time_lag_review):
        downstream_readiness = "blocked"
    elif time_lag_review:
        downstream_readiness = "ready_with_gaps"
    elif validation_summary["acceptable"] is False:
        downstream_readiness = "warning"
    elif acceptable_gap_count > 0:
        downstream_readiness = "ready_with_gaps"
    else:
        downstream_readiness = "ready"

    return {
        "retry_recommendation": retry_recommendation,
        "manual_review_required": manual_review_required,
        "downstream_readiness": downstream_readiness,
        "blocking_reasons": blocking_reasons,
        "validation": validation_summary,
        "time_lag_review": time_lag_review,
    }


def _build_run_report(
    *,
    run_row: dict[str, Any],
    warnings: list[str],
    validation_report: dict[str, Any] | None,
    precheck_report: dict[str, Any] | None,
    failed_market_tickers: list[str],
    failed_fundamental_tickers: list[str],
    unified_status: str | None = None,
    true_failed_tickers: list[str] | None = None,
    acceptable_gap_tickers: list[str] | None = None,
    manual_review_tickers: list[str] | None = None,
    market_true_failed_tickers: list[str] | None = None,
    market_acceptable_gap_tickers: list[str] | None = None,
    market_manual_review_tickers: list[str] | None = None,
    fundamental_true_failed_tickers: list[str] | None = None,
    fundamental_acceptable_gap_tickers: list[str] | None = None,
    fundamental_manual_review_tickers: list[str] | None = None,
) -> dict[str, Any]:
    metrics = _decode_json_field(run_row.get("metrics_json"), {})
    modes = _decode_json_field(run_row.get("modes_json"), {})
    tickers = _decode_json_field(run_row.get("tickers_json"), [])
    acceptable = validation_report.get("acceptable") if validation_report else None
    final_status = unified_status or run_row.get("status")
    raw_market_missing_tickers = sorted(failed_market_tickers)
    raw_fundamental_missing_tickers = sorted(failed_fundamental_tickers)
    raw_fetch_missing_tickers_union = sorted(set(raw_market_missing_tickers) | set(raw_fundamental_missing_tickers))
    true_failed_tickers = sorted(true_failed_tickers or [])
    acceptable_gap_tickers = sorted(acceptable_gap_tickers or [])
    manual_review_tickers = sorted(manual_review_tickers or [])
    market_true_failed_tickers = sorted(market_true_failed_tickers or [])
    market_acceptable_gap_tickers = sorted(market_acceptable_gap_tickers or [])
    market_manual_review_tickers = sorted(market_manual_review_tickers or [])
    fundamental_true_failed_tickers = sorted(fundamental_true_failed_tickers or [])
    fundamental_acceptable_gap_tickers = sorted(fundamental_acceptable_gap_tickers or [])
    fundamental_manual_review_tickers = sorted(fundamental_manual_review_tickers or [])
    classification_summary = _classification_summary(
        true_failed_tickers=true_failed_tickers,
        acceptable_gap_tickers=acceptable_gap_tickers,
        manual_review_tickers=manual_review_tickers,
    )
    decision_summary = _decision_summary_from_classification(
        classification_summary=classification_summary,
        validation_report=validation_report,
    )
    return {
        "run_id": run_row.get("run_id"),
        "status": run_row.get("status"),
        "unified_status": final_status,
        "final_status": final_status,
        "stage": run_row.get("stage"),
        "stage_timeline": _stage_timeline_from_row(run_row),
        "start_date": run_row.get("start_date"),
        "end_date": run_row.get("end_date"),
        "started_at": run_row.get("started_at"),
        "updated_at": run_row.get("updated_at"),
        "finished_at": run_row.get("finished_at"),
        "manifest_path": run_row.get("manifest_path"),
        "checkpoint_path": run_row.get("checkpoint_path"),
        "lock_path": run_row.get("lock_path"),
        "tickers": tickers,
        "ticker_count": len(tickers),
        "modes": modes,
        "metrics": metrics,
        "warnings": warnings,
        "warning_count": len(warnings),
        "validation": validation_report,
        "validation_acceptable": acceptable,
        "precheck": precheck_report,
        "failed_market_tickers": raw_market_missing_tickers,
        "failed_fundamental_tickers": raw_fundamental_missing_tickers,
        "raw_market_missing_tickers": raw_market_missing_tickers,
        "raw_fundamental_missing_tickers": raw_fundamental_missing_tickers,
        "raw_fetch_missing_tickers_union": raw_fetch_missing_tickers_union,
        "raw_fetch_missing_ticker_count": len(raw_fetch_missing_tickers_union),
        "failed_tickers_union": raw_fetch_missing_tickers_union,
        "failed_ticker_count": len(raw_fetch_missing_tickers_union),
        "true_failed_tickers": true_failed_tickers,
        "true_failed_ticker_count": len(true_failed_tickers),
        "acceptable_gap_tickers": acceptable_gap_tickers,
        "acceptable_gap_ticker_count": len(acceptable_gap_tickers),
        "manual_review_tickers": manual_review_tickers,
        "manual_review_ticker_count": len(manual_review_tickers),
        "classification_summary": classification_summary,
        "market_classification": {
            "true_failed_tickers": market_true_failed_tickers,
            "acceptable_gap_tickers": market_acceptable_gap_tickers,
            "manual_review_tickers": market_manual_review_tickers,
        },
        "fundamental_classification": {
            "true_failed_tickers": fundamental_true_failed_tickers,
            "acceptable_gap_tickers": fundamental_acceptable_gap_tickers,
            "manual_review_tickers": fundamental_manual_review_tickers,
        },
        "retry_recommendation": decision_summary["retry_recommendation"],
        "manual_review_required": decision_summary["manual_review_required"],
        "downstream_readiness": decision_summary["downstream_readiness"],
        "blocking_reasons": decision_summary["blocking_reasons"],
        "error": run_row.get("error"),
    }


def _save_run_report(settings, report: dict[str, Any], manifest_path: str | Path | None = None) -> Path:
    path = _run_report_path(settings, manifest_path)
    return _write_json_atomic(path, report)


def _build_result_payload(
    *,
    base_result: dict[str, Any],
    unified_status: str,
    cli_stage: str,
    validation_report: dict[str, Any] | None,
    run_report: dict[str, Any] | None,
    manifest_output_path: Path | None,
    checkpoint_path: Path | None,
    run_state_db_path: Path | None,
    run_id: str | None,
    classification_summary: dict[str, Any],
    true_failed_tickers: list[str],
    acceptable_gap_tickers: list[str],
    manual_review_tickers: list[str],
    raw_market_missing_tickers: list[str],
    raw_fundamental_missing_tickers: list[str],
    market_true_failed_tickers: list[str] | None = None,
    market_acceptable_gap_tickers: list[str] | None = None,
    market_manual_review_tickers: list[str] | None = None,
    fundamental_true_failed_tickers: list[str] | None = None,
    fundamental_acceptable_gap_tickers: list[str] | None = None,
    fundamental_manual_review_tickers: list[str] | None = None,
) -> dict[str, Any]:
    result = dict(base_result)
    raw_fetch_missing_tickers_union = sorted(set(raw_market_missing_tickers) | set(raw_fundamental_missing_tickers))
    validation_summary = {
        "acceptable": validation_report.get("acceptable") if validation_report else None,
        "review_required": validation_report.get("review_required") if validation_report else None,
        "warnings": validation_report.get("warnings", []) if validation_report else [],
    }
    decision_summary = _decision_summary_from_classification(
        classification_summary=classification_summary,
        validation_report=validation_report,
    )
    market_classification_summary = _classification_summary(
        true_failed_tickers=sorted(market_true_failed_tickers or []),
        acceptable_gap_tickers=sorted(market_acceptable_gap_tickers or []),
        manual_review_tickers=sorted(market_manual_review_tickers or []),
    )
    fundamental_classification_summary = _classification_summary(
        true_failed_tickers=sorted(fundamental_true_failed_tickers or []),
        acceptable_gap_tickers=sorted(fundamental_acceptable_gap_tickers or []),
        manual_review_tickers=sorted(fundamental_manual_review_tickers or []),
    )
    result["summary"] = {
        "unified_status": unified_status,
        "cli_stage": cli_stage,
        "classification_summary": classification_summary,
        "market_classification_summary": market_classification_summary,
        "fundamental_classification_summary": fundamental_classification_summary,
        "validation": validation_summary,
        "raw_fetch_missing_summary": {
            "market_missing_count": len(raw_market_missing_tickers),
            "fundamental_missing_count": len(raw_fundamental_missing_tickers),
            "raw_fetch_missing_ticker_count": len(raw_fetch_missing_tickers_union),
        },
        "retry_recommendation": decision_summary["retry_recommendation"],
        "manual_review_required": decision_summary["manual_review_required"],
        "downstream_readiness": decision_summary["downstream_readiness"],
        "blocking_reasons": decision_summary["blocking_reasons"],
    }
    result["details"] = {
        "classification": {
            "true_failed_tickers": true_failed_tickers,
            "acceptable_gap_tickers": acceptable_gap_tickers,
            "manual_review_tickers": manual_review_tickers,
            "market": {
                "true_failed_tickers": sorted(market_true_failed_tickers or []),
                "acceptable_gap_tickers": sorted(market_acceptable_gap_tickers or []),
                "manual_review_tickers": sorted(market_manual_review_tickers or []),
            },
            "fundamental": {
                "true_failed_tickers": sorted(fundamental_true_failed_tickers or []),
                "acceptable_gap_tickers": sorted(fundamental_acceptable_gap_tickers or []),
                "manual_review_tickers": sorted(fundamental_manual_review_tickers or []),
            },
        },
        "raw_fetch_missing": {
            "raw_market_missing_tickers": raw_market_missing_tickers,
            "raw_fundamental_missing_tickers": raw_fundamental_missing_tickers,
            "raw_fetch_missing_tickers_union": raw_fetch_missing_tickers_union,
        },
        "artifacts": {
            "manifest": str(manifest_output_path) if manifest_output_path else result.get("manifest_path"),
            "checkpoint": str(checkpoint_path) if checkpoint_path else result.get("checkpoint_path"),
            "validation_report_path": result.get("validation_report_path"),
            "run_report_path": result.get("run_report_path"),
            "precheck_report_path": result.get("precheck_report_path"),
        },
        "run": {
            "run_id": run_id,
            "run_state_db_path": str(run_state_db_path) if run_state_db_path else None,
        },
        "validation_report": validation_report,
        "run_report": run_report,
    }
    result["unified_status"] = unified_status
    result["cli_stage"] = cli_stage
    if "failed_market_tickers" in result:
        result.pop("failed_market_tickers", None)
    if "fundamental_failed_tickers" in result:
        result.pop("fundamental_failed_tickers", None)
    return result


def _build_quick_result(
    *,
    base_result: dict[str, Any],
    unified_status: str,
    cli_stage: str,
    validation_report: dict[str, Any] | None = None,
    classification_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_result_payload(
        base_result=base_result,
        unified_status=unified_status,
        cli_stage=cli_stage,
        validation_report=validation_report,
        run_report=None,
        manifest_output_path=None,
        checkpoint_path=None,
        run_state_db_path=None,
        run_id=None,
        classification_summary=classification_summary or {
            "true_failed_count": 0,
            "acceptable_gap_count": 0,
            "manual_review_count": 0,
        },
        true_failed_tickers=[],
        acceptable_gap_tickers=[],
        manual_review_tickers=[],
        raw_market_missing_tickers=[],
        raw_fundamental_missing_tickers=[],
    )


def _manifest_path(settings, manifest_path: str | Path | None = None) -> Path:
    if manifest_path:
        return Path(manifest_path)
    return settings.data_dir / "raw" / "tushare_manifest.json"


def _checkpoint_path(settings, checkpoint_path: str | Path | None = None, manifest_path: str | Path | None = None) -> Path:
    if checkpoint_path:
        return Path(checkpoint_path)
    manifest = _manifest_path(settings, manifest_path)
    return manifest.with_name(f"{manifest.stem}.checkpoint.json")


def _load_manifest(settings, manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = _manifest_path(settings, manifest_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _next_start_date_from_manifest(manifest: dict[str, Any]) -> str | None:
    last_end = manifest.get("last_end_date")
    if not last_end:
        return None
    dt = pd.to_datetime(last_end) + timedelta(days=1)
    return dt.strftime("%Y%m%d")


def _resolve_tickers(
    cli_tickers: list[str] | None,
    manifest: dict[str, Any],
    append_tickers: bool,
    tickers_file: str | Path | None = None,
) -> list[str]:
    previous = list(manifest.get("tickers", []))
    file_tickers: list[str] = []
    if tickers_file:
        raw = Path(tickers_file).read_text(encoding="utf-8").strip()
        if raw:
            if raw.startswith("["):
                file_tickers = list(json.loads(raw))
            else:
                file_tickers = raw.split()
    current = list(cli_tickers or []) or file_tickers
    if append_tickers:
        return sorted(set(previous) | set(current))
    return current or previous


def _update_manifest(
    settings,
    market_dir: Path,
    fundamental_dir: Path,
    tickers: list[str],
    start_date: str,
    end_date: str,
    market_rows: int,
    fundamental_rows: int,
    warnings: list[str],
    modes: dict[str, bool],
    manifest_path: str | Path | None = None,
    dataset_max_date: str | None = None,
    latest_complete_end_date: str | None = None,
    unified_status: str | None = None,
    classification_summary: dict[str, Any] | None = None,
    market_classification_summary: dict[str, Any] | None = None,
    fundamental_classification_summary: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
):
    manifest_path = _manifest_path(settings, manifest_path)
    previous = _load_manifest(settings, manifest_path)
    payload = {
        "version": 2,
        "partition_mode": "by_ticker",
        "market_dir": str(market_dir),
        "fundamental_dir": str(fundamental_dir),
        "tickers": tickers,
        "ticker_count": len(tickers),
        "last_start_date": start_date,
        "last_end_date": end_date,
        "target_end_date": end_date,
        "dataset_max_date": dataset_max_date,
        "latest_complete_end_date": latest_complete_end_date,
        "market_rows": market_rows,
        "fundamental_rows": fundamental_rows,
        "warnings": warnings,
        "modes": modes,
        "unified_status": unified_status,
        "classification_summary": classification_summary or {},
        "market_classification_summary": market_classification_summary or {},
        "fundamental_classification_summary": fundamental_classification_summary or {},
        "previous_last_end_date": previous.get("last_end_date"),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    decision_summary = _decision_summary_from_classification(
        classification_summary=payload["classification_summary"],
        validation_report=validation_report,
    )
    payload.update(
        {
            "retry_recommendation": decision_summary["retry_recommendation"],
            "manual_review_required": decision_summary["manual_review_required"],
            "downstream_readiness": decision_summary["downstream_readiness"],
            "blocking_reasons": decision_summary["blocking_reasons"],
        }
    )
    _write_json_atomic(manifest_path, payload)
    return manifest_path


def _load_checkpoint(settings, checkpoint_path: str | Path | None = None, manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = _checkpoint_path(settings, checkpoint_path, manifest_path)
    if not path.exists():
        return {
            "version": 1,
            "market_completed_tickers": [],
            "fundamental_completed_tickers": [],
            "market_failed_tickers": [],
            "fundamental_failed_tickers": [],
            "true_failed_tickers": [],
            "acceptable_gap_tickers": [],
            "manual_review_tickers": [],
            "market_true_failed_tickers": [],
            "market_acceptable_gap_tickers": [],
            "market_manual_review_tickers": [],
            "fundamental_true_failed_tickers": [],
            "fundamental_acceptable_gap_tickers": [],
            "fundamental_manual_review_tickers": [],
            "updated_at": None,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("true_failed_tickers", [])
    payload.setdefault("acceptable_gap_tickers", [])
    payload.setdefault("manual_review_tickers", [])
    payload.setdefault("market_true_failed_tickers", [])
    payload.setdefault("market_acceptable_gap_tickers", [])
    payload.setdefault("market_manual_review_tickers", [])
    payload.setdefault("fundamental_true_failed_tickers", [])
    payload.setdefault("fundamental_acceptable_gap_tickers", [])
    payload.setdefault("fundamental_manual_review_tickers", [])
    return payload


def _save_checkpoint(
    settings,
    checkpoint: dict[str, Any],
    checkpoint_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> Path:
    path = _checkpoint_path(settings, checkpoint_path, manifest_path)
    payload = dict(checkpoint)
    payload["version"] = 1
    payload["updated_at"] = datetime.now(UTC).isoformat()
    return _write_json_atomic(path, payload)


def _completed_tickers(df: pd.DataFrame) -> list[str]:
    if df.empty or "ticker" not in df.columns:
        return []
    return sorted({str(x) for x in df["ticker"].dropna().tolist()})


def _failed_tickers(requested: list[str], df: pd.DataFrame) -> list[str]:
    completed = set(_completed_tickers(df))
    return sorted([t for t in requested if t not in completed])


def _classify_ticker_outcomes(
    *,
    requested: list[str],
    completed_tickers: list[str],
    missing_tickers: list[str],
    reference_names: dict[str, str] | None = None,
    reference_records: dict[str, dict[str, str]] | None = None,
    latest_local_dates: dict[str, str] | None = None,
    target_end_date: str | None = None,
    warning_messages: list[str] | None = None,
) -> dict[str, list[str]]:
    reference_names = reference_names or {}
    reference_records = reference_records or {}
    latest_local_dates = latest_local_dates or {}
    warning_messages = warning_messages or []
    completed_set = set(completed_tickers)
    missing_set = set(missing_tickers)
    true_failed: list[str] = []
    acceptable_gap: list[str] = []
    manual_review: list[str] = []
    target_end = pd.to_datetime(target_end_date) if target_end_date else None

    warning_text = "\n".join(str(message) for message in warning_messages)

    for ticker in requested:
        if ticker in completed_set or ticker not in missing_set:
            continue
        record = reference_records.get(ticker, {})
        name = str(record.get("name") or reference_names.get(ticker, "") or "")
        list_status = str(record.get("list_status") or "")
        list_date = str(record.get("list_date") or "")
        delist_date = str(record.get("delist_date") or "")
        latest_local_date = latest_local_dates.get(ticker)
        latest_local_ts = pd.to_datetime(latest_local_date) if latest_local_date else None
        stale_days = None
        if target_end is not None and latest_local_ts is not None:
            stale_days = int((target_end - latest_local_ts).days)
        list_date_ts = pd.to_datetime(list_date) if list_date else None
        delist_date_ts = pd.to_datetime(delist_date) if delist_date else None

        ticker_warning_lines = [
            line for line in warning_text.splitlines()
            if ticker in line
        ]
        has_empty_warning = any("returned empty" in line for line in ticker_warning_lines)
        has_fetch_error_warning = any(
            any(keyword in line for keyword in ["failed for", "timeout", "retry_warning", "error="])
            for line in ticker_warning_lines
        )

        if list_status and list_status != "L":
            acceptable_gap.append(ticker)
        elif delist_date_ts is not None and target_end is not None and delist_date_ts <= target_end:
            acceptable_gap.append(ticker)
        elif list_date_ts is not None and target_end is not None and list_date_ts > target_end:
            manual_review.append(ticker)
        elif "ST" in name.upper():
            acceptable_gap.append(ticker)
        elif has_empty_warning and not has_fetch_error_warning:
            acceptable_gap.append(ticker)
        elif latest_local_ts is None:
            manual_review.append(ticker)
        elif has_fetch_error_warning:
            true_failed.append(ticker)
        elif stale_days is not None and stale_days <= 7:
            manual_review.append(ticker)
        else:
            true_failed.append(ticker)

    leftovers = sorted(missing_set - set(true_failed) - set(acceptable_gap) - set(manual_review))
    manual_review.extend(leftovers)
    return {
        "true_failed_tickers": sorted(true_failed),
        "acceptable_gap_tickers": sorted(acceptable_gap),
        "manual_review_tickers": sorted(set(manual_review)),
    }


def _write_partitioned(base_dir: Path, df: pd.DataFrame) -> int:
    base_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    if df.empty:
        return written
    for ticker, group in df.groupby("ticker", sort=True):
        merged = _merge_ticker_partition(base_dir, str(ticker), group.copy())
        path = _partition_file_path(base_dir, str(ticker))
        _write_dataset(path, merged)
        written += len(group)
    return written


def _business_day_count(start_date: str, end_date: str) -> int:
    return len(pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="B"))


def _validate_partition_dir(base_dir: Path, tickers: list[str], start_date: str, end_date: str) -> dict[str, Any]:
    expected = set(tickers)
    files = sorted(base_dir.glob("*.parquet")) if base_dir.exists() else []
    file_map = {p.stem: p for p in files}
    present = set(file_map)
    missing = sorted(expected - present)
    extra = sorted(present - expected)
    expected_days = _business_day_count(start_date, end_date)
    suspicious_row_tickers: list[str] = []
    uncovered_range_tickers: list[str] = []
    min_rows_threshold = max(5, expected_days // 2) if expected_days > 0 else 5

    for ticker in sorted(expected & present):
        df = _read_dataset(file_map[ticker])
        if df is None or df.empty:
            suspicious_row_tickers.append(ticker)
            uncovered_range_tickers.append(ticker)
            continue
        df["date"] = pd.to_datetime(df["date"])
        sample = df.loc[(df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))].copy()
        if len(sample) < min_rows_threshold:
            suspicious_row_tickers.append(ticker)
        if sample.empty:
            uncovered_range_tickers.append(ticker)
            continue
        if sample["date"].min() > pd.to_datetime(start_date) or sample["date"].max() < pd.to_datetime(end_date):
            uncovered_range_tickers.append(ticker)

    return {
        "file_count": len(files),
        "missing_count": len(missing),
        "missing_tickers": missing,
        "extra_count": len(extra),
        "extra_tickers": extra,
        "suspicious_row_count": len(suspicious_row_tickers),
        "suspicious_row_tickers": suspicious_row_tickers,
        "uncovered_range_count": len(uncovered_range_tickers),
        "uncovered_range_tickers": uncovered_range_tickers,
        "expected_business_days": expected_days,
        "min_rows_threshold": min_rows_threshold,
    }


def _validate_collection(
    market_dir: Path,
    fundamental_dir: Path,
    tickers: list[str],
    start_date: str,
    end_date: str,
    collect_market: bool,
    collect_fundamental: bool,
    true_failed_tickers: list[str] | None = None,
    acceptable_gap_tickers: list[str] | None = None,
    manual_review_tickers: list[str] | None = None,
    market_true_failed_tickers: list[str] | None = None,
    market_acceptable_gap_tickers: list[str] | None = None,
    market_manual_review_tickers: list[str] | None = None,
    fundamental_true_failed_tickers: list[str] | None = None,
    fundamental_acceptable_gap_tickers: list[str] | None = None,
    fundamental_manual_review_tickers: list[str] | None = None,
) -> dict[str, Any]:
    report = {
        "ticker_count": len(tickers),
        "start_date": start_date,
        "end_date": end_date,
        "market": None,
        "fundamental": None,
    }
    true_failed_tickers = sorted(true_failed_tickers or [])
    acceptable_gap_tickers = sorted(acceptable_gap_tickers or [])
    manual_review_tickers = sorted(manual_review_tickers or [])
    review_required = len(manual_review_tickers) > 0
    acceptable = len(true_failed_tickers) == 0 and not review_required
    warnings: list[str] = []
    if acceptable_gap_tickers:
        warnings.append(
            f"acceptable_gap_tickers={','.join(acceptable_gap_tickers)}"
        )
    if market_manual_review_tickers and not fundamental_manual_review_tickers and acceptable_gap_tickers:
        warnings.append(
            f"resume_day_tushare_not_updated={','.join(sorted(market_manual_review_tickers))}"
        )
    if collect_market:
        market_report = _validate_partition_dir(market_dir, tickers, start_date, end_date)
        report["market"] = market_report
    if collect_fundamental:
        fundamental_report = _validate_partition_dir(fundamental_dir, tickers, start_date, end_date)
        report["fundamental"] = fundamental_report
    report["true_failed_tickers"] = true_failed_tickers
    report["acceptable_gap_tickers"] = acceptable_gap_tickers
    report["manual_review_tickers"] = manual_review_tickers
    report["market_classification"] = {
        "true_failed_tickers": sorted(market_true_failed_tickers or []),
        "acceptable_gap_tickers": sorted(market_acceptable_gap_tickers or []),
        "manual_review_tickers": sorted(market_manual_review_tickers or []),
    }
    report["fundamental_classification"] = {
        "true_failed_tickers": sorted(fundamental_true_failed_tickers or []),
        "acceptable_gap_tickers": sorted(fundamental_acceptable_gap_tickers or []),
        "manual_review_tickers": sorted(fundamental_manual_review_tickers or []),
    }
    if market_manual_review_tickers and not fundamental_manual_review_tickers and acceptable_gap_tickers:
        report["review_reason"] = "resume_day_tushare_not_updated"
    report["review_required"] = review_required
    report["warnings"] = warnings
    report["acceptable"] = acceptable
    return report


def _validation_report_path(settings, manifest_path: str | Path | None = None) -> Path:
    manifest = _manifest_path(settings, manifest_path)
    return manifest.with_name(f"{manifest.stem}.validation.json")


def _precheck_report_path(settings, manifest_path: str | Path | None = None) -> Path:
    manifest = _manifest_path(settings, manifest_path)
    return manifest.with_name(f"{manifest.stem}.precheck.json")


def _compute_manifest_dates(
    market_dir: Path,
    fundamental_dir: Path,
    tickers: list[str],
    end_date: str,
    collect_market: bool,
    collect_fundamental: bool,
) -> tuple[str | None, str | None]:
    dataset_max_candidates: list[pd.Timestamp] = []
    complete_candidates: list[pd.Timestamp] = []
    target_end = pd.to_datetime(end_date)

    for base_dir, enabled in ((market_dir, collect_market), (fundamental_dir, collect_fundamental)):
        if not enabled:
            continue
        dataset_dates: list[pd.Timestamp] = []
        complete_dates: list[pd.Timestamp] = []
        for ticker in tickers:
            path = _partition_file_path(base_dir, ticker)
            if not path.exists():
                continue
            df = _read_dataset(path)
            if df is None or df.empty or "date" not in df.columns:
                continue
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if dates.empty:
                continue
            max_date = dates.max()
            dataset_dates.append(max_date)
            complete_dates.append(min(max_date, target_end))
        if dataset_dates:
            dataset_max_candidates.append(max(dataset_dates))
        if complete_dates:
            complete_candidates.append(min(complete_dates))

    dataset_max_date = max(dataset_max_candidates).strftime("%Y%m%d") if dataset_max_candidates else None
    latest_complete_end_date = min(complete_candidates).strftime("%Y%m%d") if complete_candidates else None
    return dataset_max_date, latest_complete_end_date


def _latest_partition_dates(
    market_dir: Path,
    fundamental_dir: Path,
    tickers: list[str],
    collect_market: bool,
    collect_fundamental: bool,
) -> dict[str, str]:
    latest_dates: dict[str, list[pd.Timestamp]] = {}
    for base_dir, enabled in ((market_dir, collect_market), (fundamental_dir, collect_fundamental)):
        if not enabled:
            continue
        for ticker in tickers:
            path = _partition_file_path(base_dir, ticker)
            if not path.exists():
                continue
            df = _read_dataset(path)
            if df is None or df.empty or "date" not in df.columns:
                continue
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if dates.empty:
                continue
            latest_dates.setdefault(ticker, []).append(dates.max())
    return {ticker: max(values).strftime("%Y%m%d") for ticker, values in latest_dates.items() if values}


def _save_validation_report(settings, report: dict[str, Any], manifest_path: str | Path | None = None) -> Path:
    path = _validation_report_path(settings, manifest_path)
    return _write_json_atomic(path, report)


def _save_precheck_report(settings, report: dict[str, Any], manifest_path: str | Path | None = None) -> Path:
    path = _precheck_report_path(settings, manifest_path)
    return _write_json_atomic(path, report)


def _load_reference_records(settings, manifest_path: str | Path | None = None) -> dict[str, dict[str, str]]:
    manifest = _manifest_path(settings, manifest_path)
    reference_path = manifest.parent / "reference" / "stock_basic_main_board.parquet"
    if not reference_path.exists():
        return {}
    required_columns = ["ticker", "name", "list_status", "list_date", "delist_date"]
    try:
        df = pd.read_parquet(reference_path, columns=required_columns)
    except Exception:
        try:
            df = pd.read_parquet(reference_path)
        except Exception:
            return {}
    if df.empty or "ticker" not in df.columns:
        return {}
    records: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            continue
        records[ticker] = {
            "name": str(row.get("name") or "").strip(),
            "list_status": str(row.get("list_status") or "").strip(),
            "list_date": str(row.get("list_date") or "").strip(),
            "delist_date": str(row.get("delist_date") or "").strip(),
        }
    return records


def _load_reference_names(settings, manifest_path: str | Path | None = None) -> dict[str, str]:
    return {ticker: payload.get("name", "") for ticker, payload in _load_reference_records(settings, manifest_path).items()}


def _classify_existing_tickers(base_dir: Path, tickers: list[str], end_date: str) -> dict[str, Any]:
    covered: list[str] = []
    incremental: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    incremental_start_dates: dict[str, str] = {}
    target_end = pd.to_datetime(end_date)

    for ticker in tickers:
        path = _partition_file_path(base_dir, ticker)
        if not path.exists():
            missing.append(ticker)
            continue
        try:
            df = _read_dataset(path)
            if df is None or df.empty or "date" not in df.columns:
                invalid.append(ticker)
                continue
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if dates.empty:
                invalid.append(ticker)
                continue
            max_date = dates.max()
            if max_date >= target_end:
                covered.append(ticker)
            else:
                incremental.append(ticker)
                incremental_start_dates[ticker] = (max_date + pd.Timedelta(days=1)).strftime("%Y%m%d")
        except Exception:
            invalid.append(ticker)

    return {
        "covered_tickers": sorted(covered),
        "incremental_tickers": sorted(incremental),
        "missing_tickers": sorted(missing),
        "invalid_tickers": sorted(invalid),
        "incremental_start_dates": incremental_start_dates,
    }


def _build_precheck_report(
    market_dir: Path,
    fundamental_dir: Path,
    tickers: list[str],
    end_date: str,
    collect_market: bool,
    collect_fundamental: bool,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "ticker_count": len(tickers),
        "target_end_date": end_date,
        "market": None,
        "fundamental": None,
    }
    if collect_market:
        market = _classify_existing_tickers(market_dir, tickers, end_date)
        market["covered_count"] = len(market["covered_tickers"])
        market["incremental_count"] = len(market["incremental_tickers"])
        market["missing_count"] = len(market["missing_tickers"])
        market["invalid_count"] = len(market["invalid_tickers"])
        report["market"] = market
    if collect_fundamental:
        fundamental = _classify_existing_tickers(fundamental_dir, tickers, end_date)
        fundamental["covered_count"] = len(fundamental["covered_tickers"])
        fundamental["incremental_count"] = len(fundamental["incremental_tickers"])
        fundamental["missing_count"] = len(fundamental["missing_tickers"])
        fundamental["invalid_count"] = len(fundamental["invalid_tickers"])
        report["fundamental"] = fundamental
    return report


def _iter_chunks(items: list[str], chunk_size: int):
    for i in range(0, len(items), chunk_size):
        yield i, items[i : i + chunk_size]


def _group_tickers_by_start_date(
    tickers: list[str],
    incremental_start_dates: dict[str, str],
    default_start_date: str,
) -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {}
    for ticker in tickers:
        start_date = incremental_start_dates.get(ticker, default_start_date)
        grouped.setdefault(start_date, []).append(ticker)
    return [(start_date, grouped[start_date]) for start_date in sorted(grouped)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Tushare data and persist to partitioned formal file datasets")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--tickers", nargs="*", default=[])
    parser.add_argument("--tickers-file", default="", help="read tickers from a whitespace-separated or JSON array file")
    parser.add_argument("--append-tickers", action="store_true", help="merge given tickers with manifest tickers")
    parser.add_argument("--market-output-dir", "--market-output", dest="market_output_dir", default="")
    parser.add_argument("--fundamental-output-dir", "--fundamental-output", dest="fundamental_output_dir", default="")
    parser.add_argument("--market-only", action="store_true")
    parser.add_argument("--fundamental-only", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=100, help="tickers per fetch/write chunk")
    parser.add_argument("--manifest-path", default="", help="explicit manifest path")
    parser.add_argument("--checkpoint-path", default="", help="explicit ticker-level checkpoint path")
    parser.add_argument("--check-only", action="store_true", help="validate parameters and resolved inputs without fetching data")
    parser.add_argument("--precheck-only", action="store_true", help="run precheck classification only and write a precheck report")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    manifest = _load_manifest(settings, args.manifest_path or None)
    checkpoint = _load_checkpoint(settings, args.checkpoint_path or None, args.manifest_path or None)

    start_date = args.start_date or _next_start_date_from_manifest(manifest)
    if not start_date:
        raise SystemExit("start-date is required for first run (no manifest found)")

    tickers = _resolve_tickers(args.tickers, manifest, args.append_tickers, args.tickers_file or None)
    if not tickers:
        raise SystemExit("tickers are required (or must exist in manifest)")

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(args.end_date)
    if len(tickers) < 10 and (end_dt - start_dt).days >= 180:
        print(
            f"[warning] suspiciously small ticker_count={len(tickers)} for a long range {start_date}->{args.end_date}; check --tickers/--tickers-file/manifest before running",
            flush=True,
        )

    if args.market_only and args.fundamental_only:
        raise SystemExit("market-only and fundamental-only are mutually exclusive")

    collect_market = not args.fundamental_only
    collect_fundamental = not args.market_only

    market_dir = Path(args.market_output_dir) if args.market_output_dir else Path(settings.market_data_dir or settings.data_dir / "raw" / "market")
    fundamental_dir = Path(args.fundamental_output_dir) if args.fundamental_output_dir else Path(settings.fundamental_data_dir or settings.data_dir / "raw" / "fundamentals")

    market_rows_written = 0
    fundamental_rows_written = 0
    market_rows_fetched = 0
    fundamental_rows_fetched = 0
    warnings: list[str] = []

    market_completed = set(checkpoint.get("market_completed_tickers", []))
    fundamental_completed = set(checkpoint.get("fundamental_completed_tickers", []))
    market_failed = set(checkpoint.get("market_failed_tickers", []))
    fundamental_failed = set(checkpoint.get("fundamental_failed_tickers", []))
    true_failed_tickers = set(checkpoint.get("true_failed_tickers", []))
    acceptable_gap_tickers = set(checkpoint.get("acceptable_gap_tickers", []))
    manual_review_tickers = set(checkpoint.get("manual_review_tickers", []))
    market_true_failed_tickers = set(checkpoint.get("market_true_failed_tickers", []))
    market_acceptable_gap_tickers = set(checkpoint.get("market_acceptable_gap_tickers", []))
    market_manual_review_tickers = set(checkpoint.get("market_manual_review_tickers", []))
    fundamental_true_failed_tickers = set(checkpoint.get("fundamental_true_failed_tickers", []))
    fundamental_acceptable_gap_tickers = set(checkpoint.get("fundamental_acceptable_gap_tickers", []))
    fundamental_manual_review_tickers = set(checkpoint.get("fundamental_manual_review_tickers", []))

    precheck_report = _build_precheck_report(
        market_dir,
        fundamental_dir,
        tickers,
        args.end_date,
        collect_market,
        collect_fundamental,
    )
    precheck_report_path = _save_precheck_report(settings, precheck_report, args.manifest_path or None)

    precheck_market = precheck_report.get("market") or {}
    precheck_fundamental = precheck_report.get("fundamental") or {}
    precheck_market_covered = set(precheck_market.get("covered_tickers", []))
    precheck_fundamental_covered = set(precheck_fundamental.get("covered_tickers", []))
    market_incremental_start_dates = precheck_market.get("incremental_start_dates", {})
    fundamental_incremental_start_dates = precheck_fundamental.get("incremental_start_dates", {})
    reference_records = _load_reference_records(settings, args.manifest_path or None)
    reference_names = {ticker: payload.get("name", "") for ticker, payload in reference_records.items()}
    latest_local_dates = _latest_partition_dates(
        market_dir,
        fundamental_dir,
        tickers,
        collect_market,
        collect_fundamental,
    )

    pending_market_tickers = [t for t in tickers if t not in market_completed and t not in precheck_market_covered]
    pending_fundamental_tickers = [t for t in tickers if t not in fundamental_completed and t not in precheck_fundamental_covered]

    result = {
        "market_output_dir": str(market_dir),
        "fundamental_output_dir": str(fundamental_dir),
        "manifest_path": str(_manifest_path(settings, args.manifest_path or None)),
        "checkpoint_path": str(_checkpoint_path(settings, args.checkpoint_path or None, args.manifest_path or None)),
        "precheck_report": precheck_report,
        "precheck_report_path": str(precheck_report_path),
        "market_rows_fetched": market_rows_fetched,
        "fundamental_rows_fetched": fundamental_rows_fetched,
        "warnings": warnings,
        "resolved_start_date": start_date,
        "resolved_end_date": args.end_date,
        "resolved_tickers": tickers,
        "tickers_file": args.tickers_file or None,
        "ticker_count": len(tickers),
        "pending_market_ticker_count": len(pending_market_tickers),
        "pending_fundamental_ticker_count": len(pending_fundamental_tickers),
        "failed_market_ticker_count": len(market_failed),
        "failed_fundamental_ticker_count": len(fundamental_failed),
        "partition_mode": "by_ticker",
        "modes": {
            "market": collect_market,
            "fundamental": collect_fundamental,
            "dry_run": args.dry_run,
            "check_only": args.check_only,
            "precheck_only": args.precheck_only,
        },
    }
    run_state_db_path = _run_state_db_path(settings)
    run_id = f"col_{uuid4().hex}"

    if args.check_only:
        result["unified_status"] = _derive_collection_status(
            check_only=True,
            precheck_only=False,
            blocked_by_lock=False,
            interrupted=False,
            failed=False,
            market_failed_tickers=[],
            fundamental_failed_tickers=[],
            validation_report=None,
        )
        result["cli_stage"] = _derive_cli_stage(result["unified_status"])
        result = _build_quick_result(
            base_result=result,
            unified_status=result["unified_status"],
            cli_stage=result["cli_stage"],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.precheck_only:
        result["unified_status"] = _derive_collection_status(
            check_only=False,
            precheck_only=True,
            blocked_by_lock=False,
            interrupted=False,
            failed=False,
            market_failed_tickers=[],
            fundamental_failed_tickers=[],
            validation_report=None,
        )
        result["cli_stage"] = _derive_cli_stage(result["unified_status"])
        result = _build_quick_result(
            base_result=result,
            unified_status=result["unified_status"],
            cli_stage=result["cli_stage"],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.dry_run:
        result["unified_status"] = "ready"
        result["cli_stage"] = _derive_cli_stage(result["unified_status"])
        result = _build_quick_result(
            base_result=result,
            unified_status=result["unified_status"],
            cli_stage=result["cli_stage"],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    run_lock_path: Path | None = None
    stale_lock_payload: dict[str, Any] | None = None
    checkpoint_base_path = _checkpoint_path(settings, args.checkpoint_path or None, args.manifest_path or None)
    current_stage = "initializing"
    lifecycle_stage = "initializing"
    validation_report: dict[str, Any] | None = None
    validation_report_path: Path | None = None
    manifest_output_path: Path | None = None
    unified_status: str | None = None
    metrics = _run_metrics_payload(
        market_rows_fetched=market_rows_fetched,
        fundamental_rows_fetched=fundamental_rows_fetched,
        market_rows_written=market_rows_written,
        fundamental_rows_written=fundamental_rows_written,
        pending_market_ticker_count=len(pending_market_tickers),
        pending_fundamental_ticker_count=len(pending_fundamental_tickers),
        failed_market_ticker_count=len(market_failed),
        failed_fundamental_ticker_count=len(fundamental_failed),
        market_retry_stats={},
        fundamental_retry_stats={},
    )
    _create_run_state(
        run_state_db_path,
        run_id=run_id,
        manifest_path=_manifest_path(settings, args.manifest_path or None),
        checkpoint_path=checkpoint_base_path,
        status="running",
        stage=current_stage,
        start_date=start_date,
        end_date=args.end_date,
        tickers=tickers,
        modes=result["modes"],
        metrics=metrics,
        warning_count=len(warnings),
        error=None,
        lock_path=None,
    )
    try:
        run_lock_path, stale_lock_payload = _acquire_or_recover_run_lock(settings, run_state_db_path, args.manifest_path or None)
        if stale_lock_payload:
            warnings.append(f"stale_lock_recovered|lock_path={run_lock_path}|payload={json.dumps(stale_lock_payload, ensure_ascii=False)}")
            metrics = _run_metrics_payload(
                market_rows_fetched=market_rows_fetched,
                fundamental_rows_fetched=fundamental_rows_fetched,
                market_rows_written=market_rows_written,
                fundamental_rows_written=fundamental_rows_written,
                pending_market_ticker_count=len(pending_market_tickers),
                pending_fundamental_ticker_count=len(pending_fundamental_tickers),
                failed_market_ticker_count=len(market_failed),
                failed_fundamental_ticker_count=len(fundamental_failed),
                market_retry_stats={},
                fundamental_retry_stats={},
            )
        _update_run_state(
            run_state_db_path,
            run_id=run_id,
            status="running",
            stage="locked",
            metrics=metrics,
            warning_count=len(warnings),
        )

        market_true_failed_tickers: set[str] = set(checkpoint.get("market_true_failed_tickers", []))
        market_acceptable_gap_tickers: set[str] = set(checkpoint.get("market_acceptable_gap_tickers", []))
        market_manual_review_tickers: set[str] = set(checkpoint.get("market_manual_review_tickers", []))
        fundamental_true_failed_tickers: set[str] = set(checkpoint.get("fundamental_true_failed_tickers", []))
        fundamental_acceptable_gap_tickers: set[str] = set(checkpoint.get("fundamental_acceptable_gap_tickers", []))
        fundamental_manual_review_tickers: set[str] = set(checkpoint.get("fundamental_manual_review_tickers", []))

        if collect_market:
            market_adapter = TushareMarketDataAdapter()
            market_chunk_idx = 0
            current_stage = "market"
            lifecycle_stage = "market"
            for group_start_date, group_tickers in _group_tickers_by_start_date(pending_market_tickers, market_incremental_start_dates, start_date):
                for offset, chunk in _iter_chunks(group_tickers, args.chunk_size):
                    market_chunk_idx += 1
                    print(
                        f"[market] chunk={market_chunk_idx} tickers={offset + 1}-{offset + len(chunk)} size={len(chunk)} start_date={group_start_date}",
                        flush=True,
                    )
                    chunk_df = market_adapter.fetch_daily_bars(chunk, group_start_date, args.end_date)
                    warnings.extend(getattr(market_adapter, "warnings", []) or [])
                    market_rows_fetched += len(chunk_df)
                    market_rows_written += _write_partitioned(market_dir, chunk_df)
                    completed_in_chunk = _completed_tickers(chunk_df)
                    missing_in_chunk = _failed_tickers(chunk, chunk_df)
                    classified_in_chunk = _classify_ticker_outcomes(
                        requested=chunk,
                        completed_tickers=completed_in_chunk,
                        missing_tickers=missing_in_chunk,
                        reference_names=reference_names,
                        reference_records=reference_records,
                        latest_local_dates=latest_local_dates,
                        target_end_date=args.end_date,
                        warning_messages=getattr(market_adapter, "warnings", []) or [],
                    )
                    failed_in_chunk = classified_in_chunk["true_failed_tickers"]
                    market_completed.update(completed_in_chunk)
                    market_failed.update(missing_in_chunk)
                    true_failed_tickers.update(classified_in_chunk["true_failed_tickers"])
                    acceptable_gap_tickers.update(classified_in_chunk["acceptable_gap_tickers"])
                    manual_review_tickers.update(classified_in_chunk["manual_review_tickers"])
                    market_true_failed_tickers.update(classified_in_chunk["true_failed_tickers"])
                    market_acceptable_gap_tickers.update(classified_in_chunk["acceptable_gap_tickers"])
                    market_manual_review_tickers.update(classified_in_chunk["manual_review_tickers"])
                    checkpoint["market_completed_tickers"] = sorted(market_completed)
                    checkpoint["fundamental_completed_tickers"] = sorted(fundamental_completed)
                    checkpoint["market_failed_tickers"] = sorted(market_failed)
                    checkpoint["fundamental_failed_tickers"] = sorted(fundamental_failed)
                    checkpoint["true_failed_tickers"] = sorted(true_failed_tickers)
                    checkpoint["acceptable_gap_tickers"] = sorted(acceptable_gap_tickers)
                    checkpoint["manual_review_tickers"] = sorted(manual_review_tickers)
                    checkpoint["market_true_failed_tickers"] = sorted(market_true_failed_tickers)
                    checkpoint["market_acceptable_gap_tickers"] = sorted(market_acceptable_gap_tickers)
                    checkpoint["market_manual_review_tickers"] = sorted(market_manual_review_tickers)
                    checkpoint.update(_checkpoint_status_payload("running", "market"))
                    _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)
                    metrics = _run_metrics_payload(
                        market_rows_fetched=market_rows_fetched,
                        fundamental_rows_fetched=fundamental_rows_fetched,
                        market_rows_written=market_rows_written,
                        fundamental_rows_written=fundamental_rows_written,
                        pending_market_ticker_count=len([t for t in pending_market_tickers if t not in market_completed]),
                        pending_fundamental_ticker_count=len([t for t in pending_fundamental_tickers if t not in fundamental_completed]),
                        failed_market_ticker_count=len(market_failed),
                        failed_fundamental_ticker_count=len(fundamental_failed),
                        market_retry_stats=getattr(market_adapter, 'retry_stats', {}),
                        fundamental_retry_stats=getattr(locals().get('fundamental_adapter', None), 'retry_stats', {}) if locals().get('fundamental_adapter', None) is not None else {},
                    )
                    _update_run_state(
                        run_state_db_path,
                        run_id=run_id,
                        status="running",
                        stage=current_stage,
                        metrics=metrics,
                        warning_count=len(warnings),
                    )

        if collect_fundamental:
            fundamental_adapter = TushareFundamentalDataAdapter()
            fundamental_chunk_idx = 0
            current_stage = "fundamental"
            lifecycle_stage = "fundamental"
            for group_start_date, group_tickers in _group_tickers_by_start_date(pending_fundamental_tickers, fundamental_incremental_start_dates, start_date):
                for offset, chunk in _iter_chunks(group_tickers, args.chunk_size):
                    fundamental_chunk_idx += 1
                    print(
                        f"[fundamental] chunk={fundamental_chunk_idx} tickers={offset + 1}-{offset + len(chunk)} size={len(chunk)} start_date={group_start_date}",
                        flush=True,
                    )
                    chunk_df = fundamental_adapter.fetch_fundamentals(chunk, group_start_date, args.end_date)
                    warnings.extend(getattr(fundamental_adapter, "warnings", []) or [])
                    fundamental_rows_fetched += len(chunk_df)
                    fundamental_rows_written += _write_partitioned(fundamental_dir, chunk_df)
                    completed_in_chunk = _completed_tickers(chunk_df)
                    missing_in_chunk = _failed_tickers(chunk, chunk_df)
                    classified_in_chunk = _classify_ticker_outcomes(
                        requested=chunk,
                        completed_tickers=completed_in_chunk,
                        missing_tickers=missing_in_chunk,
                        reference_names=reference_names,
                        reference_records=reference_records,
                        latest_local_dates=latest_local_dates,
                        target_end_date=args.end_date,
                        warning_messages=getattr(fundamental_adapter, "warnings", []) or [],
                    )
                    failed_in_chunk = classified_in_chunk["true_failed_tickers"]
                    fundamental_completed.update(completed_in_chunk)
                    fundamental_failed.update(missing_in_chunk)
                    true_failed_tickers.update(classified_in_chunk["true_failed_tickers"])
                    acceptable_gap_tickers.update(classified_in_chunk["acceptable_gap_tickers"])
                    manual_review_tickers.update(classified_in_chunk["manual_review_tickers"])
                    fundamental_true_failed_tickers.update(classified_in_chunk["true_failed_tickers"])
                    fundamental_acceptable_gap_tickers.update(classified_in_chunk["acceptable_gap_tickers"])
                    fundamental_manual_review_tickers.update(classified_in_chunk["manual_review_tickers"])
                    checkpoint["market_completed_tickers"] = sorted(market_completed)
                    checkpoint["fundamental_completed_tickers"] = sorted(fundamental_completed)
                    checkpoint["market_failed_tickers"] = sorted(market_failed)
                    checkpoint["fundamental_failed_tickers"] = sorted(fundamental_failed)
                    checkpoint["true_failed_tickers"] = sorted(true_failed_tickers)
                    checkpoint["acceptable_gap_tickers"] = sorted(acceptable_gap_tickers)
                    checkpoint["manual_review_tickers"] = sorted(manual_review_tickers)
                    checkpoint["fundamental_true_failed_tickers"] = sorted(fundamental_true_failed_tickers)
                    checkpoint["fundamental_acceptable_gap_tickers"] = sorted(fundamental_acceptable_gap_tickers)
                    checkpoint["fundamental_manual_review_tickers"] = sorted(fundamental_manual_review_tickers)
                    checkpoint.update(_checkpoint_status_payload("running", "fundamental"))
                    _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)
                    metrics = _run_metrics_payload(
                        market_rows_fetched=market_rows_fetched,
                        fundamental_rows_fetched=fundamental_rows_fetched,
                        market_rows_written=market_rows_written,
                        fundamental_rows_written=fundamental_rows_written,
                        pending_market_ticker_count=len([t for t in pending_market_tickers if t not in market_completed]),
                        pending_fundamental_ticker_count=len([t for t in pending_fundamental_tickers if t not in fundamental_completed]),
                        failed_market_ticker_count=len(market_failed),
                        failed_fundamental_ticker_count=len(fundamental_failed),
                        market_retry_stats=getattr(locals().get('market_adapter', None), 'retry_stats', {}) if locals().get('market_adapter', None) is not None else {},
                        fundamental_retry_stats=getattr(fundamental_adapter, 'retry_stats', {}),
                    )
                    _update_run_state(
                        run_state_db_path,
                        run_id=run_id,
                        status="running",
                        stage=current_stage,
                        metrics=metrics,
                        warning_count=len(warnings),
                    )

        lifecycle_stage = "validation"
        validation_report = _validate_collection(
            market_dir,
            fundamental_dir,
            tickers,
            start_date,
            args.end_date,
            collect_market,
            collect_fundamental,
            true_failed_tickers=sorted(true_failed_tickers),
            acceptable_gap_tickers=sorted(acceptable_gap_tickers),
            manual_review_tickers=sorted(manual_review_tickers),
            market_true_failed_tickers=sorted(market_true_failed_tickers),
            market_acceptable_gap_tickers=sorted(market_acceptable_gap_tickers),
            market_manual_review_tickers=sorted(market_manual_review_tickers),
            fundamental_true_failed_tickers=sorted(fundamental_true_failed_tickers),
            fundamental_acceptable_gap_tickers=sorted(fundamental_acceptable_gap_tickers),
            fundamental_manual_review_tickers=sorted(fundamental_manual_review_tickers),
        )
        validation_report_path = _save_validation_report(settings, validation_report, args.manifest_path or None)
        lifecycle_stage = "finalizing"
        unified_status = _derive_collection_status(
            check_only=False,
            precheck_only=False,
            blocked_by_lock=False,
            interrupted=False,
            failed=False,
            market_failed_tickers=sorted(market_failed),
            fundamental_failed_tickers=sorted(fundamental_failed),
            validation_report=validation_report,
            true_failed_tickers=sorted(true_failed_tickers),
            acceptable_gap_tickers=sorted(acceptable_gap_tickers),
        )
        dataset_max_date, latest_complete_end_date = _compute_manifest_dates(
            market_dir,
            fundamental_dir,
            tickers,
            args.end_date,
            collect_market,
            collect_fundamental,
        )
        classification_summary = _classification_summary(
            true_failed_tickers=sorted(true_failed_tickers),
            acceptable_gap_tickers=sorted(acceptable_gap_tickers),
            manual_review_tickers=sorted(manual_review_tickers),
        )
        market_classification_summary = _classification_summary(
            true_failed_tickers=sorted(market_true_failed_tickers),
            acceptable_gap_tickers=sorted(market_acceptable_gap_tickers),
            manual_review_tickers=sorted(market_manual_review_tickers),
        )
        fundamental_classification_summary = _classification_summary(
            true_failed_tickers=sorted(fundamental_true_failed_tickers),
            acceptable_gap_tickers=sorted(fundamental_acceptable_gap_tickers),
            manual_review_tickers=sorted(fundamental_manual_review_tickers),
        )
        manifest_output_path = _update_manifest(
            settings,
            market_dir,
            fundamental_dir,
            tickers,
            start_date,
            args.end_date,
            market_rows_written,
            fundamental_rows_written,
            warnings,
            result["modes"],
            args.manifest_path or None,
            dataset_max_date=dataset_max_date,
            latest_complete_end_date=latest_complete_end_date,
            unified_status=unified_status,
            classification_summary=classification_summary,
            market_classification_summary=market_classification_summary,
            fundamental_classification_summary=fundamental_classification_summary,
            validation_report=validation_report,
        )
        checkpoint.update(_checkpoint_status_payload(unified_status, _derive_cli_stage(unified_status)))
        checkpoint["true_failed_tickers"] = sorted(true_failed_tickers)
        checkpoint["acceptable_gap_tickers"] = sorted(acceptable_gap_tickers)
        checkpoint["manual_review_tickers"] = sorted(manual_review_tickers)
        checkpoint["market_true_failed_tickers"] = sorted(market_true_failed_tickers)
        checkpoint["market_acceptable_gap_tickers"] = sorted(market_acceptable_gap_tickers)
        checkpoint["market_manual_review_tickers"] = sorted(market_manual_review_tickers)
        checkpoint["fundamental_true_failed_tickers"] = sorted(fundamental_true_failed_tickers)
        checkpoint["fundamental_acceptable_gap_tickers"] = sorted(fundamental_acceptable_gap_tickers)
        checkpoint["fundamental_manual_review_tickers"] = sorted(fundamental_manual_review_tickers)
        checkpoint_path = _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)

        failed_market_path = None
        failed_fundamental_path = None
        if market_failed:
            failed_market_path = checkpoint_base_path.with_name(f"{checkpoint_base_path.stem}.market_failed.json")
            _write_json_atomic(failed_market_path, sorted(market_failed))
        if fundamental_failed:
            failed_fundamental_path = checkpoint_base_path.with_name(f"{checkpoint_base_path.stem}.fundamental_failed.json")
            _write_json_atomic(failed_fundamental_path, sorted(fundamental_failed))

        run_row = _latest_run_state(run_state_db_path, run_id)
        run_report = _build_run_report(
            run_row=run_row or {},
            warnings=warnings,
            validation_report=validation_report,
            precheck_report=precheck_report,
            failed_market_tickers=sorted(market_failed),
            failed_fundamental_tickers=sorted(fundamental_failed),
            unified_status=unified_status,
            true_failed_tickers=sorted(true_failed_tickers),
            acceptable_gap_tickers=sorted(acceptable_gap_tickers),
            manual_review_tickers=sorted(manual_review_tickers),
            market_true_failed_tickers=sorted(market_true_failed_tickers),
            market_acceptable_gap_tickers=sorted(market_acceptable_gap_tickers),
            market_manual_review_tickers=sorted(market_manual_review_tickers),
            fundamental_true_failed_tickers=sorted(fundamental_true_failed_tickers),
            fundamental_acceptable_gap_tickers=sorted(fundamental_acceptable_gap_tickers),
            fundamental_manual_review_tickers=sorted(fundamental_manual_review_tickers),
        )
        run_report["lifecycle_stage"] = lifecycle_stage
        run_report_path = _save_run_report(settings, run_report, args.manifest_path or None)
        result["unified_status"] = unified_status
        result["cli_stage"] = _derive_cli_stage(unified_status)
        result["run_id"] = run_id
        result["run_state_db_path"] = str(run_state_db_path)
        result["manifest"] = str(manifest_output_path or _manifest_path(settings, args.manifest_path or None))
        result["checkpoint"] = str(checkpoint_path)
        result["validation_report"] = validation_report
        result["validation_report_path"] = str(validation_report_path)
        result["run_report"] = run_report
        result["run_report_path"] = str(run_report_path)
        result["market_failed_tickers"] = sorted(market_failed)
        result["fundamental_failed_tickers"] = sorted(fundamental_failed)
        result["market_failed_path"] = str(failed_market_path) if failed_market_path else None
        result["fundamental_failed_path"] = str(failed_fundamental_path) if failed_fundamental_path else None
        result["market_rows_written"] = market_rows_written
        result["fundamental_rows_written"] = fundamental_rows_written
        result["lock_path"] = str(run_lock_path)
        result = _build_result_payload(
            base_result=result,
            unified_status=unified_status,
            cli_stage=result["cli_stage"],
            validation_report=validation_report,
            run_report=run_report,
            manifest_output_path=manifest_output_path,
            checkpoint_path=checkpoint_path,
            run_state_db_path=run_state_db_path,
            run_id=run_id,
            classification_summary=classification_summary,
            true_failed_tickers=sorted(true_failed_tickers),
            acceptable_gap_tickers=sorted(acceptable_gap_tickers),
            manual_review_tickers=sorted(manual_review_tickers),
            raw_market_missing_tickers=sorted(market_failed),
            raw_fundamental_missing_tickers=sorted(fundamental_failed),
            market_true_failed_tickers=sorted(market_true_failed_tickers),
            market_acceptable_gap_tickers=sorted(market_acceptable_gap_tickers),
            market_manual_review_tickers=sorted(market_manual_review_tickers),
            fundamental_true_failed_tickers=sorted(fundamental_true_failed_tickers),
            fundamental_acceptable_gap_tickers=sorted(fundamental_acceptable_gap_tickers),
            fundamental_manual_review_tickers=sorted(fundamental_manual_review_tickers),
        )

        metrics = _run_metrics_payload(
            market_rows_fetched=market_rows_fetched,
            fundamental_rows_fetched=fundamental_rows_fetched,
            market_rows_written=market_rows_written,
            fundamental_rows_written=fundamental_rows_written,
            pending_market_ticker_count=len([t for t in pending_market_tickers if t not in market_completed]),
            pending_fundamental_ticker_count=len([t for t in pending_fundamental_tickers if t not in fundamental_completed]),
            failed_market_ticker_count=len(market_failed),
            failed_fundamental_ticker_count=len(fundamental_failed),
            market_retry_stats=getattr(locals().get('market_adapter', None), 'retry_stats', {}) if locals().get('market_adapter', None) is not None else {},
            fundamental_retry_stats=getattr(locals().get('fundamental_adapter', None), 'retry_stats', {}) if locals().get('fundamental_adapter', None) is not None else {},
        )
        _update_run_state(
            run_state_db_path,
            run_id=run_id,
            status=unified_status,
            stage=_derive_cli_stage(unified_status),
            metrics=metrics,
            warning_count=len(warnings),
            finished=True,
        )
        final_run_row = _latest_run_state(run_state_db_path, run_id)
        if final_run_row is not None:
            final_run_report = _build_run_report(
                run_row=final_run_row,
                warnings=warnings,
                validation_report=validation_report,
                precheck_report=precheck_report,
                failed_market_tickers=sorted(market_failed),
                failed_fundamental_tickers=sorted(fundamental_failed),
                unified_status=unified_status,
                true_failed_tickers=sorted(true_failed_tickers),
                acceptable_gap_tickers=sorted(acceptable_gap_tickers),
                manual_review_tickers=sorted(manual_review_tickers),
            )
            final_run_report["lifecycle_stage"] = lifecycle_stage
            _save_run_report(settings, final_run_report, args.manifest_path or None)

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except RuntimeError as exc:
        unified_status = _derive_collection_status(
            check_only=False,
            precheck_only=False,
            blocked_by_lock=True,
            interrupted=False,
            failed=False,
            market_failed_tickers=sorted(market_failed),
            fundamental_failed_tickers=sorted(fundamental_failed),
            validation_report=None,
        )
        checkpoint.update(_checkpoint_status_payload(unified_status, _derive_cli_stage(unified_status)))
        _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)
        _update_run_state(
            run_state_db_path,
            run_id=run_id,
            status=unified_status,
            stage=_derive_cli_stage(unified_status),
            metrics=metrics,
            warning_count=len(warnings),
            error=str(exc),
            finished=True,
        )
        blocked_row = _latest_run_state(run_state_db_path, run_id)
        if blocked_row is not None:
            blocked_report = _build_run_report(
                run_row=blocked_row,
                warnings=warnings,
                validation_report=None,
                precheck_report=precheck_report,
                failed_market_tickers=sorted(market_failed),
                failed_fundamental_tickers=sorted(fundamental_failed),
                unified_status=unified_status,
                true_failed_tickers=sorted(true_failed_tickers),
                acceptable_gap_tickers=sorted(acceptable_gap_tickers),
                manual_review_tickers=sorted(manual_review_tickers),
            )
            blocked_report["lifecycle_stage"] = lifecycle_stage
            _save_run_report(settings, blocked_report, args.manifest_path or None)
        raise
    except Exception as exc:
        metrics = _run_metrics_payload(
            market_rows_fetched=market_rows_fetched,
            fundamental_rows_fetched=fundamental_rows_fetched,
            market_rows_written=market_rows_written,
            fundamental_rows_written=fundamental_rows_written,
            pending_market_ticker_count=len([t for t in pending_market_tickers if t not in market_completed]),
            pending_fundamental_ticker_count=len([t for t in pending_fundamental_tickers if t not in fundamental_completed]),
            failed_market_ticker_count=len(market_failed),
            failed_fundamental_ticker_count=len(fundamental_failed),
            market_retry_stats=getattr(locals().get('market_adapter', None), 'retry_stats', {}) if locals().get('market_adapter', None) is not None else {},
            fundamental_retry_stats=getattr(locals().get('fundamental_adapter', None), 'retry_stats', {}) if locals().get('fundamental_adapter', None) is not None else {},
        )
        unified_status = _derive_collection_status(
            check_only=False,
            precheck_only=False,
            blocked_by_lock=False,
            interrupted=False,
            failed=True,
            market_failed_tickers=sorted(market_failed),
            fundamental_failed_tickers=sorted(fundamental_failed),
            validation_report=None,
        )
        checkpoint.update(_checkpoint_status_payload(unified_status, _derive_cli_stage(unified_status, current_stage)))
        _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)
        _update_run_state(
            run_state_db_path,
            run_id=run_id,
            status=unified_status,
            stage=_derive_cli_stage(unified_status, current_stage),
            metrics=metrics,
            warning_count=len(warnings),
            error=str(exc),
            finished=True,
        )
        failed_run_row = _latest_run_state(run_state_db_path, run_id)
        if failed_run_row is not None:
            failed_run_report = _build_run_report(
                run_row=failed_run_row,
                warnings=warnings,
                validation_report=None,
                precheck_report=precheck_report,
                failed_market_tickers=sorted(market_failed),
                failed_fundamental_tickers=sorted(fundamental_failed),
                unified_status=unified_status,
                true_failed_tickers=sorted(true_failed_tickers),
                acceptable_gap_tickers=sorted(acceptable_gap_tickers),
                manual_review_tickers=sorted(manual_review_tickers),
            )
            failed_run_report["lifecycle_stage"] = lifecycle_stage
            _save_run_report(settings, failed_run_report, args.manifest_path or None)
        raise
    finally:
        _release_run_lock(run_lock_path)


if __name__ == "__main__":
    main()
