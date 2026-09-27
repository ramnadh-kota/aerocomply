"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, complianceObligationStatusBadge, evidenceVerificationBadge, priorityBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import {
  complianceObligationsApi,
  type BackendComplianceObligation,
  type BackendComplianceTraceability,
} from "@/lib/api/compliance";
import { evidenceApi } from "@/lib/api/evidence";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const EVIDENCE_TYPE_OPTIONS = [
  { value: "INSPECTION_RECORD", label: "Inspection Record / NDT Report" },
  { value: "MAINTENANCE_RECORD", label: "Maintenance Record / Logbook Entry" },
  { value: "CERTIFICATE", label: "Certificate of Conformance (CoC)" },
  { value: "OEM_DOCUMENT", label: "OEM Technical Publication / SB" },
  { value: "WORK_ORDER_SIGNOFF", label: "Work Order Task Signoff" },
  { value: "OTHER", label: "Other Technical Evidence" },
];

export default function ObligationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const obligationId = params?.id;
  const { accessToken, isAuthenticated } = useSession();

  const [obligation, setObligation] = useState<BackendComplianceObligation | null>(null);
  const [traceability, setTraceability] = useState<BackendComplianceTraceability | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Attach evidence modal state
  const [showAttachModal, setShowAttachModal] = useState(false);
  const [newEvidenceTitle, setNewEvidenceTitle] = useState("");
  const [newEvidenceType, setNewEvidenceType] = useState("INSPECTION_RECORD");
  const [newEvidenceSource, setNewEvidenceSource] = useState("");
  const [newEvidenceDesc, setNewEvidenceDesc] = useState("");

  // Rejection modal state
  const [rejectingEvidenceId, setRejectingEvidenceId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");

  const loadData = async () => {
    if (!accessToken || !obligationId) return;
    setLoading(true);
    setError(null);
    try {
      const [obData, traceData] = await Promise.all([
        complianceObligationsApi.get(accessToken, obligationId),
        complianceObligationsApi.traceability(accessToken, obligationId),
      ]);
      setObligation(obData);
      setTraceability(traceData);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated && accessToken && obligationId) {
      loadData();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, accessToken, obligationId]);

  const handleReevaluate = async () => {
    if (!accessToken || !obligationId) return;
    setActionLoading(true);
    setSuccessMessage(null);
    try {
      await complianceObligationsApi.evaluate(accessToken, obligationId);
      setSuccessMessage("Applicability engine successfully re-evaluated against asset configuration snapshot.");
      await loadData();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setActionLoading(false);
    }
  };

  const handleAttachEvidence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !obligationId || !newEvidenceTitle) return;
    setActionLoading(true);
    setError(null);
    try {
      await complianceObligationsApi.attachEvidence(accessToken, obligationId, {
        title: newEvidenceTitle,
        evidence_type: newEvidenceType,
        source: newEvidenceSource || "Technical Records Portal",
        description: newEvidenceDesc,
      });
      setShowAttachModal(false);
      setNewEvidenceTitle("");
      setNewEvidenceSource("");
      setNewEvidenceDesc("");
      setSuccessMessage("Evidence record attached to compliance digital thread.");
      await loadData();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerifyEvidence = async (evidenceId: string) => {
    if (!accessToken) return;
    setActionLoading(true);
    setError(null);
    try {
      await evidenceApi.verify(accessToken, evidenceId, "Authorized technical compliance verification signoff.");
      setSuccessMessage("Evidence verified. Compliance state updated.");
      await loadData();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setActionLoading(false);
    }
  };

  const handleRejectEvidence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !rejectingEvidenceId || !rejectionReason) return;
    setActionLoading(true);
    setError(null);
    try {
      await evidenceApi.reject(accessToken, rejectingEvidenceId, rejectionReason);
      setRejectingEvidenceId(null);
      setRejectionReason("");
      setSuccessMessage("Evidence rejected. Compliance state transitioned to reflect active blocker.");
      await loadData();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="ac-section">
        <p className="ac-text-muted">Loading compliance digital thread...</p>
      </div>
    );
  }

  if (error && !obligation) {
    return (
      <div className="ac-section">
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compliance", href: "/compliance" }, { label: "Obligation" }]} />
        <div className="ac-card" style={{ borderColor: "var(--ac-status-non_compliant)", marginTop: 16 }}>
          <h2 className="ac-h2" style={{ color: "var(--ac-status-non_compliant)" }}>Error Loading Obligation</h2>
          <p className="ac-text-sm">{error.message}</p>
          <Link href="/compliance" className="ac-btn" style={{ marginTop: 12 }}>Back to Compliance Overview</Link>
        </div>
      </div>
    );
  }

  if (!obligation || !traceability) {
    return (
      <div className="ac-section">
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compliance", href: "/compliance" }, { label: "Obligation" }]} />
        <p className="ac-text-muted" style={{ marginTop: 16 }}>No obligation found with ID {obligationId}.</p>
      </div>
    );
  }

  const obBadge = complianceObligationStatusBadge(obligation.status);
  const pBadge = priorityBadge(obligation.priority);
  const why = traceability.why_applies;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Compliance", href: "/compliance" },
          { label: "Obligations" },
          { label: obligation.id.slice(0, 8) },
        ]}
      />

      {/* Header */}
      <div className="ac-section-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
            <span className="ac-eyebrow" style={{ color: "var(--ac-accent)" }}>COMPLIANCE DIGITAL THREAD</span>
            <span className="ac-text-muted">•</span>
            <span className="ac-mono ac-text-xs">{obligation.id}</span>
          </div>
          <h1 className="ac-h1">
            {traceability.requirement_number}: {traceability.requirement_title}
          </h1>
          <p className="ac-subtitle">
            Asset: <span className="ac-mono" style={{ fontWeight: 600 }}>{traceability.asset.identifier}</span> ({traceability.asset.variant})
          </p>
        </div>
        <div className="ac-flex ac-gap-2 ac-items-center">
          <StatusBadge status={obBadge.status} label={obBadge.label} />
          <StatusBadge status={pBadge.status} label={`Priority: ${pBadge.label}`} />
          <button
            onClick={handleReevaluate}
            disabled={actionLoading}
            className="ac-btn"
            style={{ fontSize: 12, padding: "6px 12px", background: "var(--ac-bg-surface-hover)" }}
          >
            {actionLoading ? "Evaluating..." : "↻ Re-evaluate Applicability"}
          </button>
          <button
            onClick={() => setShowAttachModal(true)}
            className="ac-btn ac-btn-primary"
            style={{ fontSize: 12, padding: "6px 12px" }}
          >
            + Attach Evidence
          </button>
        </div>
      </div>

      {successMessage && (
        <div className="ac-card" style={{ borderColor: "var(--ac-status-compliant)", marginBottom: 16, padding: "10px 16px" }}>
          <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-compliant)" }}>
            ✓ {successMessage}
          </p>
        </div>
      )}

      {error && (
        <div className="ac-card" style={{ borderColor: "var(--ac-status-non_compliant)", marginBottom: 16, padding: "10px 16px" }}>
          <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non_compliant)" }}>
            ⚠ {error.message}
          </p>
        </div>
      )}

      {/* 6-Step Digital Thread Flow Visualizer */}
      <section className="ac-section" style={{ marginBottom: 24 }}>
        <div className="ac-card" style={{ background: "var(--ac-bg-surface)", padding: 16 }}>
          <p className="ac-eyebrow" style={{ marginBottom: 12, color: "var(--ac-text-muted)" }}>
            DIGITAL THREAD TRACEABILITY PIPELINE
          </p>
          <div
            className="ac-flex ac-items-center ac-gap-2"
            style={{
              overflowX: "auto",
              paddingBottom: 8,
              fontSize: 13,
            }}
          >
            {/* Step 1: Requirement */}
            <div style={{ flex: 1, minWidth: 150, padding: "10px 12px", borderRadius: 6, background: "var(--ac-bg-surface-hover)", border: "1px solid var(--ac-border)" }}>
              <div className="ac-eyebrow" style={{ fontSize: 10, color: "var(--ac-text-muted)" }}>1. REQUIREMENT</div>
              <div className="ac-mono" style={{ fontWeight: 600, marginTop: 4 }}>{traceability.requirement_number}</div>
              <div className="ac-text-xs ac-text-muted" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{traceability.requirement_title}</div>
            </div>

            <span style={{ color: "var(--ac-text-muted)" }}>→</span>

            {/* Step 2: Applicability */}
            <div style={{ flex: 1, minWidth: 150, padding: "10px 12px", borderRadius: 6, background: "var(--ac-bg-surface-hover)", border: "1px solid var(--ac-border)" }}>
              <div className="ac-eyebrow" style={{ fontSize: 10, color: "var(--ac-text-muted)" }}>2. APPLICABILITY</div>
              <div style={{ marginTop: 4 }}>
                <StatusBadge status={why.is_applicable ? "APPLICABLE" : why.system_result === "INSUFFICIENT_DATA" ? "INSUFFICIENT_DATA" : "NOT_APPLICABLE"} label={why.system_result ?? "EVALUATED"} />
              </div>
              <div className="ac-text-xs ac-text-muted" style={{ marginTop: 4 }}>{why.rule_code ?? "Rule linked"}</div>
            </div>

            <span style={{ color: "var(--ac-text-muted)" }}>→</span>

            {/* Step 3: Required Action */}
            <div style={{ flex: 1, minWidth: 160, padding: "10px 12px", borderRadius: 6, background: "var(--ac-bg-surface-hover)", border: "1px solid var(--ac-border)" }}>
              <div className="ac-eyebrow" style={{ fontSize: 10, color: "var(--ac-text-muted)" }}>3. REQUIRED ACTION</div>
              <div style={{ fontWeight: 500, fontSize: 12, marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {obligation.required_action || "Technical Compliance Action"}
              </div>
              <div className="ac-text-xs ac-text-muted" style={{ marginTop: 4 }}>
                Due: {obligation.due_date ? new Date(obligation.due_date).toLocaleDateString() : "Pending"}
              </div>
            </div>

            <span style={{ color: "var(--ac-text-muted)" }}>→</span>

            {/* Step 4: Evidence */}
            <div style={{ flex: 1, minWidth: 150, padding: "10px 12px", borderRadius: 6, background: "var(--ac-bg-surface-hover)", border: "1px solid var(--ac-border)" }}>
              <div className="ac-eyebrow" style={{ fontSize: 10, color: "var(--ac-text-muted)" }}>4. EVIDENCE</div>
              <div style={{ marginTop: 4, fontWeight: 600 }}>
                {traceability.provided_evidence.length} Record(s)
              </div>
              <div className="ac-text-xs ac-text-muted" style={{ marginTop: 4 }}>
                {traceability.what_evidence_required.length} Required item(s)
              </div>
            </div>

            <span style={{ color: "var(--ac-text-muted)" }}>→</span>

            {/* Step 5: Verification */}
            <div style={{ flex: 1, minWidth: 150, padding: "10px 12px", borderRadius: 6, background: "var(--ac-bg-surface-hover)", border: "1px solid var(--ac-border)" }}>
              <div className="ac-eyebrow" style={{ fontSize: 10, color: "var(--ac-text-muted)" }}>5. VERIFICATION</div>
              <div style={{ marginTop: 4 }}>
                <StatusBadge
                  status={traceability.is_verified ? "VERIFIED" : obligation.status === "NON_COMPLIANT" ? "NON_COMPLIANT" : "UNVERIFIED"}
                  label={traceability.is_verified ? "Verified" : obligation.status === "NON_COMPLIANT" ? "Rejected / Blocker" : "Pending Signoff"}
                />
              </div>
              <div className="ac-text-xs ac-text-muted" style={{ marginTop: 4 }}>
                {obligation.verified_at ? new Date(obligation.verified_at).toLocaleDateString() : "Unverified"}
              </div>
            </div>

            <span style={{ color: "var(--ac-text-muted)" }}>→</span>

            {/* Step 6: Compliance State */}
            <div style={{ flex: 1, minWidth: 150, padding: "10px 12px", borderRadius: 6, background: "var(--ac-bg-surface-hover)", border: `2px solid ${obBadge.status === "COMPLIANT" ? "var(--ac-status-compliant)" : "var(--ac-border)"}` }}>
              <div className="ac-eyebrow" style={{ fontSize: 10, color: "var(--ac-text-muted)" }}>6. COMPLIANCE STATE</div>
              <div style={{ marginTop: 4 }}>
                <StatusBadge status={obBadge.status} label={obBadge.label} />
              </div>
              <div className="ac-text-xs ac-text-muted" style={{ marginTop: 4 }}>
                {traceability.is_compliant ? "Deterministic Pass" : "Action Required"}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Grid: Explainability & Action Details */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
        {/* Left Column: Why Applies + Reasoning */}
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Applicability Intelligence</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>
              <strong>Why does this requirement apply?</strong>
            </p>
            <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginBottom: 12 }}>
              <StatusBadge status={why.is_applicable ? "APPLICABLE" : "UNKNOWN"} label={why.system_result ?? "Evaluated"} />
              <span className="ac-text-sm ac-mono">{why.rule_code ?? "Direct Asset Assignment"}</span>
            </div>

            {why.rule_title && (
              <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>
                Rule: <span className="ac-text-secondary">{why.rule_title}</span>
              </p>
            )}

            {why.reasoning_trace && why.reasoning_trace.length > 0 && (
              <div style={{ marginTop: 12, padding: 12, background: "var(--ac-bg-surface-hover)", borderRadius: 6 }}>
                <p className="ac-eyebrow" style={{ fontSize: 11, marginBottom: 6 }}>KLEENE 3-VALUED REASONING TRACE</p>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }} className="ac-mono">
                  {why.reasoning_trace.map((trace, idx) => (
                    <li key={idx} style={{ marginBottom: 4 }}>{trace}</li>
                  ))}
                </ul>
              </div>
            )}

            {why.evaluated_at && (
              <p className="ac-text-xs ac-text-muted" style={{ marginTop: 12, margin: 0 }}>
                Evaluated against immutable configuration snapshot at: {new Date(why.evaluated_at).toLocaleString()}
              </p>
            )}
          </div>
        </section>

        {/* Right Column: Required Action & Blocker Analysis */}
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Resolution & Blocker Analysis</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              <strong>Required Action:</strong>
            </p>
            <p className="ac-text-sm" style={{ margin: "0 0 12px", color: "var(--ac-text-secondary)" }}>
              {obligation.required_action || "Complete required maintenance/inspection procedure as specified."}
            </p>

            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
              <strong>Current State Explanation:</strong>
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 12px" }}>
              {traceability.why_current_state}
            </p>

            {traceability.blockers.length > 0 ? (
              <div style={{ padding: 12, background: "rgba(239, 68, 68, 0.08)", border: "1px solid var(--ac-status-non_compliant)", borderRadius: 6 }}>
                <p className="ac-eyebrow" style={{ color: "var(--ac-status-non_compliant)", fontSize: 11, marginBottom: 6 }}>
                  ACTIVE COMPLIANCE BLOCKERS ({traceability.blockers.length})
                </p>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                  {traceability.blockers.map((b, i) => (
                    <li key={i} style={{ color: "var(--ac-status-non_compliant)", marginBottom: 4 }}>{b}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div style={{ padding: 12, background: "rgba(34, 197, 94, 0.08)", border: "1px solid var(--ac-status-compliant)", borderRadius: 6 }}>
                <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-compliant)", fontWeight: 500 }}>
                  ✓ No blockers detected. All required actions and evidence are verified.
                </p>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Required Evidence Specifications */}
      <section className="ac-section" style={{ marginBottom: 24 }}>
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Required Evidence Gates</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          {traceability.what_evidence_required.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ padding: 16, margin: 0 }}>
              No specific evidence types pre-mandated. Any verified technical signoff or inspection record satisfies this obligation.
            </p>
          ) : (
            <table className="ac-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Evidence Type</th>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Requirement Specification</th>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {traceability.what_evidence_required.map((req, idx) => {
                  const matchingProvided = traceability.provided_evidence.filter(
                    (p) => p.evidence_type === req.type && p.verification_status === "VERIFIED"
                  );
                  const isSatisfied = matchingProvided.length > 0;
                  return (
                    <tr key={idx} style={{ borderTop: "1px solid var(--ac-border)" }}>
                      <td style={{ padding: "12px 16px" }}>
                        <span className="ac-mono ac-text-sm" style={{ fontWeight: 600 }}>{req.type}</span>
                      </td>
                      <td style={{ padding: "12px 16px", color: "var(--ac-text-secondary)" }}>
                        {req.description}
                      </td>
                      <td style={{ padding: "12px 16px" }}>
                        <StatusBadge
                          status={isSatisfied ? "VERIFIED" : "UNVERIFIED"}
                          label={isSatisfied ? "Satisfied" : "Missing / Unverified"}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Attached Evidence Digital Thread */}
      <section className="ac-section">
        <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
          <h2 className="ac-h2">Attached Evidence Digital Thread ({traceability.provided_evidence.length})</h2>
          <button
            onClick={() => setShowAttachModal(true)}
            className="ac-btn"
            style={{ fontSize: 12, padding: "4px 10px" }}
          >
            + Attach Evidence
          </button>
        </div>

        <div className="ac-card" style={{ padding: 0 }}>
          {traceability.provided_evidence.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center" }}>
              <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 12px" }}>
                No evidence has been attached to this obligation yet.
              </p>
              <button
                onClick={() => setShowAttachModal(true)}
                className="ac-btn ac-btn-primary"
                style={{ fontSize: 12 }}
              >
                Attach First Evidence Item
              </button>
            </div>
          ) : (
            <table className="ac-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Title / Record</th>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Type</th>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Source</th>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Verification Status</th>
                  <th style={{ textAlign: "left", padding: "10px 16px" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {traceability.provided_evidence.map((ev) => {
                  const vBadge = evidenceVerificationBadge(ev.verification_status);
                  return (
                    <tr key={ev.id} style={{ borderTop: "1px solid var(--ac-border)" }}>
                      <td style={{ padding: "12px 16px" }}>
                        <Link href={`/evidence/${ev.id}`} style={{ fontWeight: 600, color: "var(--ac-accent)" }}>
                          {ev.title || "Untitled Evidence"}
                        </Link>
                        <div className="ac-mono ac-text-xs ac-text-muted" style={{ marginTop: 2 }}>{ev.id}</div>
                        {ev.rejection_reason && (
                          <div className="ac-text-xs" style={{ color: "var(--ac-status-non_compliant)", marginTop: 4 }}>
                            Rejection Note: {ev.rejection_reason}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "12px 16px" }}>
                        <span className="ac-mono ac-text-sm">{ev.evidence_type || "RECORD"}</span>
                      </td>
                      <td style={{ padding: "12px 16px", color: "var(--ac-text-secondary)" }}>
                        {ev.source || "Direct upload"}
                      </td>
                      <td style={{ padding: "12px 16px" }}>
                        <StatusBadge status={vBadge.status} label={vBadge.label} />
                        {ev.verified_at && (
                          <div className="ac-text-xs ac-text-muted" style={{ marginTop: 2 }}>
                            Verified: {new Date(ev.verified_at).toLocaleDateString()}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "12px 16px" }}>
                        <div className="ac-flex ac-gap-2">
                          {ev.verification_status !== "VERIFIED" && (
                            <button
                              onClick={() => handleVerifyEvidence(ev.id)}
                              disabled={actionLoading}
                              className="ac-btn"
                              style={{
                                fontSize: 11,
                                padding: "4px 8px",
                                background: "rgba(34, 197, 94, 0.1)",
                                color: "var(--ac-status-compliant)",
                                border: "1px solid var(--ac-status-compliant)",
                              }}
                            >
                              ✓ Verify
                            </button>
                          )}
                          {ev.verification_status !== "REJECTED" && (
                            <button
                              onClick={() => setRejectingEvidenceId(ev.id)}
                              disabled={actionLoading}
                              className="ac-btn"
                              style={{
                                fontSize: 11,
                                padding: "4px 8px",
                                background: "rgba(239, 68, 68, 0.1)",
                                color: "var(--ac-status-non_compliant)",
                                border: "1px solid var(--ac-status-non_compliant)",
                              }}
                            >
                              ✕ Reject
                            </button>
                          )}
                          <Link
                            href={`/evidence/${ev.id}`}
                            className="ac-btn"
                            style={{ fontSize: 11, padding: "4px 8px" }}
                          >
                            Details →
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Attach Evidence Modal */}
      {showAttachModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            className="ac-card"
            style={{
              width: "100%",
              maxWidth: 500,
              padding: 24,
              background: "var(--ac-bg-surface)",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
          >
            <h2 className="ac-h2" style={{ marginBottom: 16 }}>Attach Evidence to Digital Thread</h2>
            <form onSubmit={handleAttachEvidence}>
              <div style={{ marginBottom: 12 }}>
                <label className="ac-eyebrow" style={{ display: "block", marginBottom: 4 }}>Evidence Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Ultrasonic NDT Disk Inspection Report"
                  value={newEvidenceTitle}
                  onChange={(e) => setNewEvidenceTitle(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "var(--ac-bg-input)",
                    border: "1px solid var(--ac-border)",
                    borderRadius: 6,
                    color: "inherit",
                  }}
                />
              </div>

              <div style={{ marginBottom: 12 }}>
                <label className="ac-eyebrow" style={{ display: "block", marginBottom: 4 }}>Evidence Type</label>
                <select
                  value={newEvidenceType}
                  onChange={(e) => setNewEvidenceType(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "var(--ac-bg-input)",
                    border: "1px solid var(--ac-border)",
                    borderRadius: 6,
                    color: "inherit",
                  }}
                >
                  {EVIDENCE_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: 12 }}>
                <label className="ac-eyebrow" style={{ display: "block", marginBottom: 4 }}>Source / Issuing Authority</label>
                <input
                  type="text"
                  placeholder="e.g. NDT Facility Bay 2 / FAA Repair Station 42"
                  value={newEvidenceSource}
                  onChange={(e) => setNewEvidenceSource(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "var(--ac-bg-input)",
                    border: "1px solid var(--ac-border)",
                    borderRadius: 6,
                    color: "inherit",
                  }}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label className="ac-eyebrow" style={{ display: "block", marginBottom: 4 }}>Description / Technical Notes</label>
                <textarea
                  rows={3}
                  placeholder="Enter scan findings, signoff notes, or certificate numbers..."
                  value={newEvidenceDesc}
                  onChange={(e) => setNewEvidenceDesc(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "var(--ac-bg-input)",
                    border: "1px solid var(--ac-border)",
                    borderRadius: 6,
                    color: "inherit",
                    fontFamily: "inherit",
                  }}
                />
              </div>

              <div className="ac-flex ac-justify-end ac-gap-2">
                <button
                  type="button"
                  onClick={() => setShowAttachModal(false)}
                  className="ac-btn"
                  style={{ padding: "8px 16px" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="ac-btn ac-btn-primary"
                  style={{ padding: "8px 16px" }}
                >
                  {actionLoading ? "Attaching..." : "Attach Record"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reject Evidence Modal */}
      {rejectingEvidenceId && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            className="ac-card"
            style={{
              width: "100%",
              maxWidth: 450,
              padding: 24,
              background: "var(--ac-bg-surface)",
              borderColor: "var(--ac-status-non_compliant)",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
          >
            <h2 className="ac-h2" style={{ color: "var(--ac-status-non_compliant)", marginBottom: 8 }}>
              Reject Evidence Record
            </h2>
            <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 16 }}>
              Rejecting evidence marks the obligation NON_COMPLIANT and records an active compliance blocker on the asset.
            </p>
            <form onSubmit={handleRejectEvidence}>
              <div style={{ marginBottom: 16 }}>
                <label className="ac-eyebrow" style={{ display: "block", marginBottom: 4 }}>Rejection Reason *</label>
                <textarea
                  required
                  rows={3}
                  placeholder="Explain why this evidence fails to satisfy the technical requirement..."
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "var(--ac-bg-input)",
                    border: "1px solid var(--ac-border)",
                    borderRadius: 6,
                    color: "inherit",
                    fontFamily: "inherit",
                  }}
                />
              </div>

              <div className="ac-flex ac-justify-end ac-gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setRejectingEvidenceId(null);
                    setRejectionReason("");
                  }}
                  className="ac-btn"
                  style={{ padding: "8px 16px" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="ac-btn"
                  style={{
                    padding: "8px 16px",
                    background: "var(--ac-status-non_compliant)",
                    color: "#fff",
                  }}
                >
                  {actionLoading ? "Rejecting..." : "Confirm Rejection"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
