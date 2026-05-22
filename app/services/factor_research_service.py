from __future__ import annotations

from typing import Any

from app.domain.data_contracts import factor_column
from app.domain.research.validation import run_factor_validation


def run_factor_research(
    dataset,
    factor_names: list[str],
    horizons: list[int],
    groups: int = 5,
    split_date: str | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for factor_name in factor_names:
        factor_col = factor_column(factor_name)
        results[factor_name] = run_factor_validation(
            dataset=dataset,
            factor_col=factor_col,
            horizons=horizons,
            groups=groups,
            split_date=split_date,
        )
    return results
