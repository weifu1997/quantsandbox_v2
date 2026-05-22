from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.domain.backtest.performance_metrics import annual_return, max_drawdown, sharpe_ratio, total_return, win_rate, periods_per_year, turnover_from_holdings
from app.domain.backtest.cost_model import estimate_transaction_cost
from app.domain.backtest.rebalance_calendar import select_rebalance_dates
from app.domain.data_contracts import factor_column
from scripts.build_research_realism_stress import build_candidate_dataset, find_registry_item, load_registry_and_reviews, latest_review

REPORTS_DIR = Path("data/reports")
TICKERS_FILE = REPORTS_DIR / "filtered_universe_amount_bottom_30pct_latest.json"
LOW_BUCKET_PERCENTILE = 0.30
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
TRACKED = [
    ("growth_line", "revgrowth_always_on_v1", 2),
    ("valuation_line", "pbindlow_downtrend_narrow_quality_v1", 1),
]


def load_filtered_tickers() -> list[str]:
    payload = json.loads(TICKERS_FILE.read_text(encoding="utf-8"))
    return payload["filtered_universe"]["tickers"]


def classify_low_bucket(cross: pd.DataFrame) -> pd.DataFrame:
    ranked = cross.copy()
    ranked["amount"] = pd.to_numeric(ranked["amount"], errors="coerce")
    ranked = ranked.dropna(subset=["amount"])
    ranked = ranked.sort_values("amount", ascending=True).reset_index(drop=True)
    n = len(ranked)
    if n == 0:
        ranked["liq_bucket"] = []
        return ranked
    low_n = max(1, int(n * LOW_BUCKET_PERCENTILE))
    ranked["liq_bucket"] = "mid_high"
    ranked.loc[: low_n - 1, "liq_bucket"] = "low"
    return ranked


def build_gated_equal_holdings(cross: pd.DataFrame, factor_col: str, top_n: int, low_liquidity_max_slots: int) -> tuple[dict[str, float], dict[str, Any]]:
    ranked = cross.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).copy()
    ranked = classify_low_bucket(ranked)
    chosen = []
    low_used = 0
    skipped_low = 0
    for _, row in ranked.iterrows():
        bucket = row.get("liq_bucket", "mid_high")
        if bucket == "low" and low_used >= low_liquidity_max_slots:
            skipped_low += 1
            continue
        chosen.append(str(row["ticker"]))
        if bucket == "low":
            low_used += 1
        if len(chosen) >= top_n:
            break
    if not chosen:
        return {}, {"low_liquidity_slots_used": 0, "low_liquidity_slots_cap": low_liquidity_max_slots, "skipped_low_candidates": skipped_low}
    w = 1.0 / len(chosen)
    return {t: w for t in chosen}, {
        "low_liquidity_slots_used": low_used,
        "low_liquidity_slots_cap": low_liquidity_max_slots,
        "skipped_low_candidates": skipped_low,
    }


