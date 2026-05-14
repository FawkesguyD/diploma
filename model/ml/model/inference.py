from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from model.ml.model.inference_preprocessing import prepare_inference_frame
from model.ml.model.inference_validation import ConfidenceLevel, validate_inference_record
from model.ml.model.market_bounds import MarketBoundResult, apply_market_bounds
from model.ml.model.normalization import fill_categorical_features_for_catboost, prepare_objects_frame
from model.ml.model.persistence import (
    LoadedModelBundle,
    inverse_transform_predictions,
    load_model_bundle,
)


DEFAULT_BASE_CURRENCY = "RUB"
DEFAULT_OUTPUT_CURRENCY = "RUB"
DEFAULT_LISTING_CURRENCY = "RUB"
DEFAULT_FX_RATE = 1.0
VALUATION_NOTE = (
    "Модельная proxy-оценка по данным объявлений в RUB. Это не гарантия сделки и не официальная оценка."
)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    if not np.isfinite(result):
        return None
    return result


def _normalize_output_currency(output_currency: str | None) -> str:
    normalized = (output_currency or DEFAULT_OUTPUT_CURRENCY).upper()
    if normalized != "RUB":
        raise ValueError("Сервис работает только в RUB; output_currency должен быть RUB.")
    return "RUB"


def _normalize_rub_currency(currency: str | None) -> str:
    normalized = DEFAULT_LISTING_CURRENCY if currency is None or pd.isna(currency) else str(currency).upper()
    if normalized != "RUB":
        raise ValueError("Сервис работает только с ценами в RUB.")
    return "RUB"


def _is_catboost_bundle(bundle: LoadedModelBundle) -> bool:
    model_module = getattr(bundle.model.__class__, "__module__", "")
    return bundle.model_name.startswith("catboost_regressor") or model_module.startswith("catboost")


def _feature_group(feature_name: str) -> str:
    feature_groups = {
        "total_area_m2": "area",
        "area": "area",
        "living_area_m2": "area",
        "kitchen_area_m2": "area",
        "kitchen_area": "area",
        "kitchen_ratio": "area_layout",
        "area_per_room": "area_layout",
        "rooms_density": "area_layout",
        "rooms": "rooms",
        "is_studio": "rooms",
        "district": "district",
        "latitude": "geo",
        "longitude": "geo",
        "has_coordinates": "geo",
        "building_type": "building",
        "object_type": "building",
        "region": "region",
        "floor": "floor",
        "level": "floor",
        "total_floors": "floor",
        "levels": "floor",
        "floor_ratio": "floor",
        "is_top_floor": "floor",
        "is_first_floor": "floor",
    }
    return feature_groups.get(feature_name, feature_name)


def _format_feature_topic(feature_name: str, raw_value: Any) -> str:
    default_topics = {
        "total_area_m2": "площадь объекта",
        "area": "площадь объекта",
        "kitchen_area_m2": "площадь кухни",
        "kitchen_area": "площадь кухни",
        "level": "этаж",
        "floor": "этаж",
        "levels": "этажность дома",
        "total_floors": "этажность дома",
        "kitchen_ratio": "доля кухни",
        "rooms_density": "плотность комнат",
        "is_studio": "студийная планировка",
        "object_type": "тип рынка",
        "region": "регион",
        "rooms": "комнатность",
        "district": "район",
        "building_type": "тип дома",
        "latitude": "широта",
        "longitude": "долгота",
        "has_coordinates": "наличие координат",
    }
    if raw_value is None or pd.isna(raw_value):
        return default_topics.get(feature_name, feature_name.replace("_", " "))

    try:
        if feature_name in {"total_area_m2", "area"}:
            return f"площадь {float(raw_value):.1f} м²"
        if feature_name in {"kitchen_area_m2", "kitchen_area"}:
            return f"площадь кухни {float(raw_value):.1f} м²"
        if feature_name in {"level", "floor"}:
            return f"этаж {int(float(raw_value))}"
        if feature_name in {"levels", "total_floors"}:
            return f"этажность дома {int(float(raw_value))}"
        if feature_name == "rooms":
            return f"комнатность {int(float(raw_value))}"
        if feature_name in {"building_type", "object_type", "region", "district"}:
            return f"{default_topics.get(feature_name, feature_name)} {raw_value}"
    except (TypeError, ValueError):
        return default_topics.get(feature_name, feature_name.replace("_", " "))

    return default_topics.get(feature_name, feature_name.replace("_", " "))


