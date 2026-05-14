export type Confidence = "high" | "medium" | "low";

export type CurrencyPriceOutput = {
  expected_price_proxy: number;
  comparison_currency: "RUB";
  predicted_price_currency: "RUB";
  listing_price_in_comparison_currency: number | null;
  delta_abs: number | null;
  delta_pct: number | null;
};

export type PredictionResponse = {
  predicted_price_rub: number;
  price_per_m2_rub: number;
  listing_price_rub: number | null;
  delta_abs_rub: number | null;
  delta_pct: number | null;
  confidence: Confidence;
  warnings: string[];
  sanity_checks: Record<string, unknown>;
  base_currency: string;
  output_currency: string;
  listing_price: number | null;
  listing_currency: "RUB";
  fx_rate_used: number | null;
  price_outputs: Record<string, CurrencyPriceOutput>;
  top_factors: string[];
  explanation_summary: string | null;
  valuation_note: string;
};

export type PredictObjectInput = {
  rooms: number | null;
  area: number | null;
  kitchen_area_m2: number | null;
  floor: number | null;
  total_floors: number | null;
  building_type: string | null;
  object_type: string | null;
  region: string | null;
  latitude: number | null;
  longitude: number | null;
  listing_price: number | null;
  listing_currency: "RUB";
};
