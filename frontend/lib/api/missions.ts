import { apiRequest } from "@/lib/apiClient";

export interface BackendMission {
  id: string;
  organization_id: string;
  asset_id: string;
  pilot_user_id: string | null;
  status: "PLANNED" | "AUTHORIZED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
  purpose: string;
  operating_area: string | null;
  planned_start: string | null;
  planned_end: string | null;
  authorized_at: string | null;
  authorized_by_user_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface MissionListResponse {
  items: BackendMission[];
  total: number;
  limit: number;
  offset: number;
}

export interface MissionCreateParams {
  asset_id: string;
  pilot_user_id?: string | null;
  purpose: string;
  operating_area?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  notes?: string | null;
}

export interface MissionUpdateParams {
  pilot_user_id?: string | null;
  purpose?: string;
  operating_area?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  status?: string;
  notes?: string | null;
}

export interface MissionAuthorizeParams {
  notes?: string;
}

export interface MissionQueryParams {
  asset_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

function missionQuery(params?: MissionQueryParams): string {
  if (!params) return "";
  const parts: string[] = [];
  if (params.asset_id) parts.push(`asset_id=${encodeURIComponent(params.asset_id)}`);
  if (params.status) parts.push(`status=${encodeURIComponent(params.status)}`);
  if (params.limit !== undefined) parts.push(`limit=${params.limit}`);
  if (params.offset !== undefined) parts.push(`offset=${params.offset}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

export const missionsApi = {
  listMissions: (accessToken: string, params?: MissionQueryParams) =>
    apiRequest<MissionListResponse>(`/missions${missionQuery(params)}`, { accessToken }),

  getMission: (accessToken: string, missionId: string) =>
    apiRequest<BackendMission>(`/missions/${missionId}`, { accessToken }),

  createMission: (accessToken: string, payload: MissionCreateParams) =>
    apiRequest<BackendMission>("/missions", { method: "POST", body: payload, accessToken }),

  updateMission: (accessToken: string, missionId: string, payload: MissionUpdateParams) =>
    apiRequest<BackendMission>(`/missions/${missionId}`, { method: "PATCH", body: payload, accessToken }),

  authorizeMission: (accessToken: string, missionId: string, payload?: MissionAuthorizeParams) =>
    apiRequest<BackendMission>(`/missions/${missionId}/authorize`, {
      method: "POST",
      body: payload ?? {},
      accessToken,
    }),
};
