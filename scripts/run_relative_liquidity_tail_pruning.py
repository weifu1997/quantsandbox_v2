from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

REFERENCE_FILE = Path("data/raw/reference/stock_basic_main_board.parquet")
MARKET_DIR = Path("data/raw/market")
REPORTS_DIR = Path("data/reports")

TESTED_METHODS = [
    {"label": "amount_bottom_10pct", "field": "amount", "method": "cross_sectional_tail_prune", "tail_cut": 0.10},
    {"label": "amount_bottom_20pct", "field": "amount", "method": "cross_sectional_tail_prune", "tail_cut": 0.20},
    {"label": "amount_bottom_30pct", "field": "amount", "method": "cross_sectional_tail_prune", "tail_cut": 0.30},
]


def load_base_universe(limit: int = 1000) -> list[str]:
    ref = pd.read_parquet(REFERENCE_FILE).drop_duplicates(subset=["ticker"]).copy()
    out = []
    for ticker in ref["ticker"].astype(str).tolist():
        if (MARKET_DIR / f"{ticker}.parquet").exists():
            out.append(ticker)
        if len(out) >= limit:
            break
    return out


def ticker_liquidity_score(ticker: str, field: str = "amount") -> float | None:
    path = MARKET_DIR / f"{ticker}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=[field])
    values = pd.to_numeric(pd.Series(df[field]), errors="coerce").dropna()
    if len(values) == 0:
        return None
    return float(values.median())


def prune_bottom_liquidity_tail(base_tickers: list[str], field: str, tail_cut: float) -> list[str]:
    scored = []
    for ticker in base_tickers:
        score = ticker_liquidity_score(ticker, field)
        if score is not None:
            scored.append((ticker, score))
    if not scored:
        return []
    scored.sort(key=lambda x: x[1])
    drop_n = int(len(scored) * tail_cut)
    kept = scored[drop_n:]
    return [ticker for ticker, _ in kept]


def universe_effect(base_count: int, retained_count: int) -> dict[str, Any]:
    retained_fraction = float(retained_count / base_count) if base_count else 0.0
    return {
        "retained_fraction": retained_fraction,
        "coverage_change_vs_base": retained_fraction - 1.0,
    }


def derive_recommendation(retained_fraction: float) -> str:
    if retained_fraction >= 0.8:
        return "promising"
    if retained_fraction >= 0.65:
        return "needs_more_review"
    return "too_weak"


def effect_block(line_name: str, recommendation: str, retained_fraction: float) -> dict[str, str]:
    if recommendation == "promising":
        return {
            "review_status": f"{line_name} should remain meaningful enough to justify full post-pruning reruns.",
            "realism_shift": "expected_improvement",
            "capacity_shift": "expected_improvement",
        }
    if recommendation == "needs_more_review":
        return {
            "review_status": f"{line_name} may survive moderate liquidity tail pruning, but requires full rerun evidence.",
            "realism_shift": "expected_improvement",
            "capacity_shift": "expected_improvement",
        }
    return {
        "review_status": f"{line_name} may become too weak if too much of the universe is removed even under relative tail pruning.",
        "realism_shift": "uncertain",
        "capacity_shift": "expected_improvement",
    }


def build_report(limit: int = 1000) -> dict[str, Any]:
    base_tickers = load_base_universe(limit)
    base_count = len(base_tickers)
    results = []
    for method in TESTED_METHODS:
        kept = prune_bottom_liquidity_tail(base_tickers, method["field"], method["tail_cut"])
        ue = universe_effect(base_count, len(kept))
        recommendation = derive_recommendation(ue["retained_fraction"])
        results.append({
            "label": method["label"],
            "universe_effect": ue,
            "growth_effect": effect_block("growth_line", recommendation, ue["retained_fraction"]),
            "value_effect": effect_block("valuation_line", recommendation, ue["retained_fraction"]),
            "recommendation": recommendation,
        })
    return {
        "report_type": "relative_liquidity_tail_pruning",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "base_context": {
            "tracked_growth": "revgrowth_always_on_v1",
            "tracked_value_primary": "pbindlow_downtrend_narrow_quality_v1",
            "tracked_value_reference": "pbindlow_downtrend_only_v1",
        },
        "tested_methods": TESTED_METHODS,
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Relative Liquidity Tail-Pruning Summary",
        "",
        "## Why this experiment exists",
        "- Hard liquidity floors were too destructive, so this experiment removes only the worst liquidity tail instead of imposing an absolute wall.",
        "",
        "## Tested methods",
        "| label | field | method | tail cut |",
        "|---|---|---|---:|",
    ]
    for method in report["tested_methods"]:
        lines.append(f"| {method['label']} | {method['field']} | {method['method']} | {method['tail_cut']} |")
    lines += ["", "## Universe effect", "| label | retained fraction | coverage change |", "|---|---:|---:|"]
    for row in report["results"]:
        ue = row["universe_effect"]
        lines.append(f"| {row['label']} | {ue['retained_fraction']} | {ue['coverage_change_vs_base']} |")
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
    (REPORTS_DIR / "relative_liquidity_tail_pruning_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / "relative_liquidity_tail_pruning_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    report = build_report()
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"relative_liquidity_tail_pruning_{timestamp}.json"
    md_path = REPORTS_DIR / f"relative_liquidity_tail_pruning_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
