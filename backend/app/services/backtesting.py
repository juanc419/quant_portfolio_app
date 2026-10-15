from __future__ import annotations

import math
from typing import Any

import pandas as pd
from quant_core.analytics.risk import (
    annualized_sharpe,
    historical_cvar,
    historical_var,
    max_drawdown,
)
from quant_core.backtesting.engine import backtest_weights
from quant_core.optimization.hrp import HierarchicalRiskParity
from quant_core.optimization.mean_variance import MeanVarianceOptimizer
from quant_core.optimization.risk_parity import RiskParityOptimizer
from quant_core.strategies.base import Strategy, StrategyInput
from quant_core.strategies.beta import BetaInvestingConfig, BetaInvestingStrategy
from quant_core.strategies.clustering import ClusterSelectionConfig, ClusterSelectionStrategy
from quant_core.strategies.momentum.config import MomentumConfig
from quant_core.strategies.momentum.liquidity import (
    LiquidityMomentumConfig,
    LiquidityMomentumStrategy,
)
from quant_core.strategies.momentum.momentum import MomentumStrategy
from quant_core.strategies.momentum.weighting import (
    InverseVolatilityWeighting,
    MomentumWeighting,
)
from quant_core.strategies.sector_rotation import SectorRotationConfig, SectorRotationStrategy

from app.schemas import BacktestMethod, BacktestSettings, OptimizerName
from app.services.market_data import panel_to_frames


def run_backtest(
    settings: BacktestSettings,
    method: BacktestMethod,
    optimizer: OptimizerName,
) -> dict[str, Any]:
    all_prices, all_volumes = panel_to_frames(settings.panel)
    benchmark_prices = None
    if settings.benchmark_asset:
        benchmark_prices = all_prices[settings.benchmark_asset].rename("benchmark")
        tradable_prices = all_prices.drop(columns=settings.benchmark_asset)
        if all_volumes is not None:
            all_volumes = all_volumes.drop(columns=settings.benchmark_asset)
    else:
        tradable_prices = all_prices

    if tradable_prices.shape[1] < 2:
        raise ValueError("Se necesitan al menos dos activos invertibles, además del benchmark.")
    if method == BacktestMethod.LIQUIDITY_MOMENTUM and all_volumes is None:
        raise ValueError("La estrategia de momentum con liquidez requiere un panel de volúmenes.")

    asset_returns = tradable_prices.pct_change(fill_method=None)
    benchmark_returns = (
        benchmark_prices.pct_change(fill_method=None).rename("benchmark")
        if benchmark_prices is not None
        else None
    )
    lookback = settings.lookback_months * 21
    skip = settings.skip_months * 21
    strategy = _make_strategy(method, settings, lookback, skip, tradable_prices.shape[1])
    signal_dates = tradable_prices.groupby(tradable_prices.index.to_period("M")).tail(1).index
    target_rows: list[pd.Series] = []

    for signal_date in signal_dates:
        history_prices = tradable_prices.loc[:signal_date]
        if len(history_prices) <= lookback:
            continue
        history_returns = asset_returns.loc[:signal_date].tail(lookback)
        inputs = StrategyInput(
            prices=history_prices,
            volumes=all_volumes.loc[:signal_date] if all_volumes is not None else None,
            benchmark_returns=(
                benchmark_returns.loc[:signal_date] if benchmark_returns is not None else None
            ),
            as_of=signal_date,
        )
        signal = strategy.generate(inputs)
        selected = signal.signals.index[signal.signals["selected"]]
        if selected.empty:
            continue
        weights = _allocate(
            selected=selected,
            signal=signal,
            optimizer=optimizer,
            historical_returns=history_returns,
            settings=settings,
        )
        target = pd.Series(0.0, index=tradable_prices.columns, name=signal_date)
        target.loc[weights.index] = weights
        target_rows.append(target)

    if not target_rows:
        raise ValueError(
            "No se generaron rebalanceos. Revisa la longitud del histórico y los parámetros de señal."
        )

    targets = pd.DataFrame(target_rows)
    simulation = backtest_weights(
        asset_returns,
        targets,
        initial_capital=settings.initial_capital,
        transaction_cost_bps=settings.transaction_cost_bps,
        execution_lag=1,
    )
    net_returns = simulation.net_returns
    metrics: dict[str, float | int | None] = {
        "total_return": _finite(float(simulation.equity.iloc[-1] / settings.initial_capital - 1)),
        "cagr": _cagr(net_returns, settings.annualization),
        "annualized_volatility": _finite(
            float(net_returns.std(ddof=1) * math.sqrt(settings.annualization))
        ),
        "sharpe_ratio": _finite(
            annualized_sharpe(net_returns, annualization=settings.annualization)
        ),
        "max_drawdown": _finite(max_drawdown(net_returns)),
        "historical_var_95": _finite(historical_var(net_returns, confidence=0.95)),
        "historical_cvar_95": _finite(historical_cvar(net_returns, confidence=0.95)),
        "annual_turnover": _finite(float(simulation.turnover.mean() * settings.annualization)),
        "rebalances": len(targets),
    }

    benchmark_equity = None
    if benchmark_returns is not None:
        aligned = benchmark_returns.reindex(simulation.equity.index).fillna(0.0)
        benchmark_equity = (1.0 + aligned).cumprod() * settings.initial_capital

    latest = targets.iloc[-1]
    latest_holdings = [
        {"asset": asset, "weight": float(weight)}
        for asset, weight in latest[latest > 1e-12].sort_values(ascending=False).items()
    ]
    dates = simulation.equity.index.strftime("%Y-%m-%d").tolist()
    return {
        "method": method.value,
        "optimizer": optimizer.value,
        "label": f"{_method_label(method, settings)} · {_OPTIMIZER_LABELS[optimizer]}",
        "metrics": metrics,
        "latest_signal_date": targets.index[-1].strftime("%Y-%m-%d"),
        "latest_holdings": latest_holdings,
        "series": {
            "dates": dates,
            "equity": _safe_series(simulation.equity),
            "drawdown": _safe_series(simulation.drawdown),
            "benchmark_equity": _safe_series(benchmark_equity)
            if benchmark_equity is not None
            else None,
        },
    }


