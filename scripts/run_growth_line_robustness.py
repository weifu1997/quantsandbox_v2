from __future__ import annotations

import json
import sys
from itertools import product
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
FACTORS = ["revenue_growth", "profit_growth"]
GRID = [
    {"horizon": 10, "frequencies": ["W", "M"]},
    {"horizon": 20, "frequencies": ["M"]},
]
TOP_NS = [10, 20, 30]
WEIGHTING = "equal"
BENCHMARK = "equal_weight_universe"
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
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
    horizons = sorted({item["horizon"] for item in GRID})
    dataset, dataset_summary, _ = build_research_dataset(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        factor_names=FACTORS,
        horizons=horizons,
        experiment_id=None,
    )
    split_date = resolve_split_date(dataset)

    factor_validation = run_factor_research(
        dataset,
        FACTORS,
        horizons,
        groups=5,
        split_date=split_date,
    )

    grid_results = []
    for factor in FACTORS:
        for spec in GRID:
            horizon = spec["horizon"]
            for freq, top_n in product(spec["frequencies"], TOP_NS):
                bt = run_strategy_backtest(
                    dataset=dataset,
                    factor_name=factor,
                    top_n=top_n,
                    rebalance_frequency=freq,
                    weighting=WEIGHTING,
                    benchmark=BENCHMARK,
                    commission_bps=COMMISSION_BPS,
                    slippage_bps=SLIPPAGE_BPS,
                    horizon=horizon,
                ).payload
                grid_results.append({
                    "factor": factor,
                    "horizon": horizon,
                    "rebalance_frequency": freq,
                    "top_n": top_n,
                    "validation_full_sample": factor_validation[factor]["full_sample"][str(horizon)],
                    "validation_in_sample": factor_validation[factor]["in_sample"].get(str(horizon), {}),
                    "validation_out_sample": factor_validation[factor]["out_sample"].get(str(horizon), {}),
                    "backtest": bt,
                })
                print(f"[done] {factor} h={horizon} f={freq} top_n={top_n}", flush=True)

    ranked = sorted(
        grid_results,
        key=lambda x: (
            x["backtest"].get("sharpe", 0.0),
            x["backtest"].get("annual_return", 0.0),
            -(x["backtest"].get("max_drawdown", 0.0) or 0.0),
        ),
        reverse=True,
    )

    report = {
        "report_type": "growth_line_robustness_grid_real_filemode",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "ticker_count": len(tickers),
            "factors": FACTORS,
            "grid": GRID,
            "top_ns": TOP_NS,
            "weighting": WEIGHTING,
            "benchmark": BENCHMARK,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "data_mode": "real_file_mode",
        },
        "dataset_summary": dataset_summary,
        "grid_results": grid_results,
        "top_ranked_points": ranked[:8],
        "notes": [
            "Task 25: corrected robustness grid for growth-line contenders under frequency-aligned horizon settings.",
            "Use this to decide which growth factor deserves the next research priority without overlapping-forward-return distortion.",
        ],
    }

    out_path = Path("data/reports") / f"growth_line_robustness_{pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
