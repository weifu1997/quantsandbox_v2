from __future__ import annotations

import pandas as pd


def select_rebalance_dates(
    dates: list[pd.Timestamp],
    frequency: str,
) -> list[pd.Timestamp]:
    unique = sorted(pd.to_datetime(pd.Series(dates)).drop_duplicates().tolist())
    if str(frequency).upper() == "D":
        return unique
    if str(frequency).upper() == "W":
        picked = []
        current_week = None
        for dt in unique:
            year_week = (dt.isocalendar().year, dt.isocalendar().week)
            if year_week != current_week:
                picked.append(dt)
                current_week = year_week
        return picked
    if str(frequency).upper() == "M":
        picked = []
        current_month = None
        for dt in unique:
            ym = (dt.year, dt.month)
            if ym != current_month:
                picked.append(dt)
                current_month = ym
        return picked
    return unique
