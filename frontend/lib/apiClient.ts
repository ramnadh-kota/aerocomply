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

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
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
    body: body ? JSON.stringify(body) : undefined,
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
