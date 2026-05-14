from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from model.apps.analytics_service.config import (
    DEFAULT_CURRENCY,
    DEFAULT_MODEL_PATH,
    MODEL_PATH_ENV,
    MODEL_READINESS_PATH,
    SERVICE_NAME,
)
from model.apps.analytics_service.schemas import RealEstateScoreRequest, ScoreMethod, ScoreResponse
from model.apps.analytics_service.service import (
    calculate_formula,
    calculate_price_per_meter,
    calculate_regression,
)
from model.ml.model.persistence import LoadedModelBundle, load_model_bundle
from model.ml.model.readiness import ModelReadinessError, load_ready_model_bundle


app = FastAPI(
    title="Сервис аналитики недвижимости",
    version="0.1.0",
    description=(
        "Изолированный MVP-сервис для price_per_meter, formula и regression аналитики. "
        "Regression возвращает proxy valuation/model estimate, trained on listing data."
    ),
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Any, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Ошибка валидации запроса.",
            "errors": jsonable_encoder(exc.errors()),
        },
    )


@lru_cache(maxsize=1)
def get_model_bundle() -> LoadedModelBundle:
    try:
        return load_ready_model_bundle(
            configured_model_path=DEFAULT_MODEL_PATH,
            manifest_path=MODEL_READINESS_PATH,
            model_path_is_explicit=MODEL_PATH_ENV is not None,
        )
    except ModelReadinessError:
        if MODEL_READINESS_PATH.exists():
            raise
        if DEFAULT_MODEL_PATH.exists():
            return load_model_bundle(DEFAULT_MODEL_PATH)
        raise


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "currency": DEFAULT_CURRENCY}


@app.post("/score", response_model=ScoreResponse)
def score(
    payload: RealEstateScoreRequest,
    method: ScoreMethod = Query(..., description="Метод расчёта: price_per_meter, formula или regression."),
) -> ScoreResponse:
    try:
        if method == "price_per_meter":
            return calculate_price_per_meter(payload)
        if method == "formula":
            return calculate_formula(payload)
        bundle = get_model_bundle()
        return calculate_regression(payload, bundle)
    except (FileNotFoundError, ModelReadinessError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Расчёт analytics score не выполнен: {exc}") from exc


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": SERVICE_NAME,
        "health_url": "/health",
        "score_url": "/score?method=regression",
        "currency_mode": "RUB-only",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8090")),
        reload=False,
    )
