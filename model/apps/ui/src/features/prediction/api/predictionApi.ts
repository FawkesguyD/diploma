import { apiFetch, ApiError } from "../../../shared/api/client";
import { PredictionResponse, PredictObjectInput } from "../model/types";

function buildObjectFeatures(input: PredictObjectInput): Record<string, unknown> {
  const features: Record<string, unknown> = {};

  if (input.rooms !== null) features.rooms = input.rooms;
  if (input.area !== null) features.area = input.area;
  if (input.kitchen_area_m2 !== null) features.kitchen_area_m2 = input.kitchen_area_m2;
  if (input.floor !== null) features.floor = input.floor;
  if (input.total_floors !== null) features.total_floors = input.total_floors;
  if (input.building_type) features.building_type = input.building_type;
  if (input.object_type) features.object_type = input.object_type;
  if (input.region) features.region = input.region;
  if (input.latitude !== null) features.latitude = input.latitude;
  if (input.longitude !== null) features.longitude = input.longitude;
  if (input.listing_price !== null) features.listing_price = input.listing_price;
  features.listing_currency = input.listing_currency;

  return features;
}

export async function predictObject(input: PredictObjectInput): Promise<PredictionResponse> {
  const payload = await apiFetch<unknown>("/predict", {
    method: "POST",
    json: {
      object_features: buildObjectFeatures(input),
      output_currency: "RUB",
      include_explanation: true,
    },
  });

  if (payload === null || typeof payload !== "object") {
    throw new ApiError("Invalid prediction response.", 500);
  }

  return payload as PredictionResponse;
}
