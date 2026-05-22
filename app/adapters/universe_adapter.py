from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.config.settings import get_settings


def _reference_path(name: str) -> Path:
    settings = get_settings()
    base = settings.data_dir / 'raw' / 'reference'
    reports = settings.reports_dir
    mapping = {
        'main_board': base / 'stock_basic_main_board.parquet',
        'stock_basic_main_board': base / 'stock_basic_main_board.parquet',
        '主板': base / 'stock_basic_main_board.parquet',
        'hs300': base / 'hs300.parquet',
        'zz500': base / 'zz500.parquet',
        'expanded_main_board_1000': base / 'stock_basic_main_board.parquet',
    }
    # 预定义的筛选池文件
    filtered_universe_names = {
        'growth_amount_bottom_50pct',
        'filtered_universe_growth_amount_bottom_50pct',
        'growth_amount_bottom_30pct',
        'filtered_universe_growth_amount_bottom_30pct',
        'growth_amount_bottom_20pct',
        'filtered_universe_growth_amount_bottom_20pct',
    }
    if name in filtered_universe_names:
        return reports / f'filtered_universe_growth_amount_bottom_{name.split("_bottom_")[1].replace("pct", "pct")}_latest.json'
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
