import numpy as np
import pandas as pd
from app.main import app
from app.schemas import MarketDataRequest, PricePanel
from app.services.market_data import ProviderNotInstalled, panel_to_frames
from fastapi.testclient import TestClient

client = TestClient(app)


def _test_panel(rows: int = 420, seed: int = 19) -> PricePanel:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=rows)
    returns = rng.normal(0.0004, 0.009, (rows, 4))
    prices = 100 * np.cumprod(1 + returns, axis=0)
    volumes = rng.lognormal(12, 0.35, (rows, 4))
    assets = ["SPY", "AAA", "BBB", "CCC"]
    return PricePanel(
        dates=[value.date() for value in dates],
        prices={asset: prices[:, index].tolist() for index, asset in enumerate(assets)},
        volumes={asset: volumes[:, index].tolist() for index, asset in enumerate(assets)},
    )


def _panel_payload() -> dict:
    return _test_panel().model_dump(mode="json")


def test_health_and_method_catalog_are_available() -> None:
    health = client.get("/health")
    methods = client.get("/api/v1/methods")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert methods.status_code == 200
    catalog = methods.json()
    assert {item["id"] for item in catalog["backtest_selection"]} >= {
        "momentum",
        "low_beta",
        "sector_rotation",
        "cluster_selection",
        "liquidity_momentum",
    }
    assert {item["id"] for item in catalog["optimizers"]} >= {
        "equal",
        "inverse_volatility",
        "minimum_variance",
        "hrp",
        "risk_parity",
    }
    assert {"piotroski", "fama_french"}.issubset(
        {item["id"] for item in catalog["fundamental_selection"]}
    )


def test_test_panel_is_reproducible_and_conversion_preserves_shape() -> None:
    panel = _test_panel(rows=80, seed=31)
    prices, volumes = panel_to_frames(panel)

    assert prices.shape == (80, 4)
    assert volumes is not None and volumes.shape == prices.shape
    assert _test_panel(rows=80, seed=31).prices == panel.prices


def test_market_data_provider_catalog_is_available() -> None:
    response = client.get("/api/v1/market-data/providers")

    assert response.status_code == 200
    providers = {item["id"] for item in response.json()["providers"]}
    assert providers == {"yfinance", "metatrader5"}


