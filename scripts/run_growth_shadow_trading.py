from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.domain.backtest.engine import run_topn_backtest
from app.domain.data_contracts import factor_column
from scripts.build_research_realism_stress import build_candidate_dataset, find_registry_item, load_registry_and_reviews

REPORTS_DIR = Path("data/reports")
OUT_DIR = REPORTS_DIR / "paper_trading"


def latest_growth_registry_item() -> dict[str, Any]:
    registry, reviews, _, _ = load_registry_and_reviews("growth_line")
    item = find_registry_item(registry, "revgrowth_always_on_v1")
    latest_review = sorted([r for r in reviews if r.get("strategy_id") == "revgrowth_always_on_v1"], key=lambda x: (str(x.get("end_date", "")), str(x.get("review_id", ""))))[-1]
    item["_latest_review"] = latest_review
    return item


def market_regime_label(frame: pd.DataFrame) -> pd.Series:
    hs300 = frame.groupby("date")["close"].mean().sort_index()
    ma60 = hs300.rolling(60).mean()
    vol20 = hs300.pct_change().rolling(20).std(ddof=0)
    vol_med = float(vol20.median(skipna=True)) if vol20.notna().any() else 0.0
    trend = pd.Series("below_ma60", index=hs300.index)
    trend.loc[hs300 >= ma60] = "above_ma60"
    vol = pd.Series("low_vol", index=hs300.index)
    vol.loc[vol20 >= vol_med] = "high_vol"
    return (trend.astype(str) + "__" + vol.astype(str)).rename("market_regime")


def build_shadow_tape() -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    item = latest_growth_registry_item()
    review = item.pop("_latest_review")
    dataset = build_candidate_dataset("growth_line", item, review)
    bt = run_topn_backtest(
        dataset=dataset,
        factor_col=factor_column(item["factor"]),
        top_n=int(item["params"]["top_n"]),
        rebalance_frequency=str(item["params"]["rebalance_frequency"]),
        weighting=str(item["params"]["weighting"]),
        benchmark=str(item["params"]["benchmark"]),
        commission_bps=float(item["params"]["commission_bps"]),
        slippage_bps=float(item["params"]["slippage_bps"]),
        horizon=int(item["params"]["horizon"]),
    ).payload
    holdings = bt.get("holdings_by_rebalance_date", {})
    costs = bt.get("cost_by_rebalance_date", {})
    exec_diag = bt.get("execution_by_rebalance_date", {})
    regime_map = market_regime_label(dataset).to_dict()
    rows = []
    for dt, names in holdings.items():
        for ticker in names:
            rows.append({
                "date": dt,
                "ticker": ticker,
                "side": "buy_or_hold",
                "signal_price": None,
                "simulated_fill_price": None,
                "slippage_bps": exec_diag.get(dt, {}).get("impact_cost_bps"),
                "fee_cost": costs.get(dt),
                "market_regime": regime_map.get(pd.Timestamp(dt)),
            })
    tape = pd.DataFrame(rows)
    summary = {
        "rows": int(len(tape)),
        "regime_stats": tape.groupby("market_regime").size().to_dict() if not tape.empty else {},
        "backtest_summary": {
            "annual_return": bt.get("annual_return"),
            "sharpe": bt.get("sharpe"),
            "max_drawdown": bt.get("max_drawdown"),
        },
    }
    ts = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    tape_path = OUT_DIR / f"growth_shadow_trading_tape_{ts}.csv"
    summary_path = OUT_DIR / f"growth_shadow_trading_summary_{ts}.json"
    tape.to_csv(tape_path, index=False)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "growth_shadow_trading_tape_latest.csv").write_text(tape_path.read_text(encoding="utf-8"), encoding="utf-8")
    (OUT_DIR / "growth_shadow_trading_summary_latest.json").write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
    return tape_path, summary_path


if __name__ == "__main__":
    paths = build_shadow_tape()
    print(json.dumps({"tape": str(paths[0]), "summary": str(paths[1])}, ensure_ascii=False, indent=2))
