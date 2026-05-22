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

from app.domain.backtest.cost_model import estimate_transaction_cost
from app.domain.backtest.dynamic_impact_model import estimate_dynamic_impact_bps
from app.domain.data_contracts import factor_column
from app.domain.backtest.portfolio_construction import build_topn_equal_weight_portfolio, build_topn_score_weight_portfolio
from app.domain.backtest.rebalance_calendar import select_rebalance_dates
from app.domain.backtest.performance_metrics import annual_return, max_drawdown, periods_per_year, sharpe_ratio, total_return, win_rate
from scripts.run_growth_executable_alpha_validation import DEFAULT_STRATEGY_ID, REPORTS_DIR, build_growth_sample

AUM_ASSUMPTIONS = [
    {"label": "model_small", "aum": 1_000_000.0},
    {"label": "model_medium", "aum": 5_000_000.0},
    {"label": "model_large", "aum": 10_000_000.0},
]


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if abs(float(denominator)) < 1e-12:
        return None
    return float(numerator / denominator)


def build_holdings_tape(dataset: pd.DataFrame, params: dict[str, Any], factor_name: str) -> list[dict[str, Any]]:
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    factor_col = factor_column(factor_name)
    return_col = f"future_return_{int(params['horizon'])}d"
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col])
    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), str(params["rebalance_frequency"]))

    tape: list[dict[str, Any]] = []
    previous_holdings: dict[str, float] = {}
    for dt in rebalance_dates:
        cross = sample.loc[sample["date"] == dt].copy()
        if cross.empty:
            continue
        if str(params["weighting"]).lower() == "score":
            holdings = build_topn_score_weight_portfolio(cross, factor_col, int(params["top_n"]))
        else:
            holdings = build_topn_equal_weight_portfolio(cross, factor_col, int(params["top_n"]))
        if not holdings:
            continue
        cross = cross.set_index("ticker")
        gross = 0.0
        for ticker, weight in holdings.items():
            if ticker in cross.index:
                gross += float(weight) * float(cross.loc[ticker, return_col])
        tape.append(
            {
                "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                "holdings": {str(k): float(v) for k, v in holdings.items()},
                "previous_holdings": dict(previous_holdings),
                "gross_return": float(gross),
                "cross_section": cross[["amount"]].copy() if "amount" in cross.columns else pd.DataFrame(index=cross.index),
            }
        )
        previous_holdings = holdings
    return tape


def compute_turnover(prev_holdings: dict[str, float], holdings: dict[str, float]) -> float:
    tickers = set(prev_holdings) | set(holdings)
    return float(sum(abs(float(holdings.get(t, 0.0)) - float(prev_holdings.get(t, 0.0))) for t in tickers))


