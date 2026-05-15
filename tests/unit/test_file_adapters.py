import pandas as pd

from app.adapters.fundamental_data_adapter import FileFundamentalDataAdapter, build_fundamental_data_adapter
from app.adapters.market_data_adapter import FileMarketDataAdapter, build_market_data_adapter


def test_file_market_data_adapter(tmp_path) -> None:
    path = tmp_path / "market_data.parquet"
    df = pd.DataFrame(
        [
            {"date": "2024-01-02", "ticker": "sh600519", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000, "amount": 10500},
            {"date": "2024-01-03", "ticker": "sh600519", "open": 10.5, "high": 11.2, "low": 10.2, "close": 11.0, "volume": 1200, "amount": 13200},
        ]
    )
    df.to_parquet(path, index=False)
    adapter = FileMarketDataAdapter(path)
    sample = adapter.fetch_daily_bars(["sh600519"], "2024-01-01", "2024-01-31")
    assert len(sample) == 2
    assert "amount" in sample.columns


def test_file_fundamental_data_adapter(tmp_path) -> None:
    path = tmp_path / "fundamentals.parquet"
    df = pd.DataFrame(
        [
            {"date": "2024-01-02", "ticker": "sh600519", "pe": 10.0, "pb": 1.5, "roe": 0.12},
            {"date": "2024-01-03", "ticker": "sh600519", "pe": 10.2, "pb": 1.5, "roe": 0.12},
        ]
    )
    df.to_parquet(path, index=False)
    adapter = FileFundamentalDataAdapter(path)
    sample = adapter.fetch_fundamentals(["sh600519"], "2024-01-01", "2024-01-31")
    assert len(sample) == 2
    assert "pe" in sample.columns


def test_build_adapters_default_to_memory() -> None:
    assert build_market_data_adapter().__class__.__name__ == "InMemoryMarketDataAdapter"
    assert build_fundamental_data_adapter().__class__.__name__ == "InMemoryFundamentalDataAdapter"
