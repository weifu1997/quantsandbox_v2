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
    parser.add_argument("--check-only", action="store_true", help="validate parameters and resolved inputs without fetching data")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    manifest = _load_manifest(settings, args.manifest_path or None)

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

    if collect_market:
        market_adapter = TushareMarketDataAdapter()
        for chunk_idx, (offset, chunk) in enumerate(_iter_chunks(tickers, args.chunk_size), start=1):
            print(
                f"[market] chunk={chunk_idx} tickers={offset + 1}-{offset + len(chunk)} size={len(chunk)}",
                flush=True,
            )
            chunk_df = market_adapter.fetch_daily_bars(chunk, start_date, args.end_date)
            warnings.extend(getattr(market_adapter, "warnings", []) or [])
            market_rows_fetched += len(chunk_df)
            market_rows_written += _write_partitioned(market_dir, chunk_df)

    if collect_fundamental:
        fundamental_adapter = TushareFundamentalDataAdapter()
        for chunk_idx, (offset, chunk) in enumerate(_iter_chunks(tickers, args.chunk_size), start=1):
            print(
                f"[fundamental] chunk={chunk_idx} tickers={offset + 1}-{offset + len(chunk)} size={len(chunk)}",
                flush=True,
            )
            chunk_df = fundamental_adapter.fetch_fundamentals(chunk, start_date, args.end_date)
            warnings.extend(getattr(fundamental_adapter, "warnings", []) or [])
            fundamental_rows_fetched += len(chunk_df)
            fundamental_rows_written += _write_partitioned(fundamental_dir, chunk_df)

    result = {
        "market_output_dir": str(market_dir),
        "fundamental_output_dir": str(fundamental_dir),
        "manifest_path": str(_manifest_path(settings, args.manifest_path or None)),
        "market_rows_fetched": market_rows_fetched,
        "fundamental_rows_fetched": fundamental_rows_fetched,
        "warnings": warnings,
        "resolved_start_date": start_date,
        "resolved_end_date": args.end_date,
        "resolved_tickers": tickers,
        "tickers_file": args.tickers_file or None,
        "ticker_count": len(tickers),
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

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

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
    result["manifest"] = str(manifest_path)
    result["market_rows_written"] = market_rows_written
    result["fundamental_rows_written"] = fundamental_rows_written

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
