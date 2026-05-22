from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

REPORTS_DIR = Path("data/reports")
REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")

TESTED_FILTERS = [
    {"label": "amount_floor_300k_cov70", "amount_floor": 300_000, "coverage_ratio_min": 0.70},
    {"label": "amount_floor_500k_cov70", "amount_floor": 500_000, "coverage_ratio_min": 0.70},
    {"label": "amount_floor_1000k_cov70", "amount_floor": 1_000_000, "coverage_ratio_min": 0.70},
]


def load_base_universe(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    available = []
    for ticker in ref["ticker"].astype(str).tolist():
        if (MARKET_DIR / f"{ticker}.parquet").exists():
            available.append(ticker)
        if len(available) >= limit:
            break
    return available


def ticker_liquidity_coverage(ticker: str, amount_floor: float) -> float | None:
    path = MARKET_DIR / f"{ticker}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=["amount"])
    amounts = pd.to_numeric(pd.Series(df["amount"]), errors="coerce").dropna()
    if len(amounts) == 0:
        return None
    return float((amounts >= amount_floor).mean())


def filter_high_liquidity_tickers(base_tickers: list[str], amount_floor: float, coverage_ratio_min: float) -> list[str]:
    eligible = []
    for ticker in base_tickers:
        cov = ticker_liquidity_coverage(ticker, amount_floor)
        if cov is None:
            continue
        if cov >= coverage_ratio_min:
            eligible.append(ticker)
    return eligible


def universe_effect(base_count: int, eligible_count: int) -> dict[str, Any]:
    coverage_change_vs_base = float((eligible_count - base_count) / base_count) if base_count else 0.0
    return {
        "eligible_ticker_count": eligible_count,
        "coverage_change_vs_base": coverage_change_vs_base,
    }


def derive_recommendation(eligible_count: int, base_count: int) -> str:
    if base_count == 0:
        return "needs_more_review"
    ratio = eligible_count / base_count
    if ratio >= 0.7:
        return "promising"
    if ratio >= 0.4:
        return "needs_more_review"
    return "too_destructive"


def effect_block(line_name: str, recommendation: str, coverage_change_vs_base: float) -> dict[str, str]:
    if recommendation == "promising":
        review_status = f"{line_name} can be rerun on the tighter liquidity universe with reasonable coverage retention."
        realism_shift = "expected_improvement"
        capacity_shift = "expected_improvement"
    elif recommendation == "too_destructive":
        review_status = f"{line_name} may lose too much universe coverage under this liquidity floor."
        realism_shift = "uncertain"
        capacity_shift = "expected_improvement"
    else:
        review_status = f"{line_name} requires post-filter reruns before deciding whether the liquidity tightening is net positive."
        realism_shift = "needs_measurement"
        capacity_shift = "expected_improvement"
    return {
        "review_status": review_status,
        "realism_shift": realism_shift,
        "capacity_shift": capacity_shift,
        "coverage_change_vs_base": str(coverage_change_vs_base),
    }


def build_report(limit: int = 1000) -> dict[str, Any]:
    base_tickers = load_base_universe(limit)
    base_count = len(base_tickers)
    results = []
    for filt in TESTED_FILTERS:
        eligible = filter_high_liquidity_tickers(base_tickers, filt["amount_floor"], filt["coverage_ratio_min"])
        ue = universe_effect(base_count, len(eligible))
        recommendation = derive_recommendation(len(eligible), base_count)
        results.append({
            "label": filt["label"],
            "universe_effect": ue,
            "growth_effect": effect_block("growth_line", recommendation, ue["coverage_change_vs_base"]),
            "value_effect": effect_block("valuation_line", recommendation, ue["coverage_change_vs_base"]),
            "recommendation": recommendation,
        })
    return {
        "report_type": "high_liquidity_filter_refactor",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "base_context": {
            "tracked_growth": "revgrowth_always_on_v1",
            "tracked_value_primary": "pbindlow_downtrend_narrow_quality_v1",
            "tracked_value_reference": "pbindlow_downtrend_only_v1",
        },
        "tested_filters": TESTED_FILTERS,
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# High-Liquidity Filter Refactor Summary",
        "",
        "## Why this refactor exists",
        "- Current capacity scans breach too early, so the next intervention is to tighten tradability rather than expand strategy surface.",
        "",
        "## Tested liquidity filters",
        "| label | amount floor | coverage min |",
        "|---|---:|---:|",
    ]
    tested_map = {x["label"]: x for x in report["tested_filters"]}
    for label, cfg in tested_map.items():
        lines.append(f"| {label} | {cfg['amount_floor']} | {cfg['coverage_ratio_min']} |")
    lines += ["", "## Universe effect", "| label | eligible tickers | coverage change |", "|---|---:|---:|"]
    for row in report["results"]:
        ue = row["universe_effect"]
        lines.append(f"| {row['label']} | {ue['eligible_ticker_count']} | {ue['coverage_change_vs_base']} |")
    lines += ["", "## Growth effect"]
    for row in report["results"]:
        lines.append(f"- {row['label']}: {row['growth_effect']['review_status']}")
    lines += ["", "## Value effect"]
    for row in report["results"]:
        lines.append(f"- {row['label']}: {row['value_effect']['review_status']}")
    lines += ["", "## Recommendation"]
    for row in report["results"]:
        lines.append(f"- {row['label']}: {row['recommendation']}")
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path) -> None:
    (REPORTS_DIR / "high_liquidity_filter_refactor_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / "high_liquidity_filter_refactor_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    report = build_report()
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"high_liquidity_filter_refactor_{timestamp}.json"
    md_path = REPORTS_DIR / f"high_liquidity_filter_refactor_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
