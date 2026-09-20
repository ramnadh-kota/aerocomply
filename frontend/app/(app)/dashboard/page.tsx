"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CoreLoopDiagram } from "@/components/core-loop/CoreLoopDiagram";
import { assessments } from "@/lib/mock/assessments";
import { getAircraftById, currentRegistration, getAircraftVariant } from "@/lib/mock/aircraft";
import { getRequirementById } from "@/lib/mock/regulations";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { overdueMaintenanceEvents, upcomingMaintenanceEvents } from "@/lib/mock/maintenance";
import { activeProjects } from "@/lib/mock/maintenanceProjects";
import { openWorkOrders, overdueWorkOrders, awaitingPartsWorkOrders, awaitingReviewWorkOrders } from "@/lib/mock/workOrders";
import { techniciansOnShift } from "@/lib/mock/technicians";
import { StatusBadge, workOrderStatusBadge, priorityBadge, projectStatusBadge } from "@/components/status/StatusBadge";
import { inspectorReviews } from "@/lib/mock/inspectorReviews";
import { findings } from "@/lib/mock/findings";
import { getFleetAnalytics, getMaintenanceAnalytics, getComplianceAnalytics, getInspectionAnalytics } from "@/lib/mock/ai/analytics";
import { DailyBriefCard } from "@/components/dashboard/DailyBriefCard";
import { OperationalPriorityQueue } from "@/components/dashboard/OperationalPriorityQueue";
import { FleetTatSummary } from "@/components/dashboard/FleetTatSummary";
import { ViewingAsBadge } from "@/components/layout/ViewingAsBadge";
import { PLATFORM_AI_NAME } from "@/lib/brand";
import { AircraftContextLayer } from "@/components/aircraft-visual/AircraftContextLayer";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { aircraftApi, type BackendAircraft } from "@/lib/api/aircraft";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import { workOrdersApi, type BackendWorkOrder } from "@/lib/api/workOrders";
import { deferredItemsApi, type BackendDeferredItem } from "@/lib/api/deferred-items";
import { findingsApi, type BackendFinding } from "@/lib/api/findings";

const DISTRIBUTION = [
  { label: "Compliant", pct: 92, color: "var(--ac-status-compliant)" },
  { label: "Review Required", pct: 5, color: "var(--ac-status-review)" },
  { label: "Insufficient Data", pct: 2, color: "var(--ac-status-insufficient)" },
  { label: "Non-Compliant", pct: 1, color: "var(--ac-status-non-compliant)" },
];

const ATTENTION_ITEMS = [
  { text: "3 assessments require engineering review", href: "/assessments" },
  { text: "2 aircraft have incomplete configuration evidence", href: "/aircraft" },
  { text: "1 component installation history has a missing removal date", href: "/components" },
  { text: "1 applicability condition cannot be resolved", href: "/assessments/asmt-1" },
];

const WO_CLOSED_STATUSES = new Set(["COMPLETED", "CANCELLED", "CLOSED"]);

function IllustrativeBadge() {
  return <span className="ac-illustrative-badge">Illustrative Data</span>;
}

/** Real-data KPI + fleet/work-order charts, backed by the live backend
 * (aircraft, drones, work orders, deferred items). Fetched client-side with
 * the signed-in user's access token -- same pattern as /drones, /aircraft
 * REAL-mode panels. No mock data is used inside this component. */