def _build_explanation_summary(
    factor_details: list[dict[str, Any]],
    *,
    confidence: ConfidenceLevel = "high",
) -> str:
    positive_topics = [item["topic"] for item in factor_details if item["direction"] == "positive"]
    negative_topics = [item["topic"] for item in factor_details if item["direction"] == "negative"]
    confidence_note = ""
    if confidence == "low":
        confidence_note = " Входные данные низкого качества, поэтому оценку стоит использовать только как слабый сигнал."
    elif confidence == "medium":
        confidence_note = " Входные данные содержат ограничения, поэтому оценка имеет среднюю уверенность."

    if positive_topics and negative_topics:
        return (
            f"Оценку поддержали факторы: {', '.join(positive_topics[:2])}. "
            f"Факторы вроде {negative_topics[0]} частично снизили оценку."
            f"{confidence_note}"
        )
    if positive_topics:
        return f"Оценку поддержали факторы: {', '.join(positive_topics[:3])}.{confidence_note}"
    if negative_topics:
        return f"На оценку заметно повлияли факторы: {', '.join(negative_topics[:3])}.{confidence_note}"
    return f"Оценка построена по характеристикам объявления и рыночным ограничениям.{confidence_note}"


def _fallback_explanation(
    object_features: dict[str, Any],
    *,
    confidence: ConfidenceLevel,
) -> tuple[list[str], str]:
    factors: list[dict[str, Any]] = []

    area = _coerce_optional_float(object_features.get("area") or object_features.get("total_area_m2"))
    if area is not None:
        direction = "positive" if area >= 45 else "negative"
        factors.append({"topic": f"площадь {area:.1f} м²", "direction": direction})

    rooms = _coerce_optional_float(object_features.get("rooms"))
    if rooms is not None:
        direction = "positive" if rooms >= 2 else "negative"
        factors.append({"topic": f"комнатность {int(rooms)}", "direction": direction})

    for field_name in ("region", "district", "building_type", "object_type"):
        value = object_features.get(field_name)
        if value:
            factors.append({"topic": _format_feature_topic(field_name, value), "direction": "positive"})

    top_factors = [
        f"Фактор «{item['topic']}» {'повысил' if item['direction'] == 'positive' else 'снизил'} proxy-оценку"
        for item in factors[:5]
    ]
    return top_factors[:5], _build_explanation_summary(factors[:5], confidence=confidence)


