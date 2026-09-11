// Typed REAL-mode client for the backend Lisa conversation-context
// endpoints (backend/app/api/v1/lisa.py: GET/POST /lisa/context...).
// organization_id/user_id are never sent — the backend derives them from
// the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendLisaConversationContext {
  id: string;
  organization_id: string;
  user_id: string;
  current_aircraft_id: string | null;
  current_work_order_id: string | null;
  current_task_id: string | null;
  current_part_id: string | null;
  current_part_requirement_id: string | null;
  current_procurement_request_id: string | null;
  current_vendor_id: string | null;
  current_purchase_order_id: string | null;
  current_technician_user_id: string | null;
  current_aog_event_id: string | null;
  previous_question: string | null;
  context_version: number;
  last_activity_at: string;
}

export const lisaContextApi = {
  get: (accessToken: string) =>
    apiRequest<BackendLisaConversationContext>("/lisa/context", { accessToken }),
  reset: (accessToken: string) =>
    apiRequest<BackendLisaConversationContext>("/lisa/context/reset", {
      method: "POST",
      accessToken,
    }),
};
