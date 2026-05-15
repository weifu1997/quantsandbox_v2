#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import tushare as ts

from app.config.settings import get_settings


def ts_to_ticker(ts_code: str) -> str:
    value = str(ts_code).upper()
    if value.endswith('.SH'):
        return f"sh{value[:-3].lower()}"
    if value.endswith('.SZ'):
        return f"sz{value[:-3].lower()}"
    return value.lower()


def collect_stock_basic(market: str = '主板', list_status: str = 'L') -> tuple[pd.DataFrame, dict]:
    settings = get_settings()
    if not settings.tushare_token:
        raise RuntimeError('QS_TUSHARE_TOKEN is required')

    ts.set_token(settings.tushare_token)
    pro = ts.pro_api()
    if settings.tushare_http_url:
        pro._DataApi__http_url = settings.tushare_http_url

    df = pro.stock_basic(
        exchange='',
        market=market,
        list_status=list_status,
        fields='ts_code,symbol,name,area,industry,market,list_status,list_date,delist_date'
    )
    if df is None or df.empty:
        return pd.DataFrame(), {'rows': 0, 'market': market, 'list_status': list_status}

    df = df.copy()
    df['ticker'] = df['ts_code'].apply(ts_to_ticker)
    df['updated_at'] = datetime.now(UTC).isoformat()
    summary = {
        'rows': int(len(df)),
        'market': market,
        'list_status': list_status,
        'ticker_count': int(df['ticker'].nunique()),
    }
    return df, summary


def main() -> None:
    parser = argparse.ArgumentParser(description='Collect stock_basic reference table from Tushare')
    parser.add_argument('--market', default='主板')
    parser.add_argument('--list-status', default='L')
    parser.add_argument('--output', default='')
    args = parser.parse_args()

    settings = get_settings()
    output = Path(args.output) if args.output else settings.data_dir / 'raw' / 'reference' / 'stock_basic_main_board.parquet'
    output.parent.mkdir(parents=True, exist_ok=True)

    df, summary = collect_stock_basic(market=args.market, list_status=args.list_status)
    if df.empty:
        raise SystemExit('stock_basic returned empty result')

    if output.suffix.lower() == '.csv':
        df.to_csv(output, index=False)
    else:
        df.to_parquet(output, index=False)

    manifest = output.with_suffix('.json')
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps({
        'output': str(output),
        'summary_path': str(manifest),
        'summary': summary,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
