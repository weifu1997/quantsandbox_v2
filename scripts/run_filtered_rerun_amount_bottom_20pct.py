from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from scripts.run_relative_liquidity_tail_pruning import load_base_universe, prune_bottom_liquidity_tail

REPORTS_DIR = Path("data/reports")
FILTER_CONFIG = {
    "label": "amount_bottom_20pct",
    "field": "amount",
    "method": "cross_sectional_tail_prune",
    "tail_cut": 0.20,
}


def universe_effect(base_count: int, eligible_count: int) -> dict[str, Any]:
    retained_fraction = float(eligible_count / base_count) if base_count else 0.0
    return {
        "retained_fraction": retained_fraction,
        "eligible_ticker_count": eligible_count,
    }


def derive_net_assessment(retained_fraction: float) -> str:
    if retained_fraction >= 0.8:
        return "promising"
    if retained_fraction >= 0.65:
        return "mixed"
    return "not_enough"


def effect_block(line_name: str, retained_fraction: float) -> dict[str, str]:
    if retained_fraction >= 0.8:
        review = f"{line_name} should retain enough breadth to justify a full filtered rerun."
        realism = "expected_improvement"
        capacity = "expected_improvement"
    elif retained_fraction >= 0.65:
        review = f"{line_name} may still be viable, but filtered rerun evidence is required before drawing conclusions."
        realism = "possibly_improved"
        capacity = "possibly_improved"
    else:
        review = f"{line_name} may lose too much breadth even under relative tail pruning."
        realism = "uncertain"
        capacity = "uncertain"
    return {
        "review_effect": review,
        "realism_effect": realism,
        "capacity_effect": capacity,
    }


def build_report(limit: int = 1000) -> dict[str, Any]:
    base_tickers = load_base_universe(limit)
    kept = prune_bottom_liquidity_tail(base_tickers, FILTER_CONFIG["field"], FILTER_CONFIG["tail_cut"])
    ue = universe_effect(len(base_tickers), len(kept))
    assessment = derive_net_assessment(ue["retained_fraction"])
    return {
        "report_type": "filtered_rerun_chain",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "filter_config": dict(FILTER_CONFIG),
        "universe_effect": ue,
        "growth_line": effect_block("growth_line", ue["retained_fraction"]),
        "valuation_line": effect_block("valuation_line", ue["retained_fraction"]),
        "comparison_summary": {
            "growth_improved": None,
            "value_improved": None,
            "capacity_improved": None,
            "net_assessment": assessment,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Filtered Rerun Chain Summary",
        "",
        "## Filter configuration",
        f"- label: {report['filter_config']['label']}",
        f"- field: {report['filter_config']['field']}",
        f"- method: {report['filter_config']['method']}",
        f"- tail_cut: {report['filter_config']['tail_cut']}",
        "",
        "## Universe retention",
        f"- retained_fraction: {report['universe_effect']['retained_fraction']}",
        f"- eligible_ticker_count: {report['universe_effect']['eligible_ticker_count']}",
        "",
        "## Growth line effect",
        f"- review: {report['growth_line']['review_effect']}",
        f"- realism: {report['growth_line']['realism_effect']}",
        f"- capacity: {report['growth_line']['capacity_effect']}",
        "",
        "## Valuation line effect",
        f"- review: {report['valuation_line']['review_effect']}",
        f"- realism: {report['valuation_line']['realism_effect']}",
        f"- capacity: {report['valuation_line']['capacity_effect']}",
        "",
        "## Net assessment",
        f"- {report['comparison_summary']['net_assessment']}",
    ]
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path) -> None:
    (REPORTS_DIR / "filtered_rerun_amount_bottom_20pct_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / "filtered_rerun_amount_bottom_20pct_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    report = build_report()
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"filtered_rerun_amount_bottom_20pct_{timestamp}.json"
    md_path = REPORTS_DIR / f"filtered_rerun_amount_bottom_20pct_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
