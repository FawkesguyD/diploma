from __future__ import annotations

import math
import os
import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased
from starlette.middleware.sessions import SessionMiddleware

from model.apps.api.deps import get_current_user, get_db_session
from model.ml.model.prediction import (
    LoadedModelBundle,
    predict_proxy_valuation_from_bundle,
    score_proxy_valuations_from_bundle,
)
from model.ml.model.inference_validation import validate_inference_record
from model.ml.model.readiness import ModelReadinessError, load_ready_model_bundle
from model.ml.model.runtime_adapters import build_listing_model_payload
from model.ml.model.utils import ARTIFACTS_DIR
from model.shared.auth import verify_password
from model.shared.db.control_objects import (
    get_control_object_sample_seed,
    listing_projection_from_control_row,
    payload_int,
    payload_text,
)
from model.shared.db.models import AnalyticsControlObject, Listing, ShortlistItem, User, Valuation


MODEL_PATH_ENV = os.getenv("MODEL_PATH")
DEFAULT_MODEL_PATH = Path(MODEL_PATH_ENV or ARTIFACTS_DIR / "best_model_russia2021.joblib")
MODEL_READINESS_PATH = Path(os.getenv("MODEL_READINESS_PATH", ARTIFACTS_DIR / "model_readiness.json"))
DEFAULT_LISTING_CURRENCY = "RUB"
MODEL_BASE_CURRENCY = "RUB"
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "real_estate_session")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-session-secret-change-me")
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 12)))
DEFAULT_UI_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
CONTROL_OBJECT_SAMPLE_SEED = get_control_object_sample_seed()
LOGGER = logging.getLogger("uvicorn.error")

def _parse_allowed_origins() -> list[str]:
    raw_value = os.getenv("UI_ALLOWED_ORIGINS", DEFAULT_UI_ALLOWED_ORIGINS)
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


class CurrencyPriceOutput(BaseModel):
    expected_price_proxy: float
    comparison_currency: str
    predicted_price_currency: str
    listing_price_in_comparison_currency: float | None = None
    delta_abs: float | None = None
    delta_pct: float | None = None


class PredictionResponse(BaseModel):
    predicted_price_rub: float
    price_per_m2_rub: float
    listing_price_rub: float | None = None
    delta_abs_rub: float | None = None
    delta_pct: float | None = None
    confidence: Literal["high", "medium", "low"]
    warnings: list[str] = Field(default_factory=list)
    sanity_checks: dict[str, Any] = Field(default_factory=dict)
    base_currency: str
    output_currency: str
    listing_price: float | None = None
    listing_currency: str
    fx_rate_used: float | None = None
    price_outputs: dict[str, CurrencyPriceOutput]
    top_factors: list[str] = Field(default_factory=list)
    explanation_summary: str | None = None
    valuation_note: str


class SinglePredictionRequest(BaseModel):
    object_features: dict[str, Any] = Field(
        ...,
        description="Listing attributes used for MVP proxy valuation.",
    )
    output_currency: Literal["RUB"] = Field(
        default="RUB",
        description="Deprecated compatibility field. The API returns RUB only.",
    )
    fx_rate: float | None = Field(
        default=None,
        gt=0,
        description="Deprecated compatibility field. Currency conversion is disabled.",
    )
    include_explanation: bool = Field(
        default=True,
        description="If true, include lightweight local explainability in the response.",
    )


class BatchPredictionRequest(BaseModel):
    objects: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of listing objects for batch scoring.",
    )
    rank_by_undervaluation: bool = Field(
        default=True,
        description="If true, sort output by delta_pct descending and add undervaluation_rank.",
    )
    output_currency: Literal["RUB"] = Field(
        default="RUB",
        description="Deprecated compatibility field. The API returns RUB only.",
    )
    fx_rate: float | None = Field(
        default=None,
        gt=0,
        description="Deprecated compatibility field. Currency conversion is disabled.",
    )
    include_explanations: bool = Field(
        default=False,
        description="If true, compute lightweight explanation blocks for each object.",
    )


