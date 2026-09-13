"use client";

// Platform Admin — Monitoring & Health (M13).
// REAL-mode only. Consumes:
//   - GET /api/v1/platform/health (backend/app/api/v1/platform.py, M13) for
//     the on-demand platform/component health snapshot.
//   - GET /api/v1/platform/audit (M12.0, via lib/api/audit.ts) for a concise
//     "recent operational activity" slice — this page never re-implements
//     audit querying, it just calls the existing client with a small limit.
//
// This is deliberately NOT a metrics/telemetry dashboard: there is no
// charting, no historical time series, and no fabricated data. Every value
// shown is either the live response of GET /platform/health or a handful of
// the most recent real audit_events rows. The health check is on-demand —
// triggered on page load and by the Refresh button — never continuous, and
// the "Last checked" timestamp makes that explicit.
//
// Backend enforces PLATFORM_MANAGE on both endpoints — this page hiding
// itself from non-platform-admin users (see Sidebar.tsx) is a UX
// convenience only, never the security boundary.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { healthApi, type PlatformHealthResponse, type ComponentHealthResponse } from "@/lib/api/health";
import { auditApi, type AuditEventResponse } from "@/lib/api/audit";

const RECENT_ACTIVITY_LIMIT = 10;

// Maps the backend's health status strings onto the existing StatusBadge
// vocabulary (see components/status/StatusBadge.tsx) rather than inventing
// a parallel badge system — COMPLIANT/NON_COMPLIANT already carry the
// green/red semantics this page needs, with an explicit label override so
// the text still reads "Healthy" / "Unavailable", not "Compliant".
function statusBadge(status: string) {
  switch (status) {
    case "HEALTHY":
      return <StatusBadge status="COMPLIANT" label="Healthy" />;
    case "UNAVAILABLE":
      return <StatusBadge status="NON_COMPLIANT" label="Unavailable" />;
    case "NOT_APPLICABLE":
      return <StatusBadge status="NOT_APPLICABLE" label="Not Applicable" />;
    default:
      return <StatusBadge status="UNKNOWN" label={status || "Unknown"} />;
  }
}

const COMPONENT_LABELS: Record<string, string> = {
  api: "API / Application",
  database: "Database",
  entitlement_service: "Entitlement Service",
  audit_service: "Audit Service",
  background_workers: "Background Workers",
};

function componentLabel(c: ComponentHealthResponse): string {
  return COMPONENT_LABELS[c.name] ?? c.name;
}

