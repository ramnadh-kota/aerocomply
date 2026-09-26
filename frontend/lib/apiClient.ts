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
  /** Abort the request after this many ms (per attempt). Opt-in; default is no timeout. */
  timeoutMs?: number;
  /**
   * If the request fails at the network level (fetch throws — connection
   * refused/reset, DNS failure, CORS, or our own timeout below), retry ONCE
   * after a short delay. Never applies to a completed HTTP response (4xx/5xx),
   * only to a fetch() that never got a response at all. Opt-in; default false.
   */
  retryOnNetworkFailure?: boolean;
  /** Called once, right before the single network-failure retry fires. */
  onRetry?: () => void;
}

const NETWORK_RETRY_DELAY_MS = 1000;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * True for a failure that means the request never reached/returned from the
 * server at all: fetch()'s own TypeError (offline, DNS, connection
 * refused/reset, CORS), or our AbortController firing on timeout. An HTTP
 * error response (4xx/5xx) never reaches this — fetch() resolves normally
 * for those, so they're handled separately below and are never retried here.
 */
function isNetworkLevelFailure(err: unknown): boolean {
  if (err instanceof TypeError) return true;
  return err instanceof DOMException && err.name === "AbortError";
}

/** Normalize a network-level failure to a TypeError so normalizeApiError's `offline` branch catches it (a timeout's AbortError isn't naturally a TypeError). */
function toNetworkError(err: unknown): TypeError {
  if (err instanceof TypeError) return err;
  return new TypeError("Network request failed");
}

async function fetchOnce(
  path: string,
  method: string,
  headers: Record<string, string>,
  body: BodyInit | undefined,
  timeoutMs: number | undefined
): Promise<Response> {
  if (!timeoutMs) {
    return fetch(`${API_BASE_URL}${path}`, { method, headers, body });
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${API_BASE_URL}${path}`, { method, headers, body, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, accessToken, timeoutMs, retryOnNetworkFailure, onRetry } = options;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const serializedBody = body !== undefined ? JSON.stringify(body) : undefined;

  let response: Response;
  try {
    response = await fetchOnce(path, method, headers, serializedBody, timeoutMs);
  } catch (err) {
    if (retryOnNetworkFailure && isNetworkLevelFailure(err)) {
      onRetry?.();
      await delay(NETWORK_RETRY_DELAY_MS);
      try {
        response = await fetchOnce(path, method, headers, serializedBody, timeoutMs);
      } catch (retryErr) {
        throw toNetworkError(retryErr);
      }
    } else {
      throw toNetworkError(err);
    }
  }

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

/**
 * Multipart file upload — a separate helper from apiRequest because a
 * FormData body must NOT be JSON.stringified and must NOT set its own
 * Content-Type (the browser sets the multipart boundary automatically).
 * Same error handling/shape as apiRequest otherwise.
 */
export async function apiUploadFile<T>(
  path: string,
  file: File,
  options: { accessToken?: string } = {}
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });

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
  email_verified: boolean;
  phone_number?: string | null;
  profile_photo_url?: string | null;
  pending_email?: string | null;
}

export interface MessageResponse {
  message: string;
}

// Generous enough to ride out a cold-started backend (e.g. Render free/starter
// tier spinning an idle instance back up) without the user seeing a false
// "invalid credentials" or network error on an otherwise-successful login.
const LOGIN_TIMEOUT_MS = 20000;

export const authApi = {
  login: (email: string, password: string, opts: { onRetry?: () => void } = {}) =>
    apiRequest<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
      timeoutMs: LOGIN_TIMEOUT_MS,
      retryOnNetworkFailure: true,
      onRetry: opts.onRetry,
    }),

  registerOrganization: (payload: {
    organization_name: string;
    admin_email: string;
    admin_full_name: string;
    admin_password: string;
  }) => apiRequest<TokenResponse>("/auth/register-organization", { method: "POST", body: payload }),

  me: (accessToken: string) => apiRequest<CurrentUser>("/auth/me", { accessToken }),

  updateMe: (accessToken: string, payload: { full_name?: string; phone_number?: string | null }) =>
    apiRequest<CurrentUser>("/auth/me", { method: "PATCH", body: payload, accessToken }),

  uploadPhoto: (accessToken: string, file: File) =>
    apiUploadFile<CurrentUser>("/auth/me/photo", file, { accessToken }),

  deletePhoto: (accessToken: string) =>
    apiRequest<CurrentUser>("/auth/me/photo", { method: "DELETE", accessToken }),

  requestEmailVerification: (accessToken: string) =>
    apiRequest<MessageResponse>("/auth/verify-email/request", { method: "POST", accessToken }),

  confirmEmailVerification: (accessToken: string, code: string) =>
    apiRequest<MessageResponse>("/auth/verify-email/confirm", { method: "POST", body: { code }, accessToken }),

  requestEmailChange: (accessToken: string, new_email: string) =>
    apiRequest<MessageResponse>("/auth/me/change-email/request", {
      method: "POST",
      body: { new_email },
      accessToken,
    }),

  confirmEmailChange: (accessToken: string, code: string) =>
    apiRequest<CurrentUser>("/auth/me/change-email/confirm", {
      method: "POST",
      body: { code },
      accessToken,
    }),

  cancelEmailChange: (accessToken: string) =>
    apiRequest<CurrentUser>("/auth/me/change-email/cancel", {
      method: "POST",
      accessToken,
    }),

  forgotPassword: (email: string) =>
    apiRequest<MessageResponse>("/auth/forgot-password", { method: "POST", body: { email } }),

  resetPassword: (email: string, code: string, new_password: string) =>
    apiRequest<MessageResponse>("/auth/reset-password", {
      method: "POST",
      body: { email, code, new_password },
    }),
};

// Local storage keys for JWT tokens — shared across the app (login page,
// SessionContext, apiRequest callers). Kept here since apiClient owns the
// token contract.
export const ACCESS_TOKEN_STORAGE_KEY = "aerocomply_access_token";
export const REFRESH_TOKEN_STORAGE_KEY = "aerocomply_refresh_token";
