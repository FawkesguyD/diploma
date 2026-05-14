import { apiFetch } from "../../../shared/api/client";
import { OpportunityListResponse } from "../../opportunities/model/types";
import { mapOpportunityListResponse } from "../../opportunities/api/opportunityMappers";

export async function getShortlist() {
  const payload = await apiFetch<unknown>("/shortlist?output_currency=RUB");
  return mapOpportunityListResponse(payload, "shortlist");
}

export function saveShortlistItem(listingId: number, rankPosition?: number | null) {
  return apiFetch<{ listing_id: number; saved: boolean }>("/shortlist", {
    method: "POST",
    json: {
      listing_id: listingId,
      rank_position: rankPosition ?? undefined,
    },
  });
}

export function deleteShortlistItem(listingId: number) {
  return apiFetch<{ listing_id: number; saved: boolean }>(`/shortlist/${listingId}`, {
    method: "DELETE",
  });
}
