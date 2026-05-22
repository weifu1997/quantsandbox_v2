from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from scripts.growth_remediation_config import default_retry_round, load_growth_remediation_config
from scripts.run_relative_liquidity_tail_pruning import load_base_universe, prune_bottom_liquidity_tail

REPORTS_DIR = Path("data/reports")


def build_filtered_universe(limit: int = 1000, round_no: int | None = None) -> dict[str, Any]:
    remediation = load_growth_remediation_config()
    round_cfg = default_retry_round(remediation, round_no)
    field = str(remediation["liquidity_filter"]["field"])
    tail_cut = float(round_cfg["liquidity_tail_cut"])
    base_tickers = load_base_universe(limit)
    filtered_tickers = prune_bottom_liquidity_tail(base_tickers, field, tail_cut)
    retained_fraction = float(len(filtered_tickers) / len(base_tickers)) if base_tickers else 0.0
    return {
        "report_type": "filtered_universe",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "filter_config": {
            "label": f"growth_amount_bottom_{int(tail_cut * 100)}pct",
            "field": field,
            "method": "cross_sectional_tail_prune",
            "tail_cut": tail_cut,
            "default_enabled": bool(remediation["liquidity_filter"]["enabled"]),
            "strategy_id": remediation["strategy_id"],
            "round": int(round_cfg["round"]),
            "config_path": str((PROJECT_ROOT / 'config' / 'growth_deployability_remediation.json').resolve()),
            "reason": "Growth deployability remediation: remove lowest-liquidity tail while preserving original base universe artifact.",
        },
        "base_universe": {
            "ticker_count": len(base_tickers),
            "artifact_alias": remediation["liquidity_filter"]["base_backup_name"],
            "tickers": base_tickers,
        },
        "filtered_universe": {
            "ticker_count": len(filtered_tickers),
            "retained_fraction": retained_fraction,
            "as_of_date": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
            "tickers": filtered_tickers,
        },
    }


def main() -> Path:
    payload = build_filtered_universe()
    tail_pct = int(float(payload["filter_config"]["tail_cut"]) * 100)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORTS_DIR / f"filtered_universe_growth_amount_bottom_{tail_pct}pct_{timestamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = REPORTS_DIR / f"filtered_universe_growth_amount_bottom_{tail_pct}pct_latest.json"
    latest.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    base_backup = REPORTS_DIR / payload["base_universe"]["artifact_alias"]
    base_backup.write_text(json.dumps({"filtered_universe": {"tickers": payload["base_universe"]["tickers"]}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)
    return out_path


if __name__ == "__main__":
    main()
