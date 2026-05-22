from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from app.config.settings import get_settings
from app.domain.data_contracts import factor_column
from app.domain.research.validation import run_factor_validation
from app.domain.backtest.engine import run_topn_backtest
from app.services.dataset_service import build_research_dataset


START_DATE = "20240101"
END_DATE = "20251231"
HORIZON = 20
REBALANCE_FREQUENCY = "W"
TOP_N = 10
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
BASE_REPORT = Path("data/reports/exp_8a03a423067c47579e75a9537e0b0b8e.json")
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")


def load_tickers() -> list[str]:
    data = json.loads(BASE_REPORT.read_text(encoding="utf-8"))
    tickers = data["config"]["tickers"]
    if len(tickers) != 300:
        raise ValueError(f"expected 300 tickers from baseline report, got {len(tickers)}")
    return tickers


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def winsorize_by_date(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    def _clip(s: pd.Series) -> pd.Series:
        x = pd.to_numeric(s, errors="coerce")
        if x.notna().sum() < 5:
            return x
        lo = x.quantile(lower)
        hi = x.quantile(upper)
        return x.clip(lower=lo, upper=hi)

    return series.groupby(level=0, group_keys=False).transform(_clip)


def zscore_by_date(series: pd.Series) -> pd.Series:
    def _z(s: pd.Series) -> pd.Series:
        x = pd.to_numeric(s, errors="coerce")
        mu = x.mean()
        sd = x.std(ddof=0)
        if pd.isna(sd) or sd <= 1e-12:
            return pd.Series(np.zeros(len(x)), index=x.index, dtype="float64")
        return (x - mu) / sd

    return series.groupby(level=0, group_keys=False).transform(_z)


def demean_within_group(values: pd.Series, groups: pd.Series) -> pd.Series:
    df = pd.DataFrame({"v": pd.to_numeric(values, errors="coerce"), "g": groups})

    def _demean(frame: pd.DataFrame) -> pd.Series:
        v = frame["v"]
        g = frame["g"]
        out = v.copy()
        valid = v.notna() & g.notna()
        if valid.sum() == 0:
            return out
        means = v[valid].groupby(g[valid]).transform("mean")
        out.loc[valid] = v[valid] - means
        return out

    return df.groupby(level=0, group_keys=False).apply(_demean).reset_index(level=0, drop=True)


def residualize_size(values: pd.Series, log_mv: pd.Series) -> pd.Series:
    df = pd.DataFrame({"y": pd.to_numeric(values, errors="coerce"), "x": pd.to_numeric(log_mv, errors="coerce")})
    df = df.reset_index().rename(columns={df.reset_index().columns[0]: "date"})
    df["resid"] = np.nan

    for date, idx in df.groupby("date").groups.items():
        frame = df.loc[idx, ["y", "x"]].copy()
        valid_mask = frame[["y", "x"]].notna().all(axis=1)
        valid = frame.loc[valid_mask]
        if len(valid) < 5:
            continue
        X = np.column_stack([np.ones(len(valid)), valid["x"].to_numpy(dtype=float)])
        y = valid["y"].to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        fitted = X @ beta
        df.loc[valid.index, "resid"] = y - fitted

    return pd.Series(df["resid"].to_numpy(), index=values.index)


def residualize_industry_size(values: pd.Series, industry: pd.Series, log_mv: pd.Series) -> pd.Series:
    df = pd.DataFrame({
        "y": pd.to_numeric(values, errors="coerce"),
        "industry": industry.astype("string"),
        "x": pd.to_numeric(log_mv, errors="coerce"),
    })
    df = df.reset_index().rename(columns={df.reset_index().columns[0]: "date"})
    df["resid"] = np.nan

    for date, idx in df.groupby("date").groups.items():
        frame = df.loc[idx, ["y", "industry", "x"]].copy()
        valid = frame.dropna(subset=["y", "industry", "x"])
        if len(valid) < 8:
            continue
        dummies = pd.get_dummies(valid["industry"], prefix="ind", drop_first=True, dtype=float)
        X = pd.concat([pd.Series(1.0, index=valid.index, name="const"), valid[["x"]].astype(float), dummies], axis=1)
        y = valid["y"].to_numpy(dtype=float)
        X_np = X.to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(X_np, y, rcond=None)
        fitted = X_np @ beta
        df.loc[valid.index, "resid"] = y - fitted

    return pd.Series(df["resid"].to_numpy(), index=values.index)


def build_total_mv_cache_path(tickers: list[str]) -> Path:
    settings = get_settings()
    key = hashlib.md5("|".join(sorted(tickers)).encode("utf-8")).hexdigest()[:12]
    return settings.cache_dir / f"pb_neutralization_total_mv_{START_DATE}_{END_DATE}_{key}.parquet"


def fetch_total_mv_from_tushare(tickers: list[str]) -> pd.DataFrame:
    cache_path = build_total_mv_cache_path(tickers)
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached["date"] = pd.to_datetime(cached["date"])
        return cached

    import tushare as ts  # type: ignore

    settings = get_settings()
    token = settings.tushare_token or os.getenv("QS_TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("QS_TUSHARE_TOKEN is required for size neutralization")
    ts.set_token(token)
    pro = ts.pro_api()
    http_url = settings.tushare_http_url or os.getenv("QS_TUSHARE_HTTP_URL")
    if http_url:
        pro._DataApi__http_url = http_url

    rows: list[pd.DataFrame] = []
    total = len(tickers)
    for idx, ticker in enumerate(tickers, start=1):
        ts_code = f"{ticker[2:]}.{ticker[:2].upper()}"
        last_exc = None
        for attempt in range(3):
            try:
                df = pro.daily_basic(
                    ts_code=ts_code,
                    start_date=START_DATE,
                    end_date=END_DATE,
                    fields="ts_code,trade_date,total_mv",
                )
                if df is None or df.empty:
                    break
                df = df.rename(columns={"trade_date": "date"})[["date", "total_mv"]].copy()
                df["date"] = pd.to_datetime(df["date"])
                df["ticker"] = ticker
                rows.append(df)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(1.0 + attempt)
        if last_exc is not None:
            raise RuntimeError(f"failed to fetch total_mv for {ticker}: {last_exc}")
        if idx % 25 == 0 or idx == total:
            print(f"[total_mv] fetched {idx}/{total}", flush=True)
        time.sleep(0.72)

    if not rows:
        raise RuntimeError("total_mv fetch returned no rows")

    out = pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache_path, index=False)
    return out


def build_variant_dataset() -> tuple[pd.DataFrame, dict, list[str]]:
    tickers = load_tickers()
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        factor_names=[],
        horizons=[HORIZON],
        experiment_id=None,
    )
    dataset = dataset.copy()
    dataset["date"] = pd.to_datetime(dataset["date"])

    ref = pd.read_parquet(REFERENCE_FILE)[["ticker", "industry"]].drop_duplicates(subset=["ticker"])
    dataset = dataset.merge(ref, on="ticker", how="left")

    total_mv = fetch_total_mv_from_tushare(tickers)
    dataset = dataset.merge(total_mv, on=["date", "ticker"], how="left")
    dataset["log_total_mv"] = np.log(pd.to_numeric(dataset["total_mv"], errors="coerce").clip(lower=1e-12))

    by_date_pb = dataset.set_index("date")["pb"]
    by_date_industry = dataset.set_index("date")["industry"]
    by_date_log_mv = dataset.set_index("date")["log_total_mv"]

    pb_raw = pd.to_numeric(by_date_pb, errors="coerce")
    pb_wins = winsorize_by_date(pb_raw)
    pb_z = zscore_by_date(pb_wins)
    pb_ind = demean_within_group(pb_z, by_date_industry)
    pb_size = residualize_size(pb_z, by_date_log_mv)
    pb_ind_size = residualize_industry_size(pb_z, by_date_industry, by_date_log_mv)

    variant_map = {
        "pb_raw": pb_raw,
        "pb_winsorized": pb_wins,
        "pb_zscore": pb_z,
        "pb_industry_neutral": pb_ind,
        "pb_size_neutral": pb_size,
        "pb_industry_size_neutral": pb_ind_size,
    }

    for name, series in variant_map.items():
        dataset[factor_column(name)] = series.reset_index(drop=True)

    return dataset, dataset_summary, tickers