def explain_prediction_from_bundle(
    object_features: dict[str, Any],
    bundle: LoadedModelBundle,
    max_factors: int = 5,
    confidence: ConfidenceLevel = "high",
) -> dict[str, Any]:
    inference_frame = prepare_inference_frame(object_features, bundle.feature_config)

    if _is_catboost_bundle(bundle):
        try:
            from catboost import Pool

            cat_frame = fill_categorical_features_for_catboost(
                inference_frame,
                bundle.feature_config.categorical_features,
            )
            shap_values = bundle.model.get_feature_importance(
                type="ShapValues",
                data=Pool(cat_frame, cat_features=bundle.feature_config.categorical_features),
            )
            feature_names = list(cat_frame.columns)
            contributions = shap_values[0][:-1]
            ranked_indices = np.argsort(np.abs(contributions))[::-1]
            factor_details: list[dict[str, Any]] = []
            seen_groups: set[str] = set()

            for index in ranked_indices:
                contribution = float(contributions[index])
                if np.isclose(contribution, 0.0):
                    continue

                feature_name = feature_names[index]
                group_name = _feature_group(feature_name)
                if group_name in seen_groups:
                    continue

                raw_value = object_features.get(feature_name)
                factor_details.append(
                    {
                        "feature": feature_name,
                        "topic": _format_feature_topic(feature_name, raw_value),
                        "direction": "positive" if contribution > 0 else "negative",
                        "contribution": contribution,
                    }
                )
                seen_groups.add(group_name)
                if len(factor_details) >= max(3, max_factors):
                    break

            if factor_details:
                return {
                    "top_factors": [
                        f"Фактор «{item['topic']}» {'повысил' if item['direction'] == 'positive' else 'снизил'} proxy-оценку"
                        for item in factor_details[:max_factors]
                    ],
                    "explanation_summary": _build_explanation_summary(
                        factor_details[:max_factors],
                        confidence=confidence,
                    ),
                }
        except Exception:
            pass

    top_factors, explanation_summary = _fallback_explanation(
        object_features,
        confidence=confidence,
    )
    return {"top_factors": top_factors[:max_factors], "explanation_summary": explanation_summary}


def _predict_model_output(bundle: LoadedModelBundle, frame: pd.DataFrame) -> np.ndarray:
    if _is_catboost_bundle(bundle):
        cat_frame = fill_categorical_features_for_catboost(
            frame,
            bundle.feature_config.categorical_features,
        )
        predictions = bundle.model.predict(cat_frame)
    else:
        predictions = bundle.model.predict(frame)

    predictions = inverse_transform_predictions(predictions, bundle.target_transform)
    return np.clip(np.asarray(predictions, dtype=float), a_min=0.0, a_max=None)


def _prediction_target(bundle: LoadedModelBundle) -> str:
    metadata = bundle.metadata or {}
    return str(metadata.get("prediction_target") or "total_price")


def _area_for_price(record: dict[str, Any]) -> float:
    area = _coerce_optional_float(record.get("area") or record.get("total_area_m2"))
    if area is None or area <= 0:
        raise ValueError("Для расчёта цены нужна положительная площадь.")
    return area


def _price_fields_from_model_output(
    *,
    bundle: LoadedModelBundle,
    normalized_features: dict[str, Any],
    model_output: float,
) -> tuple[float, float, MarketBoundResult]:
    area = _area_for_price(normalized_features)
    prediction_target = _prediction_target(bundle)
    if prediction_target == "price_per_m2":
        raw_price_per_m2 = float(model_output)
    else:
        raw_price_per_m2 = float(model_output) / area

    bounds_result = apply_market_bounds(
        price_per_m2=raw_price_per_m2,
        object_features=normalized_features,
        market_bounds=(bundle.metadata or {}).get("market_bounds"),
    )
    predicted_price = bounds_result.price_per_m2_clamped * area
    return predicted_price, bounds_result.price_per_m2_clamped, bounds_result


def _build_rub_price_output(
    *,
    predicted_price_rub: float,
    listing_price_rub: float | None,
) -> dict[str, float | str | None]:
    delta_abs = None
    delta_pct = None
    if listing_price_rub is not None:
        delta_abs = predicted_price_rub - listing_price_rub
        if listing_price_rub != 0:
            delta_pct = delta_abs / listing_price_rub
    return {
        "expected_price_proxy": predicted_price_rub,
        "comparison_currency": "RUB",
        "predicted_price_currency": "RUB",
        "listing_price_in_comparison_currency": listing_price_rub,
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
    }


