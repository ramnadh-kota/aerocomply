// Typed REAL-mode client for the Platform Control Plane's soft-delete
// governance endpoints (backend/app/api/v1/platform.py,
// GET/POST /platform/deleted-records/...). Restore requires the backend's
// Permission.DATA_RESTORE; permanent-delete requires the narrower
// Permission.DATA_PERMANENT_DELETE (PLATFORM_ADMIN only) -- both enforced
// server-side, never by this client.

import { apiRequest } from "@/lib/apiClient";
import type { AssetResponse } from "@/lib/api/assets";

// Minimal shape of backend/app/schemas/work_order.py's WorkOrderResponse --
// no richer WorkOrder client type exists on the frontend yet (work orders
// are managed entirely server-side / via LISA today), so this is scoped to
// exactly what the restore action below returns.
export interface WorkOrderResponse {
  id: string;
  organization_id: string;
  aircraft_id: string | null;
  asset_id: string | null;
  work_order_number: string;
  status: string;
  priority: string;
  created_by_user_id: string | null;
  created_at: string;
}

export interface DeletedRecordResponse {
  entity_type: string;
  entity_id: string;
  organization_id: string;
  identifier: string | null;
  asset_type: string | null;
  status: string;
  deleted_at: string;
  deleted_by: string | null;
  deletion_reason: string | null;
  restored_at: string | null;
  restored_by: string | null;
}

export interface DeletedRecordListResponse {
  items: DeletedRecordResponse[];
  total: number;
  limit: number;
  offset: number;
}

export const deletionApi = {
  listDeletedRecords: (
    accessToken: string,
    params?: {
      entity_type?: "ASSET" | "ORGANIZATION" | "WORKORDER";
      organization_id?: string;
      limit?: number;
      offset?: number;
    }
  ) => {
    const query = new URLSearchParams();
    if (params?.entity_type) query.set("entity_type", params.entity_type);
    if (params?.organization_id) query.set("organization_id", params.organization_id);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return apiRequest<DeletedRecordListResponse>(
      `/platform/deleted-records${qs ? `?${qs}` : ""}`,
      { accessToken }
    );
  },

  restoreAsset: (accessToken: string, assetId: string) =>
    apiRequest<AssetResponse>(`/platform/deleted-records/assets/${assetId}/restore`, {
      accessToken,
      method: "POST",
    }),

  permanentlyDeleteAsset: (accessToken: string, assetId: string, reason: string) =>
    apiRequest<{ message: string }>(
      `/platform/deleted-records/assets/${assetId}/permanent-delete`,
      {
        accessToken,
        method: "POST",
        body: { reason, confirm: true },
      }
    ),

  restoreOrganization: (accessToken: string, organizationId: string) =>
    apiRequest<{ message: string }>(
      `/platform/deleted-records/organizations/${organizationId}/restore`,
      { accessToken, method: "POST" }
    ),

  permanentlyDeleteOrganization: (accessToken: string, organizationId: string, reason: string) =>
    apiRequest<{ message: string }>(
      `/platform/deleted-records/organizations/${organizationId}/permanent-delete`,
      {
        accessToken,
        method: "POST",
        body: { reason, confirm: true },
      }
    ),

  restoreWorkOrder: (accessToken: string, workOrderId: string) =>
    apiRequest<WorkOrderResponse>(`/platform/deleted-records/work-orders/${workOrderId}/restore`, {
      accessToken,
      method: "POST",
    }),

  permanentlyDeleteWorkOrder: (accessToken: string, workOrderId: string, reason: string) =>
    apiRequest<{ message: string }>(
      `/platform/deleted-records/work-orders/${workOrderId}/permanent-delete`,
      {
        accessToken,
        method: "POST",
        body: { reason, confirm: true },
      }
    ),
};
