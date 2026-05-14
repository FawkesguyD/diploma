export type OpportunityBackendSortBy = "score" | "undervaluation_percent";

export type OpportunitySortBy =
  | OpportunityBackendSortBy
  | "listing_price"
  | "predicted_price";

export type Opportunity = {
  listing_id: number;
  title: string;
  city: string | null;
  district: string | null;
  area: number | null;
  rooms: number | null;
  floor: number | null;
  total_floors: number | null;
  building_type: string | null;
  condition: string | null;
  year_built: number | null;
  seller_type: string | null;
  listing_price: number | null;
  listing_currency: "RUB";
  listing_price_in_comparison_currency: number | null;
  predicted_price: number;
  predicted_price_currency: "RUB";
  comparison_currency: "RUB";
  fx_rate_used: number | null;
  delta_abs: number;
  delta_pct: number;
  score: number;
  confidence: "high" | "medium" | "low";
  warnings: string[];
  sanity_checks: Record<string, unknown>;
  explanation_summary: string;
  top_factors: string[];
  source_url: string | null;
  rank_position: number | null;
  is_saved: boolean;
};

export type OpportunityListResponse = {
  items: Opportunity[];
};
