import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, workOrderStatusBadge, defectStatusBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { getAircraftById, getAircraftVariant, getAircraftType, currentRegistration } from "@/lib/mock/aircraft";
import { workOrdersForAircraft } from "@/lib/mock/workOrders";
import { defectsForAircraft } from "@/lib/mock/defects";
import { getInspectorReviewById } from "@/lib/mock/inspectorReviews";
import { getTechnicianById } from "@/lib/mock/technicians";
import { assessmentsForAircraft } from "@/lib/mock/assessments";
import { getRequirementById } from "@/lib/mock/regulations";
import { maintenanceEventsForAircraft } from "@/lib/mock/maintenance";
import { getAircraftAnalytics, getPartsAtRisk } from "@/lib/mock/ai/analytics";

export default function AircraftHealthPage({ params }: { params: { id: string } }) {
  const aircraft = getAircraftById(params.id);
  if (!aircraft) notFound();

  const analytics = getAircraftAnalytics(aircraft.id);
  if (!analytics) notFound();

  const variant = getAircraftVariant(aircraft.aircraftVariantId)!;
  const type = getAircraftType(variant.aircraftTypeId)!;
  const registration = currentRegistration(aircraft);

  const wos = workOrdersForAircraft(aircraft.id);
  const openWos = wos.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const waitingPartsWos = wos.filter((w) => w.status === "WAITING_PARTS");
  const inspectionWos = wos.filter((w) => w.inspectorReviewId);
  const pendingInspections = inspectionWos.filter((w) => getInspectorReviewById(w.inspectorReviewId!)?.status === "PENDING_INSPECTION");
  const defs = defectsForAircraft(aircraft.id);
  const openDefs = defs.filter((d) => d.status === "OPEN");
  const seriousOpenDefs = openDefs.filter((d) => d.severity === "HIGH" || d.severity === "CRITICAL");
  const assessments = assessmentsForAircraft(aircraft.id);
  const complianceAttention = assessments.filter((a) => a.finalStatus === "REVIEW_REQUIRED" || a.finalStatus === "NON_COMPLIANT");

  const statusCounts = new Map<string, number>();
  for (const w of wos) statusCounts.set(w.status, (statusCounts.get(w.status) ?? 0) + 1);

  const severityCounts = new Map<string, number>();
  for (const d of defs) severityCounts.set(d.severity, (severityCounts.get(d.severity) ?? 0) + 1);

  const byTechnician = new Map<string, number>();
  for (const w of wos) {
    if (!w.assignedTechnicianId) continue;
    byTechnician.set(w.assignedTechnicianId, (byTechnician.get(w.assignedTechnicianId) ?? 0) + 1);
  }

  const priorityRank: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  const highestPriorityWo = [...openWos].sort((a, b) => (priorityRank[a.priority] ?? 9) - (priorityRank[b.priority] ?? 9))[0];

  const woIdSet = new Set(wos.map((w) => w.id));
  const partsAtRisk = getPartsAtRisk().filter((p) => p.workOrderId && woIdSet.has(p.workOrderId));

  const upcomingEvents = maintenanceEventsForAircraft(aircraft.id).filter((e) => e.status !== "COMPLETED");
  const regulatoryDeadlines = upcomingEvents.filter((e) => e.relatedRequirementId);

  const healthTone: "COMPLIANT" | "REVIEW_REQUIRED" | "NON_COMPLIANT" =
    analytics.complianceRisk === "HIGH" ? "NON_COMPLIANT" : analytics.complianceRisk === "MEDIUM" ? "REVIEW_REQUIRED" : "COMPLIANT";

  const aiObservations: string[] = [];
  if (analytics.overdueWorkOrders > 0) aiObservations.push(`${analytics.overdueWorkOrders} work order(s) are overdue on this aircraft.`);
  if (seriousOpenDefs.length > 0) aiObservations.push(`${seriousOpenDefs.length} open HIGH/CRITICAL defect(s) require attention.`);
  if (complianceAttention.length > 0) aiObservations.push(`${complianceAttention.length} assessment(s) are Review Required or Non-Compliant.`);
  if (pendingInspections.length > 0) aiObservations.push(`${pendingInspections.length} work order(s) are awaiting inspection.`);
  if (aiObservations.length === 0) aiObservations.push("No overdue work, serious defects, or compliance exceptions detected for this aircraft.");

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Aircraft", href: "/aircraft" },
          { label: registration, href: `/aircraft/${aircraft.id}` },
          { label: "Health" },
        ]}
      />

      {/* 1. Aircraft Header */}
      <div className="ac-section-header">
        <div>
          <div className="ac-flex ac-items-center ac-gap-3">
            <h1 className="ac-h1">{registration} — Aircraft Health &amp; Maintenance Intelligence</h1>
            <StatusBadge status={aircraft.status} />
            <StatusBadge status={healthTone} label={`Health: ${analytics.complianceRisk}`} />
          </div>
          <p className="ac-subtitle">{type.manufacturer} {variant.modelDesignation} · MSN {aircraft.msn}</p>
        </div>
        <Link href={`/aircraft/${aircraft.id}`} className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>← Back to Aircraft</Link>
      </div>

      {/* 2. Maintenance Health */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance Health</h2>
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Open Work Orders</p>
            <p className="ac-kpi-value">{analytics.openWorkOrders}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Overdue Work Orders</p>
            <p className="ac-kpi-value">{analytics.overdueWorkOrders}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Waiting for Parts</p>
            <p className="ac-kpi-value">{waitingPartsWos.length}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Pending Inspections</p>
            <p className="ac-kpi-value">{pendingInspections.length}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Open Defects</p>
            <p className="ac-kpi-value">{analytics.openDefects}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Compliance Attention</p>
            <p className="ac-kpi-value">{complianceAttention.length}</p>
          </div>
        </div>
      </section>

      {/* 3. Maintenance Breakdown */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance Breakdown</h2>
        <div className="ac-grid-2">
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Work Orders by Status</p>
            {wos.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                {Array.from(statusCounts.entries()).map(([status, count]) => (
                  <Link key={status} href="/maintenance/work-orders" className="ac-flex ac-items-center ac-gap-2">
                    <StatusBadge {...workOrderStatusBadge(status)} label={`${status.replace(/_/g, " ")}: ${count}`} />
                  </Link>
                ))}
              </div>
            )}
          </div>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Defects by Severity</p>
            {defs.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                {Array.from(severityCounts.entries()).map(([severity, count]) => (
                  <Link key={severity} href="/maintenance/defects" className="ac-flex ac-items-center ac-gap-2">
                    <StatusBadge {...priorityBadge(severity)} label={`${severity}: ${count}`} />
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="ac-grid-2" style={{ marginTop: 16 }}>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Inspection Status</p>
            {inspectionWos.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {inspectionWos.map((w) => {
                  const review = getInspectorReviewById(w.inspectorReviewId!);
                  return (
                    <li key={w.id} className="ac-flex ac-justify-between" style={{ padding: "4px 0" }}>
                      <Link href={`/maintenance/inspections/${w.id}`} className="ac-mono ac-text-sm">{w.workOrderNumber}</Link>
                      {review ? <StatusBadge {...inspectorReviewStatusBadge(review.status)} /> : <span className="ac-text-sm ac-text-muted">—</span>}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Maintenance Workload</p>
            {byTechnician.size === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {Array.from(byTechnician.entries()).map(([id, count]) => (
                  <li key={id} className="ac-flex ac-justify-between" style={{ padding: "4px 0" }}>
                    <Link href={`/maintenance/technicians/${id}`} className="ac-text-sm">{getTechnicianById(id)?.name ?? id}</Link>
                    <span className="ac-text-sm ac-text-muted">{count} work order(s)</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      {/* 4. Upcoming Actions */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Upcoming Actions</h2>
        <div className="ac-grid-2">
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Upcoming Maintenance</p>
            {upcomingEvents.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {upcomingEvents.slice(0, 5).map((e) => (
                  <li key={e.id} className="ac-text-sm" style={{ padding: "4px 0" }}>{e.date} — {e.description}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Regulatory Deadlines</p>
            {regulatoryDeadlines.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {regulatoryDeadlines.map((e) => {
                  const req = getRequirementById(e.relatedRequirementId!);
                  return (
                    <li key={e.id} className="ac-text-sm" style={{ padding: "4px 0" }}>
                      {e.date} — {req ? <Link href={`/regulations/${req.id}`} className="ac-mono">{req.requirementNumber}</Link> : e.relatedRequirementId}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="ac-grid-2" style={{ marginTop: 16 }}>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Pending Inspections</p>
            {pendingInspections.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {pendingInspections.map((w) => (
                  <li key={w.id} className="ac-text-sm" style={{ padding: "4px 0" }}>
                    <Link href={`/maintenance/inspections/${w.id}`} className="ac-mono">{w.workOrderNumber}</Link> — {w.title}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Open Defects Requiring Attention</p>
            {seriousOpenDefs.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {seriousOpenDefs.map((d) => (
                  <li key={d.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "4px 0" }}>
                    <Link href="/maintenance/defects" className="ac-text-sm">{d.description}</Link>
                    <StatusBadge {...defectStatusBadge(d.status)} label={d.severity} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      {/* 5. Risk Overview */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Aircraft Risk Overview</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>Prototype analytics — non-authoritative.</p>
        <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "var(--ac-status-insufficient-bg)" }}>
          <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8 }}>
            <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", margin: 0 }}>Overall Risk / Health</p>
            <StatusBadge status={healthTone} label={analytics.complianceRisk} />
          </div>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>Main risk drivers:</p>
          <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
            {analytics.reasons.map((r, idx) => <li key={idx}>{r}</li>)}
          </ul>
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
            <strong>Highest-priority work order:</strong>{" "}
            {highestPriorityWo ? <Link href={`/maintenance/work-orders/${highestPriorityWo.id}`}>{highestPriorityWo.workOrderNumber} ({highestPriorityWo.priority})</Link> : "Insufficient source data."}
          </p>
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
            <strong>Parts risk:</strong> {partsAtRisk.length > 0 ? `${partsAtRisk.length} part(s) at risk` : "None identified."}
          </p>
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
            <strong>Compliance risk:</strong> {analytics.complianceRisk}
          </p>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            <strong>Inspection risk:</strong> {pendingInspections.length > 0 ? `${pendingInspections.length} inspection(s) pending review` : "None pending."}
          </p>
        </div>
      </section>

      {/* 6. AI Insight */}
      <section className="ac-section">
        <div className="ac-card" style={{ borderStyle: "dashed" }}>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>AI-Assisted Insight</p>
          <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
            {aiObservations.map((o, idx) => <li key={idx}>{o}</li>)}
          </ul>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>
            Source: work orders, defects, assessments, and inspector reviews for {registration}.
          </p>
          <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>
            AI-assisted analysis — non-authoritative. Verify against source records before operational decisions.
          </p>
        </div>
      </section>
    </div>
  );
}
