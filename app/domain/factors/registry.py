from __future__ import annotations

from app.domain.factors.base import FactorDefinition
from app.domain.factors.momentum import momentum_20d, momentum_20d_skip5d, momentum_60d
from app.domain.factors.quality import (
    gross_margin_factor,
    profit_growth_factor,
    revenue_growth_factor,
    roa_factor,
    roe_factor,
)
from app.domain.factors.reversal import reversal_5d
from app.domain.factors.valuation import pb_factor, pe_factor


class FactorRegistry:
    def __init__(self):
        self._factors: dict[str, FactorDefinition] = {}

    def register(self, factor: FactorDefinition) -> None:
        self._factors[factor.name] = factor

    def get(self, name: str) -> FactorDefinition:
        if name not in self._factors:
            raise KeyError(f"unknown factor: {name}")
        return self._factors[name]

    def list_names(self) -> list[str]:
        return list(self._factors.keys())

    def compute(self, name: str, df):
        return self.get(name).compute(df)


def build_default_factor_registry() -> FactorRegistry:
    registry = FactorRegistry()
    registry.register(
        FactorDefinition(
            name="momentum_20d",
            category="momentum",
            required_columns=["close"],
            min_periods=20,
            higher_is_better=True,
            compute_fn=momentum_20d,
        )
    )
    registry.register(
        FactorDefinition(
            name="momentum_60d",
            category="momentum",
            required_columns=["close"],
            min_periods=60,
            higher_is_better=True,
            compute_fn=momentum_60d,
        )
    )
    registry.register(
        FactorDefinition(
            name="momentum_20d_skip5d",
            category="momentum",
            required_columns=["close"],
            min_periods=20,
            higher_is_better=True,
            compute_fn=momentum_20d_skip5d,
        )
    )
    registry.register(
        FactorDefinition(
            name="reversal_5d",
            category="reversal",
            required_columns=["close"],
            min_periods=5,
            higher_is_better=True,
            compute_fn=reversal_5d,
        )
    )
    registry.register(
        FactorDefinition(
            name="pe",
            category="valuation",
            required_columns=["pe"],
            min_periods=0,
            higher_is_better=False,
            compute_fn=pe_factor,
        )
    )
    registry.register(
        FactorDefinition(
            name="pb",
            category="valuation",
            required_columns=["pb"],
            min_periods=0,
            higher_is_better=False,
            compute_fn=pb_factor,
        )
    )
    registry.register(
        FactorDefinition(
            name="roe",
            category="quality",
            required_columns=["roe"],
            min_periods=0,
            higher_is_better=True,
            compute_fn=roe_factor,
        )
    )
    registry.register(
        FactorDefinition(
            name="roa",
            category="quality",
            required_columns=["roa"],
            min_periods=0,
            higher_is_better=True,
            compute_fn=roa_factor,
        )
    )
    registry.register(
        FactorDefinition(
            name="gross_margin",
            category="quality",
            required_columns=["gross_margin"],
            min_periods=0,
            higher_is_better=True,
            compute_fn=gross_margin_factor,
        )
    )
    registry.register(
        FactorDefinition(
            name="revenue_growth",
            category="growth",
            required_columns=["revenue_growth"],
            min_periods=0,
            higher_is_better=True,
            compute_fn=revenue_growth_factor,
        )
    )
    registry.register(
        FactorDefinition(
            name="profit_growth",
            category="growth",
            required_columns=["profit_growth"],
            min_periods=0,
            higher_is_better=True,
            compute_fn=profit_growth_factor,
        )
    )
    return registry
