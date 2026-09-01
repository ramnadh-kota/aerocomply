"use client";

import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, operationalStatusBadge, riskLevelBadge } from "@/components/status/StatusBadge";
import { PLATFORM_NAME } from "@/lib/brand";
import { getControlTowerFleet, getControlTowerSummary, getWorkOrderPlanning, type ControlTowerAircraftRow, type OperationalStatus } from "@/lib/mock/ai/analytics";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";

// M12.1 — Maintenance Control Tower. A single operational fleet view built
// entirely on existing repositories/analytics (getControlTowerFleet /
// getControlTowerSummary in lib/mock/ai/analytics.ts) — no new mock-data
// system, no new state store. KPI clicks set local filter state; nothing is
// mutated except the audit trail entry emitted when a risk explanation is
// opened.

type KpiFilter = "ALL" | OperationalStatus | "OPEN_WORK_ORDERS" | "CRITICAL_DISCREPANCIES" | "UPCOMING_MAINTENANCE" | "MATERIAL_SHORTAGES";

export default function MaintenanceControlTowerPage() {
  const [filter, setFilter] = useState<KpiFilter>("ALL");
  const [openRiskFor, setOpenRiskFor] = useState<string | null>(null);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();

  const fleet = useMemo(() => getControlTowerFleet(), []);
  const summary = useMemo(() => getControlTowerSummary(), []);
  const planning = useMemo(() => getWorkOrderPlanning(), []);

  const filtered: ControlTowerAircraftRow[] = useMemo(() => {
    switch (filter) {
      case "ALL":
        return fleet;
      case "OPERATIONAL":
      case "UNDER_MAINTENANCE":
      case "AOG":
      case "STORED":
      case "WRITTEN_OFF":
        return fleet.filter((r) => r.operationalStatus === filter);
      case "OPEN_WORK_ORDERS":
        return fleet.filter((r) => r.openWorkOrders > 0);
      case "CRITICAL_DISCREPANCIES":
        return fleet.filter((r) => r.criticalOpenDefects > 0);
      case "UPCOMING_MAINTENANCE":
        return fleet.filter((r) => r.nextMaintenanceDue !== null);
      case "MATERIAL_SHORTAGES":
        return fleet.filter((r) => r.materialShortageCount > 0);
      default:
        return fleet;
    }
  }, [fleet, filter]);

  function toggleRisk(aircraftId: string) {
    const opening = openRiskFor !== aircraftId;
    setOpenRiskFor(opening ? aircraftId : null);
    if (opening) {
      const row = fleet.find((r) => r.aircraftId === aircraftId);
      addAuditEvent({
        actor: current?.user.name ?? "Unknown User",
        actorRole: "Maintenance",
        action: "maintenance.risk_assessed",
        objectType: "Aircraft",
        objectLabel: row?.registration ?? aircraftId,
        previousState: null,
        newState: row?.risk.risk ?? null,
      });
    }
  }

  const kpis: { label: string; value: number; filter: KpiFilter }[] = [
    { label: "Total Aircraft", value: summary.totalAircraft, filter: "ALL" },
    { label: "Operational", value: summary.operational, filter: "OPERATIONAL" },
    { label: "Under Maintenance", value: summary.underMaintenance, filter: "UNDER_MAINTENANCE" },
    { label: "AOG", value: summary.aog, filter: "AOG" },
    { label: "Open Work Orders", value: summary.openWorkOrders, filter: "OPEN_WORK_ORDERS" },
    { label: "Critical Discrepancies", value: summary.criticalDiscrepancies, filter: "CRITICAL_DISCREPANCIES" },
    { label: "Upcoming Maintenance", value: summary.upcomingMaintenance, filter: "UPCOMING_MAINTENANCE" },
    { label: "Material Shortages", value: summary.materialShortages, filter: "MATERIAL_SHORTAGES" },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/operations" }, { label: "Control Tower" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">Maintenance Control Tower</h1>
          <p className="ac-subtitle">
            A single operational view of the fleet. &quot;AOG&quot; and &quot;Under Maintenance&quot; are derived from open defects and work
            orders — not tracked status fields — and every risk score below is explainable. There is no flight-schedule data in this demo
            dataset, so location and next-flight fields are shown honestly as unavailable rather than guessed.
          </p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          {kpis.map((k) => (
            <div
              key={k.label}
              role="button"
              tabIndex={0}
              onClick={() => setFilter(k.filter)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setFilter(k.filter); }}
              className="ac-kpi-card"
              style={{ textAlign: "left", cursor: "pointer", border: filter === k.filter ? "1px solid var(--ac-accent)" : undefined }}
            >
              <p className="ac-kpi-label">{k.label}</p>
              <p className="ac-kpi-value">{k.value}</p>
              {k.filter === "OPEN_WORK_ORDERS" && (
                <Link href="/maintenance/planning" className="ac-text-sm" style={{ display: "block", marginTop: 4 }} onClick={(e) => e.stopPropagation()}>
                  Open Planning Center →
                </Link>
              )}
              {k.filter === "MATERIAL_SHORTAGES" && (
                <Link href="/maintenance/material-readiness" className="ac-text-sm" style={{ display: "block", marginTop: 4 }} onClick={(e) => e.stopPropagation()}>
                  View Material Readiness →
                </Link>
              )}
            </div>
          ))}
        </div>
        {filter !== "ALL" && (
          <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
            Filtered by {kpis.find((k) => k.filter === filter)?.label}. <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => setFilter("ALL")}>Clear filter</button>
          </p>
        )}
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Aircraft Status</h2>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Aircraft</th>
                <th>Model</th>
                <th>Status</th>
                <th>Location</th>
                <th>Next Flight</th>
                <th>Next Maintenance Due</th>
                <th>Open WOs</th>
                <th>Open Discrepancies</th>
                <th>Material Readiness</th>
                <th>Risk</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => {
                const badge = operationalStatusBadge(row.operationalStatus);
                const risk = riskLevelBadge(row.risk.risk);
                const aircraftWos = planning.filter((p) => p.aircraftId === row.aircraftId);
                const blockedWos = aircraftWos.filter((p) => p.planningStatus === "MATERIAL_BLOCKED" || p.planningStatus === "BOTH_BLOCKED");
                return (
                  <Fragment key={row.aircraftId}>
                    <tr>
                      <td><Link href={`/aircraft/${row.aircraftId}`} className="ac-mono">{row.registration}</Link></td>
                      <td>{row.model}</td>
                      <td>
                        <StatusBadge status={badge.status} label={badge.label} />
                        {row.operationalStatus === "AOG" && row.aogReason && (
                          <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{row.aogReason}</p>
                        )}
                      </td>
                      <td className="ac-text-muted">Insufficient source data.</td>
                      <td className="ac-text-muted">Insufficient source data.</td>
                      <td>{row.nextMaintenanceDue ?? <span className="ac-text-muted">Insufficient source data.</span>}</td>
                      <td>{row.openWorkOrders}</td>
                      <td>{row.openDefects}</td>
                      <td>
                        {row.materialShortageCount > 0 ? (
                          <>
                            <span style={{ color: "var(--ac-status-non_compliant)" }}>
                              {row.materialShortageCount} shortage(s){blockedWos.length > 0 ? ` — ${blockedWos.map((w) => w.workOrderNumber).join(", ")}` : ""}
                            </span>
                            <br />
                            <Link href="/maintenance/material-readiness" className="ac-text-sm">View Material Readiness →</Link>
                          </>
                        ) : (
                          "Ready"
                        )}
                      </td>
                      <td>
                        <StatusBadge status={risk.status} label={risk.label} />
                        <button className="ac-btn" style={{ padding: "2px 8px", marginLeft: 6 }} onClick={() => toggleRisk(row.aircraftId)}>
                          Why?
                        </button>
                      </td>
                    </tr>
                    {openRiskFor === row.aircraftId && (
                      <tr>
                        <td colSpan={10}>
                          <div className="ac-card" style={{ background: "var(--ac-bg-surface-hover)", margin: "4px 0" }}>
                            <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Why is {row.registration} {row.risk.risk} risk?</p>
                            <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
                              {row.risk.reasons.map((reason) => (
                                <li key={reason}>→ {reason}</li>
                              ))}
                            </ul>
                            {aircraftWos.length > 0 && (
                              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                                {aircraftWos.map((w) => (
                                  <Link key={w.workOrderId} href={`/maintenance/planning/${w.workOrderId}`} className="ac-btn" style={{ padding: "2px 8px" }}>
                                    Open Work Order {w.workOrderNumber}
                                  </Link>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={10} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>No aircraft match this filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <p className="ac-text-sm ac-text-muted">
          Continue to <Link href="/maintenance/discrepancies" className="ac-mono">Discrepancy Intelligence</Link> to investigate recurring
          patterns, or ask <Link href="/ai" className="ac-mono">Lisa</Link> which aircraft is most at risk.
        </p>
      </section>
    </div>
  );
}
