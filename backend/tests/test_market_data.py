from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from app.schemas import MarketDataProvider, MarketDataRequest
from app.services.market_data import download_market_data


def _request(provider: MarketDataProvider) -> MarketDataRequest:
    return MarketDataRequest(
        provider=provider,
        symbols=["AAA", "BBB"],
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
    )


def test_yfinance_download_adjusts_prices_and_intersects_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    histories = {
        "AAA": pd.DataFrame(
            {"Close": [10.0, 11.0, 12.0], "Volume": [100, 110, 120]},
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        ),
        "BBB": pd.DataFrame(
            {"Close": [20.0, 22.0], "Volume": [200, 220]},
            index=pd.to_datetime(["2024-01-02", "2024-01-04"]),
        ),
    }
    calls: list[tuple[str, dict]] = []

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, **kwargs: object) -> pd.DataFrame:
            calls.append((self.symbol, kwargs))
            return histories[self.symbol]

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=FakeTicker))

    panel = download_market_data(_request(MarketDataProvider.YFINANCE))

    assert panel.dates == [date(2024, 1, 2), date(2024, 1, 4)]
    assert panel.prices == {"AAA": [10.0, 12.0], "BBB": [20.0, 22.0]}
    assert panel.volumes == {"AAA": [100.0, 120.0], "BBB": [200.0, 220.0]}
    assert all(call[1]["auto_adjust"] is True for call in calls)
    assert all(call[1]["end"] == "2024-01-05" for call in calls)


def test_metatrader_download_uses_daily_bars_and_shuts_terminal_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = [
        int(pd.Timestamp(day, tz="UTC").timestamp())
        for day in ("2024-01-02", "2024-01-03")
    ]
    rates = np.array(
        [(times[0], 10.0, 11.0, 9.0, 10.5, 100, 1, 0), (times[1], 10.5, 12.0, 10.0, 11.5, 110, 1, 0)],
        dtype=[
            ("time", "i8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
            ("tick_volume", "i8"),
            ("spread", "i8"),
            ("real_volume", "i8"),
        ],
    )
    shutdown_calls: list[bool] = []
    mt5 = SimpleNamespace(
        TIMEFRAME_D1=16408,
        initialize=lambda: True,
        symbol_select=lambda symbol, selected: True,
        copy_rates_range=lambda symbol, timeframe, start, end: rates,
        shutdown=lambda: shutdown_calls.append(True),
        last_error=lambda: (0, "ok"),
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", mt5)

    panel = download_market_data(_request(MarketDataProvider.METATRADER5))

    assert panel.prices["AAA"] == [10.5, 11.5]
    assert panel.volumes["BBB"] == [100.0, 110.0]
    assert panel.dates == [date(2024, 1, 2), date(2024, 1, 3)]
    assert len(shutdown_calls) == 1


def test_market_data_request_rejects_duplicate_symbols_and_reversed_dates() -> None:
    with pytest.raises(ValueError, match="No repitas símbolos"):
        MarketDataRequest(
            provider="yfinance",
            symbols=[" spy ", "SPY"],
            start_date="2024-01-01",
            end_date="2024-02-01",
        )

    with pytest.raises(ValueError, match="fecha inicial"):
        MarketDataRequest(
            provider="yfinance",
            symbols=["SPY", "QQQ"],
            start_date="2024-02-01",
            end_date="2024-01-01",
        )
