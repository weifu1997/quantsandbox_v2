from __future__ import annotations

import argparse
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
CURRENT_CONFIG_PATH = REPORTS_DIR / "current_working_strategy_config.json"
REGISTRY_PATH = REPORTS_DIR / "revgrowth_candidate_registry.json"


def apply_round_to_growth_config(round_no: int | None = None) -> dict[str, Any]:
    remediation = load_growth_remediation_config()
    round_cfg = default_retry_round(remediation, round_no)
    tail_cut = float(round_cfg["liquidity_tail_cut"])
    limit = float(round_cfg["annual_one_way_limit"])
    extra_ticks = float(round_cfg["high_vol_extra_tick_slippage_ticks"])
    top_n = int(round_cfg.get("top_n", remediation.get("top_n", 20)))

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for item in registry:
        if item.get("strategy_id") != remediation["strategy_id"]:
            continue
        item["params"]["annual_turnover_limit"] = limit
        item["params"]["top_n"] = top_n
        item["params"]["execution_assumptions"] = {
            "bar_delay": int(remediation["execution"]["bar_delay"]),
            "tick_size": float(remediation["execution"]["tick_size"]),
            "base_tick_slippage_ticks": float(remediation["execution"]["base_tick_slippage_ticks"]),
            "high_vol_extra_tick_slippage_ticks": extra_ticks,
            "high_vol_quantile": float(remediation["execution"]["high_vol_quantile"]),
            "minimum_roundtrip_ticks": float(remediation["execution"]["minimum_roundtrip_ticks"]),
            "commission_bps": float(remediation["execution"]["commission_bps"]),
        }
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    config = json.loads(CURRENT_CONFIG_PATH.read_text(encoding="utf-8"))
    config["working_universe_policy"] = f"growth_amount_bottom_{int(tail_cut * 100)}pct"
    config.setdefault("notes", []).append(
        f"growth_remediation_round={int(round_cfg['round'])}; liquidity_tail_cut={tail_cut}; annual_turnover_limit={limit}; extra_tick_slippage={extra_ticks}; top_n={top_n}"
    )
    CURRENT_CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {
        "status": "ok",
        "round": int(round_cfg["round"]),
        "liquidity_tail_cut": tail_cut,
        "annual_one_way_limit": limit,
        "high_vol_extra_tick_slippage_ticks": extra_ticks,
        "top_n": top_n,
    }
    out = REPORTS_DIR / "growth_remediation_round_latest.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_growth_filtered_universe(round_no: int | None = None, limit: int = 1000) -> Path:
    remediation = load_growth_remediation_config()
    round_cfg = default_retry_round(remediation, round_no)
    field = str(remediation["liquidity_filter"]["field"])
    tail_cut = float(round_cfg["liquidity_tail_cut"])
    base_tickers = load_base_universe(limit)
    filtered_tickers = prune_bottom_liquidity_tail(base_tickers, field, tail_cut)
    payload = {
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
        },
        "base_universe": {
            "ticker_count": len(base_tickers),
            "tickers": base_tickers,
        },
        "filtered_universe": {
            "ticker_count": len(filtered_tickers),
            "retained_fraction": float(len(filtered_tickers) / len(base_tickers)) if base_tickers else 0.0,
            "tickers": filtered_tickers,
        },
    }
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    pct = int(tail_cut * 100)
    out_path = REPORTS_DIR / f"filtered_universe_growth_amount_bottom_{pct}pct_{timestamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = REPORTS_DIR / f"filtered_universe_growth_amount_bottom_{pct}pct_latest.json"
    latest.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    base_backup = REPORTS_DIR / remediation["liquidity_filter"]["base_backup_name"]
    base_backup.write_text(json.dumps({"filtered_universe": {"tickers": base_tickers}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=None)
    args = parser.parse_args()
    payload = apply_round_to_growth_config(args.round)
    universe_path = build_growth_filtered_universe(args.round)
    print(json.dumps({"config": payload, "universe_path": str(universe_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
