from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.services.dataset_service import build_research_dataset
from app.services.factor_research_service import run_factor_research
from app.services.backtest_service import run_strategy_backtest

START_DATE = "20240101"
END_DATE = "20251231"
HORIZON = 60
REBALANCE_FREQUENCY = "W"
TOP_N = 10
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
FACTORS = ["roe", "roa", "gross_margin", "revenue_growth", "profit_growth"]
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
FUND_DIR = Path("data/raw/fundamentals")


def load_expanded_tickers(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    ref["has_market"] = ref["ticker"].apply(lambda t: (MARKET_DIR / f"{t}.parquet").exists())
    ref["has_fund"] = ref["ticker"].apply(lambda t: (FUND_DIR / f"{t}.parquet").exists())
    ref = ref.loc[ref["has_market"] & ref["has_fund"]].copy()
    return ref["ticker"].tolist()[:limit]


def resolve_split_date(dataset: pd.DataFrame) -> str | None:
    unique_dates = sorted(dataset["date"].drop_duplicates().tolist())
    if not unique_dates:
        return None
    split_date = unique_dates[len(unique_dates) // 2]
    return str(pd.Timestamp(split_date).date())


def main() -> None:
    tickers = load_expanded_tickers(1000)
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        factor_names=FACTORS,
        horizons=[HORIZON],
        experiment_id=None,
    )

    split_date = resolve_split_date(dataset)
    factor_results = run_factor_research(
        dataset,
        FACTORS,
        [HORIZON],
        groups=5,
        split_date=split_date,
    )

    backtest_results = {}
    coverage = {}
    for factor in FACTORS:
        backtest_results[factor] = run_strategy_backtest(
            dataset=dataset,
            factor_name=factor,
            top_n=TOP_N,
            rebalance_frequency=REBALANCE_FREQUENCY,
            weighting=WEIGHTING,
            benchmark=BENCHMARK,
            commission_bps=COMMISSION_BPS,
            slippage_bps=SLIPPAGE_BPS,
            horizon=HORIZON,
        ).payload
        col = f"factor:{factor}"
        coverage[factor] = {
            "non_null_ratio": float(pd.to_numeric(dataset[col], errors="coerce").notna().mean()),
            "valid_non_null_ratio": float(pd.to_numeric(dataset.loc[dataset["is_valid_sample"] == True, col], errors="coerce").notna().mean()),
        }
        print(f"[done] {factor}", flush=True)

    report = {
        "report_type": "quality_growth_first_batch_real_filemode",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "ticker_count": len(tickers),
            "factors": FACTORS,
            "horizon": HORIZON,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "top_n": TOP_N,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "data_mode": "real_file_mode",
        },
        "dataset_summary": dataset_summary,
        "factor_coverage": coverage,
        "factor_results": factor_results,
        "backtest_results": backtest_results,
        "notes": [
            "First formal quality/growth cross-factor study using real file-mode fundamentals.",
            "Coverage caveat is expected for roa and gross_margin in some industries such as banks/financials.",
        ],
    }

    out_path = Path("data/reports") / f"quality_growth_real_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
