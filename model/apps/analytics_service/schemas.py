from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.apps.analytics_service.config import ALIAS_GROUPS, DEFAULT_CURRENCY, REJECTED_DERIVED_FIELDS


ScoreMethod = Literal["price_per_meter", "formula", "regression"]


def _has_value(value: Any) -> bool:
    return value is not None and value != ""


def _normalize_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    rejected_fields = sorted(set(normalized) & REJECTED_DERIVED_FIELDS)
    if rejected_fields:
        joined = ", ".join(rejected_fields)
        raise ValueError(f"Производные признаки (derived features) нельзя передавать во входном payload: {joined}.")

    for canonical_name, aliases in ALIAS_GROUPS.items():
        canonical_value = normalized.get(canonical_name)
        selected_alias = None
        for alias in aliases:
            if alias in normalized and _has_value(normalized.get(alias)):
                selected_alias = alias
                alias_value = normalized[alias]
                if _has_value(canonical_value) and canonical_value != alias_value:
                    raise ValueError(
                        f"Поля {canonical_name} и {alias} переданы одновременно с разными значениями."
                    )
                if not _has_value(canonical_value):
                    normalized[canonical_name] = alias_value
                break
        for alias in aliases:
            normalized.pop(alias, None)

    return normalized


class RealEstateScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    listing_id: str | int | None = None
    rooms: int | None = Field(default=None, ge=0)
    area: float = Field(..., gt=0)
    kitchen_area: float | None = Field(default=None, ge=0)
    level: int | None = Field(default=None, ge=1)
    levels: int | None = Field(default=None, ge=1)
    building_type: str | int | None = None
    object_type: str | int | None = None
    region: str | int | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    listing_price: float | None = Field(default=None, gt=0)
    listing_currency: str = DEFAULT_CURRENCY

    city: str | None = None
    district: str | None = None
    living_area_m2: float | None = Field(default=None, ge=0)
    ceiling_height: float | None = Field(default=None, gt=0)
    building_series: str | None = None
    year_built: int | None = Field(default=None, ge=1800)
    condition: str | None = None
    heating: str | None = None
    gas_supply: str | None = None
    bathroom: str | None = None
    balcony: str | None = None
    parking: str | None = None
    furniture: str | None = None
    flooring: str | None = None
    door_type: str | None = None
    has_landline_phone: bool | None = None
    internet: str | None = None
    mortgage: bool | None = None
    seller_type: str | None = None
    photo_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def normalize_alias_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return _normalize_aliases(data)
        return data

    @model_validator(mode="after")
    def validate_business_rules(self) -> "RealEstateScoreRequest":
        self.listing_currency = self.listing_currency.upper()
        if self.listing_currency != DEFAULT_CURRENCY:
            raise ValueError("Новый analytics service работает только с listing_currency=RUB; FX не поддерживается.")
        if self.kitchen_area is not None and self.kitchen_area > self.area:
            raise ValueError("kitchen_area не может быть больше area.")
        if self.level is not None and self.levels is not None and self.level > self.levels:
            raise ValueError("level не может быть больше levels.")
        return self

    def model_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class InputSummary(BaseModel):
    rooms: int | None = None
    area: float
    kitchen_area: float | None = None
    level: int | None = None
    levels: int | None = None
    building_type: str | int | None = None
    object_type: str | int | None = None
    region: str | int | None = None
    latitude: float | None = None
    longitude: float | None = None
    listing_price: float | None = None
    listing_currency: str = DEFAULT_CURRENCY


class FormulaComponent(BaseModel):
    field: str
    value: float
    coefficient: float
    contribution: float


class PricePerMeterScoreResponse(BaseModel):
    method: Literal["price_per_meter"]
    input_summary: InputSummary
    score: float
    analytical_score: float
    price_per_m2_score: float
    interpretation: str
    listing_price: float
    area: float
    price_per_m2: float


class FormulaScoreResponse(BaseModel):
    method: Literal["formula"]
    input_summary: InputSummary
    score: float
    expected_price_proxy: float
    listing_price: float | None = None
    delta_abs: float | None = None
    delta_pct: float | None = None
    output_currency: Literal["RUB"] = "RUB"
    coefficients_used: dict[str, float]
    formula_components: list[FormulaComponent]
    interpretation: str


class RegressionScoreResponse(BaseModel):
    method: Literal["regression"]
    expected_price_proxy: float
    listing_price: float | None = None
    delta_abs: float | None = None
    delta_pct: float | None = None
    output_currency: Literal["RUB"] = "RUB"
    valuation_note: str
    explanation_summary: str | None = None
    top_factors: list[str] = Field(default_factory=list)


ScoreResponse = PricePerMeterScoreResponse | FormulaScoreResponse | RegressionScoreResponse