def run_scaled_scenario(tape: list[dict[str, Any]], params: dict[str, Any], aum: float, dynamic_impact: bool) -> dict[str, Any]:
    returns: list[float] = []
    equity_curve: list[float] = []
    cost_paid = 0.0
    impact_cost_paid = 0.0
    turnover_values: list[float] = []
    participation_rates: list[float] = []
    impact_bps_values: list[float] = []
    bucket_counts = {"very_light": 0, "light": 0, "medium": 0, "heavy": 0, "extreme": 0}
    equity = float(aum)

    for row in tape:
        holdings = row["holdings"]
        previous_holdings = row["previous_holdings"]
        gross = float(row["gross_return"])
        turnover = compute_turnover(previous_holdings, holdings)
        turnover_values.append(turnover)
        base_cost = float(estimate_transaction_cost(turnover, float(params.get("commission_bps", 10.0)), float(params.get("slippage_bps", 5.0))) * equity)
        impact_cost = 0.0
        cross = row["cross_section"]
        all_tickers = set(previous_holdings) | set(holdings)
        for ticker in all_tickers:
            target_weight = float(holdings.get(ticker, 0.0))
            current_weight = float(previous_holdings.get(ticker, 0.0))
            trade_notional = abs(target_weight - current_weight) * float(equity)
            amount = 0.0
            if ticker in cross.index and "amount" in cross.columns:
                maybe = cross.loc[ticker, "amount"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
                amount = float(maybe) if pd.notna(maybe) else 0.0
            estimate = estimate_dynamic_impact_bps(trade_notional, amount)
            participation_rates.append(float(estimate.participation_rate))
            impact_bps_values.append(float(estimate.impact_bps))
            bucket_counts[estimate.bucket_label] = bucket_counts.get(estimate.bucket_label, 0) + 1
            if dynamic_impact:
                impact_cost += float(trade_notional * estimate.impact_bps / 10000.0)
        total_cost = base_cost + impact_cost
        net = gross - (total_cost / float(equity) if equity > 0 else 0.0)
        returns.append(float(net))
        cost_paid += total_cost
        impact_cost_paid += impact_cost
        equity *= 1.0 + float(net)
        equity_curve.append(float(equity))

    ppy = periods_per_year(str(params["rebalance_frequency"]))
    return {
        "aum": float(aum),
        "annual_return": annual_return(returns, ppy),
        "total_return": total_return(equity_curve),
        "sharpe": sharpe_ratio(returns, ppy),
        "max_drawdown": max_drawdown(equity_curve),
        "turnover": float(sum(turnover_values) / len(turnover_values)) if turnover_values else 0.0,
        "win_rate": win_rate(returns),
        "base_cost_paid": float(cost_paid - impact_cost_paid),
        "impact_cost_paid": float(impact_cost_paid),
        "total_cost_paid_with_impact": float(cost_paid),
        "execution_diagnostics": {
            "avg_participation_rate": float(pd.Series(participation_rates).mean()) if participation_rates else 0.0,
            "p90_participation_rate": float(pd.Series(participation_rates).quantile(0.90)) if participation_rates else 0.0,
            "max_participation_rate": float(max(participation_rates)) if participation_rates else 0.0,
            "avg_dynamic_impact_bps": float(pd.Series(impact_bps_values).mean()) if impact_bps_values else 0.0,
            "bucket_counts": bucket_counts,
        },
    }


def classify_working_config_recommendation(dynamic_payload: dict[str, Any]) -> dict[str, str]:
    diag = dynamic_payload["execution_diagnostics"]
    extreme = int(diag["bucket_counts"].get("extreme", 0))
    heavy = int(diag["bucket_counts"].get("heavy", 0))
    annual_return = float(dynamic_payload["annual_return"])
    avg_bps = float(diag.get("avg_dynamic_impact_bps", 0.0))
    if annual_return < 0 or extreme > 0:
        return {
            "status": "stop_using",
            "reason": "capital-scaled dynamic impact pushes growth into extreme execution buckets or negative executable return",
        }
    if avg_bps > 25 or heavy > 0:
        return {
            "status": "needs_revision",
            "reason": "capital-scaled dynamic impact materially degrades executability and now requires a revised working config",
        }
    if avg_bps > 10:
        return {
            "status": "keep_with_caution",
            "reason": "growth still works, but capital-scaled impact friction is high enough that the working config should only be kept cautiously",
        }
    return {
        "status": "keep",
        "reason": "even after capital scaling, impact diagnostics remain inside the current tolerance band",
    }


def first_bucket_entry(stress_cases: list[dict[str, Any]]) -> dict[str, str | None]:
    out: dict[str, str | None] = {"light": None, "medium": None, "heavy": None, "extreme": None}
    for case in stress_cases:
        counts = case["dynamic_impact_v1"]["execution_diagnostics"]["bucket_counts"]
        for label in ["light", "medium", "heavy", "extreme"]:
            if out[label] is None and int(counts.get(label, 0)) > 0:
                out[label] = str(case["capital_label"])
    return out


def build_case(capital_label: str, aum: float, tape: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    base = run_scaled_scenario(tape, params, aum, dynamic_impact=False)
    dynamic = run_scaled_scenario(tape, params, aum, dynamic_impact=True)
    annual_delta = float(dynamic["annual_return"] - base["annual_return"])
    sharpe_delta = float(dynamic["sharpe"] - base["sharpe"])
    annual_erosion_rate = safe_ratio(base["annual_return"] - dynamic["annual_return"], base["annual_return"])
    sharpe_erosion_rate = safe_ratio(base["sharpe"] - dynamic["sharpe"], base["sharpe"])
    recommendation = classify_working_config_recommendation(dynamic)
    return {
        "capital_label": capital_label,
        "aum": float(aum),
        "comparison_discipline": {
            "same_strategy": True,
            "same_window": True,
            "same_universe": True,
            "same_params": True,
            "capital_assumption_only_change": True,
        },
        "fixed_cost_baseline": base,
        "dynamic_impact_v1": dynamic,
        "executable_alpha_erosion": {
            "annual_return_delta": annual_delta,
            "sharpe_delta": sharpe_delta,
            "annual_return_erosion_rate": annual_erosion_rate,
            "sharpe_erosion_rate": sharpe_erosion_rate,
            "base_cost_paid": float(dynamic["base_cost_paid"]),
            "impact_cost_paid": float(dynamic["impact_cost_paid"]),
            "total_cost_paid_with_impact": float(dynamic["total_cost_paid_with_impact"]),
        },
        "working_config_recommendation_impact": recommendation,
    }


def build_report(strategy_id: str = DEFAULT_STRATEGY_ID, tickers_file: str | None = None, sample_limit: int = 1000) -> dict[str, Any]:
    dataset, registry_item, review, tickers_trace = build_growth_sample(
        strategy_id=strategy_id,
        tickers_file=tickers_file,
        sample_limit=sample_limit,
        reports_dir=REPORTS_DIR,
    )
    tape = build_holdings_tape(dataset, registry_item["params"], str(registry_item["factor"]))
    stress_cases = [build_case(item["label"], float(item["aum"]), tape, registry_item["params"]) for item in AUM_ASSUMPTIONS]
    return {
        "report_type": "growth_executable_alpha_scale_stress",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "strategy_id": strategy_id,
        "review_context": {
            "review_id": review.get("review_id"),
            "window_label": review.get("window_label"),
            "start_date": review.get("start_date"),
            "end_date": review.get("end_date"),
        },
        "operating_params": dict(registry_item.get("params", {})),
        "strategy_filter": dict(registry_item.get("filter", {})),
        "sample_summary": {
            "rows": int(len(dataset)),
            "active_dates": int(dataset["date"].nunique()),
            "unique_tickers": int(dataset["ticker"].nunique()),
            "rebalance_dates": len(tape),
        },
        "stress_cases": stress_cases,
        "bucket_entry_thresholds": first_bucket_entry(stress_cases),
        "source_artifacts": {
            "tickers_file": tickers_trace,
            "registry": str(REPORTS_DIR / "revgrowth_candidate_registry.json"),
            "reviews": str(REPORTS_DIR / "revgrowth_candidate_reviews.json"),
            "p31_participation_diagnostic": str(REPORTS_DIR / "growth_participation_diagnostic_latest.json"),
            "p3_validation": str(REPORTS_DIR / "growth_executable_alpha_validation_latest.json"),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Growth Executable Alpha Scale Stress",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Strategy: {report['strategy_id']}",
        f"- Review window: {report['review_context']['window_label']} ({report['review_context']['start_date']} → {report['review_context']['end_date']})",
        "",
        "## Bucket entry thresholds",
    ]
    for label, capital_label in report["bucket_entry_thresholds"].items():
        lines.append(f"- {label}: {capital_label}")
    lines += ["", "## Stress cases"]
    for case in report["stress_cases"]:
        base = case["fixed_cost_baseline"]
        dyn = case["dynamic_impact_v1"]
        erosion = case["executable_alpha_erosion"]
        rec = case["working_config_recommendation_impact"]
        lines.append(f"### {case['capital_label']} (aum={case['aum']})")
        lines.append(f"- annual_return: {base['annual_return']} → {dyn['annual_return']} (delta={erosion['annual_return_delta']})")
        lines.append(f"- sharpe: {base['sharpe']} → {dyn['sharpe']} (delta={erosion['sharpe_delta']})")
        lines.append(f"- annual_return_erosion_rate: {erosion['annual_return_erosion_rate']}")
        lines.append(f"- sharpe_erosion_rate: {erosion['sharpe_erosion_rate']}")
        lines.append(f"- base_cost_paid: {erosion['base_cost_paid']}")
        lines.append(f"- impact_cost_paid: {erosion['impact_cost_paid']}")
        lines.append(f"- total_cost_paid_with_impact: {erosion['total_cost_paid_with_impact']}")
        lines.append(f"- bucket_counts: {dyn['execution_diagnostics']['bucket_counts']}")
        lines.append(f"- working_config_recommendation: {rec['status']} — {rec['reason']}")
        lines.append("")
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path) -> None:
    (REPORTS_DIR / "growth_executable_alpha_scale_stress_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / "growth_executable_alpha_scale_stress_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    parser = argparse.ArgumentParser(description="Run capital-scale executable alpha stress for growth")
    parser.add_argument("--strategy-id", default=DEFAULT_STRATEGY_ID)
    parser.add_argument("--tickers-file", default=None)
    parser.add_argument("--sample-limit", type=int, default=1000)
    args = parser.parse_args()

    report = build_report(strategy_id=args.strategy_id, tickers_file=args.tickers_file, sample_limit=args.sample_limit)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"growth_executable_alpha_scale_stress_{timestamp}.json"
    md_path = REPORTS_DIR / f"growth_executable_alpha_scale_stress_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