def _make_strategy(
    method: BacktestMethod,
    settings: BacktestSettings,
    lookback: int,
    skip: int,
    asset_count: int,
) -> Strategy:
    if method == BacktestMethod.MOMENTUM:
        return MomentumStrategy(
            MomentumConfig(
                lookback_months=settings.lookback_months,
                skip_months=settings.skip_months,
                top_n=settings.top_n,
                positive_momentum_only=True,
                weighting_method="equal",
            )
        )
    if method == BacktestMethod.LOW_BETA:
        return BetaInvestingStrategy(
            BetaInvestingConfig(
                top_n=settings.top_n,
                lookback=lookback,
                min_observations=max(2, min(60, lookback)),
                benchmark_column=None,
            )
        )
    if method == BacktestMethod.SECTOR_ROTATION:
        return SectorRotationStrategy(
            SectorRotationConfig(top_n=settings.top_n, lookback=lookback, skip_period=skip)
        )
    if method == BacktestMethod.CLUSTER_SELECTION:
        return ClusterSelectionStrategy(
            ClusterSelectionConfig(
                top_n=settings.top_n,
                lookback=lookback,
                skip_period=skip,
                cluster_count=min(10, asset_count),
                max_per_cluster=2,
                max_per_sector=2,
                min_observations=max(2, min(126, lookback)),
                selection_rule="capped_cluster",
                cluster_method="average",
            )
        )
    if method == BacktestMethod.LIQUIDITY_MOMENTUM:
        momentum_config = MomentumConfig(
            lookback_months=settings.lookback_months,
            skip_months=settings.skip_months,
            top_n=settings.top_n,
            positive_momentum_only=True,
            weighting_method="equal",
        )
        return LiquidityMomentumStrategy(
            LiquidityMomentumConfig(
                momentum=momentum_config,
                liquidity_window=max(2, min(63, lookback)),
            )
        )
    raise ValueError(f"Método de selección no soportado: {method}.")


