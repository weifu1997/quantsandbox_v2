from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.domain.backtest.dynamic_impact_model import DEFAULT_BUCKETS, estimate_dynamic_impact_bps
from app.domain.data_contracts import factor_column
from app.domain.backtest.portfolio_construction import build_topn_equal_weight_portfolio, build_topn_score_weight_portfolio
from app.domain.backtest.rebalance_calendar import select_rebalance_dates
from scripts.run_growth_executable_alpha_validation import (
    DEFAULT_STRATEGY_ID,
    REPORTS_DIR,
    build_growth_sample,
)


AUM_ASSUMPTIONS = [
    {"label": "actual_equity_curve_start", "aum": 1.0},
    {"label": "model_small", "aum": 1_000_000.0},
    {"label": "model_medium", "aum": 5_000_000.0},
    {"label": "model_large", "aum": 10_000_000.0},
]


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(pd.Series(values, dtype="float64").quantile(q))


def summarize_values(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "median": None,
            "p90": None,
            "max": None,
            "mean": None,
        }
    series = pd.Series(values, dtype="float64")
    return {
        "count": int(series.shape[0]),
        "min": float(series.min()),
        "median": float(series.median()),
        "p90": float(series.quantile(0.90)),
        "max": float(series.max()),
        "mean": float(series.mean()),
    }


def bucket_thresholds() -> list[dict[str, float | str]]:
    return [
        {"label": bucket.label, "max_participation_rate": float(bucket.max_rate), "impact_bps": float(bucket.impact_bps)}
        for bucket in DEFAULT_BUCKETS
    ]


def build_holdings_by_date(dataset: pd.DataFrame, params: dict[str, Any], factor_name: str) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    sample = dataset.copy()
    sample["date"] = pd.to_datetime(sample["date"])
    if "is_valid_sample" in sample.columns:
        sample = sample.loc[sample["is_valid_sample"] == True].copy()
    factor_col = factor_column(factor_name)
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col])
    rebalance_dates = select_rebalance_dates(sample["date"].tolist(), str(params["rebalance_frequency"]))
    holdings_by_date: dict[str, dict[str, float]] = {}
    turnover_by_date: dict[str, float] = {}
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
        date_key = pd.Timestamp(dt).strftime("%Y-%m-%d")
        holdings_by_date[date_key] = {str(k): float(v) for k, v in holdings.items()}
        all_tickers = set(previous_holdings) | set(holdings)
        turnover = 0.0
        for ticker in all_tickers:
            turnover += abs(float(holdings.get(ticker, 0.0)) - float(previous_holdings.get(ticker, 0.0)))
        turnover_by_date[date_key] = float(turnover)
        previous_holdings = holdings
    return holdings_by_date, turnover_by_date


def analyze_aum_scale(
    dataset: pd.DataFrame,
    holdings_by_date: dict[str, dict[str, float]],
    aum: float,
) -> dict[str, Any]:
    frame = dataset[["date", "ticker", "amount"]].copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")

    trade_notionals: list[float] = []
    participation_rates: list[float] = []
    amount_values: list[float] = []
    impact_bps_values: list[float] = []
    bucket_counts: Counter[str] = Counter()
    per_rebalance_avg_participation: list[float] = []
    per_rebalance_max_participation: list[float] = []
    previous_holdings: dict[str, float] = {}

    for date_key in sorted(holdings_by_date):
        holdings = holdings_by_date[date_key]
        cross = frame.loc[frame["date"] == date_key].set_index("ticker")
        per_name_rates: list[float] = []
        all_tickers = set(previous_holdings) | set(holdings)
        for ticker in all_tickers:
            target_weight = float(holdings.get(ticker, 0.0))
            current_weight = float(previous_holdings.get(ticker, 0.0))
            trade_notional = abs(target_weight - current_weight) * float(aum)
            amount = None
            if ticker in cross.index:
                maybe = cross.loc[ticker, "amount"]
                if hasattr(maybe, "iloc"):
                    maybe = maybe.iloc[0]
                amount = float(maybe) if pd.notna(maybe) else 0.0
            else:
                amount = 0.0
            estimate = estimate_dynamic_impact_bps(trade_notional, amount)
            trade_notionals.append(float(trade_notional))
            participation_rates.append(float(estimate.participation_rate))
            impact_bps_values.append(float(estimate.impact_bps))
            amount_values.append(float(amount))
            bucket_counts[str(estimate.bucket_label)] += 1
            per_name_rates.append(float(estimate.participation_rate))
        if per_name_rates:
            per_rebalance_avg_participation.append(float(sum(per_name_rates) / len(per_name_rates)))
            per_rebalance_max_participation.append(float(max(per_name_rates)))
        previous_holdings = holdings

    total = sum(bucket_counts.values())
    bucket_ratio = {label: float(bucket_counts.get(label, 0) / total) if total else 0.0 for label in [b.label for b in DEFAULT_BUCKETS]}
    return {
        "aum": float(aum),
        "trade_notional_summary": summarize_values(trade_notionals),
        "amount_summary": summarize_values(amount_values),
        "participation_summary": summarize_values(participation_rates),
        "impact_bps_summary": summarize_values(impact_bps_values),
        "per_rebalance_avg_participation_summary": summarize_values(per_rebalance_avg_participation),
        "per_rebalance_max_participation_summary": summarize_values(per_rebalance_max_participation),
        "bucket_counts": dict(bucket_counts),
        "bucket_ratio": bucket_ratio,
    }


