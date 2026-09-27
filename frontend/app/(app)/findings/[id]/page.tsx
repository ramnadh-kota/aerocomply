"use client";

// Canonical Finding detail route (M20.4 / D2-3).
// Findings are a real, backend-persisted domain record correlated with the
// compliance digital thread and flight readiness gates.

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, findingSeverityBadge, findingStatusBadge, complianceObligationStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { findingsApi, type BackendFinding } from "@/lib/api/findings";
import { complianceIntelligenceApi, type FindingComplianceImpact, complianceObligationsApi, type BackendComplianceObligation } from "@/lib/api/compliance";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

function severityBadge(severity: string) {
  return <StatusBadge {...findingSeverityBadge(severity)} />;
}

function statusBadge(status: string) {
  return <StatusBadge {...findingStatusBadge(status)} />;
}

export default function FindingDetailPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const { accessToken, isAuthenticated } = useSession();
  const [finding, setFinding] = useState<BackendFinding | null>(null);
  const [impact, setImpact] = useState<FindingComplianceImpact | null>(null);
  const [obligations, setObligations] = useState<BackendComplianceObligation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [selectedObligationId, setSelectedObligationId] = useState("");
  const [safetySignificance, setSafetySignificance] = useState("AIRWORTHINESS");
  const [complianceRelevance, setComplianceRelevance] = useState("MANDATORY_AD");

  const refresh = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      findingsApi.get(accessToken, params.id),
      complianceIntelligenceApi.getFindingImpact(accessToken, params.id).catch(() => null),
      complianceObligationsApi.list(accessToken).catch(() => []),
    ])
      .then(([findingData, impactData, obList]) => {
        setFinding(findingData);
        setImpact(impactData);
        setObligations(obList);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [accessToken, isAuthenticated, params.id]);

  const dispose = async () => {
    if (!accessToken || !finding) return;
    setActionError(null);
    try {
      await findingsApi.addDisposition(accessToken, finding.id, { disposition_type: "NO_ACTION_REQUIRED" });
      refresh();
    } catch (err) {
      setActionError(normalizeApiError(err));
    }
  };

  const close = async () => {
    if (!accessToken || !finding) return;
    setActionError(null);
    try {
      await findingsApi.close(accessToken, finding.id);
      refresh();
    } catch (err) {
      setActionError(normalizeApiError(err));
    }
  };

  const handleCorrelateCompliance = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !finding) return;
    setActionError(null);
    try {
      await findingsApi.correlateCompliance(accessToken, finding.id, {
        compliance_obligation_id: selectedObligationId || undefined,
        safety_significance: safetySignificance,
        compliance_relevance: complianceRelevance,
      });
      setShowLinkModal(false);
      refresh();
    } catch (err) {
      setActionError(normalizeApiError(err));
    }
  };

  return (
    <div>
      {(!finding || loading || error) && (
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Finding" }]} />
      )}

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Sign in to view this finding. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel
          loading={loading}
          error={error}
          isEmpty={!loading && !error && !finding}
          emptyMessage="This finding could not be located."
        >
          {finding && (
            <>
              <PageHeader
                breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Finding" }]}
                eyebrow="FINDING"
                title={finding.title}
                subtitle={
                  <span className="ac-flex ac-gap-2" style={{ marginTop: 6 }}>
                    {statusBadge(finding.status)}
                    {severityBadge(finding.severity)}
                    {impact?.is_readiness_blocker && (
                      <span className="ac-badge ac-badge-danger" style={{ fontWeight: 700 }}>
                        READINESS BLOCKER
                      </span>
                    )}
                  </span>
                }
                actions={
                  <div className="ac-flex ac-gap-2">
                    {finding.status !== "CLOSED" && (
                      <button className="ac-btn" onClick={() => setShowLinkModal(true)}>
                        Correlate Compliance
                      </button>
                    )}
                    {finding.status !== "CLOSED" && finding.dispositions.length === 0 && (
                      <button className="ac-btn" onClick={dispose}>No Action Required</button>
                    )}
                    {finding.status !== "CLOSED" && finding.dispositions.length > 0 && (
                      <button className="ac-btn ac-btn-primary" onClick={close}>Close Finding</button>
                    )}
                  </div>
                }
              />

              {actionError && (
                <div className="ac-card" style={{ padding: "var(--ac-space-3)", marginBottom: "var(--ac-space-4)", borderColor: "var(--ac-danger)" }}>
                  <p className="ac-text-sm ac-text-danger" style={{ margin: 0 }}>{actionError.message}</p>
                </div>
              )}

              {/* Compliance & Operational Readiness Impact Section */}
              <section className="ac-section">
                <div className="ac-section-header">
                  <h2 className="ac-h2" style={{ margin: 0 }}>Compliance & Readiness Impact</h2>
                </div>
                <div className="ac-card">
                  {impact?.is_readiness_blocker ? (
                    <div style={{ padding: "12px 16px", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--ac-danger)", borderRadius: "var(--ac-radius)", marginBottom: 16 }}>
                      <p style={{ margin: "0 0 4px", fontWeight: 700, color: "var(--ac-danger)", fontSize: 14 }}>
                        Active Operational Flight Blocker
                      </p>
                      <p className="ac-text-sm" style={{ margin: 0 }}>
                        {impact.blocker_reason}
                      </p>
                    </div>
                  ) : (
                    <div style={{ padding: "10px 14px", backgroundColor: "rgba(34, 197, 94, 0.1)", border: "1px solid var(--ac-success)", borderRadius: "var(--ac-radius)", marginBottom: 16 }}>
                      <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-success)", fontWeight: 600 }}>
                        No flight readiness blockage from this finding.
                      </p>
                    </div>
                  )}

                  <div className="ac-grid-2" style={{ gap: 12 }}>
                    <div>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>Linked Compliance Obligation</p>
                      {finding.compliance_obligation_id ? (
                        <div className="ac-flex ac-gap-2 ac-items-center">
                          <Link href={`/compliance/obligations/${finding.compliance_obligation_id}`} className="ac-btn ac-btn-sm">
                            View Obligation →
                          </Link>
                          {impact?.current_compliance_state && (
                            <StatusBadge {...complianceObligationStatusBadge(impact.current_compliance_state)} />
                          )}
                        </div>
                      ) : (
                        <p className="ac-text-sm" style={{ margin: 0 }}>
                          Not directly linked. <button className="ac-btn-link" onClick={() => setShowLinkModal(true)}>Link now</button>
                        </p>
                      )}
                    </div>

                    <div>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>Regulatory Requirement</p>
                      <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>
                        {impact?.regulatory_requirement_number || "None directly cited"}
                        {impact?.regulatory_requirement_title && ` — ${impact.regulatory_requirement_title}`}
                      </p>
                    </div>

                    <div>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>Safety Significance</p>
                      <p className="ac-text-sm ac-mono" style={{ margin: 0 }}>
                        {finding.safety_significance || impact?.safety_significance || "STANDARD"}
                      </p>
                    </div>

                    <div>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>Compliance Relevance</p>
                      <p className="ac-text-sm ac-mono" style={{ margin: 0 }}>
                        {finding.compliance_relevance || impact?.compliance_relevance || "OPERATIONAL"}
                      </p>
                    </div>

                    <div>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>Required Action to Clear</p>
                      <p className="ac-text-sm" style={{ margin: 0 }}>
                        {impact?.corrective_action_required || "Resolve finding through disposition and attach closure evidence."}
                      </p>
                    </div>

                    <div>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>Evidence & Verification Gate</p>
                      <p className="ac-text-sm" style={{ margin: 0 }}>
                        Status: <strong className="ac-mono">{impact?.evidence_status || "NO_EVIDENCE"}</strong>
                        {impact?.evidence_verification_status && (
                          <span> (Verification: <strong className="ac-mono">{impact.evidence_verification_status}</strong>)</span>
                        )}
                      </p>
                    </div>
                  </div>
                </div>
              </section>

              {/* Summary Section */}
              <section className="ac-section">
                <div className="ac-section-header">
                  <h2 className="ac-h2" style={{ margin: 0 }}>Summary</h2>
                </div>
                <div className="ac-card">
                  <p className="ac-text-sm" style={{ margin: "0 0 12px" }}>{finding.description}</p>
                  <div className="ac-grid-2" style={{ gap: 8 }}>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Finding ID</p>
                    <p className="ac-text-sm ac-mono" style={{ margin: 0 }}>{finding.id}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Discovered</p>
                    <p className="ac-text-sm" style={{ margin: 0 }}>{new Date(finding.discovered_at).toLocaleString()}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Created</p>
                    <p className="ac-text-sm" style={{ margin: 0 }}>{new Date(finding.created_at).toLocaleString()}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Last Updated</p>
                    <p className="ac-text-sm" style={{ margin: 0 }}>{new Date(finding.updated_at).toLocaleString()}</p>
                  </div>
                </div>
              </section>

              {/* Operational Context Section */}
              <section className="ac-section">
                <div className="ac-section-header">
                  <h2 className="ac-h2" style={{ margin: 0 }}>Operational Context</h2>
                </div>
                <div className="ac-card">
                  <div className="ac-grid-2" style={{ gap: 8 }}>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Aircraft</p>
                    {finding.aircraft_id ? (
                      <Link href={`/aircraft/${finding.aircraft_id}`} className="ac-btn" style={{ justifySelf: "start", fontSize: 12, padding: "2px 10px" }}>
                        View Aircraft →
                      </Link>
                    ) : (
                      <p className="ac-text-sm" style={{ margin: 0 }}>Not linked</p>
                    )}

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Drone Asset</p>
                    {finding.asset_id ? (
                      <div className="ac-flex ac-gap-2">
                        <Link href={`/drones/${finding.asset_id}`} className="ac-btn" style={{ justifySelf: "start", fontSize: 12, padding: "2px 10px" }}>
                          View Drone →
                        </Link>
                        <Link href={`/compliance/assets/${finding.asset_id}/impact`} className="ac-btn ac-btn-primary" style={{ justifySelf: "start", fontSize: 12, padding: "2px 10px" }}>
                          View Compliance Impact →
                        </Link>
                      </div>
                    ) : (
                      <p className="ac-text-sm" style={{ margin: 0 }}>Not linked</p>
                    )}

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Component</p>
                    <p className="ac-text-sm" style={{ margin: 0 }}>
                      {finding.component_id ? (
                        <span className="ac-mono">{finding.component_id}</span>
                      ) : (
                        "Not linked"
                      )}
                    </p>

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Work Order</p>
                    <p className="ac-text-sm" style={{ margin: 0 }}>
                      {finding.work_order_id ? (
                        <span className="ac-mono">{finding.work_order_id}</span>
                      ) : (
                        "Not linked"
                      )}
                    </p>

                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Inspection Requirement</p>
                    <p className="ac-text-sm" style={{ margin: 0 }}>
                      {finding.inspection_requirement_id ? (
                        <Link href={`/compliance/inspections/${finding.inspection_requirement_id}/impact`} className="ac-btn" style={{ justifySelf: "start", fontSize: 12, padding: "2px 10px" }}>
                          View Inspection Impact →
                        </Link>
                      ) : (
                        "Not linked"
                      )}
                    </p>
                  </div>
                </div>
              </section>

              {/* Disposition Section */}
              <section className="ac-section">
                <div className="ac-section-header">
                  <h2 className="ac-h2" style={{ margin: 0 }}>Disposition</h2>
                </div>
                <div className="ac-card">
                  {finding.dispositions.length === 0 ? (
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No disposition recorded yet.</p>
                  ) : (
                    <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                      {finding.dispositions.map((d) => (
                        <li key={d.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                          <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{d.disposition_type.replace(/_/g, " ")}</p>
                          {d.corrective_action && (
                            <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>{d.corrective_action}</p>
                          )}
                          <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                            Recorded {new Date(d.created_at).toLocaleString()}
                            {d.closed_at && ` · Closed ${new Date(d.closed_at).toLocaleString()}`}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>

              {/* Activity Section */}
              <section className="ac-section">
                <div className="ac-section-header">
                  <h2 className="ac-h2" style={{ margin: 0 }}>Activity</h2>
                </div>
                <div className="ac-card">
                  <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                    <li style={{ padding: "6px 0" }}>
                      <span className="ac-text-sm">Finding created</span>
                      <span className="ac-text-sm ac-text-muted" style={{ marginLeft: 8 }}>
                        {new Date(finding.created_at).toLocaleString()}
                      </span>
                    </li>
                    {finding.dispositions.map((d) => (
                      <li key={d.id} style={{ padding: "6px 0" }}>
                        <span className="ac-text-sm">Disposition added: {d.disposition_type.replace(/_/g, " ")}</span>
                        <span className="ac-text-sm ac-text-muted" style={{ marginLeft: 8 }}>
                          {new Date(d.created_at).toLocaleString()}
                        </span>
                      </li>
                    ))}
                    {finding.status === "CLOSED" && (
                      <li style={{ padding: "6px 0" }}>
                        <span className="ac-text-sm">Finding closed</span>
                        <span className="ac-text-sm ac-text-muted" style={{ marginLeft: 8 }}>
                          {new Date(finding.updated_at).toLocaleString()}
                        </span>
                      </li>
                    )}
                  </ul>
                </div>
              </section>

              {/* Correlate Modal */}
              {showLinkModal && (
                <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
                  <div className="ac-card" style={{ width: "100%", maxWidth: 500, padding: "var(--ac-space-4)" }}>
                    <h3 className="ac-h3" style={{ margin: "0 0 12px" }}>Correlate Finding to Compliance</h3>
                    <form onSubmit={handleCorrelateCompliance}>
                      <div style={{ marginBottom: 12 }}>
                        <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Compliance Obligation</label>
                        <select
                          className="ac-input"
                          value={selectedObligationId}
                          onChange={(e) => setSelectedObligationId(e.target.value)}
                        >
                          <option value="">-- Select Compliance Obligation --</option>
                          {obligations.map((o) => (
                            <option key={o.id} value={o.id}>
                              Obligation {o.id.slice(0, 8)}... ({o.status} - Req: {o.requirement_id.slice(0, 8)}...)
                            </option>
                          ))}
                        </select>
                      </div>

                      <div style={{ marginBottom: 12 }}>
                        <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Safety Significance</label>
                        <select
                          className="ac-input"
                          value={safetySignificance}
                          onChange={(e) => setSafetySignificance(e.target.value)}
                        >
                          <option value="AIRWORTHINESS">AIRWORTHINESS (Airworthiness Directive / Mandatory)</option>
                          <option value="FLIGHT_SAFETY">FLIGHT_SAFETY (Direct Flight Hazard)</option>
                          <option value="NON_SAFETY">NON_SAFETY (Cosmetic / Operational Comfort)</option>
                        </select>
                      </div>

                      <div style={{ marginBottom: 16 }}>
                        <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Compliance Relevance</label>
                        <select
                          className="ac-input"
                          value={complianceRelevance}
                          onChange={(e) => setComplianceRelevance(e.target.value)}
                        >
                          <option value="MANDATORY_AD">MANDATORY_AD (Airworthiness Directive Compliance)</option>
                          <option value="CERTIFICATION_BASIS">CERTIFICATION_BASIS (Type Certification Compliance)</option>
                          <option value="OPERATIONAL_RULE">OPERATIONAL_RULE (Flight Operations Requirement)</option>
                          <option value="INTERNAL_AUDIT">INTERNAL_AUDIT (Company Quality Assurance)</option>
                        </select>
                      </div>

                      <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end" }}>
                        <button type="button" className="ac-btn" onClick={() => setShowLinkModal(false)}>Cancel</button>
                        <button type="submit" className="ac-btn ac-btn-primary">Save Correlation</button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}
