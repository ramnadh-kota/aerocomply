"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, evidenceVerificationBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { evidenceApi, type BackendEvidence } from "@/lib/api/evidence";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function ComplianceEvidenceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const evidenceId = params?.id;
  const { accessToken, isAuthenticated } = useSession();

  const [evidence, setEvidence] = useState<BackendEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Reject modal
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");

  const loadEvidence = async () => {
    if (!accessToken || !evidenceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await evidenceApi.get(accessToken, evidenceId);
      setEvidence(data);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated && accessToken && evidenceId) {
      loadEvidence();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, accessToken, evidenceId]);

  const handleVerify = async () => {
    if (!accessToken || !evidenceId) return;
    setActionLoading(true);
    setError(null);
    try {
      await evidenceApi.verify(accessToken, evidenceId, "Technical compliance review and verification approval.");
      setSuccessMessage("Evidence record verified. Compliance state updated.");
      await loadEvidence();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !evidenceId || !rejectionReason) return;
    setActionLoading(true);
    setError(null);
    try {
      await evidenceApi.reject(accessToken, evidenceId, rejectionReason);
      setShowRejectModal(false);
      setRejectionReason("");
      setSuccessMessage("Evidence record rejected with reason. Compliance state updated.");
      await loadEvidence();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="ac-section">
        <p className="ac-text-muted">Loading evidence digital thread record...</p>
      </div>
    );
  }

  if (error && !evidence) {
    return (
      <div className="ac-section">
        <Breadcrumbs
          items={[
            { label: "Dashboard", href: "/dashboard" },
            { label: "Compliance", href: "/compliance" },
            { label: "Evidence" },
          ]}
        />
        <div className="ac-card" style={{ borderColor: "var(--ac-status-non_compliant)", marginTop: 16 }}>
          <h2 className="ac-h2" style={{ color: "var(--ac-status-non_compliant)" }}>Error Loading Evidence</h2>
          <p className="ac-text-sm">{error.message}</p>
          <Link href="/compliance" className="ac-btn" style={{ marginTop: 12 }}>Back to Compliance</Link>
        </div>
      </div>
    );
  }

  if (!evidence) {
    return (
      <div className="ac-section">
        <Breadcrumbs
          items={[
            { label: "Dashboard", href: "/dashboard" },
            { label: "Compliance", href: "/compliance" },
            { label: "Evidence" },
          ]}
        />
        <p className="ac-text-muted" style={{ marginTop: 16 }}>Evidence record not found.</p>
      </div>
    );
  }

  const vBadge = evidenceVerificationBadge(evidence.verification_status || "UNVERIFIED");

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Compliance", href: "/compliance" },
          ...(evidence.compliance_obligation_id
            ? [{ label: "Obligation", href: `/compliance/obligations/${evidence.compliance_obligation_id}` }]
            : []),
          { label: "Evidence" },
          { label: evidence.id.slice(0, 8) },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
            <span className="ac-eyebrow" style={{ color: "var(--ac-accent)" }}>EVIDENCE DIGITAL THREAD</span>
            <span className="ac-text-muted">•</span>
            <span className="ac-mono ac-text-xs">{evidence.id}</span>
          </div>
          <h1 className="ac-h1">{evidence.title || "Technical Evidence Record"}</h1>
          <p className="ac-subtitle">{evidence.description || "Digital thread verification artifact."}</p>
        </div>
        <div className="ac-flex ac-gap-2 ac-items-center">
          <StatusBadge status={vBadge.status} label={vBadge.label} />
          {evidence.verification_status !== "VERIFIED" && (
            <button
              onClick={handleVerify}
              disabled={actionLoading}
              className="ac-btn"
              style={{
                fontSize: 12,
                padding: "6px 12px",
                background: "rgba(34, 197, 94, 0.15)",
                color: "var(--ac-status-compliant)",
                border: "1px solid var(--ac-status-compliant)",
              }}
            >
              ✓ Verify Evidence
            </button>
          )}
          {evidence.verification_status !== "REJECTED" && (
            <button
              onClick={() => setShowRejectModal(true)}
              disabled={actionLoading}
              className="ac-btn"
              style={{
                fontSize: 12,
                padding: "6px 12px",
                background: "rgba(239, 68, 68, 0.15)",
                color: "var(--ac-status-non_compliant)",
                border: "1px solid var(--ac-status-non_compliant)",
              }}
            >
              ✕ Reject Evidence
            </button>
          )}
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

      {/* Grid: Metadata & Linked Records */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
        {/* Left Column: Metadata */}
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence Metadata</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Evidence Type: <span className="ac-mono" style={{ fontWeight: 600 }}>{evidence.evidence_type || "INSPECTION_RECORD"}</span>
            </p>
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Source / System: <span className="ac-text-secondary">{evidence.source || "Technical Records"}</span>
            </p>
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Captured At: <span className="ac-text-muted">{evidence.captured_at ? new Date(evidence.captured_at).toLocaleString() : "Not recorded"}</span>
            </p>
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Created: <span className="ac-text-muted">{new Date(evidence.created_at).toLocaleString()}</span>
            </p>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Updated: <span className="ac-text-muted">{evidence.updated_at ? new Date(evidence.updated_at).toLocaleString() : "N/A"}</span>
            </p>
          </div>
        </section>

        {/* Right Column: Linked Digital Thread Records */}
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Linked Digital Thread Entities</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Compliance Obligation:{" "}
              {evidence.compliance_obligation_id ? (
                <Link href={`/compliance/obligations/${evidence.compliance_obligation_id}`} className="ac-mono" style={{ color: "var(--ac-accent)", fontWeight: 600 }}>
                  {evidence.compliance_obligation_id} →
                </Link>
              ) : (
                <span className="ac-text-muted">Direct Asset Linkage</span>
              )}
            </p>

            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Regulatory Requirement:{" "}
              {evidence.regulatory_requirement_id ? (
                <span className="ac-mono">{evidence.regulatory_requirement_id}</span>
              ) : (
                <span className="ac-text-muted">Derived via Obligation</span>
              )}
            </p>

            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Aircraft / Asset:{" "}
              {evidence.aircraft_id ? (
                <Link href={`/aircraft/${evidence.aircraft_id}`} className="ac-mono" style={{ color: "var(--ac-accent)" }}>
                  Aircraft {evidence.aircraft_id.slice(0, 8)}
                </Link>
              ) : evidence.asset_id ? (
                <Link href={`/assets/${evidence.asset_id}`} className="ac-mono" style={{ color: "var(--ac-accent)" }}>
                  Asset {evidence.asset_id.slice(0, 8)}
                </Link>
              ) : (
                <span className="ac-text-muted">N/A</span>
              )}
            </p>

            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Component:{" "}
              {evidence.component_id ? (
                <span className="ac-mono">{evidence.component_id}</span>
              ) : (
                <span className="ac-text-muted">Not Component Specific</span>
              )}
            </p>

            <p className="ac-text-sm" style={{ margin: 0 }}>
              Work Order / Task:{" "}
              {evidence.work_order_id ? (
                <Link href={`/maintenance/work-orders/${evidence.work_order_id}`} className="ac-mono" style={{ color: "var(--ac-accent)" }}>
                  Work Order {evidence.work_order_id.slice(0, 8)}
                </Link>
              ) : evidence.task_id ? (
                <span className="ac-mono">Task {evidence.task_id.slice(0, 8)}</span>
              ) : (
                <span className="ac-text-muted">Direct Technical Evidence</span>
              )}
            </p>
          </div>
        </section>
      </div>

      {/* Verification & Audit History Section */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Verification & Provenance Audit Trail</h2>
        <div className="ac-card">
          <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginBottom: 12 }}>
            <StatusBadge status={vBadge.status} label={vBadge.label} />
            {evidence.verified_at && (
              <span className="ac-text-sm ac-text-muted">
                Verified on {new Date(evidence.verified_at).toLocaleString()}
              </span>
            )}
          </div>

          {evidence.verifier_user_id && (
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
              Verifier Identity: <span className="ac-mono">{evidence.verifier_user_id}</span>
            </p>
          )}

          {evidence.verification_notes && (
            <div style={{ marginTop: 8, padding: 12, background: "var(--ac-bg-surface-hover)", borderRadius: 6 }}>
              <p className="ac-eyebrow" style={{ fontSize: 11, marginBottom: 4 }}>VERIFICATION NOTES</p>
              <p className="ac-text-sm" style={{ margin: 0 }}>{evidence.verification_notes}</p>
            </div>
          )}

          {evidence.rejection_reason && (
            <div style={{ marginTop: 8, padding: 12, background: "rgba(239, 68, 68, 0.08)", border: "1px solid var(--ac-status-non_compliant)", borderRadius: 6 }}>
              <p className="ac-eyebrow" style={{ color: "var(--ac-status-non_compliant)", fontSize: 11, marginBottom: 4 }}>REJECTION AUDIT REASON</p>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non_compliant)" }}>{evidence.rejection_reason}</p>
            </div>
          )}

          {evidence.provenance && (
            <div style={{ marginTop: 12, padding: 12, background: "var(--ac-bg-surface-hover)", borderRadius: 6 }}>
              <p className="ac-eyebrow" style={{ fontSize: 11, marginBottom: 4 }}>PROVENANCE METADATA</p>
              <pre className="ac-mono ac-text-xs" style={{ margin: 0, overflowX: "auto" }}>
                {JSON.stringify(evidence.provenance, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </section>

      {/* Reject Modal */}
      {showRejectModal && (
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
              Reject Technical Evidence
            </h2>
            <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 16 }}>
              Provide a verifiable explanation for the rejection. This will be recorded in the immutable compliance audit log.
            </p>
            <form onSubmit={handleReject}>
              <div style={{ marginBottom: 16 }}>
                <label className="ac-eyebrow" style={{ display: "block", marginBottom: 4 }}>Rejection Reason *</label>
                <textarea
                  required
                  rows={3}
                  placeholder="e.g. Ultrasonic scan certificate missing NDT Level III inspector stamp."
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
                  onClick={() => setShowRejectModal(false)}
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
