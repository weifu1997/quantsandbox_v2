from app.reports.json_report import render_json_report


def test_json_report_contains_warnings_and_diagnostics() -> None:
    payload = render_json_report(
        config={"factors": ["momentum_20d"]},
        dataset_summary={
            "rows": 100,
            "valid_sample_ratio": 0.4,
            "invalid_reasons": {"missing_future_return_20d": 10},
        },
        factor_results={
            "momentum_20d": {
                "full_sample": {
                    "20": {
                        "ic": {"rank_ic_mean": 0.01},
                        "group_returns": {"Q1": 0.03, "Q2": 0.02, "Q3": 0.01, "Q4": 0.0, "Q5": -0.01},
                        "monotonicity_score": 0.25,
                    }
                },
                "in_sample": {"20": {"ic": {"rank_ic_mean": 0.05}}},
                "out_sample": {"20": {"ic": {"rank_ic_mean": -0.01}}},
            }
        },
        backtest_results={"momentum_20d": {"total_return": 0.1}},
    )
    assert "warnings" in payload
    assert len(payload["warnings"]) >= 2
    assert "factor_diagnostics" in payload
    assert payload["factor_diagnostics"][0]["warnings"]
