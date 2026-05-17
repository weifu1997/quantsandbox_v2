import pandas as pd
import pytest

from app.domain.data_contracts import (
    REQUIRED_FUNDAMENTAL_COLUMNS,
    REQUIRED_PRICE_COLUMNS,
    add_sample_flags,
    attach_listing_days,
    factor_column,
    future_return_column,
    normalize_ticker,
    normalize_trade_date,
    validate_backtest_dataset,
    validate_fundamental_dataframe,
    validate_market_dataframe,
    validate_research_dataset,
)


def test_factor_and_future_return_column_helpers() -> None:
    assert factor_column('momentum_20d') == 'factor:momentum_20d'
    assert future_return_column(20) == 'future_return_20d'
    with pytest.raises(ValueError):
        factor_column('')
    with pytest.raises(ValueError):
        future_return_column(0)


def test_validate_market_and_fundamental_contracts() -> None:
    market = pd.DataFrame([{c: 1 for c in REQUIRED_PRICE_COLUMNS}])
    market['date'] = ['2024-01-02']
    market['ticker'] = ['sh600519']
    validate_market_dataframe(market)

    fundamentals = pd.DataFrame([{c: 1 for c in REQUIRED_FUNDAMENTAL_COLUMNS}])
    fundamentals['date'] = ['2024-01-02']
    fundamentals['ticker'] = ['sh600519']
    validate_fundamental_dataframe(fundamentals)

    with pytest.raises(ValueError, match='market dataframe missing columns'):
        validate_market_dataframe(market.drop(columns=['amount']))
    with pytest.raises(ValueError, match='fundamental dataframe missing columns'):
        validate_fundamental_dataframe(fundamentals.drop(columns=['roe']))


def test_validate_research_and_backtest_contracts() -> None:
    df = pd.DataFrame([
        {
            'date': '2024-01-02',
            'ticker': 'sh600519',
            'open': 10.0,
            'high': 11.0,
            'low': 9.0,
            'close': 10.5,
            'volume': 1000,
            'amount': 10500,
            'pe': 10.0,
            'pb': 1.5,
            'roe': 0.12,
            'roa': 0.08,
            'gross_margin': 0.35,
            'revenue_growth': 0.1,
            'profit_growth': 0.12,
            'listed_days': 800,
            'factor:momentum_20d': 0.03,
            'future_return_20d': 0.05,
            'is_valid_sample': True,
            'missing_reason': '',
        }
    ])
    validate_research_dataset(df, factor_names=['momentum_20d'], horizons=[20], require_sample_flags=True)
    validate_backtest_dataset(df, 'factor:momentum_20d', 'future_return_20d')

    with pytest.raises(ValueError, match='research dataset missing columns'):
        validate_research_dataset(df.drop(columns=['pe']), factor_names=['momentum_20d'], horizons=[20])
    with pytest.raises(ValueError, match='backtest dataset missing columns'):
        validate_backtest_dataset(df.drop(columns=['future_return_20d']), 'factor:momentum_20d', 'future_return_20d')


def test_add_sample_flags_applies_listed_days_filter() -> None:
    df = pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600519', 'future_return_20d': 0.1, 'listed_days': 90},
        {'date': '2024-01-03', 'ticker': 'sh600519', 'future_return_20d': 0.2, 'listed_days': 150},
    ])
    flagged = add_sample_flags(df, horizons=[20], min_days=1, min_listed_days=120)
    assert bool(flagged.loc[0, 'is_valid_sample']) is False
    assert flagged.loc[0, 'missing_reason'] == 'too_few_listed_days_min_120'
    assert bool(flagged.loc[1, 'is_valid_sample']) is True


def test_add_sample_flags_respects_configurable_listed_days_threshold() -> None:
    df = pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600519', 'future_return_20d': 0.1, 'listed_days': 90},
    ])
    flagged = add_sample_flags(df, horizons=[20], min_days=1, min_listed_days=60)
    assert bool(flagged.loc[0, 'is_valid_sample']) is True
    assert flagged.loc[0, 'missing_reason'] == ''


def test_attach_listing_days_from_reference(tmp_path) -> None:
    ref = tmp_path / 'stock_basic_main_board.parquet'
    pd.DataFrame([
        {'ticker': 'sh600519', 'list_date': '2001-08-27'},
        {'ticker': 'sz000858', 'list_date': '2001-01-01'},
    ]).to_parquet(ref, index=False)

    dataset = pd.DataFrame([
        {'date': '2024-01-02', 'ticker': 'sh600519', 'close': 10},
        {'date': '2024-01-02', 'ticker': 'sz000858', 'close': 20},
    ])
    attached, meta = attach_listing_days(dataset, ref)
    assert 'listed_days' in attached.columns
    assert attached['listed_days'].notna().all()
    assert meta['listing_days_attached'] == 2

def test_normalizers() -> None:
    assert normalize_ticker(' SH600519 ') == 'sh600519'
    assert normalize_trade_date('2024-01-02') == pd.Timestamp('2024-01-02')
