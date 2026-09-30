// Typed REAL-mode client for the maintenance requirement register (backend/app/api/v1/maintenance.py).
import { apiRequest } from "@/lib/apiClient";

export interface BackendMaintenanceRequirement {
  id: string;
  organization_id: string;
  description: string;
  ata_chapter: string;
  interval_type: string;
  fh_interval: number | null;
  fc_interval: number | null;
  calendar_interval_days: number | null;
  task_reference: string | null;
}

export const maintenanceRequirementsApi = {
  list: (accessToken: string) =>
    apiRequest<BackendMaintenanceRequirement[]>("/maintenance-requirements", { accessToken }),
};