function RealFleetPanel() {
  const { accessToken, isAuthenticated } = useSession();
  const [aircraft, setAircraft] = useState<BackendAircraft[]>([]);
  const [drones, setDrones] = useState<DroneResponse[]>([]);
  const [workOrders, setWorkOrders] = useState<BackendWorkOrder[]>([]);
  const [deferredItems, setDeferredItems] = useState<BackendDeferredItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      aircraftApi.list(accessToken),
      dronesApi.listDrones(accessToken),
      workOrdersApi.list(accessToken),
      deferredItemsApi.listForFleet(accessToken, true),
    ])
      .then(([ac, dr, wo, di]) => {
        setAircraft(ac);
        setDrones(dr);
        setWorkOrders(wo);
        setDeferredItems(di);
        setAsOf(new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }));
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, isAuthenticated]);

  const totalAssets = aircraft.length + drones.length;
  const activeAssets = aircraft.filter((a) => a.status === "ACTIVE").length + drones.filter((d) => d.status === "ACTIVE").length;
  const groundedAssets =
    aircraft.filter((a) => a.status === "GROUNDED").length + drones.filter((d) => d.status === "GROUNDED").length;
  const unknownAssets = totalAssets - activeAssets - groundedAssets;
  const openWorkOrderCount = workOrders.filter((w) => !WO_CLOSED_STATUSES.has(w.status)).length;

  const woByStatus = workOrders.reduce<Record<string, number>>((acc, w) => {
    acc[w.status] = (acc[w.status] ?? 0) + 1;
    return acc;
  }, {});
  const maxWoCount = Math.max(1, ...Object.values(woByStatus));

  const statusColor = { ACTIVE: "var(--ac-status-compliant)", GROUNDED: "var(--ac-status-non-compliant)", UNKNOWN: "var(--ac-status-unknown)" } as const;

  return (
    <>
      <section className="ac-section">
        <PageHeader
          title="Fleet Overview"
          subtitle="Live counts from the connected backend (aircraft + drone assets, work orders, MEL items)"
          actions={<ViewingAsBadge />}
        />

        {!isAuthenticated ? (
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Sign in to view live fleet data. <Link href="/login">Sign in →</Link>
            </p>
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!loading && !error && totalAssets === 0 && workOrders.length === 0}
            emptyMessage="No aircraft, drones, or work orders exist for this organization yet."
          >
            <div className="ac-kpi-grid">
              <div className="ac-kpi-card-real">
                <p className="ac-kpi-label">Total Assets</p>
                <p className="ac-kpi-value">{totalAssets}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{aircraft.length} aircraft · {drones.length} drones</p>
              </div>
              <div className="ac-kpi-card-real">
                <p className="ac-kpi-label">Active Assets</p>
                <p className="ac-kpi-value">{activeAssets}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>status = ACTIVE</p>
              </div>
              <div className="ac-kpi-card-real">
                <p className="ac-kpi-label">Grounded / Attention</p>
                <p className="ac-kpi-value">{groundedAssets}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>status = GROUNDED</p>
              </div>
              <div className="ac-kpi-card-real">
                <p className="ac-kpi-label">Open Work Orders</p>
                <p className="ac-kpi-value">{openWorkOrderCount}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>of {workOrders.length} total</p>
              </div>
              <div className="ac-kpi-card-real">
                <p className="ac-kpi-label">Open MEL / Deferred Items</p>
                <p className="ac-kpi-value">{deferredItems.length}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>fleet-wide, open only</p>
              </div>
            </div>
            {asOf && <p className="ac-kpi-asof">As of {asOf} · live backend query, not a fabricated trend</p>}

            <div className="ac-grid-2" style={{ marginTop: "var(--ac-space-5)" }}>
              <div className="ac-card">
                <p className="ac-eyebrow" style={{ marginBottom: 10 }}>Fleet Status Distribution</p>
                {totalAssets === 0 ? (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No aircraft or drone assets yet.</p>
                ) : (
                  [
                    { label: "Active", count: activeAssets, color: statusColor.ACTIVE },
                    { label: "Grounded", count: groundedAssets, color: statusColor.GROUNDED },
                    { label: "Unknown", count: unknownAssets, color: statusColor.UNKNOWN },
                  ].map((row) => (
                    <div className="ac-chart-bar-row" key={row.label}>
                      <span className="ac-text-sm">{row.label}</span>
                      <div className="ac-chart-bar-track">
                        <div
                          className="ac-chart-bar-fill"
                          style={{ width: `${totalAssets > 0 ? (row.count / totalAssets) * 100 : 0}%`, background: row.color }}
                        />
                      </div>
                      <span className="ac-chart-bar-count">{row.count}</span>
                    </div>
                  ))
                )}
              </div>

              <div className="ac-card">
                <p className="ac-eyebrow" style={{ marginBottom: 10 }}>Work Order Status Breakdown</p>
                {workOrders.length === 0 ? (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No work orders yet.</p>
                ) : (
                  Object.entries(woByStatus)
                    .sort((a, b) => b[1] - a[1])
                    .map(([status, count]) => (
                      <div className="ac-chart-bar-row" key={status}>
                        <span className="ac-text-sm">{status.replace(/_/g, " ")}</span>
                        <div className="ac-chart-bar-track">
                          <div
                            className="ac-chart-bar-fill"
                            style={{ width: `${(count / maxWoCount) * 100}%`, background: "var(--ac-accent)" }}
                          />
                        </div>
                        <span className="ac-chart-bar-count">{count}</span>
                      </div>
                    ))
                )}
              </div>
            </div>
          </RealDataPanel>
        )}
      </section>
    </>
  );
}

