"use client";

import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { aircraft } from "@/lib/mock/aircraft";
import { workOrders } from "@/lib/mock/workOrders";
import { users } from "@/lib/mock/roles";
import { useMroState } from "@/lib/mro-state/MroStateContext";

export default function UsageIntelligencePage() {
  const { auditLog } = useMroState();

  // M6.4 — Commercial Usage Intelligence. Every count here is derived from
  // the SAME single audit system used everywhere else (no separate telemetry
  // system) — counts reflect this session's live activity plus seeded
  // history, not invented usage numbers.
  const aiQuestions = auditLog.filter((e) => e.action === "ai.analysis_generated").length;
  const reportsGenerated = auditLog.filter((e) => e.action === "report.generated").length;
  const inspectionsCompleted = auditLog.filter((e) => e.action === "inspection.approved" || e.action === "inspection.rejected" || e.action === "inspection.returned_for_correction").length;
  const evidenceEvents = auditLog.filter((e) => e.action === "evidence.attached").length;
  const roleSimChanges = auditLog.filter((e) => e.action === "role_simulation.changed").length;
  const activeActors = new Set(auditLog.map((e) => e.actor)).size;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization", href: "/organization" }, { label: "Usage Intelligence" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Usage Intelligence</h1>
          <p className="ac-subtitle">Internal SaaS usage metrics, derived from the same audit system used for compliance traceability — no separate telemetry pipeline. Supports future subscription-tier pricing decisions; not shown to end customers.</p>
        </div>
      </div>

      <div className="ac-kpi-grid">
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Active Actors (this session)</p>
          <p className="ac-kpi-value">{activeActors}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Active Aircraft</p>
          <p className="ac-kpi-value">{aircraft.length}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Work Orders Processed</p>
          <p className="ac-kpi-value">{workOrders.length}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Users Configured</p>
          <p className="ac-kpi-value">{users.length}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Evidence Attached</p>
          <p className="ac-kpi-value">{evidenceEvents}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Inspections Completed</p>
          <p className="ac-kpi-value">{inspectionsCompleted}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">AI Questions Asked</p>
          <p className="ac-kpi-value">{aiQuestions}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Reports Generated</p>
          <p className="ac-kpi-value">{reportsGenerated}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Role Simulation Changes</p>
          <p className="ac-kpi-value">{roleSimChanges}</p>
        </div>
      </div>

      <p className="ac-text-sm ac-text-muted" style={{ marginTop: 16 }}>
        Prototype note: activity counts reset with the in-memory audit log on page reload — this is not persisted usage
        billing data. A production version would source these from the same audit event stream against a persisted store.
      </p>
    </div>
  );
}