class BatchPredictionItem(BaseModel):
    input_index: int | None = None
    listing_id: str | int | None = None
    predicted_price_rub: float
    price_per_m2_rub: float
    listing_price_rub: float | None = None
    delta_abs_rub: float | None = None
    delta_pct: float | None = None
    confidence: Literal["high", "medium", "low"]
    warnings: list[str] = Field(default_factory=list)
    sanity_checks: dict[str, Any] = Field(default_factory=dict)
    base_currency: str
    output_currency: str
    listing_price: float | None = None
    listing_currency: str
    fx_rate_used: float | None = None
    price_outputs: dict[str, CurrencyPriceOutput]
    top_factors: list[str] = Field(default_factory=list)
    explanation_summary: str | None = None
    valuation_note: str
    undervaluation_rank: int | None = None


class BatchPredictionResponse(BaseModel):
    count: int
    ranked: bool
    results: list[BatchPredictionItem]


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthUserResponse(BaseModel):
    id: int
    name: str
    email: str


class OpportunityItem(BaseModel):
    listing_id: int
    title: str
    city: str | None = None
    district: str | None = None
    area: float | None = None
    rooms: int | None = None
    floor: int | None = None
    total_floors: int | None = None
    building_type: str | None = None
    condition: str | None = None
    year_built: int | None = None
    seller_type: str | None = None
    listing_price: float | None = None
    listing_currency: str
    listing_price_in_comparison_currency: float | None = None
    predicted_price: float
    predicted_price_currency: str
    comparison_currency: str
    fx_rate_used: float | None = None
    delta_abs: float
    delta_pct: float
    score: float
    confidence: Literal["high", "medium", "low"] = "medium"
    warnings: list[str] = Field(default_factory=list)
    sanity_checks: dict[str, Any] = Field(default_factory=dict)
    explanation_summary: str
    top_factors: list[str] = Field(default_factory=list)
    source_url: str | None = None
    rank_position: int | None = None
    is_saved: bool = False


class OpportunityListResponse(BaseModel):
    items: list[OpportunityItem]


class SaveShortlistRequest(BaseModel):
    listing_id: int
    rank_position: int | None = Field(default=None, ge=1)


class ShortlistMutationResponse(BaseModel):
    listing_id: int
    saved: bool


