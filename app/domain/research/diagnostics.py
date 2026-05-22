from __future__ import annotations

from typing import Any


def diagnose_factor(
    factor_name: str,
    ic_summary: dict[str, Any],
    group_summary: dict[str, Any],
) -> dict[str, Any]:
    ic_mean = float(ic_summary.get("ic_mean", 0.0) or 0.0)
    rank_ic_mean = float(ic_summary.get("rank_ic_mean", 0.0) or 0.0)
    sample_count = int(ic_summary.get("sample_count", 0) or 0)
    positive_ic_ratio = float(ic_summary.get("positive_ic_ratio", 0.0) or 0.0)

    monotonicity = float(group_summary.get("monotonicity_score", 0.0) or 0.0)
    group_returns = group_summary.get("group_returns", {}) or {}
    top_bucket = float(group_returns.get("Q5", 0.0) or 0.0)
    bottom_bucket = float(group_returns.get("Q1", 0.0) or 0.0)
    spread = top_bucket - bottom_bucket

    strengths: list[str] = []
    warnings: list[str] = []

    if abs(ic_mean) >= 0.03:
        strengths.append("ic_mean_is_material")
    else:
        warnings.append("ic_mean_is_weak")

    if abs(rank_ic_mean) >= 0.03:
        strengths.append("rank_ic_mean_is_material")
    else:
        warnings.append("rank_ic_mean_is_weak")

    if monotonicity >= 0.75:
        strengths.append("group_returns_are_mostly_monotonic")
    else:
        warnings.append("group_returns_are_not_monotonic_enough")

    if spread > 0:
        strengths.append("top_group_outperforms_bottom_group")
    else:
        warnings.append("top_group_does_not_outperform_bottom_group")

    if sample_count < 10:
        warnings.append("sample_count_is_small")

    if positive_ic_ratio < 0.5:
        warnings.append("positive_ic_ratio_is_low")

    verdict = "promising"
    if len(warnings) >= 3:
        verdict = "weak"
    elif warnings:
        verdict = "mixed"

    return {
        "factor_name": factor_name,
        "verdict": verdict,
        "summary": {
            "ic_mean": ic_mean,
            "rank_ic_mean": rank_ic_mean,
            "sample_count": sample_count,
            "positive_ic_ratio": positive_ic_ratio,
            "monotonicity_score": monotonicity,
            "top_bottom_spread": spread,
        },
        "strengths": strengths,
        "warnings": warnings,
    }