def run() -> Path:
    dataset, dataset_summary, tickers = build_variant_dataset()
    split_date = resolve_split_date(dataset)
    factor_names = [
        "pb_raw",
        "pb_winsorized",
        "pb_zscore",
        "pb_industry_neutral",
        "pb_size_neutral",
        "pb_industry_size_neutral",
    ]

    factor_results = {}
    backtest_results = {}
    coverage = {}
    for name in factor_names:
        col = factor_column(name)
        factor_results[name] = run_factor_validation(
            dataset=dataset,
            factor_col=col,
            horizons=[HORIZON],
            groups=5,
            split_date=split_date,
        )
        backtest_results[name] = run_topn_backtest(
            dataset=dataset,
            factor_col=col,
            top_n=TOP_N,
            rebalance_frequency=REBALANCE_FREQUENCY,
            weighting=WEIGHTING,
            benchmark=BENCHMARK,
            commission_bps=COMMISSION_BPS,
            slippage_bps=SLIPPAGE_BPS,
            horizon=HORIZON,
        ).payload
        coverage[name] = {
            "non_null_ratio": float(pd.to_numeric(dataset[col], errors="coerce").notna().mean()),
            "valid_non_null_ratio": float(pd.to_numeric(dataset.loc[dataset["is_valid_sample"] == True, col], errors="coerce").notna().mean()),
        }
        print(f"[done] {name}", flush=True)

    report = {
        "report_type": "pb_neutralization_experiment",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "tickers": tickers,
            "horizons": [HORIZON],
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "baseline_report": str(BASE_REPORT),
        },
        "dataset_summary": dataset_summary,
        "variant_coverage": coverage,
        "factor_results": factor_results,
        "backtest_results": backtest_results,
        "notes": [
            "pb variants are computed on top of the same 300-stock sample used by exp_8a03a423067c47579e75a9537e0b0b8e.",
            "Winsorization uses daily 1%/99% clipping.",
            "Z-score uses daily cross-sectional standardization after winsorization.",
            "Industry neutral uses same-day industry demeaning on z-scored pb.",
            "Size neutral uses same-day residualization of z-scored pb on log(total_mv).",
            "Industry+size neutral uses same-day residualization on log(total_mv) plus industry dummies.",
            "For strict comparability with the existing engine, factor direction is left unchanged from prior pb runs.",
        ],
    }

    out_path = Path("data/reports") / f"pb_neutralization_{pd.Timestamp.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path), flush=True)
    return out_path


if __name__ == "__main__":
    run()
