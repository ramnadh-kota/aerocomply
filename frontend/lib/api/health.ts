// Typed REAL-mode client for the platform-level health read API
// (backend/app/api/v1/platform.py GET /platform/health, M13). Requires the
// PLATFORM_MANAGE permission on the backend — same precedent as
// lib/api/platform.ts and lib/api/audit.ts. Strictly read-only: this is an
// on-demand snapshot, never a subscription/streaming connection, and this
// client has no write methods.

import { apiRequest } from "@/lib/apiClient";

export interface ComponentHealthResponse {
  name: string;
  status: string;
  detail: string;
  latency_ms: number | null;
}

export interface PlatformHealthResponse {
  overall_status: string;
  checked_at: string;
  components: ComponentHealthResponse[];
}

export const healthApi = {
  getPlatformHealth: (accessToken: string) =>
    apiRequest<PlatformHealthResponse>("/platform/health", { accessToken }),
};
