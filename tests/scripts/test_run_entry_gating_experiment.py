from __future__ import annotations

import pandas as pd

from scripts.run_entry_gating_experiment import build_equal_holdings, build_gated_equal_holdings, classify_low_bucket


def test_classify_low_bucket_marks_tail():
    cross = pd.DataFrame({"ticker": ["a", "b", "c", "d"], "amount": [10, 20, 30, 40]})
    out = classify_low_bucket(cross)
    assert "low" in set(out["liq_bucket"])


def test_build_gated_equal_holdings_limits_low_slots():
    cross = pd.DataFrame({
        "ticker": ["a", "b", "c", "d"],
        "factor:test": [4.0, 3.0, 2.0, 1.0],
        "amount": [10.0, 20.0, 100.0, 200.0],
    })
    holdings, meta = build_gated_equal_holdings(cross, "factor:test", 4, 1)
    assert round(sum(holdings.values()), 6) == 1.0
    assert meta["low_liquidity_slots_used"] <= 1


def test_build_equal_holdings_stays_equal():
    cross = pd.DataFrame({"ticker": ["a", "b"], "factor:test": [2.0, 1.0], "amount": [10, 20]})
    holdings = build_equal_holdings(cross, "factor:test", 2)
    assert holdings == {"a": 0.5, "b": 0.5}
