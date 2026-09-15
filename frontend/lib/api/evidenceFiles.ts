// Typed REAL-mode client for the backend EvidenceFile endpoints
// (backend/app/api/v1/evidence.py — M16.4/M16.5/M16.6). The frontend never
// re-implements upload/download/delete logic: it only calls these four
// endpoints and renders whatever the backend returns. storage_key is never
// part of BackendEvidenceFile (the backend response schema omits it — see
// EvidenceFileResponse in backend/app/schemas/evidence.py) and the frontend
// never constructs a storage URL itself.

import { apiRequest, apiUploadFile, type CurrentUser, type NormalizedApiError } from "@/lib/apiClient";

export type EvidenceFileStatus = "PENDING" | "STORED" | "FAILED" | "DELETED";

export interface BackendEvidenceFile {
  id: string;
  evidence_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string | null;
  status: EvidenceFileStatus;
  created_at: string;
  deleted_at: string | null;
}

export interface BackendEvidenceFileDownload {
  url: string;
  expires_in: number;
}

export const evidenceFilesApi = {
  upload: (accessToken: string, evidenceId: string, file: File) =>
    apiUploadFile<BackendEvidenceFile>(`/evidence/${evidenceId}/files`, file, { accessToken }),

  list: (accessToken: string, evidenceId: string) =>
    apiRequest<BackendEvidenceFile[]>(`/evidence/${evidenceId}/files`, { accessToken }),

  getDownloadUrl: (accessToken: string, evidenceId: string, fileId: string) =>
    apiRequest<BackendEvidenceFileDownload>(`/evidence/${evidenceId}/files/${fileId}/download`, {
      accessToken,
    }),

  remove: (accessToken: string, evidenceId: string, fileId: string) =>
    apiRequest<void>(`/evidence/${evidenceId}/files/${fileId}`, {
      method: "DELETE",
      accessToken,
    }),
};

// --- Upload validation (UX hint only — see below) ---

// Mirrors backend/app/api/v1/evidence.py's _ALLOWED_EVIDENCE_CONTENT_TYPES
// and backend/app/core/config.py's evidence_max_upload_bytes default. This
// is deliberately NOT a security control: the backend independently
// validates both on every request regardless of what the frontend sends,
// and remains the sole authority. Rejecting an obviously-invalid file
// client-side only saves the user a round trip.
export const ALLOWED_EVIDENCE_FILE_CONTENT_TYPES = ["application/pdf", "image/jpeg", "image/png"];
export const MAX_EVIDENCE_FILE_UPLOAD_BYTES = 10 * 1024 * 1024;

export function isAllowedEvidenceFileType(file: File): boolean {
  return ALLOWED_EVIDENCE_FILE_CONTENT_TYPES.includes(file.type);
}

export function isWithinEvidenceFileSizeLimit(file: File): boolean {
  return file.size <= MAX_EVIDENCE_FILE_UPLOAD_BYTES;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unitIndex]}`;
}

// --- Status-driven UI rules (source of truth is always the backend status
// string returned on the row — these are pure derived-display rules, not a
// second lifecycle implementation) ---

export function canDownloadEvidenceFile(status: EvidenceFileStatus): boolean {
  return status === "STORED";
}

export function canDeleteEvidenceFile(status: EvidenceFileStatus): boolean {
  return status === "STORED";
}

// --- Permission UX hint ---
//
// Mirrors the EVIDENCE_WRITE grant set in backend/app/core/permissions.py's
// ROLE_PERMISSIONS (ORG_ADMIN, COMPLIANCE_MANAGER, CAMO_MANAGER,
// MAINTENANCE_ENGINEER, plus SUPER_ADMIN which holds every permission).
// This exists ONLY to hide/disable upload and delete controls for users who
// would get a 403 anyway — it changes nothing about what the backend
// actually allows. A user who bypasses this (e.g. via devtools) still hits
// the real require_permission(Permission.EVIDENCE_WRITE) check server-side.
const EVIDENCE_WRITE_ROLES = new Set([
  "SUPER_ADMIN",
  "ORG_ADMIN",
  "COMPLIANCE_MANAGER",
  "CAMO_MANAGER",
  "MAINTENANCE_ENGINEER",
]);

export function canWriteEvidenceFiles(user: CurrentUser | null): boolean {
  if (!user) return false;
  return user.roles.some((role) => EVIDENCE_WRITE_ROLES.has(role));
}

// --- Error message mapping ---
//
// Same philosophy as normalizeApiError (backend messages for 4xx are
// user-safe; 5xx/network failures never leak internals) but with copy
// specific to each evidence-file action, per the M16.7 spec's examples.
export function evidenceFileErrorMessage(
  action: "upload" | "download" | "delete",
  error: NormalizedApiError
): string {
  // normalizeApiError already guarantees error.message is safe to display
  // for every kind except "server" (see apiClient.ts: 4xx backend bodies —
  // validation/conflict/not_found/unauthorized/forbidden/an unrecognized 4xx
  // — carry their own safe, specific text; only a 5xx response is swapped
  // for the generic server message, since a 5xx body may otherwise leak
  // storage/internal details). Only that "server" case (and, defensively,
  // any future kind this function doesn't yet know about) falls back to the
  // per-action copy below — 5xx from the evidence-file endpoints in
  // particular never carries raw StorageUploadError/StorageDeleteError/
  // StoragePresignError text (see backend/app/api/v1/evidence.py), so there
  // is nothing unsafe being hidden by using the generic message either way.
  if (error.kind !== "server") {
    return error.message;
  }
  switch (action) {
    case "upload":
      return "Unable to upload this file. Please try again.";
    case "download":
      return "Unable to download this file. It may no longer be available.";
    case "delete":
      return "Unable to delete this file. Please try again.";
  }
}
