from __future__ import annotations

import pandas as pd


def assign_quantile_groups(dataset: pd.DataFrame, factor_col: str, groups: int) -> pd.Series:
    def _assign(series: pd.Series) -> pd.Series:
        ranks = series.rank(method="first", pct=True)
        return (ranks * groups).clip(upper=groups - 0.001).astype(int) + 1

    factor = pd.to_numeric(dataset[factor_col], errors="coerce")
    return dataset.assign(_factor=factor).groupby("date", group_keys=False)["_factor"].transform(_assign)


def compute_group_returns(dataset: pd.DataFrame, factor_col: str, return_col: str, groups: int) -> dict[str, float]:
    sample = dataset.copy()
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample[return_col] = pd.to_numeric(sample[return_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col, return_col])
    if sample.empty:
        return {f"Q{i}": 0.0 for i in range(1, groups + 1)}

    sample["_group"] = assign_quantile_groups(sample, factor_col, groups)
    result = sample.groupby("_group")[return_col].mean().to_dict()
    return {f"Q{i}": float(result.get(i, 0.0)) for i in range(1, groups + 1)}


def compute_monotonicity_score(group_returns: dict[str, float]) -> float:
    values = [group_returns[k] for k in sorted(group_returns.keys())]
    if len(values) < 2:
        return 0.0
    comparisons = sum(1 for i in range(1, len(values)) if values[i] >= values[i - 1])
    return float(comparisons / (len(values) - 1))
