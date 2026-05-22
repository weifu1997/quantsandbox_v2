from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from app.adapters.fundamental_data_adapter import TushareFundamentalDataAdapter
from app.config.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description='Backfill quality/growth fields into existing fundamental parquet partitions')
    parser.add_argument('--tickers', nargs='*', default=[])
    parser.add_argument('--tickers-file', default='')
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    fundamental_dir = Path(settings.fundamental_data_dir or settings.data_dir / 'raw' / 'fundamentals')
    if args.tickers:
        tickers = args.tickers
    elif args.tickers_file:
        p = Path(args.tickers_file)
        if p.suffix.lower() == '.json':
            import json
            tickers = json.loads(p.read_text(encoding='utf-8'))
        else:
            tickers = p.read_text(encoding='utf-8').split()
    else:
        tickers = [p.stem for p in sorted(fundamental_dir.glob('*.parquet'))]
    if args.limit and args.limit > 0:
        tickers = tickers[:args.limit]

    adapter = TushareFundamentalDataAdapter()
    updated = 0
    skipped = 0
    for idx, ticker in enumerate(tickers, start=1):
        path = fundamental_dir / f'{ticker}.parquet'
        if not path.exists():
            skipped += 1
            continue
        local_df = pd.read_parquet(path)
        try:
            fi_df = adapter._fetch_fina_indicator(ticker, args.start_date, args.end_date)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            print(f'[warn] {ticker} fina_indicator failed: {exc}', flush=True)
            skipped += 1
            continue
        if fi_df.empty:
            print(f'[warn] {ticker} fina_indicator empty', flush=True)
            skipped += 1
            continue
        local_df['date'] = pd.to_datetime(local_df['date'])
        merged = pd.merge_asof(
            local_df.sort_values('date'),
            fi_df.sort_values('date'),
            on='date',
            direction='backward',
            suffixes=('', '_new'),
        )
        for col in ['roe', 'roa', 'gross_margin', 'revenue_growth', 'profit_growth']:
            if col in merged.columns:
                continue
            new_col = f'{col}_new'
            if new_col in merged.columns:
                merged[col] = merged[new_col]
        for col in ['roa', 'gross_margin', 'revenue_growth', 'profit_growth']:
            new_col = f'{col}_new'
            if new_col in merged.columns:
                merged[col] = merged[new_col]
        drop_cols = [c for c in merged.columns if c.endswith('_new')]
        merged = merged.drop(columns=drop_cols, errors='ignore')
        merged.to_parquet(path, index=False)
        updated += 1
        if idx == 1 or idx % 25 == 0 or idx == len(tickers):
            print(f'[done] {idx}/{len(tickers)} {ticker}', flush=True)

    print({'updated': updated, 'skipped': skipped, 'total': len(tickers)})


if __name__ == '__main__':
    main()
