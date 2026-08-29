"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, projectStatusBadge, priorityBadge, defectStatusBadge, workOrderStatusBadge, partStatusBadge, workPackageStatusBadge, overdueBadge } from "@/components/status/StatusBadge";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { Timeline } from "@/components/timeline/Timeline";
import { getProjectById, workPackagesForProject } from "@/lib/mock/maintenanceProjects";
import { workOrdersForProject, isOverdue } from "@/lib/mock/workOrders";
import { getAircraftById, getAircraftVariant, getAircraftType, currentRegistration } from "@/lib/mock/aircraft";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getPartById } from "@/lib/mock/parts";
import { defectsForAircraft } from "@/lib/mock/defects";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAssessmentById } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const project = getProjectById(params.id);
  if (!project) notFound();

  const aircraft = getAircraftById(project.aircraftId)!;
  const variant = getAircraftVariant(aircraft.aircraftVariantId)!;
  const type = getAircraftType(variant.aircraftTypeId)!;
  const registration = currentRegistration(aircraft);
  const packages = workPackagesForProject(project.id);
  const orders = workOrdersForProject(project.id);
  const technicianIds = Array.from(new Set(orders.map((o) => o.assignedTechnicianId).filter((x): x is string => Boolean(x))));
  const partIds = Array.from(new Set(orders.flatMap((o) => o.requiredPartIds)));
  const projectDefects = defectsForAircraft(project.aircraftId).filter((d) => d.workOrderId && orders.some((o) => o.id === d.workOrderId));
  const complianceRefs = orders.filter((o) => o.relatedRequirementId);
  const relatedAssessments = orders.map((o) => (o.relatedAssessmentId ? getAssessmentById(o.relatedAssessmentId) : undefined)).filter(Boolean);
  const relatedEvidence = relatedAssessments.flatMap((a) => evidenceForAssessment(a!.id));
  const auditEvents = auditEventsForObjectLabelContains(registration);
  const leadTechnician = project.leadTechnicianId ? getTechnicianById(project.leadTechnicianId) : undefined;

  const overdueOrders = orders.filter((o) => isOverdue(o));
  const awaitingPartsOrders = orders.filter((o) => o.status === "WAITING_PARTS");
  const awaitingReviewOrders = orders.filter((o) => o.status === "WAITING_INSPECTION");
  const scheduleRisk = overdueOrders.length > 0 || awaitingPartsOrders.length > 0 || project.riskNotes.length > 0;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Projects", href: "/maintenance/projects" }, { label: project.title }]} />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{project.title}</h1>
          <p className="ac-subtitle">
            <span className="ac-mono">{project.projectNumber}</span> ·{" "}
            <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{registration}</Link> · {type.manufacturer} {variant.modelDesignation} · PM {project.projectManager}
          </p>
        </div>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <StatusBadge {...priorityBadge(project.priority)} />
          <StatusBadge {...projectStatusBadge(project.status)} />
          <Link href={`/ai?project=${project.id}`} className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Ask AI</Link>
          <Link href={`/reports/project-${project.id}`} className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Generate Report</Link>
        </div>
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Progress</p>
          <p className="ac-kpi-value">{project.progressPercent}%</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Planned Start / Completion</p>
          <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>{project.startDate} → {project.targetCompletionDate}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Actual Start / Completion</p>
          <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>{project.actualStartDate ?? "Not started"} → {project.actualCompletionDate ?? "In progress"}</p>
        </div>
      </div>

      <div className="ac-grid-2 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Lead Technician</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{leadTechnician ? <Link href={`/maintenance/technicians/${leadTechnician.id}`}>{leadTechnician.name}</Link> : "Unassigned"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Project Type</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{project.projectType.replace(/_/g, " ")}</p>
        </div>
      </div>

      {scheduleRisk && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "rgba(154,107,255,0.06)" }}>
            <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 6 }}>AI Maintenance Insight — Prototype</p>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>
              {project.title} is currently {Math.max(1, 100 - project.progressPercent > 30 ? 8 : 4)}% behind the planned schedule.
            </p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "6px 0" }}>Potential contributors:</p>
            <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
              {overdueOrders.length > 0 && <li>{overdueOrders.length} overdue task{overdueOrders.length > 1 ? "s" : ""}</li>}
              {awaitingPartsOrders.length > 0 && <li>{awaitingPartsOrders.length} part{awaitingPartsOrders.length > 1 ? "s" : ""} awaiting receipt</li>}
              {awaitingReviewOrders.length > 0 && <li>{awaitingReviewOrders.length} compliance/task review pending</li>}
              {project.riskNotes.map((note, idx) => <li key={idx}>{note}</li>)}
            </ul>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Recommended action: Prioritize {overdueOrders[0]?.workOrderNumber ?? "outstanding work orders"} and any pending compliance review.
            </p>
          </div>
        </section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Packages</h2>
        <div className="ac-grid-2">
          {packages.map((wp) => (
            <div key={wp.id} className="ac-card">
              <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 4 }}>
                <p style={{ fontWeight: 600, margin: 0 }}>{wp.title} <span className="ac-text-muted ac-text-sm">ATA {wp.ataChapter}</span></p>
                <StatusBadge {...workPackageStatusBadge(wp.status)} />
              </div>
              <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 8px" }}>{wp.description}</p>
              <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 6 }}>
                <div style={{ width: 100, height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
                  <div style={{ width: `${wp.completionPercent}%`, height: "100%", background: "var(--ac-accent)" }} />
                </div>
                <span className="ac-text-sm ac-text-muted">{wp.completionPercent}% · due {wp.dueDate}</span>
              </div>
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                Technician: {wp.assignedTechnicianId ? getTechnicianById(wp.assignedTechnicianId)?.name : "Unassigned"} · Inspector: {wp.inspectorId ? getTechnicianById(wp.inspectorId)?.name : "Not yet assigned"}
                {wp.complianceReference && <> · Ref: <span className="ac-mono">{wp.complianceReference}</span></>}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-section-header">
          <h2 className="ac-h2">Work Orders</h2>
          <Link href="/maintenance/work-orders" className="ac-text-sm">View all →</Link>
        </div>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead><tr><th>WO#</th><th>Task</th><th>ATA</th><th>Priority</th><th>Technician</th><th>Due</th><th>Status</th></tr></thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="ac-mono"><Link href={`/maintenance/work-orders/${o.id}`}>{o.workOrderNumber}</Link></td>
                  <td className="ac-text-sm"><Link href={`/maintenance/work-orders/${o.id}`}>{o.title}</Link></td>
                  <td className="ac-mono ac-text-sm">{o.ataChapter}</td>
                  <td><StatusBadge {...priorityBadge(o.priority)} /></td>
                  <td className="ac-text-sm">{o.assignedTechnicianId ? getTechnicianById(o.assignedTechnicianId)?.name : "Unassigned"}</td>
                  <td className="ac-mono ac-text-sm">{o.dueDate}</td>
                  <td className="ac-flex ac-gap-2">
                    <StatusBadge {...workOrderStatusBadge(o.status)} />
                    {isOverdue(o) && <StatusBadge {...overdueBadge()} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Assigned Technicians</h2>
          <div className="ac-card">
            {technicianIds.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No technicians assigned yet.</p>}
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {technicianIds.map((id) => {
                const t = getTechnicianById(id)!;
                return (
                  <li key={id} style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                    <Link href={`/maintenance/technicians/${id}`} className="ac-flex ac-justify-between">
                      <span>{t.name}</span>
                      <span className="ac-text-sm ac-text-muted">{t.role}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Parts</h2>
          <div className="ac-card">
            {partIds.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No parts required.</p>}
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {partIds.map((id) => {
                const p = getPartById(id);
                if (!p) return null;
                return (
                  <li key={id} className="ac-flex ac-justify-between" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)", fontSize: 13 }}>
                    <span className="ac-mono">{p.partNumber}{p.serialNumber ? ` / ${p.serialNumber}` : ""}</span>
                    <StatusBadge {...partStatusBadge(p.status)} />
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Defects</h2>
        <div className="ac-card">
          {projectDefects.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No defects reported for this project&rsquo;s work orders.</p>}
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {projectDefects.map((d) => (
              <li key={d.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                <span className="ac-text-sm">ATA {d.ataChapter} — {d.description}</span>
                <div className="ac-flex ac-gap-2">
                  <StatusBadge {...priorityBadge(d.severity)} />
                  <StatusBadge {...defectStatusBadge(d.status)} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Compliance</h2>
        <div className="ac-card">
          {complianceRefs.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No linked regulatory requirements.</p>}
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {complianceRefs.map((o) => {
              const req = getRequirementById(o.relatedRequirementId!);
              const asmt = o.relatedAssessmentId ? getAssessmentById(o.relatedAssessmentId) : undefined;
              return (
                <li key={o.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <div className="ac-flex ac-justify-between ac-items-center">
                    <span className="ac-text-sm">
                      <Link href={`/regulations/${req?.id}`} className="ac-mono">{req?.requirementNumber}</Link> via {o.workOrderNumber}
                    </span>
                    {asmt ? (
                      <Link href={`/assessments/${asmt.id}`}>
                        <StatusBadge status={asmt.systemResult} />
                      </Link>
                    ) : (
                      <span className="ac-text-sm ac-text-muted">No assessment yet</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence</h2>
        {relatedEvidence.length === 0 && <p className="ac-text-sm ac-text-muted">No evidence linked yet.</p>}
        <div className="ac-grid-2">
          {relatedEvidence.map((e) => (
            <EvidenceCard key={e.id} evidence={e} />
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Activity / Audit</h2>
        <div className="ac-card">
          {auditEvents.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No audit events recorded yet.</p>
          ) : (
            <Timeline
              entries={auditEvents.slice(0, 8).map((e) => ({
                id: e.id,
                date: new Date(e.timestamp).toLocaleString(),
                title: e.action.replace(/_/g, " ").replace(/\./g, " — "),
                detail: `${e.actor} (${e.actorRole})`,
              }))}
            />
          )}
        </div>
      </section>
    </div>
  );
}
