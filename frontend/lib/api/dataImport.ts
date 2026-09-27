// Typed client for the M5 bulk data and operational migration Import Center
// (backend/app/api/v1/data_import.py).
// Supports Aircraft, Drones, and Flight records with sheet selection,
// column mapping, asset matching strategies, and server-side validation.

import { apiRequest, apiUploadFile } from "@/lib/apiClient";

export interface BackendImportRowResult {
  row_number: number;
  status: "VALID" | "INVALID" | "WARNING";
  errors: string[];
  warnings: string[];
  data: Record<string, string>;
}

export interface BackendImportJob {
  id: string;
  organization_id: string;
  domain: "AIRCRAFT" | "DRONE" | "FLIGHT" | string;
  filename: string;
  file_hash?: string | null;
  selected_sheet?: string | null;
  sheet_names?: string[];
  column_mapping?: Record<string, string>;
  match_strategy?: Record<string, string> | string;
  unmatched_assets?: string[];
  status:
    | "VALIDATED"
    | "AWAITING_CONFIRMATION"
    | "COMPLETED"
    | "COMPLETED_WITH_ERRORS"
    | "FAILED"
    | "CANCELLED";
  rows_total: number;
  rows_valid: number;
  rows_invalid: number;
  rows_created: number;
  rows_updated: number;
  rows_failed: number;
  warning_count?: number;
  error_summary: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface BackendImportJobDetail extends BackendImportJob {
  row_results: BackendImportRowResult[];
}

export interface TenantImportMapping {
  id: string;
  organization_id: string;
  domain: string;
  name: string;
  mapping: Record<string, string>;
  is_default: boolean;
  created_at: string;
}

export interface ImportConfigureRequest {
  selected_sheet?: string;
  column_mapping?: Record<string, string>;
  match_strategy?: Record<string, string> | string;
}

export interface ImportMappingCreateRequest {
  name: string;
  domain: string;
  mapping: Record<string, string>;
  is_default?: boolean;
}

export const dataImportApi = {
  validate: (accessToken: string, domain: string, file: File, sheetName?: string) => {
    const query = sheetName ? `?sheet_name=${encodeURIComponent(sheetName)}` : "";
    return apiUploadFile<BackendImportJobDetail>(`/data-import/${domain}/validate${query}`, file, {
      accessToken,
    });
  },

  configureJob: (accessToken: string, jobId: string, req: ImportConfigureRequest) =>
    apiRequest<BackendImportJobDetail>(`/data-import/jobs/${jobId}/configure`, {
      method: "POST",
      accessToken,
      body: JSON.stringify(req),
    }),

  listJobs: (accessToken: string) =>
    apiRequest<BackendImportJob[]>("/data-import/jobs", { accessToken }),

  getJob: (accessToken: string, jobId: string) =>
    apiRequest<BackendImportJobDetail>(`/data-import/jobs/${jobId}`, { accessToken }),

  commitJob: (accessToken: string, jobId: string) =>
    apiRequest<BackendImportJobDetail>(`/data-import/jobs/${jobId}/commit`, {
      method: "POST",
      accessToken,
    }),

  listMappings: (accessToken: string, domain?: string) => {
    const query = domain ? `?domain=${encodeURIComponent(domain)}` : "";
    return apiRequest<TenantImportMapping[]>(`/data-import/mappings${query}`, { accessToken });
  },

  createMapping: (accessToken: string, req: ImportMappingCreateRequest) =>
    apiRequest<TenantImportMapping>("/data-import/mappings", {
      method: "POST",
      accessToken,
      body: JSON.stringify(req),
    }),

  deleteMapping: (accessToken: string, mappingId: string) =>
    apiRequest<{ ok: boolean }>(`/data-import/mappings/${mappingId}`, {
      method: "DELETE",
      accessToken,
    }),
};