def build_root_cause(report: dict[str, Any], actual_scale: dict[str, Any]) -> dict[str, Any]:
    top_n = int(report["operating_params"]["top_n"])
    avg_turnover = float(report["before_after"]["dynamic_impact_v1"]["turnover"])
    median_trade_notional = actual_scale["trade_notional_summary"]["median"]
    median_amount = actual_scale["amount_summary"]["median"]
    max_participation = actual_scale["participation_summary"]["max"] or 0.0
    p90_participation = actual_scale["participation_summary"]["p90"] or 0.0
    very_light_cap = next(b.max_rate for b in DEFAULT_BUCKETS if b.label == "very_light")

    reasons: list[str] = []
    if median_trade_notional is not None and median_trade_notional < 1.0:
        reasons.append("equity scale inside the current backtest is ~1.0, so per-trade notional is tiny")
    if median_amount is not None and median_amount > 1_000_000:
        reasons.append("selected holdings trade against large daily amount denominators")
    if avg_turnover < 0.10:
        reasons.append("weekly turnover is low, so weight changes create small trade sizes")
    if top_n >= 20:
        reasons.append("equal-weight top_n=20 dilutes single-name trade notional")
    if p90_participation < very_light_cap:
        reasons.append("even p90 participation stays below the first impact bucket threshold")

    dominant_driver = reasons[0] if reasons else "participation remains too small across all observed dimensions"
    return {
        "dominant_driver": dominant_driver,
        "supporting_reasons": reasons,
        "very_light_threshold": float(very_light_cap),
        "observed_max_participation_rate": float(max_participation),
        "observed_p90_participation_rate": float(p90_participation),
    }


def build_sensitivity(actual_scale: dict[str, Any]) -> dict[str, Any]:
    max_participation = actual_scale["participation_summary"]["max"] or 0.0
    p90_participation = actual_scale["participation_summary"]["p90"] or 0.0
    first_warn = next(b.max_rate for b in DEFAULT_BUCKETS if b.label == "light")
    if max_participation <= 0:
        return {
            "aum_multiple_to_reach_light_bucket_at_max_trade": None,
            "aum_multiple_to_reach_light_bucket_at_p90_trade": None,
        }
    return {
        "aum_multiple_to_reach_light_bucket_at_max_trade": float(first_warn / max_participation),
        "aum_multiple_to_reach_light_bucket_at_p90_trade": float(first_warn / p90_participation) if p90_participation > 0 else None,
    }


