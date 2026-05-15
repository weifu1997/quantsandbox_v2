from __future__ import annotations

import pandas as pd


def build_topn_equal_weight_portfolio(
    cross_section: pd.DataFrame,
    factor_col: str,
    top_n: int,
) -> dict[str, float]:
    sample = cross_section.copy()
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).head(top_n)
    if sample.empty:
        return {}
    weight = 1.0 / len(sample)
    return {str(row["ticker"]): weight for _, row in sample.iterrows()}


def build_topn_score_weight_portfolio(
    cross_section: pd.DataFrame,
    factor_col: str,
    top_n: int,
) -> dict[str, float]:
    sample = cross_section.copy()
    sample[factor_col] = pd.to_numeric(sample[factor_col], errors="coerce")
    sample = sample.dropna(subset=[factor_col]).sort_values(factor_col, ascending=False).head(top_n)
    if sample.empty:
        return {}
    scores = sample[factor_col].clip(lower=0)
    total = float(scores.sum())
    if total <= 1e-12:
        return build_topn_equal_weight_portfolio(cross_section, factor_col, top_n)
    return {str(row["ticker"]): float(score / total) for (_, row), score in zip(sample.iterrows(), scores)}