app = FastAPI(
    title="Real Estate MVP Proxy-Valuation API",
    version="0.3.0",
    description=(
        "RUB-only MVP API для proxy-оценки недвижимости по данным объявлений. "
        "Ответ является модельной оценкой, а не подтверждённой ценой сделки."
    ),
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE_NAME,
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_model_bundle() -> LoadedModelBundle:
    return load_ready_model_bundle(
        configured_model_path=DEFAULT_MODEL_PATH,
        manifest_path=MODEL_READINESS_PATH,
        model_path_is_explicit=MODEL_PATH_ENV is not None,
    )


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_currency(currency: str | None, default: str = DEFAULT_LISTING_CURRENCY) -> str:
    normalized = default if currency is None else str(currency)
    normalized = normalized.upper()
    if normalized != "RUB":
        raise ValueError("Only RUB currency is supported.")
    return normalized


def _validate_rub_rows(rows: list[dict[str, Any]], output_currency: str) -> None:
    _normalize_currency(output_currency, default=DEFAULT_LISTING_CURRENCY)
    for row in rows:
        _normalize_currency(row.get("listing_currency"), default=DEFAULT_LISTING_CURRENCY)


def _build_comparison_metrics(
    *,
    listing_price: float | None,
    listing_currency: str,
    predicted_price_base: float,
    comparison_currency: str,
) -> dict[str, float | None]:
    _normalize_currency(listing_currency)
    _normalize_currency(comparison_currency)
    predicted_price = predicted_price_base
    listing_price_in_comparison_currency = listing_price
    delta_abs = 0.0
    delta_pct = 0.0
    if predicted_price is not None and listing_price_in_comparison_currency is not None:
        delta_abs = predicted_price - listing_price_in_comparison_currency
        if listing_price_in_comparison_currency != 0:
            delta_pct = delta_abs / listing_price_in_comparison_currency

    return {
        "predicted_price": predicted_price,
        "listing_price_in_comparison_currency": listing_price_in_comparison_currency,
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
    }


def _fallback_explanation_summary() -> str:
    return (
        "Модельная proxy-оценка рассчитана по данным объявлений. Используйте её как screening-сигнал, "
        "а не как подтверждённую рыночную цену сделки."
    )


def _serialize_user(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
    )


def _serialize_opportunity(
    row: dict[str, Any],
    *,
    comparison_currency: str,
    fx_rate_used: float | None,
) -> OpportunityItem:
    listing_currency = _normalize_currency(row.get("listing_currency"), default=DEFAULT_LISTING_CURRENCY)
    source_payload = row.get("source_payload") or {}
    source_object_id = row.get("source_object_id") or row.get("listing_id")
    title = row.get("title") or payload_text(source_payload, "title") or f"Объект {source_object_id}"
    city = row.get("city") or payload_text(source_payload, "city")
    district = row.get("district") or payload_text(source_payload, "district") or row.get("region")
    condition = row.get("condition") or payload_text(source_payload, "condition")
    seller_type = row.get("seller_type") or payload_text(source_payload, "seller_type")
    year_built = row.get("year_built")
    if year_built is None:
        year_built = payload_int(source_payload, "year_built")
    comparison_metrics = _build_comparison_metrics(
        listing_price=_to_float(row["listing_price"]),
        listing_currency=listing_currency,
        predicted_price_base=float(row["predicted_price"]),
        comparison_currency=comparison_currency,
    )

    return OpportunityItem(
        listing_id=row["listing_id"],
        title=title,
        city=city,
        district=district,
        area=_to_float(row["area"]),
        rooms=row["rooms"],
        floor=row["floor"],
        total_floors=row["total_floors"],
        building_type=row.get("building_type"),
        condition=condition,
        year_built=_to_int(year_built),
        seller_type=seller_type,
        listing_price=_to_float(row["listing_price"]),
        listing_currency=listing_currency,
        listing_price_in_comparison_currency=comparison_metrics["listing_price_in_comparison_currency"],
        predicted_price=float(comparison_metrics["predicted_price"] or 0.0),
        predicted_price_currency=comparison_currency,
        comparison_currency=comparison_currency,
        fx_rate_used=fx_rate_used,
        delta_abs=float(comparison_metrics["delta_abs"] or 0.0),
        delta_pct=float(comparison_metrics["delta_pct"] or 0.0),
        score=float(row["score"]),
        confidence=row.get("confidence") or "medium",
        warnings=list(row.get("warnings") or []),
        sanity_checks=dict(row.get("sanity_checks") or {}),
        explanation_summary=row.get("explanation_summary") or _fallback_explanation_summary(),
        top_factors=list(row.get("top_factors") or []),
        source_url=row.get("source_url"),
        rank_position=row.get("rank_position"),
        is_saved=bool(row["is_saved"]),
    )


def _to_quantized_decimal(value: float, precision: str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal(precision))


def _build_scoring_payload(row: dict[str, Any], bundle: LoadedModelBundle) -> dict[str, Any]:
    row = dict(row)
    source_payload = row.get("source_payload") or {}
    row["district"] = row.get("district") or payload_text(source_payload, "district")
    row["seller_type"] = row.get("seller_type") or payload_text(source_payload, "seller_type")
    row["condition"] = row.get("condition") or payload_text(source_payload, "condition")
    row["year_built"] = row.get("year_built") or payload_int(source_payload, "year_built")
    listing_currency = _normalize_currency(row.get("listing_currency"), default=DEFAULT_LISTING_CURRENCY)
    return build_listing_model_payload(row, bundle, listing_currency=listing_currency)


def _control_listing_id_expression():
    return func.coalesce(AnalyticsControlObject.listing_id, AnalyticsControlObject.id)


def _control_floor_expression():
    return func.coalesce(AnalyticsControlObject.floor, AnalyticsControlObject.level)


def _control_total_floors_expression():
    return func.coalesce(AnalyticsControlObject.total_floors, AnalyticsControlObject.levels)


def _control_object_filter():
    return AnalyticsControlObject.sample_seed == CONTROL_OBJECT_SAMPLE_SEED


def _build_control_object_projection_query():
    return (
        select(
            AnalyticsControlObject.id.label("control_object_id"),
            AnalyticsControlObject.source_object_id.label("source_object_id"),
            AnalyticsControlObject.listing_id.label("listing_id"),
            AnalyticsControlObject.title.label("title"),
            AnalyticsControlObject.city.label("city"),
            AnalyticsControlObject.district.label("district"),
            AnalyticsControlObject.listing_price.label("listing_price"),
            AnalyticsControlObject.listing_currency.label("listing_currency"),
            AnalyticsControlObject.area.label("area"),
            AnalyticsControlObject.rooms.label("rooms"),
            AnalyticsControlObject.kitchen_area.label("kitchen_area"),
            AnalyticsControlObject.level.label("level"),
            AnalyticsControlObject.levels.label("levels"),
            _control_floor_expression().label("floor"),
            _control_total_floors_expression().label("total_floors"),
            AnalyticsControlObject.building_type.label("building_type"),
            AnalyticsControlObject.condition.label("condition"),
            AnalyticsControlObject.year_built.label("year_built"),
            AnalyticsControlObject.seller_type.label("seller_type"),
            AnalyticsControlObject.object_type.label("object_type"),
            AnalyticsControlObject.region.label("region"),
            AnalyticsControlObject.latitude.label("latitude"),
            AnalyticsControlObject.longitude.label("longitude"),
            AnalyticsControlObject.source_url.label("source_url"),
            AnalyticsControlObject.source_payload.label("source_payload"),
        )
        .where(_control_object_filter())
        .where(AnalyticsControlObject.listing_price.is_not(None))
        .where(AnalyticsControlObject.area.is_not(None))
        .order_by(AnalyticsControlObject.sample_rank.asc(), AnalyticsControlObject.id.asc())
    )


def _sync_control_objects_to_listings(session: Session) -> int:
    control_rows = session.execute(_build_control_object_projection_query()).mappings().all()
    if not control_rows:
        return 0

    listing_rows_by_id: dict[int, dict[str, Any]] = {}
    for row in control_rows:
        listing_row = listing_projection_from_control_row(dict(row))
        listing_rows_by_id[int(listing_row["id"])] = listing_row
    listing_rows = list(listing_rows_by_id.values())
    statement = insert(Listing).values(listing_rows)
    updatable_columns = (
        "title",
        "city",
        "district",
        "area",
        "kitchen_area_m2",
        "rooms",
        "floor",
        "total_floors",
        "building_type",
        "condition",
        "year_built",
        "seller_type",
        "latitude",
        "longitude",
        "listing_price",
        "listing_currency",
        "source_url",
    )
    statement = statement.on_conflict_do_update(
        index_elements=[Listing.id],
        set_={
            column_name: getattr(statement.excluded, column_name)
            for column_name in updatable_columns
        },
    )
    session.execute(statement)
    return len(listing_rows)


def _build_valuation_listing_query(*, only_missing: bool):
    listing_id_expression = _control_listing_id_expression()
    statement = (
        select(
            listing_id_expression.label("listing_id"),
            AnalyticsControlObject.source_object_id.label("source_object_id"),
            AnalyticsControlObject.source_payload.label("source_payload"),
            AnalyticsControlObject.district.label("district"),
            AnalyticsControlObject.condition.label("condition"),
            AnalyticsControlObject.year_built.label("year_built"),
            AnalyticsControlObject.seller_type.label("seller_type"),
            AnalyticsControlObject.region.label("region"),
            AnalyticsControlObject.area.label("area"),
            AnalyticsControlObject.kitchen_area.label("kitchen_area_m2"),
            AnalyticsControlObject.rooms.label("rooms"),
            _control_floor_expression().label("floor"),
            _control_total_floors_expression().label("total_floors"),
            AnalyticsControlObject.building_type.label("building_type"),
            AnalyticsControlObject.object_type.label("object_type"),
            AnalyticsControlObject.latitude.label("latitude"),
            AnalyticsControlObject.longitude.label("longitude"),
            AnalyticsControlObject.listing_price.label("listing_price"),
            AnalyticsControlObject.listing_currency.label("listing_currency"),
        )
        .select_from(AnalyticsControlObject)
        .where(_control_object_filter())
        .where(AnalyticsControlObject.listing_price.is_not(None))
        .where(AnalyticsControlObject.area.is_not(None))
        .order_by(AnalyticsControlObject.sample_rank.asc(), AnalyticsControlObject.id.asc())
    )

    if only_missing:
        statement = (
            statement.outerjoin(Valuation, Valuation.listing_id == listing_id_expression)
            .where(Valuation.id.is_(None))
        )

    return statement


def _recalculate_valuation_scores(session: Session) -> None:
    session.execute(
        text(
            """
            WITH ranked AS (
              SELECT
                id,
                row_number() OVER (
                  ORDER BY undervaluation_percent DESC, listing_id ASC
                ) AS rank_position,
                count(*) OVER () AS total_items
              FROM valuations
            )
            UPDATE valuations AS valuation
            SET score = CASE
              WHEN ranked.total_items <= 1 THEN 1.0000
              ELSE ROUND(
                1 - ((ranked.rank_position - 1)::numeric / (ranked.total_items - 1)),
                4
              )
            END
            FROM ranked
            WHERE valuation.id = ranked.id
            """
        )
    )


def ensure_listing_valuations(
    session: Session,
    *,
    only_missing: bool = True,
    include_explanations: bool = False,
) -> int:
    projected_rows = _sync_control_objects_to_listings(session)
    listing_rows = session.execute(
        _build_valuation_listing_query(only_missing=only_missing)
    ).mappings().all()

    if not listing_rows:
        if projected_rows:
            session.commit()
        LOGGER.debug(
            "valuation_backfill_skipped only_missing=%s include_explanations=%s",
            only_missing,
            include_explanations,
        )
        return 0

    started_at = perf_counter()
    bundle = get_model_bundle()
    scoring_payloads: list[dict[str, Any]] = []
    skipped_invalid = 0
    for row in listing_rows:
        payload = _build_scoring_payload(row, bundle)
        validation = validate_inference_record(payload, bundle.feature_config, bundle.metadata)
        if not validation.is_valid:
            skipped_invalid += 1
            LOGGER.warning(
                "valuation_listing_skipped listing_id=%s errors=%s",
                row["listing_id"],
                validation.errors,
            )
            continue
        scoring_payloads.append(payload)

    if not scoring_payloads:
        if projected_rows:
            session.commit()
        LOGGER.warning("valuation_backfill_no_valid_rows skipped_invalid=%s", skipped_invalid)
        return 0

    scored_results = score_proxy_valuations_from_bundle(
        objects=scoring_payloads,
        bundle=bundle,
        rank_results=False,
        include_explanations=include_explanations,
    )

    valuation_rows: list[dict[str, Any]] = []
    for result in scored_results:
        listing_id = result.get("listing_id")
        price_outputs = result.get("price_outputs", {})
        rub_output = price_outputs.get("RUB", {})
        if listing_id is None:
            continue

        predicted_price = float(rub_output["expected_price_proxy"])
        undervaluation_delta = float(rub_output["delta_abs"] or 0.0)
        undervaluation_percent = float(rub_output["delta_pct"] or 0.0)

        row_payload = {
            "listing_id": int(listing_id),
            "predicted_price": _to_quantized_decimal(predicted_price, "0.01"),
            "undervaluation_delta": _to_quantized_decimal(undervaluation_delta, "0.01"),
            "undervaluation_percent": _to_quantized_decimal(undervaluation_percent, "0.0001"),
            "score": _to_quantized_decimal(0.0, "0.0001"),
            "confidence": result.get("confidence") or "medium",
            "warnings": list(result.get("warnings") or []),
            "sanity_checks": dict(result.get("sanity_checks") or {}),
            "explanation_summary": result.get("explanation_summary") or _fallback_explanation_summary(),
            "top_factors": list(result.get("top_factors") or []),
        }

        valuation_rows.append(row_payload)

    if not valuation_rows:
        return 0

    statement = insert(Valuation).values(valuation_rows)
    update_mapping = {
        "predicted_price": statement.excluded.predicted_price,
        "undervaluation_delta": statement.excluded.undervaluation_delta,
        "undervaluation_percent": statement.excluded.undervaluation_percent,
        "score": statement.excluded.score,
        "confidence": statement.excluded.confidence,
        "warnings": statement.excluded.warnings,
        "sanity_checks": statement.excluded.sanity_checks,
        "explanation_summary": statement.excluded.explanation_summary,
        "top_factors": statement.excluded.top_factors,
    }

    statement = statement.on_conflict_do_update(
        index_elements=[Valuation.listing_id],
        set_=update_mapping,
    )
    session.execute(statement)
    _recalculate_valuation_scores(session)
    session.commit()
    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    LOGGER.info(
        "valuation_backfill_done rows=%s only_missing=%s include_explanations=%s elapsed_ms=%s",
        len(valuation_rows),
        only_missing,
        include_explanations,
        elapsed_ms,
    )
    return len(valuation_rows)


def _build_opportunity_base_query(user_id: int):
    saved_shortlist_item = aliased(ShortlistItem)
    listing_id_expression = _control_listing_id_expression()
    is_saved_expression = (
        select(saved_shortlist_item.id)
        .where(
            saved_shortlist_item.user_id == user_id,
            saved_shortlist_item.listing_id == listing_id_expression,
        )
        .exists()
    )

    return select(
        listing_id_expression.label("listing_id"),
        AnalyticsControlObject.source_object_id.label("source_object_id"),
        AnalyticsControlObject.source_payload.label("source_payload"),
        AnalyticsControlObject.title.label("title"),
        AnalyticsControlObject.city.label("city"),
        AnalyticsControlObject.district.label("district"),
        AnalyticsControlObject.region.label("region"),
        AnalyticsControlObject.area.label("area"),
        AnalyticsControlObject.rooms.label("rooms"),
        _control_floor_expression().label("floor"),
        _control_total_floors_expression().label("total_floors"),
        AnalyticsControlObject.building_type.label("building_type"),
        AnalyticsControlObject.condition.label("condition"),
        AnalyticsControlObject.year_built.label("year_built"),
        AnalyticsControlObject.seller_type.label("seller_type"),
        AnalyticsControlObject.listing_price.label("listing_price"),
        AnalyticsControlObject.listing_currency.label("listing_currency"),
        AnalyticsControlObject.source_url.label("source_url"),
        Valuation.predicted_price.label("predicted_price"),
        Valuation.score.label("score"),
        Valuation.confidence.label("confidence"),
        Valuation.warnings.label("warnings"),
        Valuation.sanity_checks.label("sanity_checks"),
        Valuation.explanation_summary.label("explanation_summary"),
        Valuation.top_factors.label("top_factors"),
        is_saved_expression.label("is_saved"),
    ).select_from(AnalyticsControlObject).join(
        Valuation,
        Valuation.listing_id == listing_id_expression,
    ).where(_control_object_filter())


def _apply_sorting(statement, sort_by: Literal["score", "undervaluation_percent"]):
    if sort_by == "undervaluation_percent":
        return statement.order_by(
            Valuation.undervaluation_percent.desc(),
            Valuation.score.desc(),
            AnalyticsControlObject.sample_rank.asc(),
            AnalyticsControlObject.id.asc(),
        )
    return statement.order_by(
        Valuation.score.desc(),
        Valuation.undervaluation_percent.desc(),
        AnalyticsControlObject.sample_rank.asc(),
        AnalyticsControlObject.id.asc(),
    )


@app.get("/health")
def health() -> dict[str, str]:
    bundle = get_model_bundle()
    readiness = (bundle.metadata or {}).get("readiness") or {}
    return {
        "status": "ok",
        "model_status": str(readiness.get("status") or "active"),
        "base_currency": bundle.base_currency,
    }


@app.post("/auth/login", response_model=AuthUserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> AuthUserResponse:
    user = session.execute(
        select(User).where(User.email == payload.email.strip().lower())
    ).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    request.session.clear()
    request.session["user_id"] = user.id
    return _serialize_user(user)


@app.post("/auth/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "ok"}


@app.get("/auth/me", response_model=AuthUserResponse)
def auth_me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return _serialize_user(current_user)


@app.get("/opportunities", response_model=OpportunityListResponse)
def get_opportunities(
    sort_by: Literal["score", "undervaluation_percent"] = Query(default="score"),
    limit: int = Query(default=100, ge=1, le=500),
    output_currency: Literal["RUB"] = Query(default="RUB"),
    fx_rate: float | None = Query(default=None, gt=0),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> OpportunityListResponse:
    started_at = perf_counter()
    backfilled_rows = ensure_listing_valuations(session, only_missing=True, include_explanations=False)
    statement = _build_opportunity_base_query(current_user.id)
    statement = _apply_sorting(statement, sort_by).limit(limit)
    rows = session.execute(statement).mappings().all()
    normalized_output_currency = _normalize_currency(output_currency, default=DEFAULT_LISTING_CURRENCY)
    _validate_rub_rows(rows, normalized_output_currency)
    response = OpportunityListResponse(
        items=[
            _serialize_opportunity(
                row,
                comparison_currency=normalized_output_currency,
                fx_rate_used=None,
            )
            for row in rows
        ]
    )
    LOGGER.info(
        "opportunities_list_ready user_id=%s sort_by=%s limit=%s rows=%s backfilled_rows=%s elapsed_ms=%s",
        current_user.id,
        sort_by,
        limit,
        len(response.items),
        backfilled_rows,
        round((perf_counter() - started_at) * 1000, 1),
    )
    return response


@app.get("/shortlist", response_model=OpportunityListResponse)
def get_shortlist(
    output_currency: Literal["RUB"] = Query(default="RUB"),
    fx_rate: float | None = Query(default=None, gt=0),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> OpportunityListResponse:
    started_at = perf_counter()
    backfilled_rows = ensure_listing_valuations(session, only_missing=True, include_explanations=False)
    listing_id_expression = _control_listing_id_expression()
    statement = (
        _build_opportunity_base_query(current_user.id)
        .join(
            ShortlistItem,
            (ShortlistItem.listing_id == listing_id_expression) & (ShortlistItem.user_id == current_user.id),
        )
        .add_columns(ShortlistItem.rank_position.label("rank_position"))
        .order_by(
            ShortlistItem.rank_position.asc(),
            Valuation.score.desc(),
            AnalyticsControlObject.sample_rank.asc(),
            AnalyticsControlObject.id.asc(),
        )
    )
    rows = session.execute(statement).mappings().all()
    normalized_output_currency = _normalize_currency(output_currency, default=DEFAULT_LISTING_CURRENCY)
    _validate_rub_rows(rows, normalized_output_currency)
    response = OpportunityListResponse(
        items=[
            _serialize_opportunity(
                row,
                comparison_currency=normalized_output_currency,
                fx_rate_used=None,
            )
            for row in rows
        ]
    )
    LOGGER.info(
        "shortlist_ready user_id=%s rows=%s backfilled_rows=%s elapsed_ms=%s",
        current_user.id,
        len(response.items),
        backfilled_rows,
        round((perf_counter() - started_at) * 1000, 1),
    )
    return response


@app.post("/shortlist", response_model=ShortlistMutationResponse)
def save_shortlist_item(
    payload: SaveShortlistRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ShortlistMutationResponse:
    ensure_listing_valuations(session, only_missing=True, include_explanations=False)
    listing_id_expression = _control_listing_id_expression()
    listing_exists = session.execute(
        select(listing_id_expression)
        .select_from(AnalyticsControlObject)
        .where(_control_object_filter(), listing_id_expression == payload.listing_id)
        .limit(1)
    ).scalar_one_or_none()
    if listing_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")

    existing_item = session.execute(
        select(ShortlistItem).where(
            ShortlistItem.user_id == current_user.id,
            ShortlistItem.listing_id == payload.listing_id,
        )
    ).scalar_one_or_none()

    if existing_item is None:
        max_rank = session.execute(
            select(func.max(ShortlistItem.rank_position)).where(ShortlistItem.user_id == current_user.id)
        ).scalar_one()
        next_rank = int(max_rank or 0) + 1
        existing_item = ShortlistItem(
            user_id=current_user.id,
            listing_id=payload.listing_id,
            rank_position=payload.rank_position or next_rank,
        )
        session.add(existing_item)
    elif payload.rank_position is not None:
        existing_item.rank_position = payload.rank_position

    session.commit()
    return ShortlistMutationResponse(listing_id=payload.listing_id, saved=True)


@app.delete("/shortlist/{listing_id}", response_model=ShortlistMutationResponse)
def delete_shortlist_item(
    listing_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ShortlistMutationResponse:
    existing_item = session.execute(
        select(ShortlistItem).where(
            ShortlistItem.user_id == current_user.id,
            ShortlistItem.listing_id == listing_id,
        )
    ).scalar_one_or_none()

    if existing_item is not None:
        session.delete(existing_item)
        session.commit()

    return ShortlistMutationResponse(listing_id=listing_id, saved=False)


@app.post("/predict", response_model=PredictionResponse)
def predict(request: SinglePredictionRequest) -> PredictionResponse:
    try:
        bundle = get_model_bundle()
        result = predict_proxy_valuation_from_bundle(
            object_features=request.object_features,
            bundle=bundle,
            output_currency=request.output_currency,
            fx_rate=request.fx_rate,
            default_fx_rate=1.0,
            include_explanation=request.include_explanation,
        )
        return PredictionResponse(**_sanitize_for_json(result))
    except (FileNotFoundError, ModelReadinessError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {exc}") from exc


@app.post("/predict/batch", response_model=BatchPredictionResponse)
def predict_batch(request: BatchPredictionRequest) -> BatchPredictionResponse:
    try:
        bundle = get_model_bundle()
        objects_with_index = []
        for index, item in enumerate(request.objects):
            enriched_item = dict(item)
            enriched_item["input_index"] = index
            objects_with_index.append(enriched_item)

        results = score_proxy_valuations_from_bundle(
            objects=objects_with_index,
            bundle=bundle,
            output_currency=request.output_currency,
            fx_rate=request.fx_rate,
            default_fx_rate=1.0,
            rank_results=request.rank_by_undervaluation,
            include_explanations=request.include_explanations,
        )
        return BatchPredictionResponse(
            count=len(results),
            ranked=request.rank_by_undervaluation,
            results=_sanitize_for_json(results),
        )
    except (FileNotFoundError, ModelReadinessError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Batch prediction failed: {exc}") from exc


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "real-estate-mvp-api",
        "mode": "proxy-valuation",
        "base_currency": MODEL_BASE_CURRENCY,
        "currency_mode": "RUB-only",
        "docs_url": "/docs",
        "health_url": "/health",
        "login_url": "/auth/login",
        "current_user_url": "/auth/me",
        "opportunities_url": "/opportunities",
        "shortlist_url": "/shortlist",
        "predict_url": "/predict",
        "batch_predict_url": "/predict/batch",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
