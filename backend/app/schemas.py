from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BacktestMethod(StrEnum):
    MOMENTUM = "momentum"
    LOW_BETA = "low_beta"
    SECTOR_ROTATION = "sector_rotation"
    CLUSTER_SELECTION = "cluster_selection"
    LIQUIDITY_MOMENTUM = "liquidity_momentum"


class OptimizerName(StrEnum):
    EQUAL = "equal"
    INVERSE_VOLATILITY = "inverse_volatility"
    MOMENTUM = "momentum"
    MINIMUM_VARIANCE = "minimum_variance"
    MAXIMUM_SHARPE = "maximum_sharpe"
    HRP = "hrp"
    RISK_PARITY = "risk_parity"


class FundamentalMethod(StrEnum):
    ALTMAN_PUBLIC = "altman_public"
    ALTMAN_PRIVATE = "altman_private"
    ALTMAN_NON_MANUFACTURING = "altman_non_manufacturing"
    PIOTROSKI = "piotroski"
    BENEISH = "beneish"
    FACTOR_SCREENING = "factor_screening"
    FAMA_FRENCH = "fama_french"


class MarketDataProvider(StrEnum):
    YFINANCE = "yfinance"
    METATRADER5 = "metatrader5"


class MarketDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: MarketDataProvider
    symbols: list[str] = Field(min_length=2, max_length=50)
    start_date: date
    end_date: date

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        normalized = [symbol.strip() for symbol in symbols]
        if any(not symbol for symbol in normalized):
            raise ValueError("Los símbolos no pueden estar vacíos.")
        if len({symbol.casefold() for symbol in normalized}) != len(normalized):
            raise ValueError("No repitas símbolos.")
        return normalized

    @model_validator(mode="after")
    def validate_date_range(self) -> MarketDataRequest:
        if self.start_date >= self.end_date:
            raise ValueError("La fecha inicial debe ser anterior a la fecha final.")
        return self


class PricePanel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dates: list[date] = Field(min_length=2, max_length=5_000)
    prices: dict[str, list[float]] = Field(min_length=2, max_length=100)
    volumes: dict[str, list[float]] | None = None

    @model_validator(mode="after")
    def validate_panel(self) -> PricePanel:
        if self.dates != sorted(self.dates) or len(set(self.dates)) != len(self.dates):
            raise ValueError("Las fechas deben ser únicas y estar ordenadas.")
        for name, columns in (("prices", self.prices), ("volumes", self.volumes)):
            if columns is None:
                continue
            if len(columns) < 1:
                raise ValueError(f"{name} no puede estar vacío.")
            for asset, values in columns.items():
                if not asset.strip():
                    raise ValueError("Los nombres de activos no pueden estar vacíos.")
                if len(values) != len(self.dates):
                    raise ValueError(f"{name}[{asset}] debe tener un valor por fecha.")
                if any(not math.isfinite(value) for value in values):
                    raise ValueError(f"{name}[{asset}] no puede contener NaN o infinito.")
                if any(value < 0 for value in values) and name == "volumes":
                    raise ValueError("Los volúmenes no pueden ser negativos.")
                if any(value <= 0 for value in values) and name == "prices":
                    raise ValueError("Los precios deben ser positivos.")
            if len(set(columns)) != len(columns):
                raise ValueError(f"Los activos de {name} deben ser únicos.")
        if self.volumes is not None and set(self.volumes) != set(self.prices):
            raise ValueError("Los activos de prices y volumes deben coincidir.")
        return self


class BacktestSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel: PricePanel
    benchmark_asset: str | None = None
    top_n: int = Field(default=5, ge=1, le=50)
    lookback_months: int = Field(default=12, ge=2, le=60)
    skip_months: int = Field(default=1, ge=0, le=59)
    transaction_cost_bps: float = Field(default=10.0, ge=0, lt=10_000, allow_inf_nan=False)
    initial_capital: float = Field(default=100_000.0, gt=0, allow_inf_nan=False)
    max_weight: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
    annualization: int = Field(default=252, ge=1, le=366)

    @model_validator(mode="after")
    def validate_settings(self) -> BacktestSettings:
        if self.skip_months >= self.lookback_months:
            raise ValueError("skip_months debe ser menor que lookback_months.")
        if self.benchmark_asset is not None and self.benchmark_asset not in self.panel.prices:
            raise ValueError("benchmark_asset debe existir en el panel de precios.")
        return self


class BacktestRunRequest(BacktestSettings):
    method: BacktestMethod = BacktestMethod.MOMENTUM
    optimizer: OptimizerName = OptimizerName.EQUAL


class BacktestCompareRequest(BacktestSettings):
    methods: list[BacktestMethod] = Field(min_length=1, max_length=5)
    optimizers: list[OptimizerName] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_combinations(self) -> BacktestCompareRequest:
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("No repitas métodos de selección.")
        if len(set(self.optimizers)) != len(self.optimizers):
            raise ValueError("No repitas métodos de asignación.")
        if len(self.methods) * len(self.optimizers) > 12:
            raise ValueError("La comparación admite como máximo 12 combinaciones.")
        return self


class FundamentalSelectionRequest(BaseModel):
    method: FundamentalMethod
    fundamentals: dict[str, dict[str, Any]] = Field(min_length=1, max_length=500)
    top_n: int = Field(default=20, ge=1, le=100)
    min_score: int = Field(default=7, ge=0, le=9)


class SyntheticDataResponse(PricePanel):
    description: str
