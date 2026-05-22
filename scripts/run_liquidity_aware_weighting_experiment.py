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

LIQUIDITY_BUCKETS = [
    {"name": "high", "min_rank": 0.67, "multiplier": 1.0},
    {"name": "mid", "min_rank": 0.34, "multiplier": 0.75},
    {"name": "low", "min_rank": 0.0, "multiplier": 0.5},
]
HARD_CAP_RATIO = 0.08
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0

TRACKED = [
    ("growth_line", "revgrowth_always_on_v1"),
    ("valuation_line", "pbindlow_downtrend_narrow_quality_v1"),
]


def load_filtered_tickers() -> list[str]:
    payload = json.loads(TICKERS_FILE.read_text(encoding="utf-8"))
    return payload["filtered_universe"]["tickers"]


def liquidity_multiplier(rank_pct: float) -> tuple[str, float]:
    for bucket in LIQUIDITY_BUCKETS:
        if rank_pct >= bucket["min_rank"]:
            return bucket["name"], float(bucket["multiplier"])
    return "low", 0.5


def normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(v, 0.0) for v in weights.values())
    if total <= 0:
        return {}
    return {k: float(max(v, 0.0) / total) for k, v in weights.items() if v > 0}


def build_liquidity_aware_holdings(cross: pd.DataFrame, factor_col: str, top_n: int) -> tuple[dict[str, float], dict[str, Any]]:
    ranked = cross.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).head(top_n).copy()
    if ranked.empty:
        return {}, {"buckets": {}, "cap_hits": 0}
    ranked["amount"] = pd.to_numeric(ranked["amount"], errors="coerce")
    ranked = ranked.dropna(subset=["amount"])
    if ranked.empty:
        return {}, {"buckets": {}, "cap_hits": 0}
    ranked = ranked.sort_values("amount", ascending=True).reset_index(drop=True)
    n = len(ranked)
    weights = {}
    bucket_counts = {"high": 0, "mid": 0, "low": 0}
    for i, row in ranked.iterrows():
        rank_pct = (i + 1) / n
        bucket_name, mult = liquidity_multiplier(rank_pct)
        base = 1.0 / n
        weights[str(row["ticker"])] = base * mult
        bucket_counts[bucket_name] += 1
    weights = normalize(weights)
    cap_hits = 0
    capped = {}
    for _, row in ranked.iterrows():
        ticker = str(row["ticker"])
        amount = float(row["amount"])
        max_weight = HARD_CAP_RATIO * amount
        w = min(weights.get(ticker, 0.0), max_weight)
        if w < weights.get(ticker, 0.0):
            cap_hits += 1
        capped[ticker] = w
    capped = normalize(capped)
    return capped, {"buckets": bucket_counts, "cap_hits": cap_hits}


def build_equal_holdings(cross: pd.DataFrame, factor_col: str, top_n: int) -> dict[str, float]:
    ranked = cross.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).head(top_n)
    tickers = ranked["ticker"].astype(str).tolist()
    if not tickers:
        return {}
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def run_backtest(dataset: pd.DataFrame, factor_col: str, top_n: int, rebalance_frequency: str, horizon: int, weighting_mode: str) -> dict[str, Any]:
    return_col = f"future_return_{horizon}d"
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample["amount"] = pd.to_numeric(sample.get("amount"), errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col, "amount"])
    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), rebalance_frequency)
    returns=[]; equity_curve=[]; turnover_values=[]; equity=1.0; cost_paid=0.0; prev={}; diag=[]
    holdings_by_date={}
    for dt in rebalance_dates:
        cross = sample.loc[sample["date"] == dt].copy()
        if cross.empty:
            continue
        if weighting_mode == 'liquidity_aware':
            holdings, meta = build_liquidity_aware_holdings(cross, factor_col, top_n)
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
        holdings_by_date[pd.Timestamp(dt).strftime('%Y-%m-%d')] = list(holdings.keys())
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
        "holdings_by_rebalance_date": holdings_by_date,
        "diagnostics": diag,
    }


def run_experiment(line: str, strategy_id: str, tickers: list[str]) -> dict[str, Any]:
    registry, reviews, _, _ = load_registry_and_reviews(line)
    item = find_registry_item(registry, strategy_id)
    review_row = latest_review(reviews, strategy_id)
    dataset = build_candidate_dataset(line, item, review_row, tickers=tickers)
    factor_col = factor_column(item['factor'])
    params = item['params']
    equal = run_backtest(dataset, factor_col, params['top_n'], params['rebalance_frequency'], params['horizon'], 'equal')
    law = run_backtest(dataset, factor_col, params['top_n'], params['rebalance_frequency'], params['horizon'], 'liquidity_aware')
    return {
        "line": line,
        "strategy_id": strategy_id,
        "review_window": {k: review_row[k] for k in ['review_id','window_label','start_date','end_date']},
        "operating_params": dict(params),
        "equal_weight": equal,
        "liquidity_aware": law,
    }


def build_report() -> dict[str, Any]:
    tickers = load_filtered_tickers()
    experiments = [run_experiment(line, sid, tickers) for line, sid in TRACKED]
    return {
        "report_type": "liquidity_aware_weighting_experiment",
        "generated_at": pd.Timestamp.now('UTC').isoformat(),
        "filter_source": str(TICKERS_FILE),
        "liquidity_buckets": LIQUIDITY_BUCKETS,
        "hard_cap_ratio": HARD_CAP_RATIO,
        "experiments": experiments,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ['# Liquidity-Aware Weighting Experiment', '', f"- Filter source: {report['filter_source']}", f"- Hard cap ratio: {report['hard_cap_ratio']}", '', '## Results', '| strategy | mode | annual | sharpe | mdd | turnover | cost_paid |', '|---|---:|---:|---:|---:|---:|---:|']
    for exp in report['experiments']:
        for mode in ['equal_weight','liquidity_aware']:
            m = exp[mode]
            lines.append(f"| {exp['strategy_id']} | {mode} | {m['annual_return']:.4f} | {m['sharpe']:.4f} | {m['max_drawdown']:.4f} | {m['turnover']:.4f} | {m['cost_paid']:.4f} |")
    return '\n'.join(lines) + '\n'


def main() -> tuple[Path, Path]:
    report = build_report()
    ts = pd.Timestamp.now('UTC').strftime('%Y%m%dT%H%M%SZ')
    json_path = REPORTS_DIR / f'liquidity_aware_weighting_{ts}.json'
    md_path = REPORTS_DIR / f'liquidity_aware_weighting_{ts}.md'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    md_path.write_text(render_markdown(report), encoding='utf-8')
    (REPORTS_DIR / 'liquidity_aware_weighting_latest.json').write_text(json_path.read_text(encoding='utf-8'), encoding='utf-8')
    (REPORTS_DIR / 'liquidity_aware_weighting_latest.md').write_text(md_path.read_text(encoding='utf-8'), encoding='utf-8')
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == '__main__':
    main()
