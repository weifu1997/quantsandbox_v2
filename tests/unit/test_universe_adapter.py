from app.adapters.universe_adapter import resolve_universe


def test_resolve_universe_main_board() -> None:
    tickers = resolve_universe('main_board', asof_date='20240430')
    assert len(tickers) > 1000
    assert 'sh600519' in tickers or 'sz000001' in tickers
