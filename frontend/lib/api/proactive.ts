// Typed REAL-mode client for the backend proactive-alerts / daily-brief
// endpoints (backend/app/api/v1/proactive.py). organization_id is never
// sent — the backend derives it from the authenticated JWT, same as every
// other REAL-mode client in this directory.

import { apiRequest } from "@/lib/apiClient";

export interface BackendProactiveAlert {
  id: string;
  category: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM";
  title: string;
  message: string;
  source_type: string;
  source_id: string;
  aircraft_id: string | null;
  work_order_id: string | null;
}

export interface BackendDailyBrief {
  generated_at: string;
  critical_count: number;
  high_count: number;
  medium_count: number;
  total_count: number;
  top_priorities: BackendProactiveAlert[];
  not_implemented: string[];
}

export const proactiveApi = {
  getAlerts: (accessToken: string) =>
    apiRequest<BackendProactiveAlert[]>("/lisa/proactive-alerts", { accessToken }),
  getDailyBrief: (accessToken: string) =>
    apiRequest<BackendDailyBrief>("/lisa/daily-brief", { accessToken }),
};