def test_market_data_download_endpoint_returns_provider_metadata(monkeypatch) -> None:
    panel = PricePanel(
        dates=["2024-01-02", "2024-01-03"],
        prices={"SPY": [470.0, 472.0], "QQQ": [400.0, 402.0]},
        volumes={"SPY": [1000.0, 1100.0], "QQQ": [2000.0, 2200.0]},
    )
    monkeypatch.setattr("app.api.v1.router.download_market_data", lambda request: panel)

    response = client.post(
        "/api/v1/market-data/download",
        json={
            "provider": "yfinance",
            "symbols": ["SPY", "QQQ"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-03",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "yfinance"
    assert response.json()["symbols"] == ["SPY", "QQQ"]
    assert response.json()["observations"] == 2
    assert response.json()["prices"] == panel.prices


def test_market_data_download_reports_missing_provider(monkeypatch) -> None:
    def raise_not_installed(request: MarketDataRequest) -> PricePanel:
        raise ProviderNotInstalled("Instala el proveedor")

    monkeypatch.setattr("app.api.v1.router.download_market_data", raise_not_installed)
    response = client.post(
        "/api/v1/market-data/download",
        json={
            "provider": "metatrader5",
            "symbols": ["EURUSD", "GBPUSD"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-03",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Instala el proveedor"


def test_compare_endpoint_runs_selection_and_allocation_combinations() -> None:
    response = client.post(
        "/api/v1/backtests/compare",
        json={
            "panel": _panel_payload(),
            "benchmark_asset": "SPY",
            "methods": ["momentum", "low_beta"],
            "optimizers": ["equal", "inverse_volatility"],
            "top_n": 3,
            "lookback_months": 4,
            "skip_months": 1,
            "transaction_cost_bps": 5,
            "initial_capital": 100_000,
            "max_weight": 0.8,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["results"]) == 4
    assert body["errors"] == []
    assert any(result["label"].startswith("Momentum 4–1") for result in body["results"])
    for result in body["results"]:
        assert len(result["series"]["dates"]) == len(result["series"]["equity"])
        assert result["metrics"]["rebalances"] > 0
        assert abs(sum(item["weight"] for item in result["latest_holdings"]) - 1) < 1e-7


def test_every_price_selection_method_runs_integration() -> None:
    response = client.post(
        "/api/v1/backtests/compare",
        json={
            "panel": _panel_payload(),
            "benchmark_asset": "SPY",
            "methods": [
                "momentum",
                "low_beta",
                "sector_rotation",
                "cluster_selection",
                "liquidity_momentum",
            ],
            "optimizers": ["equal"],
            "top_n": 3,
            "lookback_months": 4,
            "skip_months": 1,
            "transaction_cost_bps": 0,
            "initial_capital": 50_000,
            "max_weight": 0.8,
        },
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == 5
    assert response.json()["errors"] == []


def test_every_allocation_method_runs_integration() -> None:
    response = client.post(
        "/api/v1/backtests/compare",
        json={
            "panel": _panel_payload(),
            "benchmark_asset": "SPY",
            "methods": ["momentum"],
            "optimizers": [
                "equal",
                "inverse_volatility",
                "momentum",
                "minimum_variance",
                "maximum_sharpe",
                "hrp",
                "risk_parity",
            ],
            "top_n": 3,
            "lookback_months": 4,
            "skip_months": 1,
            "transaction_cost_bps": 0,
            "initial_capital": 50_000,
            "max_weight": 0.8,
        },
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == 7, response.json()["errors"]
    assert response.json()["errors"] == []


def test_invalid_price_panel_is_rejected_before_backtest() -> None:
    response = client.post(
        "/api/v1/backtests/run",
        json={
            "panel": {
                "dates": ["2025-01-02", "2025-01-02"],
                "prices": {"A": [10, 11], "B": [20, 21]},
            },
            "method": "momentum",
            "optimizer": "equal",
        },
    )

    assert response.status_code == 422


def test_backtest_panel_contract_rejects_download_metadata() -> None:
    panel = _panel_payload()
    panel.update(
        {
            "provider": "yfinance",
            "symbols": list(panel["prices"]),
            "observations": len(panel["dates"]),
            "start_date": panel["dates"][0],
            "end_date": panel["dates"][-1],
            "interval": "1d",
        }
    )
    response = client.post(
        "/api/v1/backtests/compare",
        json={
            "panel": panel,
            "benchmark_asset": "SPY",
            "methods": ["momentum"],
            "optimizers": ["equal"],
            "top_n": 2,
            "lookback_months": 4,
            "skip_months": 1,
            "transaction_cost_bps": 0,
            "initial_capital": 50_000,
            "max_weight": 0.8,
        },
    )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(error["loc"][-1] == "provider" for error in errors)


def test_fundamental_screen_returns_scores_and_selected_assets() -> None:
    fields = {
        "roa_current": 0.10,
        "roa_prior": 0.05,
        "cfo_to_assets_current": 0.12,
        "long_term_debt_ratio_current": 0.2,
        "long_term_debt_ratio_prior": 0.3,
        "current_ratio_current": 1.8,
        "current_ratio_prior": 1.4,
        "shares_outstanding_current": 100,
        "shares_outstanding_prior": 100,
        "gross_margin_current": 0.4,
        "gross_margin_prior": 0.35,
        "asset_turnover_current": 0.9,
        "asset_turnover_prior": 0.8,
    }
    response = client.post(
        "/api/v1/selection/fundamental",
        json={
            "method": "piotroski",
            "fundamentals": {"AAA": fields, "BBB": fields, "CCC": fields},
            "top_n": 2,
            "min_score": 7,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score_name"] == "f_score"
    assert len(body["rows"]) == 3
    assert len(body["selected"]) == 2
    assert all(row["f_score"] == 9 for row in body["rows"])


def test_each_fundamental_method_runs_integration() -> None:
    fields = {
        "working_capital": 120,
        "retained_earnings": 170,
        "ebit": 50,
        "market_equity": 600,
        "book_equity": 240,
        "total_liabilities": 240,
        "sales": 700,
        "total_assets": 500,
        "roa_current": 0.10,
        "roa_prior": 0.06,
        "cfo_to_assets_current": 0.12,
        "long_term_debt_ratio_current": 0.20,
        "long_term_debt_ratio_prior": 0.25,
        "current_ratio_current": 1.8,
        "current_ratio_prior": 1.4,
        "shares_outstanding_current": 100,
        "shares_outstanding_prior": 100,
        "gross_margin_current": 0.40,
        "gross_margin_prior": 0.37,
        "asset_turnover_current": 0.9,
        "asset_turnover_prior": 0.8,
        "receivables_current": 35,
        "receivables_prior": 30,
        "revenue_current": 700,
        "revenue_prior": 650,
        "gross_profit_current": 280,
        "gross_profit_prior": 240,
        "current_assets_current": 210,
        "current_assets_prior": 190,
        "ppe_current": 130,
        "ppe_prior": 120,
        "long_term_investments_current": 25,
        "long_term_investments_prior": 20,
        "total_assets_current": 500,
        "total_assets_prior": 470,
        "depreciation_current": 12,
        "depreciation_prior": 10,
        "sga_current": 90,
        "sga_prior": 85,
        "total_debt_current": 180,
        "total_debt_prior": 190,
        "income_before_extraordinary_current": 46,
        "cash_flow_operations_current": 53,
        "pe_ratio": 16,
        "pb_ratio": 2,
        "ev_ebitda": 9,
        "ps_ratio": 1.6,
        "roe": 0.16,
        "roa": 0.09,
        "debt_to_equity": 0.55,
        "altman_z_score": 3.1,
        "gross_margin": 0.4,
        "roic": 0.13,
        "operating_margin": 0.15,
        "market_cap": 1000,
        "operating_profitability": 0.17,
        "asset_growth": 0.04,
    }
    fundamentals = {
        "AAA": fields,
        "BBB": {**fields, "market_cap": 800, "pe_ratio": 14},
        "CCC": {**fields, "market_cap": 600, "pe_ratio": 12},
    }

    for method in [
        "altman_public",
        "altman_private",
        "altman_non_manufacturing",
        "piotroski",
        "beneish",
        "factor_screening",
        "fama_french",
    ]:
        response = client.post(
            "/api/v1/selection/fundamental",
            json={"method": method, "fundamentals": fundamentals, "top_n": 2},
        )
        assert response.status_code == 200, f"{method}: {response.text}"
        assert len(response.json()["rows"]) == 3


def test_fama_french_selection_returns_characteristic_scores() -> None:
    fundamentals = {
        "AAA": {"market_cap": 100, "book_equity": 80, "operating_profitability": 0.22, "asset_growth": 0.03},
        "BBB": {"market_cap": 200, "book_equity": 100, "operating_profitability": 0.15, "asset_growth": 0.08},
        "CCC": {"market_cap": 300, "book_equity": 90, "operating_profitability": 0.10, "asset_growth": 0.12},
    }

    response = client.post(
        "/api/v1/selection/fundamental",
        json={"method": "fama_french", "fundamentals": fundamentals, "top_n": 2},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "fama_french"
    assert body["score_name"] == "composite_score"
    assert len(body["selected"]) == 2
    assert body["metadata"]["classification"]["AAA"]["size_bucket"] == "small"


def test_weight_cap_leaves_cash_when_universe_cannot_hold_all_capital() -> None:
    from app.services.backtesting import _enforce_cap

    weights = _enforce_cap(pd.Series({"A": 0.8, "B": 0.15, "C": 0.05}), 0.30)

    assert weights.max() <= 0.30 + 1e-12
    assert abs(weights.sum() - 0.90) < 1e-12
