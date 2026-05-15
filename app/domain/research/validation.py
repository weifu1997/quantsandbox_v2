from __future__ import annotations

from typing import Any

from app.domain.research.group_analysis import compute_group_returns, compute_monotonicity_score
from app.domain.research.ic_analysis import compute_ic_series, compute_rank_ic_series, summarize_ic
from app.domain.research.sample_split import split_in_sample_out_sample


def run_factor_validation(
    dataset,
    factor_col: str,
    horizons: list[int],
    groups: int = 5,
    split_date: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "full_sample": {},
        "in_sample": {},
        "out_sample": {},
    }
    in_sample = out_sample = None
    if split_date:
        in_sample, out_sample = split_in_sample_out_sample(dataset, split_date)

    for horizon in horizons:
        return_col = f"future_return_{horizon}d"

        def _analyze(frame):
            ic_series = compute_ic_series(frame, factor_col, return_col)
            rank_ic_series = compute_rank_ic_series(frame, factor_col, return_col)
            ic_summary = summarize_ic(ic_series, rank_ic_series)
            group_returns = compute_group_returns(frame, factor_col, return_col, groups)
            return {
                "ic": ic_summary,
                "group_returns": group_returns,
                "monotonicity_score": compute_monotonicity_score(group_returns),
            }

        result["full_sample"][str(horizon)] = _analyze(dataset)
        if in_sample is not None:
            result["in_sample"][str(horizon)] = _analyze(in_sample)
        if out_sample is not None:
            result["out_sample"][str(horizon)] = _analyze(out_sample)
    return result
