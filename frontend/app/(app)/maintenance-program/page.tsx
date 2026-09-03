import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { maintenancePrograms, maintenanceRequirements, requirementsForProgram } from "@/lib/mock/maintenanceProgram";
import { getFleetMaintenanceDue, type MaintenanceDueStatus } from "@/lib/mock/ai/analytics";

// M17 — due-status badge mapping, local to this page (not a shared
// component change) since this is the only page rendering all five
// MaintenanceDueStatus values in one table.
const DUE_STATUS_BADGE: Record<MaintenanceDueStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  CURRENT: { status: "COMPLIANT", label: "CURRENT" },
  DUE_SOON: { status: "PENDING", label: "DUE SOON" },
  DUE: { status: "REVIEW_REQUIRED", label: "DUE" },
  OVERDUE: { status: "NON_COMPLIANT", label: "OVERDUE" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

// M15 — Maintenance Program foundation. Every record here is explicitly
// DEMO DATA (see lib/mock/maintenanceProgram.ts header) — a prototype
// program built to exercise the interval/applicability/forecasting
// architecture, not a real approved aircraft maintenance program. This page
// says so directly rather than letting the clean table styling imply
// authority the data doesn't have.

export default function MaintenanceProgramPage() {
  const dueRows = getFleetMaintenanceDue().flatMap((f) => f.items.map((i) => ({ registration: f.registration, aircraftId: f.aircraftId, ...i })));

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance Program" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Maintenance Program</h1>
          <p className="ac-subtitle">
            Prototype architecture for maintenance-program intervals and applicability. Every record below is explicitly demo
            data, not an approved maintenance program — see each requirement&apos;s source.
          </p>
        </div>
      </div>

      {maintenancePrograms.map((p) => (
        <section className="ac-section" key={p.id}>
          <div className="ac-card">
            <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10, marginBottom: 8 }}>
              <div>
                <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{p.name}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Revision {p.revision} · Effective {p.effectiveDate}</p>
              </div>
              <StatusBadge status={p.status === "ACTIVE" ? "COMPLIANT" : p.status === "DRAFT" ? "PENDING" : "INSUFFICIENT_DATA"} label={p.status} />
            </div>
            <p className="ac-text-sm" style={{ margin: "0 0 12px", fontWeight: 600 }}>Source: {p.source}</p>
            <div className="ac-card" style={{ padding: 0 }}>
              <table className="ac-table">
                <thead><tr><th>ATA</th><th>Requirement</th><th>Interval</th><th>Task Reference</th></tr></thead>
                <tbody>
                  {requirementsForProgram(p.id).map((r) => (
                    <tr key={r.id}>
                      <td className="ac-mono">{r.ataChapter}</td>
                      <td className="ac-text-sm">{r.description}</td>
                      <td className="ac-text-sm">
                        {r.intervalType === "FH" && `${r.fhInterval} FH`}
                        {r.intervalType === "FC" && `${r.fcInterval} FC`}
                        {r.intervalType === "CALENDAR" && `${r.calendarIntervalDays} days`}
                        {r.intervalType === "FH_OR_CALENDAR" && `${r.fhInterval} FH or ${r.calendarIntervalDays} days`}
                        {r.intervalType === "FC_OR_CALENDAR" && `${r.fcInterval} FC or ${r.calendarIntervalDays} days`}
                        {r.intervalType === "FH_AND_FC" && `${r.fhInterval} FH and ${r.fcInterval} FC`}
                      </td>
                      <td className="ac-mono ac-text-sm">{r.taskReference ?? "Insufficient source data."}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ))}

      {maintenanceRequirements.length === 0 && (
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No maintenance program on file.</p></div>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Fleet Maintenance Due Status</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
          One row per (aircraft, requirement) pair the requirement applies to. Computed from real accomplishment records
          (lib/mock/maintenanceAccomplishments.ts) and current aircraft utilization — never from a work order&apos;s planned or
          scheduled date. UNKNOWN rows state why.
        </p>
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr><th>Aircraft</th><th>Requirement</th><th>Basis</th><th>Last Accomplished</th><th>Next Due</th><th>Remaining</th><th>Status</th><th>Note</th></tr>
            </thead>
            <tbody>
              {dueRows.map((r) => {
                const badge = DUE_STATUS_BADGE[r.dueStatus];
                return (
                  <tr key={`${r.aircraftId}-${r.requirementId}`}>
                    <td><Link href={`/aircraft/${r.aircraftId}`} className="ac-mono">{r.registration}</Link></td>
                    <td className="ac-text-sm">{r.description}</td>
                    <td>{r.basis}</td>
                    <td className="ac-text-sm">{r.lastAccomplished}</td>
                    <td className="ac-text-sm">{r.nextDue}</td>
                    <td className="ac-text-sm">{r.remaining}</td>
                    <td><StatusBadge status={badge.status} label={badge.label} /></td>
                    <td className="ac-text-sm ac-text-muted">{r.dataQualityNote}</td>
                  </tr>
                );
              })}
              {dueRows.length === 0 && (
                <tr><td colSpan={8} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No requirement currently applies to any aircraft.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ac-section">
        <p className="ac-text-sm ac-text-muted">
          Ask Lisa (&quot;what maintenance is coming due for VT-ABC&quot;, &quot;what maintenance is overdue?&quot;) for the same
          data with an explanation.
        </p>
      </section>
    </div>
  );
}
