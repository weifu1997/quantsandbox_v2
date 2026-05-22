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
    "label": "amount_bottom_30pct",
    "field": "amount",
    "method": "cross_sectional_tail_prune",
    "tail_cut": 0.30,
}


def build_filtered_universe(limit: int = 1000) -> dict[str, Any]:
    base_tickers = load_base_universe(limit)
    filtered_tickers = prune_bottom_liquidity_tail(base_tickers, FILTER_CONFIG["field"], FILTER_CONFIG["tail_cut"])
    retained_fraction = float(len(filtered_tickers) / len(base_tickers)) if base_tickers else 0.0
    return {
        "report_type": "filtered_universe",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "filter_config": dict(FILTER_CONFIG),
        "base_universe": {
            "ticker_count": len(base_tickers),
        },
        "filtered_universe": {
            "ticker_count": len(filtered_tickers),
            "retained_fraction": retained_fraction,
            "tickers": filtered_tickers,
        },
    }


def main() -> Path:
    payload = build_filtered_universe()
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORTS_DIR / f"filtered_universe_amount_bottom_30pct_{timestamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = REPORTS_DIR / "filtered_universe_amount_bottom_30pct_latest.json"
    latest.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(out_path)
    return out_path


if __name__ == "__main__":
    main()