function RealMonitoringPage() {
  const { accessToken, isAuthenticated } = useSession();

  const [health, setHealth] = useState<PlatformHealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<NormalizedApiError | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);

  const [events, setEvents] = useState<AuditEventResponse[]>([]);
  const [activityLoading, setActivityLoading] = useState(true);
  const [activityError, setActivityError] = useState<NormalizedApiError | null>(null);

  const loadHealth = useCallback(() => {
    if (!accessToken) {
      setHealthLoading(false);
      return;
    }
    setHealthLoading(true);
    setHealthError(null);
    healthApi
      .getPlatformHealth(accessToken)
      .then((res) => {
        setHealth(res);
        setLastFetchedAt(new Date());
      })
      .catch((err) => {
        setHealthError(normalizeApiError(err));
        setHealth(null);
      })
      .finally(() => setHealthLoading(false));
  }, [accessToken]);

  const loadActivity = useCallback(() => {
    if (!accessToken) {
      setActivityLoading(false);
      return;
    }
    setActivityLoading(true);
    setActivityError(null);
    auditApi
      .listAuditEvents(accessToken, { limit: RECENT_ACTIVITY_LIMIT, offset: 0 })
      .then((res) => setEvents(res.items))
      .catch((err) => {
        setActivityError(normalizeApiError(err));
        setEvents([]);
      })
      .finally(() => setActivityLoading(false));
  }, [accessToken]);

  useEffect(() => {
    if (!isAuthenticated) {
      setHealthLoading(false);
      setActivityLoading(false);
      return;
    }
    loadHealth();
    loadActivity();
  }, [isAuthenticated, loadHealth, loadActivity]);

  const refresh = () => {
    loadHealth();
    loadActivity();
  };

  if (!isAuthenticated) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
        </p>
      </div>
    );
  }

  const forbidden = healthError?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Monitoring & Health" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Platform — Monitoring &amp; Health</h1>
          <p className="ac-subtitle">
            On-demand snapshot of platform availability, database readiness, and recent administrative activity.
            This page performs a live check when opened and when you click Refresh — it does not continuously
            monitor the platform in the background.
          </p>
        </div>
        <button className="ac-btn ac-btn-primary" onClick={refresh} disabled={healthLoading}>
          {healthLoading ? "Checking…" : "Refresh"}
        </button>
      </div>

      {forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view platform health.
          </p>
        </div>
      ) : (
        <>
          <RealDataPanel
            loading={healthLoading && !health}
            error={healthError}
            isEmpty={false}
            emptyMessage="No health data available."
          >
            {health && (
              <>
                <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
                  <div className="ac-flex ac-gap-3" style={{ alignItems: "center", flexWrap: "wrap", justifyContent: "space-between" }}>
                    <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                      <span className="ac-text-sm ac-text-muted">Overall Status</span>
                      {statusBadge(health.overall_status)}
                    </div>
                    <span className="ac-text-sm ac-text-muted">
                      Last checked: {lastFetchedAt ? lastFetchedAt.toLocaleString() : new Date(health.checked_at).toLocaleString()}
                    </span>
                  </div>
                </div>

                <div className="ac-card ac-section" style={{ padding: 0 }}>
                  <div className="ac-table-desktop">
                    <table className="ac-table" style={{ width: "100%" }}>
                      <caption className="ac-sr-only">Platform component health</caption>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "var(--ac-space-2)" }}>Component</th>
                          <th style={{ textAlign: "left", padding: "var(--ac-space-2)" }}>Status</th>
                          <th style={{ textAlign: "left", padding: "var(--ac-space-2)" }}>Detail</th>
                          <th style={{ textAlign: "left", padding: "var(--ac-space-2)" }}>Latency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {health.components.map((c) => (
                          <tr key={c.name}>
                            <td style={{ padding: "var(--ac-space-2)" }}>{componentLabel(c)}</td>
                            <td style={{ padding: "var(--ac-space-2)" }}>{statusBadge(c.status)}</td>
                            <td className="ac-text-sm ac-text-muted" style={{ padding: "var(--ac-space-2)" }}>{c.detail}</td>
                            <td className="ac-text-sm ac-text-muted" style={{ padding: "var(--ac-space-2)" }}>
                              {c.latency_ms !== null ? `${c.latency_ms} ms` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="ac-row-cards">
                    {health.components.map((c) => (
                      <div className="ac-row-card" key={c.name}>
                        <div className="ac-row-card-field">
                          <span className="ac-row-card-field-label">Component</span>
                          <span>{componentLabel(c)}</span>
                        </div>
                        <div className="ac-row-card-field">
                          <span className="ac-row-card-field-label">Status</span>
                          {statusBadge(c.status)}
                        </div>
                        <div className="ac-row-card-field">
                          <span className="ac-row-card-field-label">Detail</span>
                          <span style={{ wordBreak: "break-word" }}>{c.detail}</span>
                        </div>
                        {c.latency_ms !== null && (
                          <div className="ac-row-card-field">
                            <span className="ac-row-card-field-label">Latency</span>
                            <span>{c.latency_ms} ms</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </RealDataPanel>

          <div className="ac-section-header" style={{ marginTop: "var(--ac-space-4)" }}>
            <div>
              <h2 className="ac-h2">Recent Operational Activity</h2>
              <p className="ac-subtitle">
                The {RECENT_ACTIVITY_LIMIT} most recent platform audit events. For full filtering and history, see{" "}
                <Link href="/platform/audit">Audit / Activity</Link>.
              </p>
            </div>
          </div>
          <RealDataPanel
            loading={activityLoading}
            error={activityError}
            isEmpty={!activityError && events.length === 0}
            emptyMessage="No recent activity."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <div className="ac-table-desktop">
                <table className="ac-table" style={{ width: "100%" }}>
                  <caption className="ac-sr-only">Recent audit events</caption>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", padding: "var(--ac-space-2)" }}>Timestamp</th>
                      <th style={{ textAlign: "left", padding: "var(--ac-space-2)" }}>Action</th>
                      <th style={{ textAlign: "left", padding: "var(--ac-space-2)" }}>Entity Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((e) => (
                      <tr key={e.id}>
                        <td className="ac-text-sm" style={{ padding: "var(--ac-space-2)" }}>{new Date(e.created_at).toLocaleString()}</td>
                        <td className="ac-text-sm" style={{ padding: "var(--ac-space-2)", wordBreak: "break-word" }}>{e.action}</td>
                        <td className="ac-text-sm" style={{ padding: "var(--ac-space-2)" }}>{e.entity_type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="ac-row-cards">
                {events.map((e) => (
                  <div className="ac-row-card" key={e.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Timestamp</span>
                      <span>{new Date(e.created_at).toLocaleString()}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Action</span>
                      <span style={{ wordBreak: "break-word" }}>{e.action}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Entity Type</span>
                      <span>{e.entity_type}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}

export default function PlatformMonitoringPage() {
  return <RealMonitoringPage />;
}
