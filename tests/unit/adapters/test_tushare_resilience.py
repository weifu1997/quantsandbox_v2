import logging
import time

import pandas as pd
import pytest

from app.adapters.fundamental_data_adapter import TushareFundamentalDataAdapter
from app.adapters.market_data_adapter import TushareMarketDataAdapter, _classify_retry_reason as market_classify_retry_reason, _retry_backoff_seconds as market_retry_backoff_seconds
from app.services.dataset_service import build_research_dataset
from app.utils.rate_limit import TushareRateLimiter


class SlowBatchPro:
    def __init__(self):
        self.calls = []

    def daily(self, ts_code: str, start_date: str, end_date: str):
        self.calls.append(ts_code)
        if "," in ts_code:
            raise RuntimeError("batch endpoint unavailable")
        return pd.DataFrame(
            [{
                "ts_code": ts_code,
                "trade_date": "20240102",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "vol": 1000,
                "amount": 10500,
            }]
        )


class StubFundPro:
    def daily_basic(self, ts_code: str, start_date: str, end_date: str, fields: str):
        return pd.DataFrame(
            [{
                "ts_code": ts_code,
                "trade_date": "20240102",
                "pe": 10.0,
                "pb": 1.5,
            }]
        )


def test_tushare_market_adapter_fallbacks_to_single_ticker_on_batch_failure(monkeypatch) -> None:
    adapter = TushareMarketDataAdapter.__new__(TushareMarketDataAdapter)
    adapter.pro = SlowBatchPro()
    adapter.log = logging.getLogger("test")
    adapter.warnings = []
    adapter.rate_limiter = None
    adapter._symbol_to_ts = TushareMarketDataAdapter._symbol_to_ts
    adapter._symbol_from_ts = TushareMarketDataAdapter._symbol_from_ts

    def fake_call(fn, label, retries=2, timeout_seconds=20.0, rate_kind="market", **kwargs):
        return fn(**kwargs)

    adapter._call_with_retry = fake_call
    df = adapter.fetch_daily_bars(["sh600519", "sz000858"], "20240101", "20240110")
    assert len(df) == 2
    assert adapter.warnings


def test_tushare_fundamental_adapter_partial_success(monkeypatch) -> None:
    adapter = TushareFundamentalDataAdapter.__new__(TushareFundamentalDataAdapter)
    adapter.log = logging.getLogger("test")
    adapter.warnings = []
    adapter.rate_limiter = None
    adapter._symbol_to_ts = TushareFundamentalDataAdapter._symbol_to_ts

    class Pro:
        def daily_basic(self, ts_code: str, start_date: str, end_date: str, fields: str):
            if ts_code.startswith("600519"):
                raise RuntimeError("boom")
            return pd.DataFrame([{"ts_code": ts_code, "trade_date": "20240102", "pe": 10.0, "pb": 1.5}])

    adapter.pro = Pro()
    adapter._call_with_retry = lambda fn, label, retries=2, timeout_seconds=20.0, rate_kind="fundamental", **kwargs: fn(**kwargs)
    df = adapter.fetch_fundamentals(["sh600519", "sz000858"], "20240101", "20240110")
    assert len(df) == 1
    assert adapter.warnings


def test_dataset_summary_contains_provider_warnings() -> None:
    class Market:
        warnings = ["daily failed for sh600519: timeout"]
        def fetch_daily_bars(self, tickers, start_date, end_date):
            return pd.DataFrame([
                {"date": "2024-01-02", "ticker": "sz000858", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000, "amount": 10500},
                {"date": "2024-01-03", "ticker": "sz000858", "open": 10.5, "high": 11.2, "low": 10.2, "close": 11.0, "volume": 1200, "amount": 13200},
            ])
    class Fundamental:
        warnings = ["daily_basic failed for sh600519: timeout"]
        def fetch_fundamentals(self, tickers, start_date, end_date):
            return pd.DataFrame([
                {"date": "2024-01-02", "ticker": "sz000858", "pe": 10.0, "pb": 1.5, "roe": None},
                {"date": "2024-01-03", "ticker": "sz000858", "pe": 10.2, "pb": 1.5, "roe": None},
            ])

    _, summary, _ = build_research_dataset(
        tickers=["sh600519", "sz000858"],
        start_date="20240101",
        end_date="20240110",
        factor_names=["pe"],
        horizons=[5],
        market_adapter=Market(),
        fundamental_adapter=Fundamental(),
        experiment_id="exp_warn_test",
    )
    assert summary["warnings"]


def test_rate_limiter_by_phase() -> None:
    slept = []
    current = {'t': 0.0}

    def fake_sleep(seconds: float):
        slept.append(seconds)
        current['t'] += seconds

    def fake_monotonic():
        return current['t']

    limiter = TushareRateLimiter(
        market_rpm=120.0,
        fundamental_rpm=60.0,
        retry_rpm=30.0,
        sleeper=fake_sleep,
        monotonic=fake_monotonic,
    )

    limiter.acquire('market')
    limiter.acquire('market')
    limiter.acquire('fundamental')
    limiter.acquire('fundamental')
    limiter.acquire('retry')
    limiter.acquire('retry')

    assert slept == [0.5, 1.0, 2.0]


def test_retry_reason_and_backoff_classification() -> None:
    assert market_classify_retry_reason(TimeoutError('timeout after 20s')) == 'timeout'
    assert market_classify_retry_reason(RuntimeError('429 too many requests')) == 'rate_limit'
    assert market_classify_retry_reason(RuntimeError('empty dataset')) == 'empty'
    assert market_classify_retry_reason(RuntimeError('boom')) == 'error'

    assert market_retry_backoff_seconds('timeout', 1) == 1.5
    assert market_retry_backoff_seconds('timeout', 2) == 3.0
    assert market_retry_backoff_seconds('rate_limit', 1) == 3.0
    assert market_retry_backoff_seconds('error', 2) == 2.4


def test_market_retry_stats_and_structured_warning(monkeypatch) -> None:
    adapter = TushareMarketDataAdapter.__new__(TushareMarketDataAdapter)
    adapter.log = logging.getLogger('test')
    adapter.warnings = []
    adapter.retry_stats = {'attempts': 0, 'timeouts': 0, 'rate_limits': 0, 'empties': 0, 'errors': 0}

    class DummyLimiter:
        def acquire(self, phase: str) -> None:
            return None

    adapter.rate_limiter = DummyLimiter()

    monkeypatch.setattr(time, 'sleep', lambda seconds: None)

    def always_fail(**kwargs):
        raise RuntimeError('429 too many requests')

    with pytest.raises(RuntimeError):
        adapter._call_with_retry(always_fail, label='tushare.daily(test)', retries=1)

    assert adapter.retry_stats['attempts'] == 2
    assert adapter.retry_stats['rate_limits'] == 2
    assert any('retry_warning|' in w and 'reason=rate_limit' in w for w in adapter.warnings)
