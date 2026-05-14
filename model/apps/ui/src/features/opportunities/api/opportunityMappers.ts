import { ApiError } from "../../../shared/api/client";
import { Opportunity, OpportunityListResponse } from "../model/types";

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function toBoolean(value: unknown): boolean {
  return value === true;
}

function toCurrency(value: unknown, fallback: "RUB" = "RUB"): "RUB" {
  return value === "RUB" ? value : fallback;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function toConfidence(value: unknown): "high" | "medium" | "low" {
  return value === "high" || value === "medium" || value === "low" ? value : "medium";
}

function toRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function mapOpportunityItem(payload: unknown, index: number, resourceName: string): Opportunity {
  if (payload === null || typeof payload !== "object") {
    throw new ApiError(`Invalid ${resourceName} item at index ${index}.`, 500);
  }

  const item = payload as Record<string, unknown>;
  const listingId = toNumber(item.listing_id);
  const predictedPrice = toNumber(item.predicted_price);
  const deltaAbs = toNumber(item.delta_abs);
  const deltaPct = toNumber(item.delta_pct);
  const score = toNumber(item.score);

  if (
    listingId === null ||
    predictedPrice === null ||
    deltaAbs === null ||
    deltaPct === null ||
    score === null
  ) {
    throw new ApiError(`Invalid ${resourceName} response format.`, 500);
  }

  return {
    listing_id: listingId,
    title: toStringOrNull(item.title) ?? `Listing ${listingId}`,
    city: toStringOrNull(item.city),
    district: toStringOrNull(item.district),
    area: toNumber(item.area),
    rooms: toNumber(item.rooms),
    floor: toNumber(item.floor),
    total_floors: toNumber(item.total_floors),
    building_type: toStringOrNull(item.building_type),
    condition: toStringOrNull(item.condition),
    year_built: toNumber(item.year_built),
    seller_type: toStringOrNull(item.seller_type),
    listing_price: toNumber(item.listing_price),
    listing_currency: toCurrency(item.listing_currency),
    listing_price_in_comparison_currency: toNumber(item.listing_price_in_comparison_currency),
    predicted_price: predictedPrice,
    predicted_price_currency: toCurrency(item.predicted_price_currency),
    comparison_currency: toCurrency(item.comparison_currency),
    fx_rate_used: toNumber(item.fx_rate_used),
    delta_abs: deltaAbs,
    delta_pct: deltaPct,
    score,
    confidence: toConfidence(item.confidence),
    warnings: toStringArray(item.warnings),
    sanity_checks: toRecord(item.sanity_checks),
    explanation_summary:
      toStringOrNull(item.explanation_summary) ??
      "Model estimate is a proxy valuation based on listing data.",
    top_factors: toStringArray(item.top_factors),
    source_url: toStringOrNull(item.source_url),
    rank_position: toNumber(item.rank_position),
    is_saved: toBoolean(item.is_saved),
  };
}

export function mapOpportunityListResponse(
  payload: unknown,
  resourceName: "opportunities" | "shortlist",
): OpportunityListResponse {
  if (payload === null || typeof payload !== "object") {
    throw new ApiError(`Invalid ${resourceName} response format.`, 500);
  }

  const items = (payload as { items?: unknown }).items;
  if (!Array.isArray(items)) {
    throw new ApiError(`Invalid ${resourceName} response format.`, 500);
  }

  return {
    items: items.map((item, index) => mapOpportunityItem(item, index, resourceName)),
  };
}
