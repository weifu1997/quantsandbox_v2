from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import pandas as pd

from app.adapters.fundamental_data_adapter import build_fundamental_data_adapter
from app.adapters.market_data_adapter import build_market_data_adapter
from app.config.settings import get_settings
from app.domain.data_contracts import (
    add_sample_flags,
    attach_listing_days,
    factor_column,
    future_return_column,
    normalize_ticker,
    validate_fundamental_dataframe,
    validate_market_dataframe,
    validate_research_dataset,
)
from app.domain.models import DatasetSummary
from app.domain.factors.registry import build_default_factor_registry
from app.repositories.dataset_metadata_repository import create_dataset_metadata
from app.utils.ids import new_report_id


def add_future_returns(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    result = df.copy()
    grouped = result.groupby("ticker")
    next_open = grouped["open"].shift(-1)
    result["next_open_price"] = pd.to_numeric(next_open, errors="coerce")
    daily_ret = grouped["close"].pct_change()
    result["rolling_vol_20d"] = daily_ret.groupby(result["ticker"]).transform(lambda s: s.rolling(20).std(ddof=0))
    result["rolling_vol_20d_hist_q80"] = result.groupby("ticker")["rolling_vol_20d"].transform(lambda s: s.expanding().quantile(0.8))
    for horizon in horizons:
        future_close = grouped["close"].shift(-horizon)
        result[f"future_return_{horizon}d"] = future_close / result["close"] - 1.0
        result[f"delayed_future_return_{horizon}d"] = future_close / result["next_open_price"] - 1.0
    return result


def build_dataset_summary(
    df: pd.DataFrame,
    tickers: list[str],
    factors: list[str],
    horizons: list[int],
    warnings: list[str] | None = None,
    *,
    data_mode: str | None = None,
) -> dict[str, Any]:
    invalid_reasons: dict[str, int] = {}
    if not df.empty and "missing_reason" in df.columns:
        counts = df.loc[df["is_valid_sample"] == False, "missing_reason"].value_counts(dropna=True)
        invalid_reasons = {str(k): int(v) for k, v in counts.items()}
    summary = DatasetSummary(
        rows=int(len(df)),
        tickers=list(tickers),
        factors=list(factors),
        horizons=list(horizons),
        valid_sample_ratio=float(df["is_valid_sample"].mean()) if (not df.empty and "is_valid_sample" in df.columns) else 0.0,
        invalid_reasons=invalid_reasons,
        warnings=list(warnings or []),
        data_mode=str(data_mode or "unknown"),
    )
    return asdict(summary)


def persist_dataset(dataset: pd.DataFrame, experiment_id: str | None, summary: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    dataset_id = new_report_id().replace("rep_", "ds_")
    path = settings.datasets_dir / f"{dataset_id}.parquet"
    dataset.to_parquet(path, index=False)
    return create_dataset_metadata(
        {
            "dataset_id": dataset_id,
            "experiment_id": experiment_id,
            "dataset_path": str(path),
            "summary_json": json.dumps(summary, ensure_ascii=False),
        }
    )


def build_research_dataset(
    tickers: list[str],
    start_date: str,
    end_date: str,
    factor_names: list[str],
    horizons: list[int],
    market_adapter=None,
    fundamental_adapter=None,
    experiment_id: str | None = None,
):
    market_adapter = market_adapter or build_market_data_adapter()
    fundamental_adapter = fundamental_adapter or build_fundamental_data_adapter()
    factor_registry = build_default_factor_registry()
    settings = get_settings()

    tickers = [normalize_ticker(t) for t in tickers]
    bars = market_adapter.fetch_daily_bars(tickers, start_date, end_date)
    validate_market_dataframe(bars)

    fundamentals = fundamental_adapter.fetch_fundamentals(tickers, start_date, end_date)
    validate_fundamental_dataframe(fundamentals) if not fundamentals.empty else None
    provider_warnings = []
    provider_warnings.extend(getattr(market_adapter, 'warnings', []) or [])
    provider_warnings.extend(getattr(fundamental_adapter, 'warnings', []) or [])

    data_mode = "simulated" if str(getattr(settings, "market_data_mode", "memory")).lower() == "memory" else "real_file_mode"

    if not fundamentals.empty:
        fundamentals["date"] = pd.to_datetime(fundamentals["date"])
        bars["date"] = pd.to_datetime(bars["date"])
        dataset = bars.merge(fundamentals, on=["date", "ticker"], how="left")
    else:
        dataset = bars.copy()
        provider_warnings.append('fundamental adapter returned empty dataset')

    reference_path = settings.data_dir / "raw" / "reference" / "stock_basic_main_board.parquet"
    dataset, listing_info = attach_listing_days(dataset, reference_path)
    if not listing_info.get("listing_days_attached"):
        provider_warnings.append("listing days unavailable; listed_days filter could not be applied")

    dataset = dataset.sort_values(["ticker", "date"]).reset_index(drop=True)
    validate_research_dataset(dataset)

    for factor_name in factor_names:
        series = factor_registry.compute(factor_name, dataset)
        dataset[factor_column(factor_name)] = pd.to_numeric(series, errors="coerce")

    dataset = add_future_returns(dataset, horizons)
    dataset = add_sample_flags(
        dataset,
        horizons,
        min_days=int(settings.min_sample_trading_days),
        min_listed_days=int(settings.min_sample_listed_days),
    )
    summary = build_dataset_summary(dataset, tickers, factor_names, horizons, warnings=provider_warnings, data_mode=data_mode)
    validate_research_dataset(dataset, factor_names=factor_names, horizons=horizons, require_sample_flags=True)
    metadata = persist_dataset(dataset, experiment_id=experiment_id, summary=summary)
    return dataset, summary, metadata
