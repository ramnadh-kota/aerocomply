"use client";

// M16.7 — Evidence Files section for an Evidence detail/panel. REAL-mode
// only, wired wherever a real evidence.id exists (see RealTaskGatePanel).
// Consumes the M16.4-M16.6 EvidenceFile endpoints exactly as implemented —
// upload/list/download/delete — and never invents a fifth. The backend
// remains the sole source of truth for status and the sole authority on
// permissions; canWriteEvidenceFiles only hides controls a 403 would
// otherwise reject, and file.status alone decides which actions render.

import { useEffect, useRef, useState } from "react";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { StatusBadge, evidenceFileStatusBadge } from "@/components/status/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  evidenceFilesApi,
  evidenceFileErrorMessage,
  canDownloadEvidenceFile,
  canDeleteEvidenceFile,
  canWriteEvidenceFiles,
  formatFileSize,
  isAllowedEvidenceFileType,
  isWithinEvidenceFileSizeLimit,
  MAX_EVIDENCE_FILE_UPLOAD_BYTES,
  type BackendEvidenceFile,
} from "@/lib/api/evidenceFiles";

export function EvidenceFilesPanel({ evidenceId }: { evidenceId: string }) {
  const { accessToken, user } = useSession();
  const canWrite = canWriteEvidenceFiles(user);

  const [files, setFiles] = useState<BackendEvidenceFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<NormalizedApiError | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<BackendEvidenceFile | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadFiles = () => {
    if (!accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setListError(null);
    evidenceFilesApi
      .list(accessToken, evidenceId)
      .then(setFiles)
      .catch((err) => setListError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, evidenceId]);

  function handleFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setUploadError(null);
    if (!file) {
      setSelectedFile(null);
      return;
    }
    // Client-side checks are a UX convenience only — the backend
    // independently re-validates both content type and size on every
    // request and is the only thing that can actually reject a bad upload.
    if (!isAllowedEvidenceFileType(file)) {
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setUploadError("Only PDF, JPEG, and PNG files are supported.");
      return;
    }
    if (!isWithinEvidenceFileSizeLimit(file)) {
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setUploadError(
        `File exceeds the maximum upload size of ${formatFileSize(MAX_EVIDENCE_FILE_UPLOAD_BYTES)}.`
      );
      return;
    }
    setSelectedFile(file);
  }

  function handleUpload() {
    if (!accessToken || !selectedFile) return;
    setUploading(true);
    setUploadError(null);
    evidenceFilesApi
      .upload(accessToken, evidenceId, selectedFile)
      .then(() => {
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
        // Refresh the list from the backend rather than optimistically
        // inserting the response — the row's real, authoritative status
        // (STORED vs FAILED) is what list() returns, and re-fetching keeps
        // this component from ever drifting from server state.
        loadFiles();
      })
      .catch((err) => setUploadError(evidenceFileErrorMessage("upload", normalizeApiError(err))))
      .finally(() => setUploading(false));
  }

  function handleDownload(file: BackendEvidenceFile) {
    if (!accessToken) return;
    setDownloadError(null);
    setDownloadingId(file.id);
    evidenceFilesApi
      .getDownloadUrl(accessToken, evidenceId, file.id)
      .then((res) => {
        // The signed URL is used immediately and never stored in component
        // state beyond this call — nothing here persists it, logs it, or
        // keeps it around after the browser navigation is issued.
        window.open(res.url, "_blank", "noopener,noreferrer");
      })
      .catch((err) => setDownloadError(evidenceFileErrorMessage("download", normalizeApiError(err))))
      .finally(() => setDownloadingId(null));
  }

  function confirmDelete() {
    if (!accessToken || !deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    evidenceFilesApi
      .remove(accessToken, evidenceId, deleteTarget.id)
      .then(() => {
        setDeleteTarget(null);
        loadFiles();
      })
      .catch((err) => setDeleteError(evidenceFileErrorMessage("delete", normalizeApiError(err))))
      .finally(() => setDeleting(false));
  }

  return (
    <div className="ac-card" style={{ marginTop: 12 }}>
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
        <span className="ac-eyebrow">Files</span>
        {canWrite && (
          <div className="ac-flex ac-gap-2" style={{ alignItems: "center", flexWrap: "wrap" }}>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,image/jpeg,image/png"
              onChange={handleFileChosen}
              disabled={uploading}
              aria-label="Choose evidence file to upload"
              style={{ maxWidth: 220 }}
            />
            <button
              className="ac-btn ac-btn-sm ac-btn-primary"
              disabled={!selectedFile || uploading}
              onClick={handleUpload}
            >
              {uploading ? "Uploading…" : "Upload"}
            </button>
          </div>
        )}
      </div>

      {selectedFile && !uploading && (
        <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>
          Selected: <span className="ac-mono">{selectedFile.name}</span> ({formatFileSize(selectedFile.size)})
        </p>
      )}
      {uploadError && (
        <p className="ac-text-sm" role="alert" style={{ color: "var(--ac-status-non-compliant)", margin: "0 0 8px" }}>
          {uploadError}
        </p>
      )}
      {downloadError && (
        <p className="ac-text-sm" role="alert" style={{ color: "var(--ac-status-non-compliant)", margin: "0 0 8px" }}>
          {downloadError}
        </p>
      )}
      {deleteError && (
        <p className="ac-text-sm" role="alert" style={{ color: "var(--ac-status-non-compliant)", margin: "0 0 8px" }}>
          {deleteError}
        </p>
      )}

      {loading && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Loading files…</p>}

      {!loading && listError && (
        <p className="ac-text-sm" role="alert" style={{ color: "var(--ac-status-non-compliant)", margin: 0 }}>
          {listError.message}
        </p>
      )}

      {!loading && !listError && files.length === 0 && (
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          No files attached to this evidence yet.
          {!canWrite && " (Read-only access — an authorized user can upload files here.)"}
        </p>
      )}

      {!loading && !listError && files.length > 0 && (
        <>
          {/* Desktop table — hidden below 640px in favor of the stacked-card
              layout, matching the existing .ac-table-desktop/.ac-row-cards
              pattern (see e.g. app/(app)/platform/organizations/page.tsx) so
              no action column can be pushed off-screen on narrow viewports. */}
          <div className="ac-table-desktop" style={{ overflowX: "auto" }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <tr key={file.id}>
                    <td style={{ maxWidth: 220, overflowWrap: "break-word" }}>{file.original_filename}</td>
                    <td>{file.content_type}</td>
                    <td>{formatFileSize(file.size_bytes)}</td>
                    <td>
                      <StatusBadge {...evidenceFileStatusBadge(file.status)} />
                      {file.status === "DELETED" && file.deleted_at && (
                        <span className="ac-text-sm ac-text-muted" style={{ display: "block", marginTop: 2 }}>
                          Deleted {new Date(file.deleted_at).toLocaleString()}
                        </span>
                      )}
                    </td>
                    <td>{new Date(file.created_at).toLocaleString()}</td>
                    <td>
                      <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                        {canDownloadEvidenceFile(file.status) && (
                          <button
                            className="ac-btn ac-btn-sm"
                            disabled={downloadingId === file.id}
                            onClick={() => handleDownload(file)}
                          >
                            {downloadingId === file.id ? "Preparing…" : "Download"}
                          </button>
                        )}
                        {canWrite && canDeleteEvidenceFile(file.status) && (
                          <button
                            className="ac-btn ac-btn-sm"
                            style={{ borderColor: "var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)" }}
                            onClick={() => setDeleteTarget(file)}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ac-row-cards">
            {files.map((file) => (
              <div className="ac-row-card" key={file.id}>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Filename</span>
                  <span style={{ overflowWrap: "break-word", textAlign: "right", maxWidth: "60%" }}>
                    {file.original_filename}
                  </span>
                </div>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Type</span>
                  <span>{file.content_type}</span>
                </div>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Size</span>
                  <span>{formatFileSize(file.size_bytes)}</span>
                </div>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Status</span>
                  <StatusBadge {...evidenceFileStatusBadge(file.status)} />
                </div>
                {file.status === "DELETED" && file.deleted_at && (
                  <div className="ac-row-card-field">
                    <span className="ac-row-card-field-label">Deleted</span>
                    <span>{new Date(file.deleted_at).toLocaleString()}</span>
                  </div>
                )}
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Uploaded</span>
                  <span>{new Date(file.created_at).toLocaleString()}</span>
                </div>
                <div className="ac-row-card-actions">
                  {canDownloadEvidenceFile(file.status) && (
                    <button
                      className="ac-btn"
                      disabled={downloadingId === file.id}
                      onClick={() => handleDownload(file)}
                    >
                      {downloadingId === file.id ? "Preparing…" : "Download"}
                    </button>
                  )}
                  {canWrite && canDeleteEvidenceFile(file.status) && (
                    <button
                      className="ac-btn"
                      style={{ borderColor: "var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)" }}
                      onClick={() => setDeleteTarget(file)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete this evidence file?"
        body={`This removes access to the stored file "${deleteTarget?.original_filename ?? ""}". The file's record is kept for history, but it can no longer be downloaded. This cannot be undone.`}
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => {
          setDeleteTarget(null);
          setDeleteError(null);
        }}
      />
    </div>
  );
}
