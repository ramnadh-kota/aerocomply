import { describe, it, expect } from "vitest";
import {
  ALLOWED_EVIDENCE_FILE_CONTENT_TYPES,
  MAX_EVIDENCE_FILE_UPLOAD_BYTES,
  isAllowedEvidenceFileType,
  isWithinEvidenceFileSizeLimit,
  formatFileSize,
  canDownloadEvidenceFile,
  canDeleteEvidenceFile,
  canWriteEvidenceFiles,
  evidenceFileErrorMessage,
} from "../lib/api/evidenceFiles";
import { evidenceFileStatusBadge } from "../components/status/StatusBadge";
import { ApiError, normalizeApiError, type CurrentUser } from "../lib/apiClient";

function makeFile(name: string, type: string, sizeBytes: number): File {
  // jsdom is not part of this project's test environment (see
  // vitest.config.ts: environment "node"), so File/Blob come from Node's
  // own web-platform globals (Node 20+). A real File with `size` reflecting
  // actual content length is constructed directly rather than mocked.
  const content = new Uint8Array(sizeBytes);
  return new File([content], name, { type });
}

function makeUser(roles: string[]): CurrentUser {
  return {
    id: "user-1",
    organization_id: "org-1",
    email: "u@example.com",
    full_name: "Test User",
    roles,
  };
}

describe("Evidence File upload validation (UX hint only, M16.7)", () => {
  it("allows exactly the backend's declared MIME allowlist", () => {
    expect(ALLOWED_EVIDENCE_FILE_CONTENT_TYPES).toEqual([
      "application/pdf",
      "image/jpeg",
      "image/png",
    ]);
  });

  it("accepts an allowed content type", () => {
    expect(isAllowedEvidenceFileType(makeFile("a.pdf", "application/pdf", 10))).toBe(true);
    expect(isAllowedEvidenceFileType(makeFile("a.jpg", "image/jpeg", 10))).toBe(true);
    expect(isAllowedEvidenceFileType(makeFile("a.png", "image/png", 10))).toBe(true);
  });

  it("rejects an unsupported content type", () => {
    expect(isAllowedEvidenceFileType(makeFile("a.txt", "text/plain", 10))).toBe(false);
    expect(isAllowedEvidenceFileType(makeFile("a.exe", "application/octet-stream", 10))).toBe(false);
  });

  it("accepts a file within the configured size limit", () => {
    expect(isWithinEvidenceFileSizeLimit(makeFile("a.pdf", "application/pdf", 1024))).toBe(true);
    expect(
      isWithinEvidenceFileSizeLimit(makeFile("a.pdf", "application/pdf", MAX_EVIDENCE_FILE_UPLOAD_BYTES))
    ).toBe(true);
  });

  it("rejects a file exceeding the configured size limit", () => {
    expect(
      isWithinEvidenceFileSizeLimit(
        makeFile("a.pdf", "application/pdf", MAX_EVIDENCE_FILE_UPLOAD_BYTES + 1)
      )
    ).toBe(false);
  });

  it("matches the backend's evidence_max_upload_bytes default (10 MiB)", () => {
    expect(MAX_EVIDENCE_FILE_UPLOAD_BYTES).toBe(10 * 1024 * 1024);
  });
});

