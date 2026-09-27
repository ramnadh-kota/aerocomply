"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { StatusBadge, findingSeverityBadge, findingStatusBadge, complianceObligationStatusBadge, evidenceVerificationBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { complianceIntelligenceApi, type InspectionComplianceImpact } from "@/lib/api/compliance";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function InspectionComplianceImpactPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const { accessToken, isAuthenticated } = useSession();
  const [data, setData] = useState<InspectionComplianceImpact | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const refresh = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    complianceIntelligenceApi
      .getInspectionImpact(accessToken, params.id)
      .then((res) => setData(res))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [accessToken, isAuthenticated, params.id]);

  const handleResolve = async () => {
    if (!accessToken) return;
    try {
      const res = await complianceIntelligenceApi.resolveInspection(accessToken, params.id);
      if (res.resolved) {
        setActionSuccess(`Inspection package successfully satisfied compliance obligation ${res.obligation_id}. Status: ${res.obligation_status}`);
      } else {
        setActionSuccess(`Compliance evaluated: ${res.reason || "Gates not yet satisfied."}`);
      }
      refresh();
    } catch (err: any) {
      setError(normalizeApiError(err));
    }
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Compliance", href: "/compliance" },
          { label: "Inspection Impact" },
        ]}
      />

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={!loading && !error && !data}
        emptyMessage="Inspection impact could not be found."
      >
        {data && (
          <>
            <PageHeader
              breadcrumbs={[
                { label: "Dashboard", href: "/dashboard" },
                { label: "Compliance", href: "/compliance" },
                { label: "Inspection Impact" },
              ]}
              eyebrow="INSPECTION DIGITAL THREAD"
              title={`Inspection Package: ${data.inspection_requirement_id}`}
              subtitle={
                <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginTop: 6 }}>
                  <span className={`ac-badge ${data.status === "COMPLETED" ? "ac-badge-success" : "ac-badge-warning"}`}>
                    STATUS: {data.status}
                  </span>
                  {data.required && (
                    <span className="ac-badge ac-badge-primary">REQUIRED INSPECTION ITEM (RII)</span>
                  )}
                  {data.is_readiness_blocker && (
                    <span className="ac-badge ac-badge-danger">FLIGHT BLOCKER</span>
                  )}
                </div>
              }
              actions={
                <button className="ac-btn ac-btn-primary" onClick={handleResolve}>
                  Resolve Compliance Thread
                </button>
              }
            />

            {actionSuccess && (
              <div className="ac-card" style={{ padding: "10px 14px", backgroundColor: "rgba(34, 197, 94, 0.1)", border: "1px solid var(--ac-success)", marginBottom: 16 }}>
                <p className="ac-text-sm ac-text-success" style={{ margin: 0, fontWeight: 600 }}>{actionSuccess}</p>
              </div>
            )}

            {/* Pipeline Stage Visualizer */}
            <section className="ac-section">
              <div className="ac-card">
                <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 12px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Digital Thread Traceability Pipeline
                </p>
                <div style={{ display: "flex", alignItems: "center", gap: 8, overflowX: "auto", paddingBottom: 8 }}>
                  <div style={{ padding: "8px 12px", background: "var(--ac-bg-surface)", border: "1px solid var(--ac-border)", borderRadius: 6, minWidth: 120 }}>
                    <p style={{ margin: 0, fontSize: 10, color: "var(--ac-text-muted)", textTransform: "uppercase" }}>1. Inspection</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, fontWeight: 700 }}>{data.status}</p>
                  </div>
                  <span>→</span>
                  <div style={{ padding: "8px 12px", background: "var(--ac-bg-surface)", border: "1px solid var(--ac-border)", borderRadius: 6, minWidth: 120 }}>
                    <p style={{ margin: 0, fontSize: 10, color: "var(--ac-text-muted)", textTransform: "uppercase" }}>2. Findings</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, fontWeight: 700 }}>{data.associated_findings.length} Found</p>
                  </div>
                  <span>→</span>
                  <div style={{ padding: "8px 12px", background: "var(--ac-bg-surface)", border: "1px solid var(--ac-border)", borderRadius: 6, minWidth: 120 }}>
                    <p style={{ margin: 0, fontSize: 10, color: "var(--ac-text-muted)", textTransform: "uppercase" }}>3. Evidence</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, fontWeight: 700 }}>{data.attached_evidence.length} Records</p>
                  </div>
                  <span>→</span>
                  <div style={{ padding: "8px 12px", background: "var(--ac-bg-surface)", border: "1px solid var(--ac-border)", borderRadius: 6, minWidth: 140 }}>
                    <p style={{ margin: 0, fontSize: 10, color: "var(--ac-text-muted)", textTransform: "uppercase" }}>4. Obligation</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, fontWeight: 700 }}>{data.current_compliance_state || "UNLINKED"}</p>
                  </div>
                  <span>→</span>
                  <div style={{ padding: "8px 12px", background: "var(--ac-bg-surface)", border: "1px solid var(--ac-border)", borderRadius: 6, minWidth: 120 }}>
                    <p style={{ margin: 0, fontSize: 10, color: "var(--ac-text-muted)", textTransform: "uppercase" }}>5. Readiness</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, fontWeight: 700, color: data.is_readiness_blocker ? "var(--ac-danger)" : "var(--ac-success)" }}>
                      {data.is_readiness_blocker ? "BLOCKED" : "READY"}
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {/* Blocker Alert */}
            {data.is_readiness_blocker && (
              <div style={{ padding: "12px 16px", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--ac-danger)", borderRadius: "var(--ac-radius)", marginBottom: 16 }}>
                <p style={{ margin: "0 0 4px", fontWeight: 700, color: "var(--ac-danger)", fontSize: 14 }}>
                  Readiness Gate Blocker
                </p>
                <p className="ac-text-sm" style={{ margin: 0 }}>
                  {data.blocker_reason}
                </p>
              </div>
            )}

            {/* Operational Context & Linkage */}
            <div className="ac-grid-2" style={{ gap: 16, marginBottom: 24 }}>
              <section className="ac-section">
                <div className="ac-section-header">
                  <h3 className="ac-h3" style={{ margin: 0 }}>Compliance Correlation</h3>
                </div>
                <div className="ac-card">
                  <div className="ac-grid-2" style={{ gap: 10 }}>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Linked Obligation</p>
                    {data.compliance_obligation_id ? (
                      <Link href={`/compliance/obligations/${data.compliance_obligation_id}`} className="ac-btn ac-btn-sm" style={{ justifySelf: "start" }}>
                        View Obligation →
                      </Link>
                    ) : (
                      <p className="ac-text-sm" style={{ margin: 0 }}>No direct obligation link</p>
                    )}

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Requirement</p>
                    <p className="ac-text-sm ac-mono" style={{ margin: 0 }}>
                      {data.regulatory_requirement_number || "None"}
                    </p>

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Compliance State</p>
                    {data.current_compliance_state ? (
                      <StatusBadge {...complianceObligationStatusBadge(data.current_compliance_state)} />
                    ) : (
                      <p className="ac-text-sm" style={{ margin: 0 }}>N/A</p>
                    )}
                  </div>
                </div>
              </section>

              <section className="ac-section">
                <div className="ac-section-header">
                  <h3 className="ac-h3" style={{ margin: 0 }}>Operational Scope</h3>
                </div>
                <div className="ac-card">
                  <div className="ac-grid-2" style={{ gap: 10 }}>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Asset</p>
                    {data.asset_id ? (
                      <Link href={`/compliance/assets/${data.asset_id}/impact`} className="ac-btn ac-btn-sm" style={{ justifySelf: "start" }}>
                        View Asset Impact →
                      </Link>
                    ) : (
                      <p className="ac-text-sm" style={{ margin: 0 }}>N/A</p>
                    )}

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Work Order</p>
                    <p className="ac-text-sm ac-mono" style={{ margin: 0 }}>
                      {data.work_order_id || "None"}
                    </p>

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Task</p>
                    <p className="ac-text-sm ac-mono" style={{ margin: 0 }}>
                      {data.task_id || "None"}
                    </p>
                  </div>
                </div>
              </section>
            </div>

            {/* Associated Findings */}
            <section className="ac-section">
              <div className="ac-section-header">
                <h3 className="ac-h3" style={{ margin: 0 }}>Associated Inspection Findings ({data.associated_findings.length})</h3>
              </div>
              <div className="ac-card">
                {data.associated_findings.length === 0 ? (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No findings raised during this inspection.</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {data.associated_findings.map((f) => (
                      <div key={f.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                        <Link href={`/findings/${f.id}`} style={{ fontWeight: 600, fontSize: 14 }}>
                          {f.title} →
                        </Link>
                        <div className="ac-flex ac-gap-2">
                          <StatusBadge {...findingSeverityBadge(f.severity)} />
                          <StatusBadge {...findingStatusBadge(f.status)} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>

            {/* Attached Evidence */}
            <section className="ac-section">
              <div className="ac-section-header">
                <h3 className="ac-h3" style={{ margin: 0 }}>Attached Verification Evidence ({data.attached_evidence.length})</h3>
              </div>
              <div className="ac-card">
                {data.attached_evidence.length === 0 ? (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No evidence records attached to this inspection.</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {data.attached_evidence.map((e) => (
                      <div key={e.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                        <div>
                          <Link href={`/compliance/evidence/${e.id}`} style={{ fontWeight: 600, fontSize: 14 }}>
                            {e.title} →
                          </Link>
                          <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>ID: {e.id}</p>
                        </div>
                        <div className="ac-flex ac-gap-2">
                          <StatusBadge {...evidenceVerificationBadge(e.verification_status)} />
                          <span className="ac-badge">{e.status}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </RealDataPanel>
    </div>
  );
}