def build_report(
    strategy_id: str = DEFAULT_STRATEGY_ID,
    tickers_file: str | None = None,
    sample_limit: int = 1000,
) -> dict[str, Any]:
    validation_path = REPORTS_DIR / "growth_executable_alpha_validation_latest.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    dataset, registry_item, review, tickers_trace = build_growth_sample(
        strategy_id=strategy_id,
        tickers_file=tickers_file,
        sample_limit=sample_limit,
        reports_dir=REPORTS_DIR,
    )
    holdings_by_date, turnover_by_date = build_holdings_by_date(dataset, registry_item["params"], str(registry_item["factor"]))
    scales = [analyze_aum_scale(dataset, holdings_by_date, item["aum"]) | {"label": item["label"]} for item in AUM_ASSUMPTIONS]
    actual_scale = next(x for x in scales if x["label"] == "actual_equity_curve_start")
    return {
        "report_type": "growth_participation_diagnostic",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "strategy_id": strategy_id,
        "review_context": {
            "review_id": review.get("review_id"),
            "window_label": review.get("window_label"),
            "start_date": review.get("start_date"),
            "end_date": review.get("end_date"),
        },
        "sample_summary": {
            "rows": int(len(dataset)),
            "active_dates": int(dataset["date"].nunique()),
            "unique_tickers": int(dataset["ticker"].nunique()),
            "rebalance_dates": len(holdings_by_date),
            "median_names_held": float(pd.Series([len(v) for v in holdings_by_date.values()]).median()) if holdings_by_date else None,
            "avg_turnover": float(pd.Series(list(turnover_by_date.values())).mean()) if turnover_by_date else None,
        },
        "bucket_thresholds": bucket_thresholds(),
        "actual_validation_snapshot": validation["before_after"]["dynamic_impact_v1"]["execution_diagnostics"],
        "aum_scale_analysis": scales,
        "root_cause_assessment": build_root_cause(validation, actual_scale),
        "sensitivity_check": build_sensitivity(actual_scale),
        "source_artifacts": {
            "growth_executable_alpha_validation": str(validation_path),
            "tickers_file": tickers_trace,
            "registry": str(REPORTS_DIR / "revgrowth_candidate_registry.json"),
            "reviews": str(REPORTS_DIR / "revgrowth_candidate_reviews.json"),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    root = report["root_cause_assessment"]
    lines = [
        "# Growth Participation / Impact Bucket Diagnostic",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Strategy: {report['strategy_id']}",
        f"- Review window: {report['review_context']['window_label']} ({report['review_context']['start_date']} → {report['review_context']['end_date']})",
        "",
        "## Current validation snapshot",
        f"- avg_participation_rate: {report['actual_validation_snapshot'].get('avg_participation_rate')}",
        f"- p90_participation_rate: {report['actual_validation_snapshot'].get('p90_participation_rate')}",
        f"- max_participation_rate: {report['actual_validation_snapshot'].get('max_participation_rate')}",
        f"- avg_dynamic_impact_bps: {report['actual_validation_snapshot'].get('avg_dynamic_impact_bps')}",
        f"- bucket_counts: {report['actual_validation_snapshot'].get('bucket_counts')}",
        "",
        "## Root-cause assessment",
        f"- dominant_driver: {root['dominant_driver']}",
        f"- very_light_threshold: {root['very_light_threshold']}",
        f"- observed_p90_participation_rate: {root['observed_p90_participation_rate']}",
        f"- observed_max_participation_rate: {root['observed_max_participation_rate']}",
    ]
    for item in root["supporting_reasons"]:
        lines.append(f"- reason: {item}")
    lines += ["", "## AUM scale analysis"]
    for item in report["aum_scale_analysis"]:
        lines.append(f"### {item['label']}")
        lines.append(f"- aum: {item['aum']}")
        lines.append(f"- median_trade_notional: {item['trade_notional_summary']['median']}")
        lines.append(f"- median_amount: {item['amount_summary']['median']}")
        lines.append(f"- p90_participation_rate: {item['participation_summary']['p90']}")
        lines.append(f"- max_participation_rate: {item['participation_summary']['max']}")
        lines.append(f"- bucket_ratio: {item['bucket_ratio']}")
        lines.append("")
    lines += [
        "## Sensitivity check",
        f"- aum_multiple_to_reach_light_bucket_at_max_trade: {report['sensitivity_check']['aum_multiple_to_reach_light_bucket_at_max_trade']}",
        f"- aum_multiple_to_reach_light_bucket_at_p90_trade: {report['sensitivity_check']['aum_multiple_to_reach_light_bucket_at_p90_trade']}",
        "",
    ]
    return "\n".join(lines)


def write_latest_aliases(json_path: Path, md_path: Path) -> None:
    (REPORTS_DIR / "growth_participation_diagnostic_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORTS_DIR / "growth_participation_diagnostic_latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> tuple[Path, Path]:
    parser = argparse.ArgumentParser(description="Diagnose growth participation / impact bucket root causes")
    parser.add_argument("--strategy-id", default=DEFAULT_STRATEGY_ID)
    parser.add_argument("--tickers-file", default=None)
    parser.add_argument("--sample-limit", type=int, default=1000)
    args = parser.parse_args()

    report = build_report(strategy_id=args.strategy_id, tickers_file=args.tickers_file, sample_limit=args.sample_limit)
    timestamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORTS_DIR / f"growth_participation_diagnostic_{timestamp}.json"
    md_path = REPORTS_DIR / f"growth_participation_diagnostic_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_latest_aliases(json_path, md_path)
    print(json_path)
    print(md_path)
    return json_path, md_path


if __name__ == "__main__":
    main()
