from __future__ import annotations

import json
from pathlib import Path

from scripts.run_pbindlow_candidate_review import load_tickers_from_file as load_value_tickers_from_file
from scripts.run_revgrowth_candidate_review import load_tickers_from_file as load_growth_tickers_from_file


def test_load_tickers_from_filtered_universe_payload(tmp_path: Path):
    path = tmp_path / "filtered.json"
    path.write_text(json.dumps({"filtered_universe": {"tickers": ["a", "b", "c"]}}), encoding="utf-8")
    assert load_value_tickers_from_file(str(path)) == ["a", "b", "c"]
    assert load_growth_tickers_from_file(str(path)) == ["a", "b", "c"]


def test_load_tickers_from_plain_list(tmp_path: Path):
    path = tmp_path / "plain.json"
    path.write_text(json.dumps(["x", "y"]), encoding="utf-8")
    assert load_value_tickers_from_file(str(path)) == ["x", "y"]
    assert load_growth_tickers_from_file(str(path)) == ["x", "y"]
