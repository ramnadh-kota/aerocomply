// Typed REAL-mode client for the bulk CSV import pipeline
// (backend/app/api/v1/data_import.py). Validation happens server-side —
// this client never re-implements row validation in the browser.

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
  domain: string;
  filename: string;
  status: "VALIDATED" | "COMPLETED" | "FAILED";
  rows_total: number;
  rows_valid: number;
  rows_invalid: number;
  rows_created: number;
  rows_updated: number;
  rows_failed: number;
  error_summary: string | null;
  created_at: string;
}

export interface BackendImportJobDetail extends BackendImportJob {
  row_results: BackendImportRowResult[];
}

export const dataImportApi = {
  validate: (accessToken: string, domain: string, file: File) =>
    apiUploadFile<BackendImportJobDetail>(`/data-import/${domain}/validate`, file, { accessToken }),

  listJobs: (accessToken: string) =>
    apiRequest<BackendImportJob[]>("/data-import/jobs", { accessToken }),

  getJob: (accessToken: string, jobId: string) =>
    apiRequest<BackendImportJobDetail>(`/data-import/jobs/${jobId}`, { accessToken }),

  commitJob: (accessToken: string, jobId: string) =>
    apiRequest<BackendImportJobDetail>(`/data-import/jobs/${jobId}/commit`, {
      method: "POST",
      accessToken,
    }),
};
