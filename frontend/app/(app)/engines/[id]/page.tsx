"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { Timeline } from "@/components/timeline/Timeline";
import { getEngineById, getEngineType, installationsForEngine } from "@/lib/mock/engines";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { assessmentsForEngine } from "@/lib/mock/assessments";
import { regulatoryRequirements } from "@/lib/mock/regulations";
import { maintenanceEventsForEngine } from "@/lib/mock/maintenance";
import type { ApplicabilityAssessment, EngineInstallation } from "@/lib/mock/types";

export default function EngineDetailPage({ params }: { params: { id: string } }) {
  const engine = getEngineById(params.id);
  if (!engine) notFound();

  const type = getEngineType(engine.engineTypeId)!;
  const history = installationsForEngine(engine.id).sort((a, b) => a.installedAt.localeCompare(b.installedAt));
  const current = history.find((h) => h.removedAt === null);
  const currentAircraft = current ? getAircraftById(current.aircraftId) : undefined;
  const assessments = assessmentsForEngine(engine.id);
  const maintenanceEvents = maintenanceEventsForEngine(engine.id);

  const installColumns: Column<EngineInstallation>[] = [
    { key: "aircraft", header: "Aircraft", render: (i) => { const a = getAircraftById(i.aircraftId); return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : i.aircraftId; } },
    { key: "position", header: "Position", render: (i) => i.position.replace("_", " ") },
    { key: "installed", header: "Installed", render: (i) => i.installedAt },
    { key: "removed", header: "Removed", render: (i) => i.removedAt ?? "— (current)" },
  ];

  const assessmentColumns: Column<ApplicabilityAssessment>[] = [
    { key: "req", header: "Requirement", render: (a) => regulatoryRequirements.find((r) => r.id === a.regulatoryRequirementId)?.requirementNumber },
    { key: "result", header: "System Result", render: (a) => <StatusBadge status={a.systemResult} /> },
    { key: "final", header: "Status", render: (a) => <StatusBadge status={a.finalStatus} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Engines", href: "/engines" }, { label: engine.serialNumber }]} />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{engine.serialNumber}</h1>
          <p className="ac-subtitle">{type.manufacturer} {type.modelDesignation}</p>
        </div>
      </div>

      <div className="ac-card" style={{ marginBottom: "var(--ac-space-4)", background: "var(--ac-accent-muted)", border: "1px solid var(--ac-accent)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          <strong>Engine is a first-class assessment subject.</strong> It carries its own applicability
          assessments (below), independent of whichever aircraft it happens to be installed on — see{" "}
          <span className="ac-mono">docs/adr/ADR-008</span>.
        </p>
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Current Aircraft</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {currentAircraft ? <Link href={`/aircraft/${currentAircraft.id}`}>{currentRegistration(currentAircraft)}</Link> : "Not installed"}
          </p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Position</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{current?.position.replace("_", " ") ?? "—"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Manufacturer</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{type.manufacturer}</p>
        </div>
      </div>

      <div className="ac-grid-2 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Operating Status</p>
          <div style={{ marginTop: 6 }}>
            <StatusBadge status={current ? "ACTIVE" : "STORED"} label={current ? "In Service" : "Not Installed"} />
          </div>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Compliance Status</p>
          <div style={{ marginTop: 6 }}>
            {assessments[0] ? <StatusBadge status={assessments[0].finalStatus} /> : <span className="ac-text-sm ac-text-muted">No assessments yet</span>}
          </div>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Installation History</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable columns={installColumns} rows={history} />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Applicable Requirements &amp; Assessments</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable
            columns={assessmentColumns}
            rows={assessments}
            getRowHref={(a) => `/assessments/${a.id}`}
            emptyMessage="No engine-level assessments recorded yet for this serial number."
          />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance Events</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr><th>Date</th><th>Type</th><th>Description</th><th>Status</th></tr>
            </thead>
            <tbody>
              {maintenanceEvents.length === 0 && (
                <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No maintenance events recorded for this serial number.</td></tr>
              )}
              {maintenanceEvents.map((m) => (
                <tr key={m.id}>
                  <td className="ac-mono ac-text-sm">{m.date}</td>
                  <td className="ac-text-sm">{m.eventType.replace(/_/g, " ")}</td>
                  <td className="ac-text-sm">{m.description}</td>
                  <td>
                    <StatusBadge
                      status={m.status === "OVERDUE" ? "NON_COMPLIANT" : m.status === "COMPLETED" ? "COMPLIANT" : m.status === "IN_PROGRESS" ? "REVIEW_REQUIRED" : "PENDING"}
                      label={m.status.replace(/_/g, " ")}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Timeline</h2>
        <div className="ac-card">
          <Timeline
            entries={history.flatMap((i) => {
              const entries = [{ id: `i-${i.id}`, date: i.installedAt, title: `Installed on ${getAircraftById(i.aircraftId) ? currentRegistration(getAircraftById(i.aircraftId)!) : i.aircraftId} (${i.position.replace("_", " ")})` }];
              if (i.removedAt) entries.push({ id: `r-${i.id}`, date: i.removedAt, title: "Removed" });
              return entries;
            })}
          />
        </div>
      </section>
    </div>
  );
}
