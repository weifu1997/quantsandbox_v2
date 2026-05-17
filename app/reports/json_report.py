from __future__ import annotations

from typing import Any


def _factor_diagnostics(factor_name: str, factor_payload: dict[str, Any]) -> dict[str, Any]:
    full_sample = factor_payload.get("full_sample", {})
    in_sample = factor_payload.get("in_sample", {})
    out_sample = factor_payload.get("out_sample", {})
    if not full_sample:
        return {
            "factor_name": factor_name,
            "verdict": "unknown",
            "warning": "no factor validation payload",
        }

    first_horizon = sorted(full_sample.keys(), key=lambda x: int(x))[0]
    full_payload = full_sample[first_horizon]
    full_rank_ic = float(full_payload.get("ic", {}).get("rank_ic_mean", 0.0))
    full_monotonicity = float(full_payload.get("monotonicity_score", 0.0))
    in_rank_ic = float(in_sample.get(first_horizon, {}).get("ic", {}).get("rank_ic_mean", 0.0)) if in_sample else 0.0
    out_rank_ic = float(out_sample.get(first_horizon, {}).get("ic", {}).get("rank_ic_mean", 0.0)) if out_sample else 0.0

    verdict = "watchlist"
    notes: list[str] = []
    warnings: list[str] = []
    if full_rank_ic > 0.03 and full_monotonicity >= 0.75:
        verdict = "promising"
        notes.append("rank_ic_mean > 0.03 and monotonicity >= 0.75")
    elif full_rank_ic <= 0:
        verdict = "weak"
        notes.append("rank_ic_mean <= 0")
    else:
        notes.append("signal is mixed; needs more validation")

    if in_sample and out_sample and in_rank_ic > 0 and out_rank_ic <= 0:
        warnings.append("in-sample positive but out-of-sample non-positive")
    if full_monotonicity < 0.5:
        warnings.append("group return monotonicity is weak")

    return {
        "factor_name": factor_name,
        "reference_horizon": int(first_horizon),
        "rank_ic_mean": full_rank_ic,
        "rank_ic_mean_in_sample": in_rank_ic,
        "rank_ic_mean_out_sample": out_rank_ic,
        "monotonicity_score": full_monotonicity,
        "verdict": verdict,
        "notes": notes,
        "warnings": warnings,
    }


def render_json_report(
    *,
    config: dict[str, Any],
    dataset_summary: dict[str, Any],
    factor_results: dict[str, Any],
    backtest_results: dict[str, Any],
) -> dict[str, Any]:
    diagnostics = [_factor_diagnostics(name, payload) for name, payload in factor_results.items()]
    warnings: list[str] = []

    if dataset_summary.get("valid_sample_ratio", 0.0) < 0.5:
        warnings.append("valid_sample_ratio is below 50%; results may be unstable")
    if dataset_summary.get("invalid_reasons"):
        warnings.append("dataset contains invalid samples; inspect invalid_reasons")
    warnings.extend(dataset_summary.get("warnings", []))
    if not factor_results:
        warnings.append("no factor research results available")
    if not backtest_results:
        warnings.append("no backtest results available")

    for item in diagnostics:
        warnings.extend(item.get("warnings", []))

    best_factor = None
    if diagnostics:
        best_factor = sorted(
            diagnostics,
            key=lambda x: (x.get("rank_ic_mean", 0.0), x.get("monotonicity_score", 0.0)),
            reverse=True,
        )[0]["factor_name"]

    return {
        "title": "QuantSandbox v2 Research Report",
        "output_format": "json",
        "config": config,
        "dataset_summary": dataset_summary,
        "data_mode": dataset_summary.get("data_mode", "unknown"),
        "factor_results": factor_results,
        "backtest_results": backtest_results,
        "factor_diagnostics": diagnostics,
        "summary": {
            "factor_count": len(factor_results),
            "best_factor": best_factor,
            "warning_count": len(warnings),
            "data_mode": dataset_summary.get("data_mode", "unknown"),
        },
        "warnings": warnings,
    }
