from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.run_liquidity_aware_weighting_experiment import (
    build_equal_holdings,
    build_liquidity_aware_holdings,
    normalize,
)


def test_normalize_basic():
    out = normalize({"a": 1.0, "b": 1.0})
    assert round(sum(out.values()), 6) == 1.0
    assert round(out["a"], 4) == 0.5


def test_build_liquidity_aware_holdings_penalizes_low_liquidity():
    cross = pd.DataFrame({
        "ticker": ["a", "b", "c"],
        "factor:test": [3.0, 2.0, 1.0],
        "amount": [1_000_000.0, 500_000.0, 100_000.0],
    })
    holdings, meta = build_liquidity_aware_holdings(cross, "factor:test", 3)
    assert round(sum(holdings.values()), 6) == 1.0
    assert holdings["a"] > holdings["c"]
    assert meta["buckets"]["low"] >= 1


def test_build_equal_holdings_equal_weights():
    cross = pd.DataFrame({
        "ticker": ["a", "b", "c"],
        "factor:test": [3.0, 2.0, 1.0],
    })
    holdings = build_equal_holdings(cross, "factor:test", 3)
    assert holdings == {"a": 1/3, "b": 1/3, "c": 1/3}
