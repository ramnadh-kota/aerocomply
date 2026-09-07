const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
  }
}

/**
 * Stable, UI-facing error classification. Backend error codes/messages are
 * never shown raw to the user (no stack traces, no internal error strings) —
 * every ApiError (and network failure) collapses into one of these kinds
 * with a safe, human-readable message.
 */
export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "validation"
  | "conflict"
  | "server"
  | "offline"
  | "unknown";

export interface NormalizedApiError {
  kind: ApiErrorKind;
  message: string;
  status?: number;
}

const DEFAULT_MESSAGES: Record<ApiErrorKind, string> = {
  unauthorized: "Your session has expired. Please sign in again.",
  forbidden: "You do not have permission to perform this action.",
  not_found: "The requested item could not be found.",
  validation: "The request could not be processed — please check the submitted data.",
  conflict: "This action conflicts with the item's current state.",
  server: "The server encountered an error. Please try again later.",
  offline: "Unable to reach the server. Check your connection and try again.",
  unknown: "Something went wrong. Please try again.",
};

/** Map any thrown error (ApiError or network failure) to a stable, safe shape for the UI. */
export function normalizeApiError(err: unknown): NormalizedApiError {
  if (err instanceof ApiError) {
    let kind: ApiErrorKind;
    switch (err.status) {
      case 401:
        kind = "unauthorized";
        break;
      case 403:
        kind = "forbidden";
        break;
      case 404:
        kind = "not_found";
        break;
      case 422:
        kind = "validation";
        break;
      case 409:
        kind = "conflict";
        break;
      default:
        kind = err.status >= 500 ? "server" : "unknown";
    }
    // Backend messages for 4xx are already user-safe (validation/business
    // errors); 5xx bodies may leak internals, so use the generic message.
    const message = kind === "server" ? DEFAULT_MESSAGES.server : err.message || DEFAULT_MESSAGES[kind];
    return { kind, message, status: err.status };
  }
  // fetch() throws TypeError on network failure (server down, no connection, CORS).
  if (err instanceof TypeError) {
    return { kind: "offline", message: DEFAULT_MESSAGES.offline };
  }
  return { kind: "unknown", message: DEFAULT_MESSAGES.unknown };
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  accessToken?: string;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, accessToken } = options;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorBody = data?.error ?? { code: "unknown_error", message: "Request failed" };
    throw new ApiError(response.status, errorBody.code, errorBody.message);
  }

  return data as T;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CurrentUser {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  roles: string[];
}

export const authApi = {
  login: (email: string, password: string) =>
    apiRequest<TokenResponse>("/auth/login", { method: "POST", body: { email, password } }),

  registerOrganization: (payload: {
    organization_name: string;
    admin_email: string;
    admin_full_name: string;
    admin_password: string;
  }) => apiRequest<TokenResponse>("/auth/register-organization", { method: "POST", body: payload }),

  me: (accessToken: string) => apiRequest<CurrentUser>("/auth/me", { accessToken }),
};

// Local storage keys for JWT tokens — shared across the app (login page,
// SessionContext, apiRequest callers). Kept here since apiClient owns the
// token contract.
export const ACCESS_TOKEN_STORAGE_KEY = "aerocomply_access_token";
export const REFRESH_TOKEN_STORAGE_KEY = "aerocomply_refresh_token";
