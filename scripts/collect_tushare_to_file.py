#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from typing import Any

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
        "market_rows": market_rows,
        "fundamental_rows": fundamental_rows,
        "warnings": warnings,
        "modes": modes,
        "previous_last_end_date": previous.get("last_end_date"),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
            "updated_at": None,
        }
    return json.loads(path.read_text(encoding="utf-8"))


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _completed_tickers(df: pd.DataFrame) -> list[str]:
    if df.empty or "ticker" not in df.columns:
        return []
    return sorted({str(x) for x in df["ticker"].dropna().tolist()})


def _failed_tickers(requested: list[str], df: pd.DataFrame) -> list[str]:
    completed = set(_completed_tickers(df))
    return sorted([t for t in requested if t not in completed])


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
) -> dict[str, Any]:
    report = {
        "ticker_count": len(tickers),
        "start_date": start_date,
        "end_date": end_date,
        "market": None,
        "fundamental": None,
    }
    acceptable = True
    if collect_market:
        market_report = _validate_partition_dir(market_dir, tickers, start_date, end_date)
        report["market"] = market_report
        acceptable = acceptable and market_report["missing_count"] == 0 and market_report["uncovered_range_count"] == 0
    if collect_fundamental:
        fundamental_report = _validate_partition_dir(fundamental_dir, tickers, start_date, end_date)
        report["fundamental"] = fundamental_report
        acceptable = acceptable and fundamental_report["missing_count"] == 0 and fundamental_report["uncovered_range_count"] == 0
    report["acceptable"] = acceptable
    return report


def _validation_report_path(settings, manifest_path: str | Path | None = None) -> Path:
    manifest = _manifest_path(settings, manifest_path)
    return manifest.with_name(f"{manifest.stem}.validation.json")


def _precheck_report_path(settings, manifest_path: str | Path | None = None) -> Path:
    manifest = _manifest_path(settings, manifest_path)
    return manifest.with_name(f"{manifest.stem}.precheck.json")


def _save_validation_report(settings, report: dict[str, Any], manifest_path: str | Path | None = None) -> Path:
    path = _validation_report_path(settings, manifest_path)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _save_precheck_report(settings, report: dict[str, Any], manifest_path: str | Path | None = None) -> Path:
    path = _precheck_report_path(settings, manifest_path)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _classify_existing_tickers(base_dir: Path, tickers: list[str], end_date: str) -> dict[str, list[str]]:
    covered: list[str] = []
    incremental: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
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
            if dates.max() >= target_end:
                covered.append(ticker)
            else:
                incremental.append(ticker)
        except Exception:
            invalid.append(ticker)

    return {
        "covered_tickers": sorted(covered),
        "incremental_tickers": sorted(incremental),
        "missing_tickers": sorted(missing),
        "invalid_tickers": sorted(invalid),
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
        },
    }

    if args.check_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.precheck_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if collect_market:
        market_adapter = TushareMarketDataAdapter()
        for chunk_idx, (offset, chunk) in enumerate(_iter_chunks(pending_market_tickers, args.chunk_size), start=1):
            print(
                f"[market] chunk={chunk_idx} tickers={offset + 1}-{offset + len(chunk)} size={len(chunk)}",
                flush=True,
            )
            chunk_df = market_adapter.fetch_daily_bars(chunk, start_date, args.end_date)
            warnings.extend(getattr(market_adapter, "warnings", []) or [])
            market_rows_fetched += len(chunk_df)
            market_rows_written += _write_partitioned(market_dir, chunk_df)
            completed_in_chunk = _completed_tickers(chunk_df)
            failed_in_chunk = _failed_tickers(chunk, chunk_df)
            market_completed.update(completed_in_chunk)
            market_failed.update(failed_in_chunk)
            checkpoint["market_completed_tickers"] = sorted(market_completed)
            checkpoint["fundamental_completed_tickers"] = sorted(fundamental_completed)
            checkpoint["market_failed_tickers"] = sorted(market_failed)
            checkpoint["fundamental_failed_tickers"] = sorted(fundamental_failed)
            checkpoint["stage"] = "market"
            _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)

    if collect_fundamental:
        fundamental_adapter = TushareFundamentalDataAdapter()
        for chunk_idx, (offset, chunk) in enumerate(_iter_chunks(pending_fundamental_tickers, args.chunk_size), start=1):
            print(
                f"[fundamental] chunk={chunk_idx} tickers={offset + 1}-{offset + len(chunk)} size={len(chunk)}",
                flush=True,
            )
            chunk_df = fundamental_adapter.fetch_fundamentals(chunk, start_date, args.end_date)
            warnings.extend(getattr(fundamental_adapter, "warnings", []) or [])
            fundamental_rows_fetched += len(chunk_df)
            fundamental_rows_written += _write_partitioned(fundamental_dir, chunk_df)
            completed_in_chunk = _completed_tickers(chunk_df)
            failed_in_chunk = _failed_tickers(chunk, chunk_df)
            fundamental_completed.update(completed_in_chunk)
            fundamental_failed.update(failed_in_chunk)
            checkpoint["market_completed_tickers"] = sorted(market_completed)
            checkpoint["fundamental_completed_tickers"] = sorted(fundamental_completed)
            checkpoint["market_failed_tickers"] = sorted(market_failed)
            checkpoint["fundamental_failed_tickers"] = sorted(fundamental_failed)
            checkpoint["stage"] = "fundamental"
            _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)

    checkpoint["stage"] = "completed"
    checkpoint_path = _save_checkpoint(settings, checkpoint, args.checkpoint_path or None, args.manifest_path or None)

    failed_market_path = None
    failed_fundamental_path = None
    if market_failed:
        failed_market_path = _checkpoint_path(settings, args.checkpoint_path or None, args.manifest_path or None).with_name(
            f"{_checkpoint_path(settings, args.checkpoint_path or None, args.manifest_path or None).stem}.market_failed.json"
        )
        failed_market_path.write_text(json.dumps(sorted(market_failed), ensure_ascii=False, indent=2), encoding="utf-8")
    if fundamental_failed:
        failed_fundamental_path = _checkpoint_path(settings, args.checkpoint_path or None, args.manifest_path or None).with_name(
            f"{_checkpoint_path(settings, args.checkpoint_path or None, args.manifest_path or None).stem}.fundamental_failed.json"
        )
        failed_fundamental_path.write_text(json.dumps(sorted(fundamental_failed), ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path = _update_manifest(
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
    )
    validation_report = _validate_collection(
        market_dir,
        fundamental_dir,
        tickers,
        start_date,
        args.end_date,
        collect_market,
        collect_fundamental,
    )
    validation_report_path = _save_validation_report(settings, validation_report, args.manifest_path or None)
    result["manifest"] = str(manifest_path)
    result["checkpoint"] = str(checkpoint_path)
    result["validation_report"] = validation_report
    result["validation_report_path"] = str(validation_report_path)
    result["market_failed_tickers"] = sorted(market_failed)
    result["fundamental_failed_tickers"] = sorted(fundamental_failed)
    result["market_failed_path"] = str(failed_market_path) if failed_market_path else None
    result["fundamental_failed_path"] = str(failed_fundamental_path) if failed_fundamental_path else None
    result["market_rows_written"] = market_rows_written
    result["fundamental_rows_written"] = fundamental_rows_written

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
