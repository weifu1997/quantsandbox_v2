from __future__ import annotations

import pandas as pd

from app.domain.data_contracts import attach_listing_days


def test_attach_listing_days_preserves_reference_name_column(tmp_path) -> None:
    dataset = pd.DataFrame(
        [
            {"date": "2024-01-02", "ticker": "sh600009", "open": 1.0},
        ]
    )
    reference = tmp_path / "stock_basic_main_board.parquet"
    ref_df = pd.DataFrame(
        [
            {"ticker": "sh600009", "list_date": "2020-01-01", "name": "上海机场"},
        ]
    )
    ref_df.to_parquet(reference, index=False)

    merged, info = attach_listing_days(dataset, reference)

    assert info["listing_days_attached"] == 1
    assert "name" in merged.columns
    assert merged.loc[0, "name"] == "上海机场"
