"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { StatusBadge, findingSeverityBadge, findingStatusBadge, complianceObligationStatusBadge, evidenceVerificationBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { complianceIntelligenceApi, type AssetComplianceImpact } from "@/lib/api/compliance";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function AssetComplianceImpactPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const { accessToken, isAuthenticated } = useSession();
  const [data, setData] = useState<AssetComplianceImpact | null>(null);
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
      .getAssetImpact(accessToken, params.id)
      .then((res) => setData(res))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [accessToken, isAuthenticated, params.id]);

  const handleResolveInspection = async (inspId: string) => {
    if (!accessToken) return;
    try {
      const res = await complianceIntelligenceApi.resolveInspection(accessToken, inspId);
      if (res.resolved) {
        setActionSuccess(`Inspection resolved successfully. Obligation status: ${res.obligation_status}`);
      } else {
        setActionSuccess(`Inspection evaluated: ${res.reason || "Not resolved"}`);
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
          { label: "Asset Impact" },
        ]}
      />

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={!loading && !error && !data}
        emptyMessage="Compliance impact data could not be loaded for this asset."
      >
        {data && (
          <>
            <PageHeader
              breadcrumbs={[
                { label: "Dashboard", href: "/dashboard" },
                { label: "Compliance", href: "/compliance" },
                { label: "Asset Impact" },
              ]}
              eyebrow="AEROSPACE COMPLIANCE INTELLIGENCE"
              title={`Asset Compliance & Flight Readiness: ${data.asset_id}`}
              subtitle={
                <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginTop: 6 }}>
                  <span
                    className={`ac-badge ${
                      data.overall_status === "READY"
                        ? "ac-badge-success"
                        : data.overall_status === "BLOCKED"
                        ? "ac-badge-danger"
                        : "ac-badge-warning"
                    }`}
                    style={{ fontSize: 13, fontWeight: 700, padding: "4px 10px" }}
                  >
                    READINESS: {data.overall_status}
                  </span>
                  <span className="ac-text-sm ac-text-muted">
                    Evaluated: {new Date(data.readiness_contribution.evaluated_at).toLocaleString()}
                  </span>
                </div>
              }
              actions={
                <button className="ac-btn" onClick={refresh}>
                  Re-evaluate Readiness
                </button>
              }
            />

            {actionSuccess && (
              <div className="ac-card" style={{ padding: "10px 14px", backgroundColor: "rgba(34, 197, 94, 0.1)", border: "1px solid var(--ac-success)", marginBottom: 16 }}>
                <p className="ac-text-sm ac-text-success" style={{ margin: 0, fontWeight: 600 }}>{actionSuccess}</p>
              </div>
            )}

            {/* Metric KPI Overview */}
            <div className="ac-grid-4" style={{ gap: 12, marginBottom: 24 }}>
              <div className="ac-card" style={{ padding: "14px 16px" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Active Flight Blockers</p>
                <p style={{ margin: "4px 0 0", fontSize: 24, fontWeight: 700, color: data.active_blockers.length ? "var(--ac-danger)" : "var(--ac-success)" }}>
                  {data.active_blockers.length}
                </p>
              </div>
              <div className="ac-card" style={{ padding: "14px 16px" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Critical Unresolved Findings</p>
                <p style={{ margin: "4px 0 0", fontSize: 24, fontWeight: 700, color: data.critical_findings.length ? "var(--ac-danger)" : "var(--ac-text)" }}>
                  {data.critical_findings.length}
                </p>
              </div>
              <div className="ac-card" style={{ padding: "14px 16px" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Overdue Obligations</p>
                <p style={{ margin: "4px 0 0", fontSize: 24, fontWeight: 700, color: data.overdue_obligations.length ? "var(--ac-danger)" : "var(--ac-text)" }}>
                  {data.overdue_obligations.length}
                </p>
              </div>
              <div className="ac-card" style={{ padding: "14px 16px" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Compliant Obligations</p>
                <p style={{ margin: "4px 0 0", fontSize: 24, fontWeight: 700, color: "var(--ac-success)" }}>
                  {data.readiness_contribution.compliant_obligations_count} / {data.readiness_contribution.compliance_obligations_count}
                </p>
              </div>
            </div>

            {/* Answer the core question: Why is this aircraft blocked? */}
            <section className="ac-section">
              <div className="ac-section-header">
                <h2 className="ac-h2" style={{ margin: 0 }}>
                  Active Flight Readiness Blockers ({data.active_blockers.length})
                </h2>
              </div>
              <div className="ac-card">
                {data.active_blockers.length === 0 ? (
                  <p className="ac-text-sm ac-text-success" style={{ margin: 0, fontWeight: 600 }}>
                    No active compliance blockers. This asset meets all airworthiness and compliance digital thread criteria.
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {data.active_blockers.map((b) => (
                      <div
                        key={b.blocker_id}
                        style={{
                          padding: "14px 16px",
                          border: "1px solid var(--ac-danger)",
                          borderRadius: "var(--ac-radius)",
                          backgroundColor: "rgba(239, 68, 68, 0.04)",
                        }}
                      >
                        <div className="ac-flex ac-justify-between ac-items-start" style={{ marginBottom: 6 }}>
                          <span className="ac-badge ac-badge-danger" style={{ fontWeight: 700 }}>
                            {b.category.replace(/_/g, " ")}
                          </span>
                          <span className="ac-text-sm ac-mono ac-text-muted">
                            Source: {b.source_record_type} ({b.source_record_id})
                          </span>
                        </div>
                        <h4 style={{ margin: "4px 0 6px", fontSize: 15, fontWeight: 700 }}>
                          {b.what_blocking}
                        </h4>
                        <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>
                          <strong>Why blocking:</strong> {b.why_blocking}
                        </p>
                        {b.regulatory_requirement_number && (
                          <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
                            <strong>Requirement:</strong> {b.regulatory_requirement_number} - {b.regulatory_requirement_title}
                          </p>
                        )}
                        <p className="ac-text-sm" style={{ margin: "0 0 6px", color: "var(--ac-primary)", fontWeight: 600 }}>
                          <strong>Resolution Action:</strong> {b.resolution_action}
                        </p>
                        {b.missing_evidence && (
                          <p className="ac-text-sm ac-text-danger" style={{ margin: 0 }}>
                            <strong>Missing Evidence:</strong> {b.missing_evidence}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>

            {/* Critical Findings Section */}
            <section className="ac-section">
              <div className="ac-section-header">
                <h2 className="ac-h2" style={{ margin: 0 }}>
                  Critical Inspection Findings ({data.critical_findings.length})
                </h2>
              </div>
              <div className="ac-card">
                {data.critical_findings.length === 0 ? (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    No open critical or major inspection findings recorded on this asset.
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {data.critical_findings.map((f) => (
                      <div key={f.finding_id} style={{ padding: "10px 12px", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                        <div className="ac-flex ac-justify-between ac-items-center">
                          <Link href={`/findings/${f.finding_id}`} style={{ fontWeight: 600, fontSize: 14 }}>
                            {f.title} →
                          </Link>
                          <div className="ac-flex ac-gap-2">
                            <StatusBadge {...findingSeverityBadge(f.severity)} />
                            <StatusBadge {...findingStatusBadge(f.status)} />
                          </div>
                        </div>
                        {f.blocker_reason && (
                          <p className="ac-text-sm ac-text-danger" style={{ margin: "4px 0 2px" }}>
                            {f.blocker_reason}
                          </p>
                        )}
                        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                          Required Action: {f.corrective_action_required || "Closure disposition"}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>

            {/* Inspections Requiring Action */}
            <section className="ac-section">
              <div className="ac-section-header">
                <h2 className="ac-h2" style={{ margin: 0 }}>
                  Inspections Requiring Action ({data.inspections_requiring_action.length})
                </h2>
              </div>
              <div className="ac-card">
                {data.inspections_requiring_action.length === 0 ? (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    All maintenance and airworthiness inspections are up to date.
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {data.inspections_requiring_action.map((insp) => (
                      <div key={insp.inspection_requirement_id} style={{ padding: "12px", border: "1px solid var(--ac-border)", borderRadius: "var(--ac-radius)" }}>
                        <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                          <span style={{ fontWeight: 700, fontSize: 14 }}>
                            Inspection Requirement: {insp.inspection_requirement_id.slice(0, 8)}...
                          </span>
                          <span className={`ac-badge ${insp.status === "COMPLETED" ? "ac-badge-success" : "ac-badge-warning"}`}>
                            {insp.status}
                          </span>
                        </div>
                        {insp.blocker_reason && (
                          <p className="ac-text-sm ac-text-danger" style={{ margin: "0 0 6px" }}>
                            {insp.blocker_reason}
                          </p>
                        )}
                        <div className="ac-flex ac-gap-2" style={{ marginTop: 8 }}>
                          <button
                            className="ac-btn ac-btn-primary ac-btn-sm"
                            onClick={() => handleResolveInspection(insp.inspection_requirement_id)}
                          >
                            Evaluate & Resolve Compliance
                          </button>
                          <Link href={`/compliance/inspections/${insp.inspection_requirement_id}/impact`} className="ac-btn ac-btn-sm">
                            View Inspection Detail →
                          </Link>
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
