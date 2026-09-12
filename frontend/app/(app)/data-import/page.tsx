"use client";

// Bulk Data Import — onboarding/productivity workspace. REAL-mode only:
// this uploads into the signed-in user's own organization via the backend
// (backend/app/api/v1/data_import.py); there is no demo dataset for it.
// Only Aircraft is wired up today — see backend/app/services/import_service.py
// for why (reference implementation of the pipeline, not a claim every
// domain is import-ready).

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  dataImportApi,
  type BackendImportJob,
  type BackendImportJobDetail,
  type BackendImportRowResult,
} from "@/lib/api/dataImport";

const TEMPLATE_CSV =
  "registration,msn,aircraft_type,status\nN12345,MSN-0001,A320,ACTIVE\nN67890,MSN-0002,B737,ACTIVE\n";

function downloadTemplate() {
  const blob = new Blob([TEMPLATE_CSV], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "aircraft_import_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function rowStatusBadge(status: string) {
  if (status === "INVALID") return { status: "NON_COMPLIANT" as const, label: "Invalid" };
  if (status === "WARNING") return { status: "REVIEW_REQUIRED" as const, label: "Warning" };
  return { status: "APPLICABLE" as const, label: "Valid" };
}

function ValidationPreview({
  job,
  onCommitted,
  onCancel,
}: {
  job: BackendImportJobDetail;
  onCommitted: () => void;
  onCancel: () => void;
}) {
  const { accessToken } = useSession();
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [result, setResult] = useState<BackendImportJobDetail | null>(null);

  const rowColumns: Column<BackendImportRowResult>[] = [
    { key: "row", header: "Row", render: (r) => r.row_number },
    { key: "status", header: "Status", render: (r) => <StatusBadge {...rowStatusBadge(r.status)} /> },
    { key: "registration", header: "Registration", render: (r) => r.data.registration || "—" },
    {
      key: "issues",
      header: "Issues",
      render: (r) => [...r.errors, ...r.warnings].join("; ") || "None",
    },
  ];

  const commit = () => {
    if (!accessToken) return;
    setCommitting(true);
    setError(null);
    dataImportApi
      .commitJob(accessToken, job.id)
      .then((completed) => {
        setResult(completed);
        onCommitted();
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setCommitting(false));
  };

  if (result) {
    return (
      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <h2 className="ac-h2">Import {result.status === "COMPLETED" ? "Complete" : "Failed"}</h2>
        <p className="ac-text-sm">
          {result.rows_created} created · {result.rows_failed} failed · {result.rows_invalid} skipped (invalid)
        </p>
        {result.error_summary && <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>{result.error_summary}</p>}
        <button className="ac-btn" onClick={onCancel}>Done</button>
      </div>
    );
  }

  return (
    <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
      <h2 className="ac-h2">Preview — {job.filename}</h2>
      <div className="ac-flex ac-gap-4" style={{ marginBottom: 10 }}>
        <span className="ac-text-sm">{job.rows_total} rows detected</span>
        <span className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>{job.rows_valid} importable</span>
        <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>{job.rows_invalid} invalid</span>
      </div>
      <div className="ac-card" style={{ padding: 0, marginBottom: 10 }}>
        <DataTable columns={rowColumns} rows={job.row_results} />
      </div>
      <div className="ac-flex ac-gap-2">
        <button className="ac-btn" onClick={commit} disabled={committing || job.rows_valid === 0}>
          {committing ? "Importing…" : `Confirm Import (${job.rows_valid} rows)`}
        </button>
        <button className="ac-btn" onClick={onCancel} disabled={committing}>
          Cancel
        </button>
        {error && <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>{error.message}</span>}
      </div>
    </div>
  );
}

function RealDataImport() {
  const { accessToken, isAuthenticated } = useSession();
  const [jobs, setJobs] = useState<BackendImportJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [uploading, setUploading] = useState(false);
  const [previewJob, setPreviewJob] = useState<BackendImportJobDetail | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadJobs = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    dataImportApi
      .listJobs(accessToken)
      .then(setJobs)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !accessToken) return;
    setUploading(true);
    setError(null);
    dataImportApi
      .validate(accessToken, "aircraft", file)
      .then(setPreviewJob)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      });
  };

  const jobColumns: Column<BackendImportJob>[] = [
    { key: "file", header: "File", render: (j) => j.filename },
    { key: "domain", header: "Domain", render: (j) => j.domain },
    { key: "status", header: "Status", render: (j) => <StatusBadge {...genericStatusBadge(j.status)} /> },
    { key: "rows", header: "Rows", render: (j) => `${j.rows_valid}/${j.rows_total} valid` },
    { key: "created", header: "Created", render: (j) => `${j.rows_created}`, },
    { key: "date", header: "Date", render: (j) => new Date(j.created_at).toLocaleString(), sortValue: (j) => j.created_at },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Data Import" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Bulk Data Import</h1>
          <p className="ac-subtitle">Onboard operational data via CSV. Currently supported: Aircraft.</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Data import requires signing in. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : previewJob ? (
        <ValidationPreview
          job={previewJob}
          onCommitted={loadJobs}
          onCancel={() => setPreviewJob(null)}
        />
      ) : (
        <>
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <h2 className="ac-h2">Import Aircraft</h2>
            <p className="ac-text-sm ac-text-muted">
              Required columns: registration, msn, aircraft_type. Optional: status (defaults to ACTIVE).
            </p>
            <div className="ac-flex ac-gap-2" style={{ marginTop: 8 }}>
              <button className="ac-btn" onClick={downloadTemplate}>Download Template</button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                disabled={uploading}
                aria-label="Upload aircraft CSV"
              />
              {uploading && <span className="ac-text-sm ac-text-muted">Validating…</span>}
            </div>
            {error && <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>{error.message}</p>}
          </div>

          <h2 className="ac-h2" style={{ marginTop: "var(--ac-space-5)" }}>Import History</h2>
          <RealDataPanel
            loading={loading}
            error={null}
            isEmpty={jobs.length === 0}
            emptyMessage="No imports have been run yet."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <DataTable columns={jobColumns} rows={jobs} />
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}

export default function DataImportPage() {
  return <RealDataImport />;
}
