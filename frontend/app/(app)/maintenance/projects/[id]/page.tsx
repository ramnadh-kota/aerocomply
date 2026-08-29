"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, projectStatusBadge, priorityBadge, defectStatusBadge, workOrderStatusBadge, partStatusBadge } from "@/components/status/StatusBadge";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { Timeline } from "@/components/timeline/Timeline";
import { getProjectById, workPackagesForProject } from "@/lib/mock/maintenanceProjects";
import { workOrdersForProject } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
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
  const registration = currentRegistration(aircraft);
  const packages = workPackagesForProject(project.id);
  const orders = workOrdersForProject(project.id);
  const technicianIds = Array.from(new Set(orders.map((o) => o.assignedTechnicianId).filter((x): x is string => Boolean(x))));
  const partIds = Array.from(new Set(orders.flatMap((o) => o.requiredPartIds)));
  const projectDefects = defectsForAircraft(project.aircraftId);
  const complianceRefs = orders.filter((o) => o.relatedRequirementId);
  const relatedAssessments = orders.map((o) => (o.relatedAssessmentId ? getAssessmentById(o.relatedAssessmentId) : undefined)).filter(Boolean);
  const relatedEvidence = relatedAssessments.flatMap((a) => evidenceForAssessment(a!.id));
  const auditEvents = auditEventsForObjectLabelContains(registration);

  const overdueCount = orders.filter((o) => o.status === "OVERDUE").length;
  const awaitingPartsCount = orders.filter((o) => o.status === "AWAITING_PARTS").length;
  const awaitingReviewComplianceCount = complianceRefs.filter((o) => o.status === "AWAITING_REVIEW").length;
  const scheduleRisk = overdueCount > 0 || awaitingPartsCount > 0;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Projects", href: "/maintenance/projects" }, { label: project.title }]} />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{project.title}</h1>
          <p className="ac-subtitle">
            <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{registration}</Link> · {project.projectType.replace(/_/g, " ")} · PM {project.projectManager}
          </p>
        </div>
        <StatusBadge {...projectStatusBadge(project.status)} />
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Progress</p>
          <p className="ac-kpi-value">{project.progressPercent}%</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Start Date</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{project.startDate}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Target Completion</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{project.targetCompletionDate}</p>
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
              {overdueCount > 0 && <li>{overdueCount} overdue task{overdueCount > 1 ? "s" : ""}</li>}
              {awaitingPartsCount > 0 && <li>{awaitingPartsCount} part{awaitingPartsCount > 1 ? "s" : ""} awaiting receipt</li>}
              {awaitingReviewComplianceCount > 0 && <li>{awaitingReviewComplianceCount} compliance review pending</li>}
            </ul>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Recommended action: Prioritize {orders.find((o) => o.status === "OVERDUE")?.workOrderNumber ?? "outstanding work orders"} and any pending compliance review.
            </p>
          </div>
        </section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Work Packages</h2>
        <div className="ac-grid-2">
          {packages.map((wp) => (
            <div key={wp.id} className="ac-card">
              <p style={{ fontWeight: 600, margin: "0 0 4px" }}>{wp.title}</p>
              <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>{wp.description}</p>
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
            <thead><tr><th>WO#</th><th>Title</th><th>Priority</th><th>Technician</th><th>Due</th><th>Status</th></tr></thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="ac-mono"><Link href={`/maintenance/work-orders/${o.id}`}>{o.workOrderNumber}</Link></td>
                  <td className="ac-text-sm"><Link href={`/maintenance/work-orders/${o.id}`}>{o.title}</Link></td>
                  <td><StatusBadge {...priorityBadge(o.priority)} /></td>
                  <td className="ac-text-sm">{o.assignedTechnicianId ? getTechnicianById(o.assignedTechnicianId)?.name : "Unassigned"}</td>
                  <td className="ac-mono ac-text-sm">{o.dueDate}</td>
                  <td><StatusBadge {...workOrderStatusBadge(o.status)} /></td>
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
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Parts Awaiting</h2>
          <div className="ac-card">
            {partIds.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No parts required.</p>}
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
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Defects</h2>
        <div className="ac-card">
          {projectDefects.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No defects reported for this aircraft.</p>}
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {projectDefects.map((d) => (
              <li key={d.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                <span className="ac-text-sm">{d.description}</span>
                <StatusBadge {...defectStatusBadge(d.status)} />
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