def build_equal_holdings(cross: pd.DataFrame, factor_col: str, top_n: int) -> dict[str, float]:
    ranked = cross.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).head(top_n)
    tickers = ranked["ticker"].astype(str).tolist()
    if not tickers:
        return {}
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def run_backtest(dataset: pd.DataFrame, factor_col: str, top_n: int, rebalance_frequency: str, horizon: int, mode: str, low_liquidity_max_slots: int) -> dict[str, Any]:
    return_col = f"future_return_{horizon}d"
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample["amount"] = pd.to_numeric(sample["amount"], errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col, "amount"])
    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), rebalance_frequency)
    returns=[]; equity_curve=[]; turnover_values=[]; equity=1.0; cost_paid=0.0; prev={}; diag=[]
    for dt in rebalance_dates:
        cross = sample.loc[sample["date"] == dt].copy()
        if cross.empty:
            continue
        if mode == 'entry_gated':
            holdings, meta = build_gated_equal_holdings(cross, factor_col, top_n, low_liquidity_max_slots)
            diag.append({"date": pd.Timestamp(dt).strftime('%Y-%m-%d'), **meta})
        else:
            holdings = build_equal_holdings(cross, factor_col, top_n)
        if not holdings:
            continue
        cross = cross.set_index('ticker')
        gross=0.0
        for ticker, weight in holdings.items():
            if ticker in cross.index:
                gross += float(weight) * float(cross.loc[ticker, return_col])
        turnover = turnover_from_holdings(prev, holdings)
        cost = estimate_transaction_cost(turnover, COMMISSION_BPS, SLIPPAGE_BPS)
        net = gross - cost
        returns.append(float(net)); turnover_values.append(turnover); cost_paid += cost; equity *= (1+float(net)); equity_curve.append(float(equity)); prev = holdings
    ppy = periods_per_year(rebalance_frequency)
    return {
        "annual_return": annual_return(returns, ppy),
        "total_return": total_return(equity_curve),
        "max_drawdown": max_drawdown(equity_curve),
        "sharpe": sharpe_ratio(returns, ppy),
        "turnover": float(sum(turnover_values)/len(turnover_values)) if turnover_values else 0.0,
        "win_rate": win_rate(returns),
        "cost_paid": float(cost_paid),
        "equity_curve": equity_curve,
        "diagnostics": diag,
    }


def run_experiment(line: str, strategy_id: str, low_slots: int, tickers: list[str]) -> dict[str, Any]:
    registry, reviews, _, _ = load_registry_and_reviews(line)
    item = find_registry_item(registry, strategy_id)
    review_row = latest_review(reviews, strategy_id)
    dataset = build_candidate_dataset(line, item, review_row, tickers=tickers)
    factor_col = factor_column(item['factor'])
    params = item['params']
    equal = run_backtest(dataset, factor_col, params['top_n'], params['rebalance_frequency'], params['horizon'], 'equal', low_slots)
    gated = run_backtest(dataset, factor_col, params['top_n'], params['rebalance_frequency'], params['horizon'], 'entry_gated', low_slots)
    return {
        "line": line,
        "strategy_id": strategy_id,
        "low_liquidity_max_slots": low_slots,
        "review_window": {k: review_row[k] for k in ['review_id','window_label','start_date','end_date']},
        "equal_weight": equal,
        "entry_gated_equal_weight": gated,
    }


def build_report() -> dict[str, Any]:
    tickers = load_filtered_tickers()
    experiments = [run_experiment(line, sid, low_slots, tickers) for line, sid, low_slots in TRACKED]
    return {
        "report_type": "entry_gating_experiment",
        "generated_at": pd.Timestamp.now('UTC').isoformat(),
        "filter_source": str(TICKERS_FILE),
        "low_bucket_percentile": LOW_BUCKET_PERCENTILE,
        "experiments": experiments,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ['# Entry Gating Experiment', '', f"- Filter source: {report['filter_source']}", f"- Low bucket percentile: {report['low_bucket_percentile']}", '', '## Results', '| strategy | mode | annual | sharpe | mdd | turnover | cost_paid |', '|---|---:|---:|---:|---:|---:|---:|']
    for exp in report['experiments']:
        for mode in ['equal_weight','entry_gated_equal_weight']:
            m = exp[mode]
            lines.append(f"| {exp['strategy_id']} | {mode} | {m['annual_return']:.4f} | {m['sharpe']:.4f} | {m['max_drawdown']:.4f} | {m['turnover']:.4f} | {m['cost_paid']:.4f} |")
    return '\n'.join(lines) + '\n'


def main() -> tuple[Path, Path]:
    report = build_report()
    ts = pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')
    json_path = REPORTS_DIR / f'entry_gating_experiment_{ts}.json'
    md_path = REPORTS_DIR / f'entry_gating_experiment_{ts}.md'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    md_path.write_text(render_markdown(report), encoding='utf-8')
    (REPORTS_DIR / 'entry_gating_experiment_latest.json').write_text(json_path.read_text(encoding='utf-8'), encoding='utf-8')
    (REPORTS_DIR / 'entry_gating_experiment_latest.md').write_text(md_path.read_text(encoding='utf-8'), encoding='utf-8')
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == '__main__':
    main()
