"use client";

// KOTA AEROSPACE M5 — Customer Data Migration & Import Center
// Authoritative ingestion engine for Aircraft, Drones, and Flight operational records.
// Connects to backend/app/api/v1/data_import.py with tenant isolation, sheet selection,
// column mapping presets, asset matching strategies, structured validation, and confirmation gate.

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

const TEMPLATES: Record<string, { filename: string; content: string; label: string }> = {
  AIRCRAFT: {
    filename: "aircraft_import_template.csv",
    content: "registration,msn,aircraft_type,manufacturer,model,status\nVT-ABC,MSN-1001,AIRCRAFT,Cessna,Grand Caravan 208B,ACTIVE\nVT-XYZ,MSN-1002,AIRCRAFT,Pilatus,PC-12,ACTIVE\n",
    label: "Aircraft Template",
  },
  DRONE: {
    filename: "drone_import_template.csv",
    content: "registration,manufacturer,model,serial_number,status\nVT-UAV-01,DJI,Matrice 350 RTK,SN-350-9901,ACTIVE\nVT-UAV-02,Autel,EVO Max 4T,SN-AUT-4402,ACTIVE\n",
    label: "Drone Template",
  },
  FLIGHT: {
    filename: "flight_records_template.csv",
    content: "registration,flight_date,flight_hours,cycles,flight_number,origin,destination,mission_type,status,notes\nVT-ABC,2026-03-01,2.5,1,KA-101,VOMM,VOBL,PASSENGER,COMPLETED,Scheduled flight\nVT-UAV-01,2026-03-02,0.8,1,SRV-042,PAD-A,PAD-A,SURVEY,COMPLETED,Corridor survey\n",
    label: "Flight Records Template",
  },
};

