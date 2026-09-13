// Typed REAL-mode client for the platform-level audit read API
// (backend/app/api/v1/platform.py GET /platform/audit). Requires the
// PLATFORM_MANAGE permission on the backend — same precedent as
// lib/api/platform.ts. Strictly read-only: this client has no create/update/
// delete methods, and never will — the audit trail is append-only and the
// frontend must never write to it.

import { apiRequest } from "@/lib/apiClient";

export interface AuditEventResponse {
  id: string;
  organization_id: string;
  created_at: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  event_metadata: Record<string, unknown>;
}

export interface AuditEventListResponse {
  items: AuditEventResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditEventListParams {
  organization_id?: string;
  action?: string;
  entity_type?: string;
  date_from?: string; // ISO datetime string
  date_to?: string; // ISO datetime string
  limit?: number;
  offset?: number;
}

export const auditApi = {
  listAuditEvents: (accessToken: string, params: AuditEventListParams = {}) => {
    const query = new URLSearchParams();
    if (params.organization_id) query.set("organization_id", params.organization_id);
    if (params.action) query.set("action", params.action);
    if (params.entity_type) query.set("entity_type", params.entity_type);
    if (params.date_from) query.set("date_from", params.date_from);
    if (params.date_to) query.set("date_to", params.date_to);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    const qs = query.toString();
    return apiRequest<AuditEventListResponse>(`/platform/audit${qs ? `?${qs}` : ""}`, { accessToken });
  },
};