describe("formatFileSize", () => {
  it("formats bytes under 1024 as bytes", () => {
    expect(formatFileSize(512)).toBe("512 B");
  });

  it("formats kilobytes", () => {
    expect(formatFileSize(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("handles a long filename's size the same as any other (no special-casing)", () => {
    expect(formatFileSize(123)).toBe("123 B");
  });
});

describe("Evidence file status -> action rules (STORED is the only downloadable/deletable state)", () => {
  it("STORED files are downloadable", () => {
    expect(canDownloadEvidenceFile("STORED")).toBe(true);
  });

  it("PENDING, FAILED, and DELETED files are not downloadable", () => {
    expect(canDownloadEvidenceFile("PENDING")).toBe(false);
    expect(canDownloadEvidenceFile("FAILED")).toBe(false);
    expect(canDownloadEvidenceFile("DELETED")).toBe(false);
  });

  it("STORED files are deletable", () => {
    expect(canDeleteEvidenceFile("STORED")).toBe(true);
  });

  it("PENDING, FAILED, and DELETED files are not deletable", () => {
    expect(canDeleteEvidenceFile("PENDING")).toBe(false);
    expect(canDeleteEvidenceFile("FAILED")).toBe(false);
    expect(canDeleteEvidenceFile("DELETED")).toBe(false);
  });
});

describe("evidenceFileStatusBadge", () => {
  it("gives DELETED a distinct, non-failure visual (neutral, not red)", () => {
    const deleted = evidenceFileStatusBadge("DELETED");
    const failed = evidenceFileStatusBadge("FAILED");
    expect(deleted.status).not.toBe(failed.status);
    expect(deleted.status).toBe("WRITTEN_OFF");
  });

  it("maps STORED to a positive/compliant visual", () => {
    expect(evidenceFileStatusBadge("STORED").status).toBe("COMPLIANT");
  });

  it("maps FAILED to a negative visual", () => {
    expect(evidenceFileStatusBadge("FAILED").status).toBe("NON_COMPLIANT");
  });

  it("always pairs status with a readable label, never color alone", () => {
    expect(evidenceFileStatusBadge("PENDING").label).toBe("PENDING");
  });
});

describe("canWriteEvidenceFiles (frontend UX hint mirroring backend EVIDENCE_WRITE grant)", () => {
  it("returns false for an unauthenticated user", () => {
    expect(canWriteEvidenceFiles(null)).toBe(false);
  });

  it("returns true for ORG_ADMIN", () => {
    expect(canWriteEvidenceFiles(makeUser(["ORG_ADMIN"]))).toBe(true);
  });

  it("returns true for MAINTENANCE_ENGINEER", () => {
    expect(canWriteEvidenceFiles(makeUser(["MAINTENANCE_ENGINEER"]))).toBe(true);
  });

  it("returns true for SUPER_ADMIN", () => {
    expect(canWriteEvidenceFiles(makeUser(["SUPER_ADMIN"]))).toBe(true);
  });

  it("returns false for VIEWER (read-only role, matches backend EVIDENCE_READ-only grant)", () => {
    expect(canWriteEvidenceFiles(makeUser(["VIEWER"]))).toBe(false);
  });

  it("returns false for QUALITY_MANAGER (backend does not grant EVIDENCE_WRITE to this role)", () => {
    expect(canWriteEvidenceFiles(makeUser(["QUALITY_MANAGER"]))).toBe(false);
  });
});

describe("evidenceFileErrorMessage (never exposes raw backend/storage internals)", () => {
  it("passes through a safe 4xx validation message for upload", () => {
    const err = normalizeApiError(new ApiError(415, "unsupported_content_type", "Unsupported content type: text/plain"));
    expect(evidenceFileErrorMessage("upload", err)).toBe("Unsupported content type: text/plain");
  });

  it("passes through a safe conflict message for delete", () => {
    const err = normalizeApiError(new ApiError(409, "conflict", "Evidence file cannot be deleted in status PENDING"));
    expect(evidenceFileErrorMessage("delete", err)).toBe("Evidence file cannot be deleted in status PENDING");
  });

  it("uses a generic, safe message for a 5xx storage failure on upload", () => {
    const err = normalizeApiError(new ApiError(502, "evidence_file_storage_failed", "boom: bucket=secret internal detail"));
    const message = evidenceFileErrorMessage("upload", err);
    expect(message).toBe("Unable to upload this file. Please try again.");
    expect(message).not.toContain("bucket");
    expect(message).not.toContain("secret");
  });

  it("uses a generic, safe message for a 5xx storage failure on download", () => {
    const err = normalizeApiError(new ApiError(502, "evidence_file_presign_failed", "boom: internal storage error"));
    const message = evidenceFileErrorMessage("download", err);
    expect(message).toBe("Unable to download this file. It may no longer be available.");
    expect(message).not.toContain("boom");
  });

  it("uses a generic, safe message for a 5xx storage failure on delete", () => {
    const err = normalizeApiError(new ApiError(502, "evidence_file_storage_delete_failed", "boom internal"));
    expect(evidenceFileErrorMessage("delete", err)).toBe("Unable to delete this file. Please try again.");
  });

  it("uses normalizeApiError's own safe offline message for a network failure (not raw fetch error text)", () => {
    const err = normalizeApiError(new TypeError("Failed to fetch"));
    const message = evidenceFileErrorMessage("upload", err);
    expect(message).toBe("Unable to reach the server. Check your connection and try again.");
    expect(message).not.toContain("fetch");
  });
});
