from fastapi import APIRouter, HTTPException

from app.schemas import (
    BacktestCompareRequest,
    BacktestMethod,
    BacktestRunRequest,
    FundamentalMethod,
    FundamentalSelectionRequest,
    MarketDataRequest,
    OptimizerName,
)
from app.services.backtesting import run_backtest
from app.services.market_data import (
    MarketDataError,
    ProviderNotInstalled,
    download_market_data,
    get_provider_status,
)
from app.services.selection import run_fundamental_selection

router = APIRouter()


@router.get("/methods")
def list_methods() -> dict[str, list[dict[str, str]]]:
    return {
        "backtest_selection": [
            {"id": method.value, "label": label}
            for method, label in (
                (BacktestMethod.MOMENTUM, "Momentum 12–1"),
                (BacktestMethod.LOW_BETA, "Beta baja"),
                (BacktestMethod.SECTOR_ROTATION, "Rotación sectorial"),
                (BacktestMethod.CLUSTER_SELECTION, "Selección por clusters"),
                (BacktestMethod.LIQUIDITY_MOMENTUM, "Momentum + liquidez"),
            )
        ],
        "optimizers": [
            {"id": optimizer.value, "label": label}
            for optimizer, label in (
                (OptimizerName.EQUAL, "Igual ponderación"),
                (OptimizerName.INVERSE_VOLATILITY, "Volatilidad inversa"),
                (OptimizerName.MOMENTUM, "Peso por ranking"),
                (OptimizerName.MINIMUM_VARIANCE, "Mínima varianza"),
                (OptimizerName.MAXIMUM_SHARPE, "Máximo Sharpe"),
                (OptimizerName.HRP, "HRP"),
                (OptimizerName.RISK_PARITY, "Risk parity"),
            )
        ],
        "fundamental_selection": [
            {"id": method.value, "label": label}
            for method, label in (
                (FundamentalMethod.ALTMAN_PUBLIC, "Altman Z · manufactura pública"),
                (FundamentalMethod.ALTMAN_PRIVATE, "Altman Z′ · manufactura privada"),
                (FundamentalMethod.ALTMAN_NON_MANUFACTURING, "Altman Z″ · no manufactura"),
                (FundamentalMethod.PIOTROSKI, "Piotroski F-score"),
                (FundamentalMethod.BENEISH, "Beneish M-score"),
                (FundamentalMethod.FACTOR_SCREENING, "Screening multifactor"),
                (FundamentalMethod.FAMA_FRENCH, "Fama–French · selección por características"),
            )
        ],
    }


@router.get("/market-data/providers")
def market_data_providers() -> dict[str, list[dict]]:
    return {"providers": get_provider_status()}


@router.post("/market-data/download")
def market_data_download(request: MarketDataRequest) -> dict:
    try:
        panel = download_market_data(request)
    except ProviderNotInstalled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        **panel.model_dump(mode="json"),
        "provider": request.provider.value,
        "symbols": list(panel.prices),
        "observations": len(panel.dates),
        "start_date": panel.dates[0],
        "end_date": panel.dates[-1],
        "interval": "1d",
    }


@router.post("/backtests/run")
def run_one(request: BacktestRunRequest) -> dict:
    try:
        return run_backtest(request, request.method, request.optimizer)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/backtests/compare")
def compare(request: BacktestCompareRequest) -> dict:
    results = []
    errors = []
    for method in request.methods:
        for optimizer in request.optimizers:
            try:
                results.append(run_backtest(request, method, optimizer))
            except (ValueError, RuntimeError) as exc:
                errors.append(
                    {"method": method.value, "optimizer": optimizer.value, "error": str(exc)}
                )
    if not results:
        details = "; ".join(f"{item['method']}: {item['error']}" for item in errors)
        raise HTTPException(
            status_code=422, detail=details or "No se pudo ejecutar la comparación."
        )
    return {"results": results, "errors": errors}


@router.post("/selection/fundamental")
def fundamental_selection(request: FundamentalSelectionRequest) -> dict:
    try:
        return run_fundamental_selection(request)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
