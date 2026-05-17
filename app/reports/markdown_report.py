from __future__ import annotations

from typing import Any


def render_markdown_report(
    *,
    config: dict[str, Any],
    dataset_summary: dict[str, Any],
    factor_results: dict[str, Any],
    backtest_results: dict[str, Any],
    factor_diagnostics: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> str:
    factor_diagnostics = factor_diagnostics or []
    warnings = warnings or []

    lines = [
        "# QuantSandbox v2 Research Report",
        "",
        "## Config",
        f"- start_date: {config.get('start_date')}",
        f"- end_date: {config.get('end_date')}",
        f"- factors: {', '.join(config.get('factors', []))}",
        f"- horizons: {', '.join(str(x) for x in config.get('horizons', []))}",
        f"- top_n: {config.get('top_n')}",
        f"- benchmark: {config.get('benchmark')}",
        "",
        "## Dataset Summary",
        f"- rows: {dataset_summary.get('rows', 0)}",
        f"- data_mode: {dataset_summary.get('data_mode', 'unknown')}",
        f"- valid_sample_ratio: {dataset_summary.get('valid_sample_ratio', 0.0):.2%}",
        f"- invalid_reasons: {dataset_summary.get('invalid_reasons', {})}",
        "",
        "## Factor Diagnostics",
    ]
    for item in factor_diagnostics:
        lines.append(
            f"- {item.get('factor_name')}: verdict={item.get('verdict')}, rank_ic_mean={item.get('rank_ic_mean', 0.0):.4f}, monotonicity={item.get('monotonicity_score', 0.0):.2f}"
        )
    lines.extend(["", "## Backtest Results"])
    for factor_name, payload in backtest_results.items():
        lines.append(
            f"- {factor_name}: total_return={payload.get('total_return', 0.0):.2%}, annual_return={payload.get('annual_return', 0.0):.2%}, sharpe={payload.get('sharpe', 0.0):.4f}, max_drawdown={payload.get('max_drawdown', 0.0):.2%}"
        )
    if warnings:
        lines.extend(["", "## Warnings"])
        for warning in warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines)
