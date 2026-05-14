import { getApiBaseUrl } from "../config/env";

type ApiFetchOptions = RequestInit & {
  json?: unknown;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

function createApiUrl(path: string) {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const normalizedBase = getApiBaseUrl().replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const requestInit: RequestInit = {
    ...options,
    credentials: "include",
    headers,
  };

  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    requestInit.body = JSON.stringify(options.json);
  }

  const response = await fetch(createApiUrl(path), requestInit);
  const payload = await parseResponseBody(response);

  if (!response.ok) {
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : typeof payload === "string" && payload.trim().length > 0
          ? payload
        : `Request failed with status ${response.status}.`;
    throw new ApiError(message, response.status);
  }

  if (typeof payload === "string") {
    throw new ApiError("API returned an invalid JSON response.", response.status);
  }

  return payload as T;
}