/** Real Findings widget, backed by the M20.2 Finding/Disposition API
 * (GET /findings, org-scoped server-side, no client-supplied org_id).
 * Distinct from lib/mock/findings.ts, which stays confined to the
 * already-illustrative-labelled "Maintenance Operations Snapshot" section
 * below. This is the one Findings surface on the dashboard that is real. */
function RealFindingsPanel() {
  const { accessToken, isAuthenticated } = useSession();
  const [openFindings, setOpenFindings] = useState<BackendFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    findingsApi
      .listForOrganization(accessToken, "OPEN")
      .then((f) => {
        setOpenFindings(f);
        setAsOf(new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }));
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, isAuthenticated]);

  if (!isAuthenticated) return null;

  return (
    <section className="ac-section">
      <div className="ac-section-header">
        <div>
          <h2 className="ac-h2" style={{ margin: 0 }}>Open Findings</h2>
          <p className="ac-subtitle" style={{ margin: 0 }}>Live from the connected backend (Finding/Disposition model)</p>
        </div>
      </div>
      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={!loading && !error && openFindings.length === 0}
        emptyMessage="No open findings for this organization."
      >
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card-real">
            <p className="ac-kpi-label">Open Findings</p>
            <p className="ac-kpi-value">{openFindings.length}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>status = OPEN, fleet-wide</p>
          </div>
        </div>
        {asOf && <p className="ac-kpi-asof">As of {asOf} · live backend query</p>}

        {openFindings.length > 0 && (
          <div className="ac-card" style={{ marginTop: "var(--ac-space-5)" }}>
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {openFindings.slice(0, 8).map((f) => (
                <li key={f.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <div className="ac-flex ac-justify-between ac-items-center" style={{ gap: 12 }}>
                    <div style={{ minWidth: 0 }}>
                      <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{f.title}</p>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                        Severity: {f.severity} · Discovered {new Date(f.discovered_at).toLocaleDateString()}
                        {f.aircraft_id ? null : f.asset_id ? " · drone asset" : ""}
                      </p>
                    </div>
                    <div className="ac-flex ac-gap-2">
                      <Link href={`/findings/${f.id}`} className="ac-btn ac-btn-primary">View Finding →</Link>
                      {f.aircraft_id ? (
                        <Link href={`/aircraft/${f.aircraft_id}`} className="ac-btn">View Asset →</Link>
                      ) : f.asset_id ? (
                        <Link href={`/drones/${f.asset_id}`} className="ac-btn">View Asset →</Link>
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </RealDataPanel>
    </section>
  );
}

export default function DashboardPage() {
  const recent = [...assessments].sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt)).slice(0, 6);
  const openReviews = assessments.filter((a) => a.humanDecision === "PENDING" || a.humanDecision === "REQUEST_MORE_EVIDENCE");
  const overdue = overdueMaintenanceEvents();
  const upcoming = upcomingMaintenanceEvents(5);
  const projects = activeProjects();
  const openWOs = openWorkOrders();
  const overdueWOs = overdueWorkOrders();
  const awaitingPartsWOs = awaitingPartsWorkOrders();
  const awaitingReviewWOs = awaitingReviewWorkOrders();
  const onShift = techniciansOnShift();
  const criticalWOs = openWOs.filter((w) => w.priority === "CRITICAL" || w.priority === "HIGH").slice(0, 5);
  const inspectionsAwaitingReview = inspectorReviews.filter((r) => r.status === "PENDING_INSPECTION").length;
  const checklistExceptions = findings.filter((f) => f.requiresDefect).length;
  const fleetAnalytics = getFleetAnalytics();
  const maintAnalytics = getMaintenanceAnalytics();
  const complianceAnalytics = getComplianceAnalytics();
  const inspectionAnalytics = getInspectionAnalytics();

  return (
    <div>
      {/* Fleet-wide hero treatment: no single aircraft is "the" dashboard
          aircraft, so this renders the generic multi-aircraft silhouette
          pairing (same logic FleetContextLayer already uses on /aircraft)
          at the higher hero opacity tier, with the blueprint grid. */}
      <AircraftContextLayer showGrid />
      <PageHeader
        title="Compliance Intelligence"
        subtitle="Fleet regulatory applicability and assessment overview"
        actions={<ViewingAsBadge />}
      />

      <RealFleetPanel />

      <RealFindingsPanel />

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2" style={{ margin: 0 }}>Daily Brief, Priority Queue &amp; TAT Summary</h2>
          <IllustrativeBadge />
        </div>
        <DailyBriefCard />
      </section>

      <section className="ac-section">
        <OperationalPriorityQueue />
      </section>

      <section className="ac-section">
        <FleetTatSummary />
      </section>

      <section className="ac-section">
        <div className="ac-card">
          <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
            <p className="ac-eyebrow" style={{ margin: 0 }}>
              The AeroComply Loop
            </p>
          </div>
          <CoreLoopDiagram />
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2" style={{ margin: 0 }}>Maintenance Operations Snapshot</h2>
          <IllustrativeBadge />
        </div>
        <div className="ac-kpi-grid">
          <Link href="/maintenance/projects" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Active Maintenance Projects</p>
            <p className="ac-kpi-value">{projects.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Open Work Orders</p>
            <p className="ac-kpi-value">{openWOs.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Overdue Tasks</p>
            <p className="ac-kpi-value">{overdueWOs.length}</p>
          </Link>
          <Link href="/maintenance/technicians" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Technicians On Shift</p>
            <p className="ac-kpi-value">{onShift.length}</p>
          </Link>
          <Link href="/maintenance/parts" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Awaiting Parts</p>
            <p className="ac-kpi-value">{awaitingPartsWOs.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Work Orders Waiting Inspection</p>
            <p className="ac-kpi-value">{awaitingReviewWOs.length}</p>
          </Link>
          <Link href="/maintenance/inspections" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Inspections Awaiting Review</p>
            <p className="ac-kpi-value">{inspectionsAwaitingReview}</p>
          </Link>
          <Link href="/maintenance/defects" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Checklist Exceptions</p>
            <p className="ac-kpi-value">{checklistExceptions}</p>
          </Link>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">AI &amp; Operations Intelligence</h2>
          <span className="ac-text-sm ac-text-muted">AI Prototype · Non-authoritative</span>
        </div>
        <div className="ac-grid-4">
          <div className="ac-card">
            <p className="ac-kpi-label">Fleet Risk</p>
            <p className="ac-kpi-value">{fleetAnalytics.aircraftAtRisk.length} / {fleetAnalytics.fleetSize}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>aircraft at elevated risk</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Maintenance Risk</p>
            <p className="ac-kpi-value">{maintAnalytics.overdue.length}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>overdue work orders</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Compliance Exposure</p>
            <p className="ac-kpi-value">{complianceAnalytics.nonCompliant + complianceAnalytics.reviewRequired}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>assessments needing attention</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Inspection Queue</p>
            <p className="ac-kpi-value">{inspectionAnalytics.pending.length}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>awaiting review</p>
          </div>
        </div>
        <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginTop: 12, flexWrap: "wrap" }}>
          <Link href="/ai" className="ac-btn ac-btn-primary">Ask {PLATFORM_AI_NAME}</Link>
          <Link href="/executive" className="ac-btn">Executive Intelligence</Link>
          <Link href="/maintenance/operations" className="ac-btn">Maintenance Operations</Link>
          <Link href="/maintenance/inspections" className="ac-btn">Inspection Queue</Link>
          <Link href="/compliance" className="ac-btn">Compliance Intelligence</Link>
          <Link href="/reports/fleet-risk" className="ac-btn">Generate Operations Report</Link>
          <Link href="/reports" className="ac-btn">Reports</Link>
          <Link href="/organization/roles" className="ac-btn">Role Management</Link>
          <ViewingAsBadge />
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Maintenance Operations</h2>
          <Link href="/maintenance/projects" className="ac-text-sm">View all →</Link>
        </div>
        <div className="ac-grid-2">
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Active Projects</p>
            <div className="ac-flex ac-flex-col ac-gap-2">
              {projects.map((p) => {
                const ac = getAircraftById(p.aircraftId);
                return (
                  <Link key={p.id} href={`/maintenance/projects/${p.id}`} className="ac-card" style={{ display: "block" }}>
                    <div className="ac-flex ac-justify-between ac-items-center">
                      <span className="ac-mono" style={{ fontWeight: 600, fontSize: 13 }}>{p.title}</span>
                      <StatusBadge {...projectStatusBadge(p.status)} />
                    </div>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      {ac ? currentRegistration(ac) : p.aircraftId} · {p.progressPercent}% complete
                    </p>
                  </Link>
                );
              })}
            </div>
          </div>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Critical Work Orders</p>
            <div className="ac-flex ac-flex-col ac-gap-2">
              {criticalWOs.map((w) => (
                <Link key={w.id} href={`/maintenance/work-orders/${w.id}`} className="ac-card" style={{ display: "block" }}>
                  <div className="ac-flex ac-justify-between ac-items-center">
                    <span className="ac-mono" style={{ fontWeight: 600, fontSize: 13 }}>{w.workOrderNumber}</span>
                    <div className="ac-flex ac-gap-2">
                      <StatusBadge {...priorityBadge(w.priority)} />
                      <StatusBadge {...workOrderStatusBadge(w.status)} />
                    </div>
                  </div>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{w.title} · Due {w.dueDate}</p>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      {awaitingReviewWOs.length > 0 && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "var(--ac-status-insufficient-bg)" }}>
            <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 6 }}>AI Maintenance Insight — Prototype</p>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>
              {projects[0]?.title ?? "The active check"} is currently 8% behind the planned schedule.
            </p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "6px 0" }}>Potential contributors:</p>
            <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
              {overdueWOs.length > 0 && <li>{overdueWOs.length} overdue task{overdueWOs.length > 1 ? "s" : ""}</li>}
              {awaitingPartsWOs.length > 0 && <li>{awaitingPartsWOs.length} part{awaitingPartsWOs.length > 1 ? "s" : ""} awaiting receipt</li>}
              <li>{awaitingReviewWOs.length} compliance/task review pending</li>
            </ul>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Recommended action: Prioritize <Link href={`/maintenance/work-orders/${awaitingReviewWOs[0].id}`} className="ac-mono">{awaitingReviewWOs[0].workOrderNumber}</Link> and the pending compliance review.
            </p>
          </div>
        </section>
      )}

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Fleet Compliance Overview</h2>
          <span className="ac-flex ac-items-center ac-gap-2 ac-text-sm ac-text-muted">
            128 aircraft (demo scenario) <IllustrativeBadge />
          </span>
        </div>
        <div className="ac-card">
          <div className="ac-flex" style={{ height: 10, borderRadius: 6, overflow: "hidden", marginBottom: 14 }}>
            {DISTRIBUTION.map((d) => (
              <div key={d.label} style={{ width: `${d.pct}%`, background: d.color }} title={`${d.label}: ${d.pct}%`} />
            ))}
          </div>
          <div className="ac-flex ac-gap-6" style={{ flexWrap: "wrap" }}>
            {DISTRIBUTION.map((d) => (
              <div key={d.label} className="ac-flex ac-items-center ac-gap-2 ac-text-sm">
                <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: "50%", background: d.color, display: "inline-block" }} />
                <span>{d.label}</span>
                <span className="ac-text-muted">{d.pct}%</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Recent Assessments</h2>
          <Link href="/assessments" className="ac-text-sm">
            View all →
          </Link>
        </div>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Requirement</th>
                <th>Aircraft</th>
                <th>Registration</th>
                <th>Assessment Date</th>
                <th>System Result</th>
                <th>Human Decision</th>
                <th>Evidence</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((a) => {
                const aircraft = a.subjectType === "AIRCRAFT" ? getAircraftById(a.subjectId) : undefined;
                const requirement = getRequirementById(a.regulatoryRequirementId);
                const variant = aircraft ? getAircraftVariant(aircraft.aircraftVariantId) : undefined;
                const evCount = evidenceForAssessment(a.id).length;
                return (
                  <tr key={a.id}>
                    <td>
                      <Link href={`/regulations/${requirement?.id}`} className="ac-mono">
                        {requirement?.requirementNumber}
                      </Link>
                    </td>
                    <td>{variant?.modelDesignation ?? "—"}</td>
                    <td>
                      <Link href={`/aircraft/${aircraft?.id}`} className="ac-mono">
                        {aircraft ? currentRegistration(aircraft) : a.subjectId}
                      </Link>
                    </td>
                    <td>{new Date(a.evaluatedAt).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })}</td>
                    <td>
                      <StatusBadge status={a.systemResult} />
                    </td>
                    <td className="ac-text-sm">{a.humanDecision.replace(/_/g, " ")}</td>
                    <td className="ac-text-sm">
                      {evCount} Evidence
                    </td>
                    <td>
                      <Link href={`/assessments/${a.id}`}>
                        <StatusBadge status={a.finalStatus} />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <div className="ac-section-header">
            <h2 className="ac-h2">Upcoming AD/SB Deadlines</h2>
            <Link href="/audit" className="ac-text-sm">View all →</Link>
          </div>
          <div className="ac-card" style={{ padding: 0 }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Aircraft</th>
                  <th>Event</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {upcoming.length === 0 && (
                  <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No scheduled items.</td></tr>
                )}
                {upcoming.map((m) => {
                  const ac = getAircraftById(m.aircraftId);
                  return (
                    <tr key={m.id}>
                      <td className="ac-mono ac-text-sm">{m.date}</td>
                      <td>
                        <Link href={`/aircraft/${m.aircraftId}`} className="ac-mono">{ac ? currentRegistration(ac) : m.aircraftId}</Link>
                      </td>
                      <td className="ac-text-sm">{m.description}</td>
                      <td><StatusBadge status="PENDING" label="Scheduled" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <div className="ac-section-header">
            <h2 className="ac-h2">Overdue Compliance Items</h2>
            <Link href="/audit" className="ac-text-sm">View all →</Link>
          </div>
          <div className="ac-card" style={{ padding: 0 }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Due</th>
                  <th>Aircraft</th>
                  <th>Event</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {overdue.length === 0 && (
                  <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>Nothing overdue.</td></tr>
                )}
                {overdue.map((m) => {
                  const ac = getAircraftById(m.aircraftId);
                  return (
                    <tr key={m.id}>
                      <td className="ac-mono ac-text-sm">{m.date}</td>
                      <td>
                        <Link href={`/aircraft/${m.aircraftId}`} className="ac-mono">{ac ? currentRegistration(ac) : m.aircraftId}</Link>
                      </td>
                      <td className="ac-text-sm">{m.description}</td>
                      <td><StatusBadge status="NON_COMPLIANT" label="Overdue" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Open Review Decisions</h2>
          <Link href="/assessments" className="ac-text-sm">View all →</Link>
        </div>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Requirement</th>
                <th>Aircraft</th>
                <th>System Result</th>
                <th>Human Decision</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {openReviews.length === 0 && (
                <tr><td colSpan={5} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No open review decisions.</td></tr>
              )}
              {openReviews.map((a) => {
                const aircraft = a.subjectType === "AIRCRAFT" ? getAircraftById(a.subjectId) : undefined;
                const requirement = getRequirementById(a.regulatoryRequirementId);
                return (
                  <tr key={a.id}>
                    <td className="ac-mono">{requirement?.requirementNumber}</td>
                    <td>
                      <Link href={`/aircraft/${aircraft?.id ?? ""}`} className="ac-mono">{aircraft ? currentRegistration(aircraft) : a.subjectId}</Link>
                    </td>
                    <td><StatusBadge status={a.systemResult} /></td>
                    <td className="ac-text-sm">{a.humanDecision.replace(/_/g, " ")}</td>
                    <td>
                      <Link href={`/assessments/${a.id}/review`} className="ac-btn">Review</Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 12 }}>
          <h2 className="ac-h2" style={{ margin: 0 }}>Attention Required</h2>
          <IllustrativeBadge />
        </div>
        <div className="ac-card">
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {ATTENTION_ITEMS.map((item) => (
              <li key={item.text} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                <Link href={item.href} className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13 }}>
                  <span aria-hidden="true" style={{ color: "var(--ac-status-review)" }}>
                    ⚠
                  </span>
                  {item.text}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
