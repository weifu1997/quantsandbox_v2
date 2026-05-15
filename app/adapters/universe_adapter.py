from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.config.settings import get_settings


def _reference_path(name: str) -> Path:
    settings = get_settings()
    base = settings.data_dir / 'raw' / 'reference'
    mapping = {
        'main_board': base / 'stock_basic_main_board.parquet',
        'stock_basic_main_board': base / 'stock_basic_main_board.parquet',
        '主板': base / 'stock_basic_main_board.parquet',
    }
    if name not in mapping:
        raise ValueError(f'unknown universe: {name}')
    return mapping[name]


def resolve_universe(name: str, asof_date: str | None = None) -> list[str]:
    path = _reference_path(name)
    if not path.exists():
        raise FileNotFoundError(f'universe reference file not found: {path}')
    df = pd.read_parquet(path)
    if asof_date:
        cutoff = pd.to_datetime(asof_date)
        if 'list_date' in df.columns:
            listed = pd.to_datetime(df['list_date'], errors='coerce')
            df = df.loc[(listed.isna()) | (listed <= cutoff)].copy()
    if 'ticker' not in df.columns:
        raise ValueError(f'universe reference file missing ticker column: {path}')
    return sorted(df['ticker'].dropna().astype(str).unique().tolist())