def _build_response(
    *,
    object_features: dict[str, Any],
    bundle: LoadedModelBundle,
    include_explanation: bool,
) -> dict[str, Any]:
    validation = validate_inference_record(
        object_features,
        bundle.feature_config,
        bundle.metadata,
    )
    if not validation.is_valid:
        raise ValueError("; ".join(validation.errors))

    normalized_features = validation.normalized_features
    listing_currency = _normalize_rub_currency(normalized_features.get("listing_currency"))
    listing_price_rub = _coerce_optional_float(
        normalized_features.get("listing_price")
        if "listing_price" in normalized_features
        else normalized_features.get(bundle.target_column)
    )

    inference_frame = prepare_inference_frame(normalized_features, bundle.feature_config)
    model_output = float(_predict_model_output(bundle, inference_frame)[0])
    predicted_price_rub, price_per_m2_rub, bounds_result = _price_fields_from_model_output(
        bundle=bundle,
        normalized_features=normalized_features,
        model_output=model_output,
    )

    warnings = list(validation.warnings)
    confidence = validation.confidence
    if bounds_result.clamped:
        warnings.append("Применено рыночное ограничение цены за м².")
        confidence = "low" if confidence == "medium" else "medium" if confidence == "high" else confidence

    price_output = _build_rub_price_output(
        predicted_price_rub=predicted_price_rub,
        listing_price_rub=listing_price_rub,
    )
    response: dict[str, Any] = {
        "predicted_price_rub": predicted_price_rub,
        "price_per_m2_rub": price_per_m2_rub,
        "listing_price_rub": listing_price_rub,
        "delta_abs_rub": price_output["delta_abs"],
        "delta_pct": price_output["delta_pct"],
        "confidence": confidence,
        "warnings": warnings,
        "sanity_checks": {
            "input_validated": True,
            "market_bounds_applied": bool((bundle.metadata or {}).get("market_bounds")),
            "clamped": bounds_result.clamped,
            "market_segment": bounds_result.segment_key,
        },
        "valuation_note": VALUATION_NOTE,
        "base_currency": "RUB",
        "output_currency": "RUB",
        "listing_price": listing_price_rub,
        "listing_currency": listing_currency,
        "fx_rate_used": None,
        "price_outputs": {"RUB": price_output},
    }

    if include_explanation:
        response.update(
            explain_prediction_from_bundle(
                normalized_features,
                bundle,
                confidence=confidence,
            )
        )
    else:
        response["top_factors"] = []
        response["explanation_summary"] = _build_explanation_summary([], confidence=confidence)

    return response


def predict_expected_price_from_bundle(
    object_features: dict[str, Any],
    bundle: LoadedModelBundle,
) -> dict[str, float | None]:
    response = _build_response(
        object_features=object_features,
        bundle=bundle,
        include_explanation=False,
    )
    return {
        "expected_price_proxy": response["predicted_price_rub"],
        "listing_price": response["listing_price_rub"],
        "delta_abs": response["delta_abs_rub"],
        "delta_pct": response["delta_pct"],
    }


def predict_expected_price(
    object_features: dict[str, Any],
    model_path: str | Path,
) -> dict[str, float | None]:
    bundle = load_model_bundle(model_path)
    return predict_expected_price_from_bundle(object_features, bundle)


def score_objects_from_bundle(
    objects: pd.DataFrame | list[dict[str, Any]] | dict[str, Any],
    bundle: LoadedModelBundle,
    listing_price_column: str | None = "listing_price",
) -> pd.DataFrame:
    raw_frame = prepare_objects_frame(objects)
    rows: list[dict[str, Any]] = []
    for record in raw_frame.to_dict(orient="records"):
        response = _build_response(
            object_features=record,
            bundle=bundle,
            include_explanation=False,
        )
        normalized = validate_inference_record(record, bundle.feature_config, bundle.metadata).normalized_features
        rows.append(
            {
                **normalized,
                "expected_price_proxy": response["predicted_price_rub"],
                "price_per_m2_rub": response["price_per_m2_rub"],
                "listing_price": response["listing_price_rub"],
                "delta_abs": response["delta_abs_rub"],
                "delta_pct": response["delta_pct"],
                "confidence": response["confidence"],
                "warnings": response["warnings"],
                "sanity_checks": response["sanity_checks"],
            }
        )
    return pd.DataFrame(rows)


