import { useQuery } from "@tanstack/react-query";

import { ApiError, isApiError } from "../../../shared/api/client";
import { getCurrentUser } from "../api/authApi";
import { CURRENT_USER_QUERY_KEY } from "./types";

export function useCurrentUser() {
  return useQuery({
    queryKey: CURRENT_USER_QUERY_KEY,
    staleTime: 5 * 60 * 1000,
    queryFn: async () => {
      try {
        return await getCurrentUser();
      } catch (error) {
        if (isApiError(error) && error.status === 401) {
          return null;
        }
        throw error;
      }
    },
  });
}

export function getReadableAuthError(error: unknown, fallback = "Authentication check failed.") {
  if (isApiError(error)) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return fallback;
}
