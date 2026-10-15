from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from importlib import import_module, util
from typing import Any

import numpy as np
import pandas as pd

from app.schemas import MarketDataProvider, MarketDataRequest, PricePanel


class MarketDataError(RuntimeError):
    """A provider could not return a usable, aligned price history."""


class ProviderNotInstalled(MarketDataError):
    """The optional Python package required by a provider is unavailable."""


def panel_to_frames(panel: PricePanel) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    index = pd.DatetimeIndex(pd.to_datetime(panel.dates), name="date")
    prices = pd.DataFrame(panel.prices, index=index, dtype=float)
    volumes = (
        pd.DataFrame(panel.volumes, index=index, dtype=float) if panel.volumes is not None else None
    )
    return prices, volumes


def get_provider_status() -> list[dict[str, Any]]:
    """Report package availability without starting a network or terminal session."""
    return [
        {
            "id": MarketDataProvider.YFINANCE.value,
            "label": "Yahoo Finance",
            "available": _module_available("yfinance"),
            "note": "Histórico diario; disponibilidad y límites dependen de Yahoo Finance.",
        },
        {
            "id": MarketDataProvider.METATRADER5.value,
            "label": "MetaTrader 5",
            "available": _module_available("MetaTrader5"),
            "note": "Requiere el terminal instalado y una cuenta conectada al bróker.",
        },
    ]


def download_market_data(request: MarketDataRequest) -> PricePanel:
    if request.provider == MarketDataProvider.YFINANCE:
        prices, volumes = _download_yfinance(request)
    else:
        prices, volumes = _download_metatrader(request)
    return _build_panel(prices, volumes)


def _module_available(module_name: str) -> bool:
    try:
        return util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _download_yfinance(request: MarketDataRequest) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    try:
        yf = import_module("yfinance")
    except (ImportError, OSError) as exc:
        raise ProviderNotInstalled(
            "Yahoo Finance requiere yfinance. En la carpeta quant_portfolio_app ejecuta "
            "`uv sync --extra dev`."
        ) from exc

    price_series: dict[str, pd.Series] = {}
    volume_series: dict[str, pd.Series] = {}
    failures: list[str] = []
    end_exclusive = request.end_date + timedelta(days=1)

    for symbol in request.symbols:
        try:
            history = yf.Ticker(symbol).history(
                start=request.start_date.isoformat(),
                end=end_exclusive.isoformat(),
                interval="1d",
                auto_adjust=True,
                actions=False,
                timeout=25,
            )
        except Exception as exc:  # noqa: BLE001 - provider exceptions vary by transport/version.
            failures.append(f"{symbol}: {exc}")
            continue

        if history is None or history.empty or "Close" not in history.columns:
            failures.append(f"{symbol}: no se recibió histórico para el rango seleccionado")
            continue

        frame = _normalize_index(history)
        close = pd.to_numeric(frame["Close"], errors="coerce")
        volume = (
            pd.to_numeric(frame["Volume"], errors="coerce")
            if "Volume" in frame.columns
            else pd.Series(0.0, index=frame.index)
        )
        price_series[symbol] = close
        volume_series[symbol] = volume

    if failures:
        raise MarketDataError("No se pudo completar la descarga: " + "; ".join(failures))
    return price_series, volume_series


def _download_metatrader(
    request: MarketDataRequest,
) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    try:
        mt5 = import_module("MetaTrader5")
    except (ImportError, OSError) as exc:
        raise ProviderNotInstalled(
            "MetaTrader 5 requiere el paquete MetaTrader5. En Windows ejecuta "
            "`uv sync --extra dev`; después abre el terminal e inicia sesión en tu bróker."
        ) from exc

    try:
        initialized = mt5.initialize()
    except Exception as exc:
        raise MarketDataError(f"No se pudo inicializar MetaTrader 5: {exc}") from exc
    if not initialized:
        raise MarketDataError(
            f"No se pudo conectar con MetaTrader 5: {mt5.last_error()}. "
            "Abre el terminal y verifica que la cuenta esté conectada."
        )

    price_series: dict[str, pd.Series] = {}
    volume_series: dict[str, pd.Series] = {}
    failures: list[str] = []
    start_utc = datetime.combine(request.start_date, time.min, tzinfo=UTC)
    end_utc = datetime.combine(request.end_date, time.max, tzinfo=UTC)

    try:
        for symbol in request.symbols:
            if not mt5.symbol_select(symbol, True):
                failures.append(f"{symbol}: el símbolo no está disponible en el bróker")
                continue
            rates = mt5.copy_rates_range(
                symbol,
                mt5.TIMEFRAME_D1,
                start_utc,
                end_utc,
            )
            if rates is None or len(rates) == 0:
                failures.append(f"{symbol}: el terminal no tiene barras diarias en ese rango")
                continue
            frame = pd.DataFrame(rates)
            frame.index = pd.DatetimeIndex(
                pd.to_datetime(frame.pop("time"), unit="s", utc=True)
            ).tz_convert(None)
            price_series[symbol] = pd.to_numeric(frame["close"], errors="coerce")
            # Tick volume is the most consistently populated activity measure across MT5 brokers.
            volume_series[symbol] = pd.to_numeric(frame["tick_volume"], errors="coerce")
    finally:
        mt5.shutdown()

    if failures:
        raise MarketDataError("No se pudo completar la descarga: " + "; ".join(failures))
    return price_series, volume_series


def _normalize_index(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    index = pd.DatetimeIndex(pd.to_datetime(normalized.index))
    if index.tz is not None:
        index = index.tz_localize(None)
    normalized.index = index.normalize()
    return normalized[~normalized.index.duplicated(keep="last")].sort_index()


def _build_panel(
    price_series: dict[str, pd.Series],
    volume_series: dict[str, pd.Series],
) -> PricePanel:
    if len(price_series) < 2:
        raise MarketDataError("Se requieren al menos dos activos con histórico válido.")

    prices = pd.concat(price_series, axis=1, join="inner").sort_index()
    prices = prices.replace([np.inf, -np.inf], np.nan)
    prices = prices.where(prices > 0).dropna(how="any")
    if prices.shape[1] < 2:
        raise MarketDataError("Los activos no tienen precios positivos en fechas comunes.")
    if len(prices) < 2:
        raise MarketDataError(
            "Los activos deben compartir al menos dos fechas. Revisa símbolos y periodo."
        )
    if len(prices) > 5_000:
        raise MarketDataError("El rango supera las 5.000 observaciones admitidas por la aplicación.")

    volumes = pd.concat(volume_series, axis=1, join="outer").reindex(prices.index)
    volumes = volumes.replace([np.inf, -np.inf], np.nan).fillna(0).clip(lower=0)
    # A valid panel must have identical asset keys in prices and volumes.
    volumes = volumes.reindex(columns=prices.columns, fill_value=0)

    return PricePanel(
        dates=[timestamp.date() for timestamp in prices.index],
        prices={symbol: prices[symbol].astype(float).tolist() for symbol in prices.columns},
        volumes={symbol: volumes[symbol].astype(float).tolist() for symbol in prices.columns},
    )
