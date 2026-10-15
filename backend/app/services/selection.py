from __future__ import annotations

import json
from typing import Any

import pandas as pd
from quant_core.strategies.base import StrategyInput
from quant_core.strategies.factors.fama_french import FamaFrenchConfig, FamaFrenchStrategy
from quant_core.strategies.fundamental.altman import AltmanConfig, AltmanZScoreStrategy
from quant_core.strategies.fundamental.beneish import BeneishConfig, BeneishMScoreStrategy
from quant_core.strategies.fundamental.factor_screening import (
    FactorScreeningConfig,
    FactorScreeningStrategy,
)
from quant_core.strategies.fundamental.piotroski import PiotroskiConfig, PiotroskiFScoreStrategy

from app.schemas import FundamentalMethod, FundamentalSelectionRequest


def run_fundamental_selection(request: FundamentalSelectionRequest) -> dict[str, Any]:
    fundamentals = pd.DataFrame.from_dict(request.fundamentals, orient="index")
    if fundamentals.index.has_duplicates:
        raise ValueError("Los identificadores de activo deben ser únicos.")

    if request.method == FundamentalMethod.ALTMAN_PUBLIC:
        strategy = AltmanZScoreStrategy(
            AltmanConfig(model="public_manufacturing", top_n=request.top_n)
        )
    elif request.method == FundamentalMethod.ALTMAN_PRIVATE:
        strategy = AltmanZScoreStrategy(
            AltmanConfig(model="private_manufacturing", top_n=request.top_n)
        )
    elif request.method == FundamentalMethod.ALTMAN_NON_MANUFACTURING:
        strategy = AltmanZScoreStrategy(
            AltmanConfig(model="non_manufacturing", top_n=request.top_n)
        )
    elif request.method == FundamentalMethod.PIOTROSKI:
        strategy = PiotroskiFScoreStrategy(
            PiotroskiConfig(min_score=request.min_score, top_n=request.top_n)
        )
    elif request.method == FundamentalMethod.BENEISH:
        strategy = BeneishMScoreStrategy(BeneishConfig(top_n=request.top_n))
    elif request.method == FundamentalMethod.FACTOR_SCREENING:
        strategy = FactorScreeningStrategy(
            FactorScreeningConfig(top_n=request.top_n, max_sector_weight=None)
        )
    elif request.method == FundamentalMethod.FAMA_FRENCH:
        strategy = FamaFrenchStrategy(FamaFrenchConfig(top_n=request.top_n))
    else:  # pragma: no cover - enum validation rejects unknown methods.
        raise ValueError(f"Método fundamental no soportado: {request.method}.")

    result = strategy.generate(StrategyInput(fundamentals=fundamentals))
    score_column = next(
        (
            column
            for column in (
                "composite_score",
                "altman_z_score",
                "f_score",
                "m_score",
            )
            if column in result.scores
        ),
        result.scores.columns[0],
    )
    score_table = result.scores.copy()
    classifications = result.metadata.get("classification")
    if isinstance(classifications, pd.DataFrame):
        score_table = score_table.join(classifications)
    rows = score_table.join(result.signals).reset_index(names="asset")
    safe_rows = json.loads(rows.to_json(orient="records", date_format="iso"))
    selected = [
        {"asset": row["asset"], "score": row.get(score_column), "rank": row.get("rank")}
        for row in safe_rows
        if row.get("selected")
    ]
    metadata = dict(result.metadata)
    if isinstance(classifications, pd.DataFrame):
        metadata["classification"] = classifications.to_dict(orient="index")
    return {
        "method": request.method.value,
        "score_name": score_column,
        "rows": safe_rows,
        "selected": selected,
        "metadata": json.loads(json.dumps(metadata, default=str)),
    }
