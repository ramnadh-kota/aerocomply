"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, projectStatusBadge, priorityBadge, workPackageStatusBadge, partStatusBadge, inspectorReviewStatusBadge, checklistResultBadge } from "@/components/status/StatusBadge";
import { getProjectById, workPackagesForProject } from "@/lib/mock/maintenanceProjects";
import { workOrders } from "@/lib/mock/workOrders";
import { getAircraftById, getAircraftVariant, getAircraftType, currentRegistration } from "@/lib/mock/aircraft";
import { getTechnicianById, technicians } from "@/lib/mock/technicians";
import { getPartById } from "@/lib/mock/parts";
import { defectsForAircraft } from "@/lib/mock/defects";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAssessmentById } from "@/lib/mock/assessments";
import { maintenanceEventsForAircraft } from "@/lib/mock/maintenance";
import { getProjectAnalytics, getPartsAtRisk } from "@/lib/mock/ai/analytics";
import { useMroState } from "@/lib/mro-state/MroStateContext";

export default function ProjectIntelligencePage({ params }: { params: { id: string } }) {
  const project = getProjectById(params.id);
  if (!project) notFound();
  const { submissions } = useMroState();

  const analytics = getProjectAnalytics(project.id);
  if (!analytics) notFound();

  const aircraft = getAircraftById(project.aircraftId)!;
  const variant = getAircraftVariant(aircraft.aircraftVariantId)!;
  const type = getAircraftType(variant.aircraftTypeId)!;
  const registration = currentRegistration(aircraft);
  const packages = workPackagesForProject(project.id);
  const orders = workOrders.filter((w) => w.projectId === project.id);
  const technicianIds = Array.from(new Set(orders.map((o) => o.assignedTechnicianId).filter((x): x is string => Boolean(x))));
  const projectDefects = defectsForAircraft(project.aircraftId).filter((d) => d.workOrderId && orders.some((o) => o.id === d.workOrderId));

  // Same live checklist/inspection state ChecklistPanel and InspectorReviewPanel
  // write to — see lib/mro-state/MroStateContext. Not a second state system.
  const records = orders.map((o) => submissions[o.id]).filter((r): r is NonNullable<typeof r> => Boolean(r));
  const allItems = records.flatMap((r) => Object.values(r.items));
  const recordedItems = allItems.filter((i) => i.result !== null).length;
  const checklistCompletionPercent = allItems.length > 0 ? Math.round((recordedItems / allItems.length) * 100) : null;
  const unknownItems = allItems.filter((i) => i.result === "UNKNOWN").length;
  const failedItems = allItems.filter((i) => i.result === "FAIL").length;

  const partIds = Array.from(new Set(orders.flatMap((o) => o.requiredPartIds)));
  const orderIdSet = new Set(orders.map((o) => o.id));
  const partsAtRisk = getPartsAtRisk().filter((p) => p.workOrderId && orderIdSet.has(p.workOrderId));

  const complianceRefs = orders.filter((o) => o.relatedRequirementId);
  const upcomingDeadlines = maintenanceEventsForAircraft(project.aircraftId).filter((e) => e.status !== "COMPLETED");

  const byTechnician = new Map<string, number>();
  for (const o of orders) {
    if (!o.assignedTechnicianId) continue;
    byTechnician.set(o.assignedTechnicianId, (byTechnician.get(o.assignedTechnicianId) ?? 0) + 1);
  }
  const overloadedTechnicianIds = Array.from(byTechnician.entries()).filter(([, count]) => count > 1).map(([id]) => id);

  const statusCounts = new Map<string, number>();
  for (const o of orders) statusCounts.set(o.status, (statusCounts.get(o.status) ?? 0) + 1);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Projects", href: "/maintenance/projects" },
          { label: project.title, href: `/maintenance/projects/${project.id}` },
          { label: "Intelligence" },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{project.title} — Project Intelligence</h1>
          <p className="ac-subtitle">
            <span className="ac-mono">{project.projectNumber}</span> · Prototype analytics — non-authoritative.
          </p>
        </div>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <Link href={`/maintenance/projects/${project.id}`} className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>← Back to Project</Link>
          <Link href={`/ai?project=${project.id}`} className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Ask AeroComply AI</Link>
          <Link href={`/reports/project-${project.id}`} className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Report</Link>
        </div>
      </div>

      {/* 1. Project Overview */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Project Overview</h2>
        <div className="ac-grid-3">
          <div className="ac-card">
            <p className="ac-kpi-label">Aircraft</p>
            <p style={{ fontWeight: 600, marginTop: 4 }}><Link href={`/aircraft/${aircraft.id}`}>{registration}</Link> · {type.manufacturer} {variant.modelDesignation}</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Maintenance Type</p>
            <p style={{ fontWeight: 600, marginTop: 4 }}>{project.projectType.replace(/_/g, " ")}</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Status / Priority</p>
            <div className="ac-flex ac-gap-2" style={{ marginTop: 4 }}>
              <StatusBadge {...projectStatusBadge(project.status)} />
              <StatusBadge {...priorityBadge(project.priority)} />
            </div>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Progress</p>
            <p className="ac-kpi-value">{project.progressPercent}%</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Due Date</p>
            <p style={{ fontWeight: 600, marginTop: 4 }}>{project.targetCompletionDate}</p>
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Assigned Technicians</p>
            {technicianIds.length === 0 ? (
              <p className="ac-text-sm ac-text-muted" style={{ marginTop: 4 }}>Insufficient source data.</p>
            ) : (
              <p style={{ marginTop: 4, fontSize: 13 }}>{technicianIds.map((id) => getTechnicianById(id)?.name).filter(Boolean).join(", ")}</p>
            )}
          </div>
        </div>
      </section>

      {/* 2. Operational KPIs */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Operational KPIs</h2>
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Work Orders</p>
            <p className="ac-kpi-value">{orders.length}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Completed</p>
            <p className="ac-kpi-value">{statusCounts.get("COMPLETED") ?? 0}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">In Progress</p>
            <p className="ac-kpi-value">{statusCounts.get("IN_PROGRESS") ?? 0}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Waiting Parts</p>
            <p className="ac-kpi-value">{statusCounts.get("WAITING_PARTS") ?? 0}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Waiting Inspection</p>
            <p className="ac-kpi-value">{statusCounts.get("WAITING_INSPECTION") ?? 0}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Open Defects</p>
            <p className="ac-kpi-value">{projectDefects.filter((d) => d.status === "OPEN").length}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Checklist Completion</p>
            <p className="ac-kpi-value">{checklistCompletionPercent === null ? "—" : `${checklistCompletionPercent}%`}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Inspection Status</p>
            <p className="ac-kpi-value">{records.filter((r) => r.inspectorDecisionStatus === "PENDING_INSPECTION").length} pending</p>
          </div>
        </div>
      </section>

      {/* 3. Resource Utilization */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Resource Utilization</h2>
        <div className="ac-grid-2">
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Technician Workload</p>
            {technicianIds.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <table className="ac-table">
                <thead><tr><th>Technician</th><th>Work Orders</th></tr></thead>
                <tbody>
                  {Array.from(byTechnician.entries()).map(([id, count]) => (
                    <tr key={id}>
                      <td><Link href={`/maintenance/technicians/${id}`}>{getTechnicianById(id)?.name ?? id}</Link></td>
                      <td>{count}{overloadedTechnicianIds.includes(id) && <span className="ac-text-sm ac-text-muted"> (overloaded)</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
              {technicianIds.length} of {technicians.length} fleet-wide technicians assigned to this project.
            </p>
          </div>

          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Parts</p>
            {partIds.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {partIds.map((id) => {
                  const p = getPartById(id);
                  if (!p) return null;
                  return (
                    <li key={id} className="ac-flex ac-justify-between" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)", fontSize: 13 }}>
                      <span className="ac-mono">{p.partNumber}</span>
                      <StatusBadge {...partStatusBadge(p.status)} />
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>{partsAtRisk.length} part(s) on this project currently at risk.</p>
          </div>
        </div>

        <div className="ac-grid-2" style={{ marginTop: 16 }}>
          {packages.map((wp) => (
            <div key={wp.id} className="ac-card">
              <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 4 }}>
                <p style={{ fontWeight: 600, margin: 0 }}>{wp.title}</p>
                <StatusBadge {...workPackageStatusBadge(wp.status)} />
              </div>
              <div className="ac-flex ac-items-center ac-gap-2">
                <div style={{ width: 100, height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
                  <div style={{ width: `${wp.completionPercent}%`, height: "100%", background: "var(--ac-accent)" }} />
                </div>
                <span className="ac-text-sm ac-text-muted">{wp.completionPercent}%</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 4. Compliance Intelligence */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Compliance Intelligence</h2>
        <div className="ac-grid-2">
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Requirements / Assessments</p>
            {complianceRefs.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {complianceRefs.map((o) => {
                  const req = getRequirementById(o.relatedRequirementId!);
                  const asmt = o.relatedAssessmentId ? getAssessmentById(o.relatedAssessmentId) : undefined;
                  return (
                    <li key={o.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                      <span className="ac-text-sm"><Link href={`/regulations/${req?.id}`} className="ac-mono">{req?.requirementNumber}</Link> via {o.workOrderNumber}</span>
                      {asmt ? <Link href={`/assessments/${asmt.id}`}><StatusBadge status={asmt.systemResult} /></Link> : <span className="ac-text-sm ac-text-muted">No assessment yet</span>}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Upcoming Deadlines</p>
            {upcomingDeadlines.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {upcomingDeadlines.slice(0, 5).map((e) => (
                  <li key={e.id} className="ac-text-sm" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                    {e.date} — {e.description}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="ac-grid-2" style={{ marginTop: 16 }}>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Checklist Exceptions</p>
            <div className="ac-flex ac-gap-2">
              <StatusBadge {...checklistResultBadge("UNKNOWN")} label={`${unknownItems} UNKNOWN`} />
              <StatusBadge {...checklistResultBadge("FAIL")} label={`${failedItems} FAILED`} />
            </div>
          </div>
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Inspection / Review Status</p>
            {records.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {orders.filter((o) => o.inspectorReviewId).map((o) => {
                  const r = submissions[o.id];
                  return (
                    <li key={o.id} className="ac-flex ac-justify-between" style={{ padding: "4px 0" }}>
                      <Link href={`/maintenance/inspections/${o.id}`} className="ac-mono ac-text-sm">{o.workOrderNumber}</Link>
                      {r ? <StatusBadge {...inspectorReviewStatusBadge(r.inspectorDecisionStatus)} /> : <span className="ac-text-sm ac-text-muted">—</span>}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </section>

      {/* 5. Risk Overview */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Risk Overview</h2>
        <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>Prototype analytics — non-authoritative.</p>
        <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "rgba(154,107,255,0.06)" }}>
          <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8 }}>
            <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", margin: 0 }}>Risk Level</p>
            <StatusBadge
              status={analytics.health === "CRITICAL" ? "NON_COMPLIANT" : analytics.health === "AT_RISK" ? "REVIEW_REQUIRED" : "COMPLIANT"}
              label={analytics.health.replace(/_/g, " ")}
            />
          </div>

          {analytics.risks.length === 0 ? (
            <p className="ac-text-sm ac-text-muted">No active risk drivers identified for this project.</p>
          ) : (
            <>
              <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>Main risk drivers / affected work orders:</p>
              <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
                {analytics.risks.map((r, idx) => (
                  <li key={idx}>
                    {r.href ? <Link href={r.href}>{r.label}</Link> : r.label} — <span className="ac-text-muted">{r.detail}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>Affected resources:</p>
          {overloadedTechnicianIds.length === 0 && partsAtRisk.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 10px" }}>No overloaded technicians or at-risk parts identified.</p>
          ) : (
            <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
              {overloadedTechnicianIds.map((id) => <li key={id}>{getTechnicianById(id)?.name} — multiple assigned work orders</li>)}
              {partsAtRisk.map((p) => <li key={p.partNumber}>{p.partNumber} — {p.status.replace(/_/g, " ")}</li>)}
            </ul>
          )}

          <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>
            {analytics.recommendedActions.length > 0 ? `Recommended: ${analytics.recommendedActions[0]}` : "No immediate action recommended."}
          </p>
        </div>
      </section>
    </div>
  );
}
