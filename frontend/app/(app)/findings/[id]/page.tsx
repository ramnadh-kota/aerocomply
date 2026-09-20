"use client";

// Canonical Finding detail route (M20.4). Findings are a real,
// backend-persisted domain record (M20.2) -- there is no mock/demo
// equivalent addressable by a real Finding UUID, so this page is always
// REAL-mode, unlike /aircraft/[id] and /drones/[id] which branch on
// DataModeContext. Reuses findingsApi (M20.2/M20.3) and the same
// RealDataPanel/StatusBadge conventions already used by
// AircraftFindingsPanel -- no new Finding model, API, or badge system.

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, findingSeverityBadge, findingStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { findingsApi, type BackendFinding } from "@/lib/api/findings";
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);

  const refresh = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    findingsApi
      .get(accessToken, params.id)
      .then((data) => setFinding(data))
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
                  </span>
                }
                actions={
                  <>
                    {finding.status !== "CLOSED" && finding.dispositions.length === 0 && (
                      <button className="ac-btn" onClick={dispose}>No Action Required</button>
                    )}
                    {finding.status !== "CLOSED" && finding.dispositions.length > 0 && (
                      <button className="ac-btn ac-btn-primary" onClick={close}>Close Finding</button>
                    )}
                  </>
                }
              />

              {actionError && (
                <div className="ac-card" style={{ padding: "var(--ac-space-3)", marginBottom: "var(--ac-space-4)" }}>
                  <p className="ac-text-sm" style={{ margin: 0 }}>{actionError.message}</p>
                </div>
              )}

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
                      <Link href={`/drones/${finding.asset_id}`} className="ac-btn" style={{ justifySelf: "start", fontSize: 12, padding: "2px 10px" }}>
                        View Drone →
                      </Link>
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
                        <span className="ac-mono">{finding.inspection_requirement_id}</span>
                      ) : (
                        "Not linked"
                      )}
                    </p>
                  </div>
                </div>
              </section>

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
            </>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}
