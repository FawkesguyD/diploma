from __future__ import annotations

from typing import Any

from model.ml.model.persistence import LoadedModelBundle
from model.ml.model.prediction import predict_proxy_valuation_from_bundle

from model.apps.analytics_service.config import (
    DEFAULT_CURRENCY,
    FORMULA_BASELINE_COEFFICIENTS,
    FORMULA_BASELINE_NOTE,
)
from model.apps.analytics_service.schemas import (
    FormulaComponent,
    FormulaScoreResponse,
    InputSummary,
    PricePerMeterScoreResponse,
    RealEstateScoreRequest,
    RegressionScoreResponse,
)


def input_summary(payload: RealEstateScoreRequest) -> InputSummary:
    return InputSummary(
        rooms=payload.rooms,
        area=payload.area,
        kitchen_area=payload.kitchen_area,
        level=payload.level,
        levels=payload.levels,
        building_type=payload.building_type,
        object_type=payload.object_type,
        region=payload.region,
        latitude=payload.latitude,
        longitude=payload.longitude,
        listing_price=payload.listing_price,
        listing_currency=payload.listing_currency,
    )


def round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def round_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def calculate_delta(expected_price_proxy: float, listing_price: float | None) -> tuple[float | None, float | None]:
    if listing_price is None:
        return None, None
    delta_abs = expected_price_proxy - listing_price
    delta_pct = delta_abs / listing_price if listing_price else None
    return round_money(delta_abs), round_ratio(delta_pct)


def calculate_price_per_meter(payload: RealEstateScoreRequest) -> PricePerMeterScoreResponse:
    if payload.listing_price is None:
        raise ValueError("Для method=price_per_meter нужно передать listing_price.")

    price_per_m2 = payload.listing_price / payload.area
    score = round_money(price_per_m2)
    return PricePerMeterScoreResponse(
        method="price_per_meter",
        input_summary=input_summary(payload),
        score=score,
        analytical_score=score,
        price_per_m2_score=score,
        interpretation=(
            "Аналитическая метрика цены за м² по объявлению. Это screening-сигнал, "
            "а не proxy valuation всего объекта."
        ),
        listing_price=round_money(payload.listing_price),
        area=payload.area,
        price_per_m2=score,
    )


def calculate_formula(payload: RealEstateScoreRequest) -> FormulaScoreResponse:
    components: list[FormulaComponent] = []
    coefficients_used: dict[str, float] = {}

    intercept = FORMULA_BASELINE_COEFFICIENTS["intercept"]
    components.append(
        FormulaComponent(field="intercept", value=1.0, coefficient=intercept, contribution=intercept)
    )
    coefficients_used["intercept"] = intercept

    for field_name in ("area", "kitchen_area", "rooms", "level", "levels"):
        value = getattr(payload, field_name)
        if value is None:
            continue
        coefficient = FORMULA_BASELINE_COEFFICIENTS[field_name]
        contribution = float(value) * coefficient
        components.append(
            FormulaComponent(
                field=field_name,
                value=float(value),
                coefficient=coefficient,
                contribution=round_money(contribution) or 0.0,
            )
        )
        coefficients_used[field_name] = coefficient

    expected_price_proxy = max(0.0, sum(component.contribution for component in components))
    delta_abs, delta_pct = calculate_delta(expected_price_proxy, payload.listing_price)
    return FormulaScoreResponse(
        method="formula",
        input_summary=input_summary(payload),
        score=round_money(expected_price_proxy) or 0.0,
        expected_price_proxy=round_money(expected_price_proxy) or 0.0,
        listing_price=round_money(payload.listing_price),
        delta_abs=delta_abs,
        delta_pct=delta_pct,
        output_currency=DEFAULT_CURRENCY,
        coefficients_used=coefficients_used,
        formula_components=components,
        interpretation=(
            f"{FORMULA_BASELINE_NOTE} Если listing_price передан, delta_abs и delta_pct "
            "можно использовать для shortlist-ранжирования по недооцененности."
        ),
    )


def calculate_regression(
    payload: RealEstateScoreRequest,
    bundle: LoadedModelBundle,
) -> RegressionScoreResponse:
    raw_result: dict[str, Any] = predict_proxy_valuation_from_bundle(
        object_features=payload.model_payload(),
        bundle=bundle,
        output_currency=DEFAULT_CURRENCY,
        fx_rate=None,
        default_fx_rate=1.0,
        include_explanation=True,
    )

    return RegressionScoreResponse(
        method="regression",
        expected_price_proxy=round_money(float(raw_result["predicted_price_rub"])) or 0.0,
        listing_price=round_money(raw_result.get("listing_price_rub")),
        delta_abs=round_money(raw_result.get("delta_abs_rub")),
        delta_pct=round_ratio(raw_result.get("delta_pct")),
        output_currency=DEFAULT_CURRENCY,
        valuation_note=raw_result.get("valuation_note")
        or "Model estimate trained on listing data; используйте как proxy valuation сигнал.",
        explanation_summary=raw_result.get("explanation_summary"),
        top_factors=list(raw_result.get("top_factors") or []),
    )