function downloadTemplate(domain: string) {
  const template = TEMPLATES[domain] || TEMPLATES.FLIGHT;
  const blob = new Blob([template.content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = template.filename;
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
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [result, setResult] = useState<BackendImportJobDetail | null>(null);
  const [filter, setFilter] = useState<"ALL" | "INVALID" | "WARNING" | "VALID">("ALL");

  const filteredRows = (job.row_results || []).filter((r) => {
    if (filter === "ALL") return true;
    return r.status === filter;
  });

  const rowColumns: Column<BackendImportRowResult>[] = [
    { key: "row", header: "Row #", render: (r: BackendImportRowResult) => r.row_number },
    { key: "status", header: "Validation", render: (r: BackendImportRowResult) => <StatusBadge {...rowStatusBadge(r.status)} /> },
    {
      key: "reg",
      header: "Asset Identifier",
      render: (r: BackendImportRowResult) => r.data.registration || r.data.aircraft_registration || r.data.tail || "—",
    },
    {
      key: "flown",
      header: "Date / Ref",
      render: (r: BackendImportRowResult) => r.data.flown_at || r.data.flight_date || r.data.msn || "—",
    },
    {
      key: "hours",
      header: "Hours / Metric",
      render: (r: BackendImportRowResult) => r.data.flight_hours || r.data.duration_minutes || r.data.aircraft_type || "—",
    },
    {
      key: "issues",
      header: "Errors & Warnings",
      render: (r: BackendImportRowResult) => {
        const issues = [...(r.errors || []).map((e) => `[Error] ${e}`), ...(r.warnings || []).map((w) => `[Warning] ${w}`)];
        return (
          <span style={{ color: r.errors?.length ? "var(--ac-status-non-compliant)" : "var(--ac-status-review-required)" }}>
            {issues.join("; ") || "Clean record"}
          </span>
        );
      },
    },
  ];

  const handleCommit = () => {
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
    const isSuccess = result.status === "COMPLETED";
    return (
      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-6)" }}>
        <div className="ac-flex ac-items-center ac-gap-3" style={{ marginBottom: "var(--ac-space-4)" }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              backgroundColor: isSuccess ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: isSuccess ? "var(--ac-status-applicable)" : "var(--ac-status-non-compliant)",
              fontWeight: "bold",
            }}
          >
            {isSuccess ? "✓" : "!"}
          </div>
          <div>
            <h2 className="ac-h2" style={{ margin: 0 }}>
              Import {isSuccess ? "Complete & Operational" : "Completed with Errors"}
            </h2>
            <p className="ac-text-sm" style={{ color: "var(--ac-text-muted)", margin: 0 }}>
              Authoritative domain persistence completed for {job.domain} dataset
            </p>
          </div>
        </div>

        <div className="ac-grid ac-grid-cols-3 ac-gap-4" style={{ marginBottom: "var(--ac-space-6)" }}>
          <div className="ac-card" style={{ padding: "var(--ac-space-3)", background: "rgba(255,255,255,0.03)" }}>
            <div className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>Records Created</div>
            <div className="ac-h2" style={{ color: "var(--ac-status-applicable)", marginTop: 4 }}>{result.rows_created}</div>
          </div>
          <div className="ac-card" style={{ padding: "var(--ac-space-3)", background: "rgba(255,255,255,0.03)" }}>
            <div className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>Records Failed</div>
            <div className="ac-h2" style={{ color: result.rows_failed ? "var(--ac-status-non-compliant)" : "var(--ac-text)", marginTop: 4 }}>{result.rows_failed}</div>
          </div>
          <div className="ac-card" style={{ padding: "var(--ac-space-3)", background: "rgba(255,255,255,0.03)" }}>
            <div className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>Invalid / Skipped</div>
            <div className="ac-h2" style={{ color: "var(--ac-text-muted)", marginTop: 4 }}>{result.rows_invalid}</div>
          </div>
        </div>

        {result.error_summary && (
          <div
            className="ac-card"
            style={{
              padding: "var(--ac-space-3)",
              marginBottom: "var(--ac-space-4)",
              background: "rgba(239, 68, 68, 0.08)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              color: "var(--ac-status-non-compliant)",
            }}
          >
            <strong>Error Log:</strong> {result.error_summary}
          </div>
        )}

        <div className="ac-flex ac-gap-3">
          <button className="ac-btn ac-btn-primary" onClick={onCancel}>
            Return to Import Center
          </button>
          {job.domain === "FLIGHT" && (
            <Link href="/aircraft" className="ac-btn">
              View Fleet Operations
            </Link>
          )}
        </div>
      </div>
    );
  }

  const hasBlockingErrors = job.rows_invalid > 0;

  return (
    <div className="ac-card ac-section" style={{ padding: "var(--ac-space-6)" }}>
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: "var(--ac-space-4)" }}>
        <div>
          <h2 className="ac-h2" style={{ margin: 0 }}>
            Staged Import Review — {job.filename}
          </h2>
          <span className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
            Domain: <strong>{job.domain}</strong>
            {job.selected_sheet && ` · Sheet: ${job.selected_sheet}`}
            {job.file_hash && ` · SHA-256: ${job.file_hash.substring(0, 10)}...`}
          </span>
        </div>
        <div className="ac-flex ac-gap-2">
          <button className="ac-btn" onClick={onCancel} disabled={committing}>
            Cancel
          </button>
          <button
            className="ac-btn ac-btn-primary"
            onClick={() => setConfirmOpen(true)}
            disabled={committing || hasBlockingErrors}
            title={hasBlockingErrors ? "Fix blocking row errors before confirming" : "Confirm and commit import"}
          >
            {committing ? "Importing..." : "Confirm & Import Records"}
          </button>
        </div>
      </div>

      {/* Summary KPI cards */}
      <div className="ac-grid ac-grid-cols-4 ac-gap-3" style={{ marginBottom: "var(--ac-space-5)" }}>
        <div
          className="ac-card"
          style={{ padding: "var(--ac-space-3)", cursor: "pointer", border: filter === "ALL" ? "1px solid var(--ac-primary)" : undefined }}
          onClick={() => setFilter("ALL")}
        >
          <div className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>Total Staged Rows</div>
          <div className="ac-h2" style={{ marginTop: 2 }}>{job.rows_total}</div>
        </div>
        <div
          className="ac-card"
          style={{ padding: "var(--ac-space-3)", cursor: "pointer", border: filter === "VALID" ? "1px solid var(--ac-status-applicable)" : undefined }}
          onClick={() => setFilter("VALID")}
        >
          <div className="ac-text-xs" style={{ color: "var(--ac-status-applicable)" }}>Ready / Valid Rows</div>
          <div className="ac-h2" style={{ color: "var(--ac-status-applicable)", marginTop: 2 }}>{job.rows_valid}</div>
        </div>
        <div
          className="ac-card"
          style={{ padding: "var(--ac-space-3)", cursor: "pointer", border: filter === "WARNING" ? "1px solid var(--ac-status-review-required)" : undefined }}
          onClick={() => setFilter("WARNING")}
        >
          <div className="ac-text-xs" style={{ color: "var(--ac-status-review-required)" }}>Warnings</div>
          <div className="ac-h2" style={{ color: "var(--ac-status-review-required)", marginTop: 2 }}>{job.warning_count || 0}</div>
        </div>
        <div
          className="ac-card"
          style={{ padding: "var(--ac-space-3)", cursor: "pointer", border: filter === "INVALID" ? "1px solid var(--ac-status-non-compliant)" : undefined }}
          onClick={() => setFilter("INVALID")}
        >
          <div className="ac-text-xs" style={{ color: "var(--ac-status-non-compliant)" }}>Errors (Blocking)</div>
          <div className="ac-h2" style={{ color: job.rows_invalid ? "var(--ac-status-non-compliant)" : "var(--ac-text-muted)", marginTop: 2 }}>
            {job.rows_invalid}
          </div>
        </div>
      </div>

      {/* Unmatched assets callout */}
      {job.unmatched_assets && job.unmatched_assets.length > 0 && (
        <div
          className="ac-card"
          style={{
            padding: "var(--ac-space-3)",
            marginBottom: "var(--ac-space-4)",
            background: "rgba(234, 179, 8, 0.08)",
            border: "1px solid rgba(234, 179, 8, 0.3)",
          }}
        >
          <strong style={{ color: "var(--ac-status-review-required)" }}>Unmatched Asset Identifiers ({job.unmatched_assets.length}): </strong>
          <span className="ac-text-sm">{job.unmatched_assets.join(", ")}</span>
        </div>
      )}

      {error && (
        <div
          className="ac-card"
          style={{
            padding: "var(--ac-space-3)",
            marginBottom: "var(--ac-space-4)",
            color: "var(--ac-status-non-compliant)",
            background: "rgba(239, 68, 68, 0.08)",
          }}
        >
          {error.message}
        </div>
      )}

      {/* Row inspection table */}
      <h3 className="ac-h3" style={{ marginBottom: "var(--ac-space-2)" }}>
        Row Inspection ({filteredRows.length} shown)
      </h3>
      <DataTable<BackendImportRowResult> columns={rowColumns} rows={filteredRows} emptyMessage="No rows in this filter." />

      {/* Customer Confirmation Modal */}
      {confirmOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            className="ac-card"
            style={{
              maxWidth: 540,
              width: "100%",
              padding: "var(--ac-space-6)",
              background: "var(--ac-surface)",
              boxShadow: "0 20px 25px -5px rgba(0,0,0,0.5)",
            }}
          >
            <h2 className="ac-h2" style={{ marginTop: 0 }}>Confirm Operational Import</h2>
            <p className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
              You are authorizing the batch ingestion of <strong>{job.rows_valid}</strong> authoritative {job.domain.toLowerCase()} records into your tenant organization.
            </p>
            <div
              style={{
                background: "rgba(255,255,255,0.04)",
                padding: "var(--ac-space-3)",
                borderRadius: "var(--ac-radius-md)",
                marginBottom: "var(--ac-space-4)",
                fontSize: 13,
              }}
            >
              <div>• File: <strong>{job.filename}</strong></div>
              <div>• Domain Target: <strong>{job.domain}</strong></div>
              <div>• Valid Records to Persist: <strong>{job.rows_valid}</strong></div>
              {job.warning_count ? <div>• Warnings Accepted: <strong>{job.warning_count}</strong></div> : null}
              <div>• Operational State: Counters & compliance will update immediately upon commit.</div>
            </div>
            <div className="ac-flex ac-justify-end ac-gap-3">
              <button className="ac-btn" onClick={() => setConfirmOpen(false)} disabled={committing}>
                Cancel
              </button>
              <button
                className="ac-btn ac-btn-primary"
                onClick={() => {
                  setConfirmOpen(false);
                  handleCommit();
                }}
                disabled={committing}
              >
                {committing ? "Committing..." : "Authorize & Commit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DataImportPage() {
  const { accessToken } = useSession();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [domain, setDomain] = useState<"AIRCRAFT" | "DRONE" | "FLIGHT">("FLIGHT");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sheetName, setSheetName] = useState<string>("");
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [activeJob, setActiveJob] = useState<BackendImportJobDetail | null>(null);
  const [history, setHistory] = useState<BackendImportJob[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<NormalizedApiError | null>(null);

  const loadHistory = () => {
    if (!accessToken) return;
    setLoadingHistory(true);
    setHistoryError(null);
    dataImportApi
      .listJobs(accessToken)
      .then(setHistory)
      .catch((err) => {
        setHistoryError(normalizeApiError(err));
        setHistory([]);
      })
      .finally(() => setLoadingHistory(false));
  };

  useEffect(() => {
    loadHistory();
  }, [accessToken]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setError(null);
    }
  };

  const handleValidate = () => {
    if (!accessToken || !selectedFile) return;
    setValidating(true);
    setError(null);

    dataImportApi
      .validate(accessToken, domain, selectedFile, sheetName || undefined)
      .then((job) => {
        setActiveJob(job);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setValidating(false));
  };

  const historyColumns: Column<BackendImportJob>[] = [
    {
      key: "created_at",
      header: "Date",
      render: (j: BackendImportJob) => new Date(j.created_at).toLocaleString(),
    },
    { key: "filename", header: "File Name", render: (j: BackendImportJob) => j.filename },
    { key: "domain", header: "Domain", render: (j: BackendImportJob) => j.domain },
    {
      key: "status",
      header: "Status",
      render: (j: BackendImportJob) => {
        const badgeProps = genericStatusBadge(j.status);
        return <StatusBadge {...badgeProps} />;
      },
    },
    {
      key: "summary",
      header: "Records",
      render: (j: BackendImportJob) => `${j.rows_created || j.rows_valid} / ${j.rows_total} (${j.rows_failed} failed)`,
    },
  ];

  return (
    <div className="ac-page">
      <Breadcrumbs items={[{ label: "Data & Migration" }, { label: "Import Center" }]} />

      <div className="ac-page-header">
        <div>
          <h1 className="ac-h1">Customer Data Import Center</h1>
          <p className="ac-page-subtitle">
            Migrate historical spreadsheets (.xlsx, .csv) and establish authoritative operational records.
          </p>
        </div>
      </div>

      {activeJob ? (
        <ValidationPreview
          job={activeJob}
          onCommitted={() => {
            loadHistory();
          }}
          onCancel={() => {
            setActiveJob(null);
            setSelectedFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
        />
      ) : (
        <div className="ac-grid ac-grid-cols-3 ac-gap-6 ac-section">
          {/* Main Upload Form */}
          <div className="ac-card ac-col-span-2" style={{ padding: "var(--ac-space-6)" }}>
            <h2 className="ac-h2" style={{ marginTop: 0, marginBottom: "var(--ac-space-4)" }}>
              New Data Ingestion
            </h2>

            {/* Domain Selector */}
            <div style={{ marginBottom: "var(--ac-space-4)" }}>
              <label className="ac-label" style={{ display: "block", marginBottom: "var(--ac-space-2)" }}>
                Target Record Domain
              </label>
              <div className="ac-flex ac-gap-3">
                {(["FLIGHT", "AIRCRAFT", "DRONE"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    className={`ac-btn ${domain === d ? "ac-btn-primary" : ""}`}
                    onClick={() => setDomain(d)}
                  >
                    {d === "FLIGHT" ? "Flight & Mission Logs" : d === "AIRCRAFT" ? "Fixed-Wing Aircraft" : "Drone UAV Fleet"}
                  </button>
                ))}
              </div>
            </div>

            {/* File Dropzone / Input */}
            <div style={{ marginBottom: "var(--ac-space-4)" }}>
              <label className="ac-label" style={{ display: "block", marginBottom: "var(--ac-space-2)" }}>
                Upload Spreadsheets (.xlsx, .xls, .csv)
              </label>
              <div
                style={{
                  border: "2px dashed var(--ac-border)",
                  borderRadius: "var(--ac-radius-lg)",
                  padding: "var(--ac-space-6)",
                  textAlign: "center",
                  background: "rgba(255,255,255,0.02)",
                  cursor: "pointer",
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={handleFileChange}
                  style={{ display: "none" }}
                />
                <div style={{ fontSize: 28, marginBottom: 8 }}>📁</div>
                {selectedFile ? (
                  <div>
                    <div style={{ fontWeight: 600 }}>{selectedFile.name}</div>
                    <div className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>
                      {(selectedFile.size / 1024).toFixed(1)} KB · Click to choose different file
                    </div>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontWeight: 500 }}>Click to select or drag and drop file</div>
                    <div className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>
                      Excel (.xlsx, .xls) multi-sheet workbooks or RFC 4180 CSV files
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Multi-sheet selection option */}
            {selectedFile && selectedFile.name.endsWith(".xlsx") && (
              <div style={{ marginBottom: "var(--ac-space-4)" }}>
                <label className="ac-label" style={{ display: "block", marginBottom: "var(--ac-space-1)" }}>
                  Worksheet Name (Optional)
                </label>
                <input
                  type="text"
                  className="ac-input"
                  placeholder="e.g. Flights, Sheet1 (defaults to first active sheet)"
                  value={sheetName}
                  onChange={(e) => setSheetName(e.target.value)}
                  style={{ width: "100%" }}
                />
              </div>
            )}

            {error && (
              <div
                className="ac-card"
                style={{
                  padding: "var(--ac-space-3)",
                  marginBottom: "var(--ac-space-4)",
                  color: "var(--ac-status-non-compliant)",
                  background: "rgba(239, 68, 68, 0.08)",
                }}
              >
                {error.message}
              </div>
            )}

            <div className="ac-flex ac-justify-end ac-gap-3">
              <button
                className="ac-btn ac-btn-primary"
                disabled={!selectedFile || validating}
                onClick={handleValidate}
              >
                {validating ? "Parsing & Validating..." : "Stage & Validate Data"}
              </button>
            </div>
          </div>

          {/* Migration Guidance & Templates */}
          <div className="ac-card" style={{ padding: "var(--ac-space-6)" }}>
            <h3 className="ac-h3" style={{ marginTop: 0 }}>
              Onboarding Guidelines
            </h3>
            <p className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
              Data ingested via the Import Center traverses the exact same domain pathways as live manual logging.
            </p>

            <div style={{ marginBottom: "var(--ac-space-4)" }}>
              <div className="ac-text-xs" style={{ fontWeight: 600, textTransform: "uppercase", color: "var(--ac-text-muted)", marginBottom: 6 }}>
                Download Canonical Templates
              </div>
              <div className="ac-flex ac-flex-col ac-gap-2">
                <button className="ac-btn ac-btn-sm" onClick={() => downloadTemplate("FLIGHT")}>
                  📥 Flight Records (.csv)
                </button>
                <button className="ac-btn ac-btn-sm" onClick={() => downloadTemplate("AIRCRAFT")}>
                  📥 Fixed-Wing Aircraft (.csv)
                </button>
                <button className="ac-btn ac-btn-sm" onClick={() => downloadTemplate("DRONE")}>
                  📥 Drone UAV Fleet (.csv)
                </button>
              </div>
            </div>

            <div
              style={{
                fontSize: 12,
                color: "var(--ac-text-muted)",
                borderTop: "1px solid var(--ac-border)",
                paddingTop: "var(--ac-space-3)",
              }}
            >
              <div>• <strong>Auto-Synonym Detection:</strong> Columns like "Reg No", "Tail", "FH", "FC", "Pilot" are automatically mapped.</div>
              <div style={{ marginTop: 4 }}>• <strong>Carry-in Baselines:</strong> Historical flight hours prior to your baseline effective date will not be double-counted.</div>
              <div style={{ marginTop: 4 }}>• <strong>Tenant Isolation:</strong> Datasets are strictly private and isolated to your organization.</div>
            </div>
          </div>
        </div>
      )}

      {/* Import History Table */}
      <div className="ac-section">
        <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: "var(--ac-space-3)" }}>
          <h2 className="ac-h2" style={{ margin: 0 }}>
            Recent Import Jobs
          </h2>
          <button className="ac-btn ac-btn-sm" onClick={loadHistory} disabled={loadingHistory}>
            {loadingHistory ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        <RealDataPanel
          loading={loadingHistory}
          error={historyError}
          isEmpty={history.length === 0}
          emptyMessage="No import jobs executed yet."
        >
          <DataTable<BackendImportJob> columns={historyColumns} rows={history} emptyMessage="No import jobs executed yet." />
        </RealDataPanel>
      </div>
    </div>
  );
}
