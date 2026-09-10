// Typed REAL-mode client for the backend AOG recovery synthesis endpoint
// (backend/app/api/v1/aog.py: GET /aog-events/recovery-status/{aircraft_id}).
// organization_id is never sent — the backend derives it from the JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendRecoveryBlocker {
  category: string;
  description: string;
  record_type: string;
  record_id: string | null;
  who_should_act: string;
  dependency: string;
}

export interface BackendAogRecoveryStatus {
  aircraft_id: string;
  registration: string;
  is_aog: boolean;
  aog_event_id: string | null;
  aog_status: string | null;
  severity: string | null;
  work_order_id: string | null;
  release_readiness_status: string | null;
  tat_status: string | null;
  tat_reason: string | null;
  blockers: BackendRecoveryBlocker[];
  next_best_action: BackendRecoveryBlocker | null;
  technician_authorization: string;
  eta: string;
  compliance_status: string;
  data_completeness: string;
}

export const aogRecoveryApi = {
  getRecoveryStatus: (accessToken: string, aircraftId: string) =>
    apiRequest<BackendAogRecoveryStatus>(`/aog-events/recovery-status/${aircraftId}`, {
      accessToken,
    }),
};
