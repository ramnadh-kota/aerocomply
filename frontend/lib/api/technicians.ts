// Typed REAL-mode client for the backend personnel/technician-qualification
// endpoints (backend/app/api/v1/users.py, backend/app/api/v1/technicians.py).
// organization_id is never sent by the client — the backend derives it from
// the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendOrganizationUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  created_at: string;
}

export interface BackendTechnicianQualification {
  id: string;
  organization_id: string;
  user_id: string;
  aircraft_type: string;
  qualification_type: string;
  granted_at: string;
  expires_at: string | null;
  revoked: boolean;
  granted_by_user_id: string | null;
  created_at: string;
}

export const usersApi = {
  list: (accessToken: string) => apiRequest<BackendOrganizationUser[]>("/users", { accessToken }),
};

export const technicianQualificationsApi = {
  list: (accessToken: string, userId?: string) =>
    apiRequest<BackendTechnicianQualification[]>(
      userId ? `/technician-qualifications?user_id=${userId}` : "/technician-qualifications",
      { accessToken }
    ),
};