def score_objects(
    objects: pd.DataFrame | list[dict[str, Any]] | dict[str, Any],
    model_path: str | Path,
    listing_price_column: str | None = "listing_price",
) -> pd.DataFrame:
    bundle = load_model_bundle(model_path)
    return score_objects_from_bundle(objects, bundle, listing_price_column)


def rank_by_undervaluation(scored_frame: pd.DataFrame) -> pd.DataFrame:
    ranked = scored_frame.sort_values(
        by=["delta_pct", "delta_abs"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)
    ranked["undervaluation_rank"] = ranked.index + 1
    return ranked


def predict_proxy_valuation_from_bundle(
    object_features: dict[str, Any],
    bundle: LoadedModelBundle,
    output_currency: str = DEFAULT_OUTPUT_CURRENCY,
    fx_rate: float | None = None,
    default_fx_rate: float = DEFAULT_FX_RATE,
    include_explanation: bool = True,
) -> dict[str, Any]:
    _normalize_output_currency(output_currency)
    return _build_response(
        object_features=object_features,
        bundle=bundle,
        include_explanation=include_explanation,
    )


def predict_proxy_valuation(
    object_features: dict[str, Any],
    model_path: str | Path,
    output_currency: str = DEFAULT_OUTPUT_CURRENCY,
    fx_rate: float | None = None,
    default_fx_rate: float = DEFAULT_FX_RATE,
    include_explanation: bool = True,
) -> dict[str, Any]:
    bundle = load_model_bundle(model_path)
    return predict_proxy_valuation_from_bundle(
        object_features=object_features,
        bundle=bundle,
        output_currency=output_currency,
        fx_rate=fx_rate,
        default_fx_rate=default_fx_rate,
        include_explanation=include_explanation,
    )


def score_proxy_valuations_from_bundle(
    objects: pd.DataFrame | list[dict[str, Any]] | dict[str, Any],
    bundle: LoadedModelBundle,
    output_currency: str = DEFAULT_OUTPUT_CURRENCY,
    fx_rate: float | None = None,
    default_fx_rate: float = DEFAULT_FX_RATE,
    rank_results: bool = True,
    include_explanations: bool = False,
    listing_id_column: str = "listing_id",
) -> list[dict[str, Any]]:
    _normalize_output_currency(output_currency)
    raw_frame = prepare_objects_frame(objects)
    results: list[dict[str, Any]] = []

    for input_index, record in enumerate(raw_frame.to_dict(orient="records")):
        if "input_index" not in record or pd.isna(record.get("input_index")):
            record["input_index"] = input_index
        response = _build_response(
            object_features=record,
            bundle=bundle,
            include_explanation=include_explanations,
        )
        result = {
            "input_index": record.get("input_index"),
            "listing_id": record.get(listing_id_column),
            "predicted_price_rub": response["predicted_price_rub"],
            "price_per_m2_rub": response["price_per_m2_rub"],
            "listing_price_rub": response["listing_price_rub"],
            "delta_abs_rub": response["delta_abs_rub"],
            "delta_pct": response["delta_pct"],
            "confidence": response["confidence"],
            "warnings": response["warnings"],
            "sanity_checks": response["sanity_checks"],
            "base_currency": "RUB",
            "output_currency": "RUB",
            "listing_price": response["listing_price_rub"],
            "listing_currency": "RUB",
            "fx_rate_used": None,
            "price_outputs": response["price_outputs"],
            "valuation_note": response["valuation_note"],
            "top_factors": response["top_factors"],
            "explanation_summary": response["explanation_summary"],
            "undervaluation_rank": None,
        }
        results.append(result)

    if rank_results:
        results = sorted(
            results,
            key=lambda item: (
                item["delta_pct"] if item["delta_pct"] is not None else -np.inf,
                item["delta_abs_rub"] if item["delta_abs_rub"] is not None else -np.inf,
            ),
            reverse=True,
        )
        for rank, item in enumerate(results, start=1):
            item["undervaluation_rank"] = rank

    return results
