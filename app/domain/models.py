from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExperimentConfig:
    start_date: str
    end_date: str
    factors: list[str] = field(default_factory=list)
    horizons: list[int] = field(default_factory=lambda: [5, 20, 60])
    tickers: list[str] = field(default_factory=list)
    universe: str | None = None
    rebalance_frequency: str = "W"
    top_n: int = 10
    weighting: str = "equal"
    benchmark: str = "equal_weight_universe"
    commission_bps: float = 10.0
    slippage_bps: float = 5.0
    report_format: str = "json"
    annual_turnover_limit: float | None = None
    initial_aum: float = 1.0
    board_lot_enabled: bool = False
    board_lot_size: int = 100
    execution_assumptions: dict | None = None


@dataclass(slots=True)
class FactorSpec:
    name: str
    category: str
    required_columns: list[str] = field(default_factory=list)
    min_periods: int = 0
    higher_is_better: bool = True


@dataclass(slots=True)
class DatasetSummary:
    rows: int = 0
    tickers: list[str] = field(default_factory=list)
    factors: list[str] = field(default_factory=list)
    horizons: list[int] = field(default_factory=list)
    valid_sample_ratio: float = 0.0
    invalid_reasons: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    data_mode: str = "unknown"


@dataclass(slots=True)
class FactorResearchResult:
    factor_name: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestResult:
    factor_name: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReportSummary:
    title: str
    output_format: str
    payload: dict[str, Any] = field(default_factory=dict)
