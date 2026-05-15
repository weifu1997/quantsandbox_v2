from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(slots=True)
class FactorDefinition:
    name: str
    category: str
    required_columns: list[str]
    min_periods: int
    higher_is_better: bool
    compute_fn: Callable[[pd.DataFrame], pd.Series]

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return self.compute_fn(df)
