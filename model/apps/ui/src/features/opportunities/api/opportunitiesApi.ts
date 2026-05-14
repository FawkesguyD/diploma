import { apiFetch } from "../../../shared/api/client";
import { OpportunityBackendSortBy, OpportunityListResponse } from "../model/types";
import { mapOpportunityListResponse } from "./opportunityMappers";

export async function getOpportunities(sortBy: OpportunityBackendSortBy) {
  const query = new URLSearchParams({
    sort_by: sortBy,
    limit: "100",
    output_currency: "RUB",
  });

  const payload = await apiFetch<unknown>(`/opportunities?${query.toString()}`);
  return mapOpportunityListResponse(payload, "opportunities");
}