def _allocate(
    *,
    selected: pd.Index,
    signal: Any,
    optimizer: OptimizerName,
    historical_returns: pd.DataFrame,
    settings: BacktestSettings,
) -> pd.Series:
    if len(selected) == 1 or optimizer == OptimizerName.EQUAL:
        return _enforce_cap(_equal(selected), settings.max_weight)
    window = historical_returns.reindex(columns=selected).dropna(how="any")
    if optimizer == OptimizerName.INVERSE_VOLATILITY:
        weights = (
            InverseVolatilityWeighting()
            .calculate(pd.Series(1.0, index=selected), window)
            .reindex(selected, fill_value=0.0)
        )
        return _enforce_cap(weights, settings.max_weight)
    if optimizer == OptimizerName.MOMENTUM:
        priority = pd.to_numeric(signal.signals["rank"].reindex(selected), errors="coerce")
        score = (float(len(selected)) + 1.0 - priority).fillna(1.0)
        weights = MomentumWeighting().calculate(score, window)
        return _enforce_cap(
            weights.reindex(selected, fill_value=0.0) if not weights.empty else _equal(selected),
            settings.max_weight,
        )
    if len(window) < 2:
        return _enforce_cap(_equal(selected), settings.max_weight)
    if optimizer in {OptimizerName.MINIMUM_VARIANCE, OptimizerName.MAXIMUM_SHARPE}:
        engine = MeanVarianceOptimizer(
            window,
            annualization=settings.annualization,
            max_weight=settings.max_weight,
            covariance_shrinkage=0.15,
        )
        result = (
            engine.minimum_variance()
            if optimizer == OptimizerName.MINIMUM_VARIANCE
            else engine.maximum_sharpe()
        )
        return _enforce_cap(result.weights.reindex(selected, fill_value=0.0), settings.max_weight)
    if optimizer == OptimizerName.HRP:
        weights = HierarchicalRiskParity(window, annualization=settings.annualization).weights()
        return _enforce_cap(weights.reindex(selected, fill_value=0.0), settings.max_weight)
    if optimizer == OptimizerName.RISK_PARITY:
        weights = RiskParityOptimizer(
            window,
            annualization=settings.annualization,
            max_weight=settings.max_weight,
        ).weights()
        return _enforce_cap(weights.reindex(selected, fill_value=0.0), settings.max_weight)
    raise ValueError(f"Método de asignación no soportado: {optimizer}.")


def _equal(assets: pd.Index) -> pd.Series:
    if len(assets) == 0:
        return pd.Series(dtype=float, index=assets, name="weight")
    return pd.Series(1.0 / len(assets), index=assets, name="weight")


def _enforce_cap(weights: pd.Series, max_weight: float) -> pd.Series:
    """Apply a long-only asset cap while redistributing residual capital fairly."""
    weights = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
    if weights.empty:
        return pd.Series(dtype=float, index=weights.index, name="weight")
    total = float(weights.sum())
    if total <= 0 or weights.empty:
        return _equal(weights.index)
    weights = weights / total
    capacity = min(1.0, max_weight * len(weights))
    remaining = min(1.0, capacity)
    capped = pd.Series(0.0, index=weights.index, dtype=float, name="weight")
    free = list(weights.index)
    priorities = weights.clip(lower=1e-12)
    while free and remaining > 1e-12:
        raw = priorities.loc[free]
        proposed = raw / raw.sum() * remaining
        breaches = proposed[proposed > max_weight + 1e-12]
        if breaches.empty:
            capped.loc[free] = proposed
            break
        for asset in breaches.index:
            capped.loc[asset] = max_weight
            remaining -= max_weight
            free.remove(asset)
    return capped


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


def _cagr(returns: pd.Series, annualization: int) -> float | None:
    growth = float((1.0 + returns).prod())
    if growth <= 0 or len(returns) == 0:
        return None
    return _finite(growth ** (annualization / len(returns)) - 1.0)


def _safe_series(series: pd.Series) -> list[float | None]:
    return [_finite(float(value)) for value in series]


def _method_label(method: BacktestMethod, settings: BacktestSettings) -> str:
    if method == BacktestMethod.MOMENTUM:
        return f"Momentum {settings.lookback_months}–{settings.skip_months}"
    if method == BacktestMethod.LIQUIDITY_MOMENTUM:
        return f"Momentum + liquidez ({settings.lookback_months}–{settings.skip_months})"
    return _METHOD_LABELS[method]


_METHOD_LABELS = {
    BacktestMethod.LOW_BETA: "Beta baja",
    BacktestMethod.SECTOR_ROTATION: "Rotación sectorial",
    BacktestMethod.CLUSTER_SELECTION: "Selección por clusters",
}

_OPTIMIZER_LABELS = {
    OptimizerName.EQUAL: "Igual ponderación",
    OptimizerName.INVERSE_VOLATILITY: "Volatilidad inversa",
    OptimizerName.MOMENTUM: "Peso por ranking",
    OptimizerName.MINIMUM_VARIANCE: "Mínima varianza",
    OptimizerName.MAXIMUM_SHARPE: "Máximo Sharpe",
    OptimizerName.HRP: "HRP",
    OptimizerName.RISK_PARITY: "Risk parity",
}
