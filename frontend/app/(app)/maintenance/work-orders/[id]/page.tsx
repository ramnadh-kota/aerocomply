"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, workOrderStatusBadge, priorityBadge, partStatusBadge } from "@/components/status/StatusBadge";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { ChecklistPanel } from "@/components/maintenance/ChecklistPanel";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById, getWorkPackageById } from "@/lib/mock/maintenanceProjects";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getPartById } from "@/lib/mock/parts";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAssessmentById } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";
import { Timeline } from "@/components/timeline/Timeline";

export default function WorkOrderDetailPage({ params }: { params: { id: string } }) {
  const wo = getWorkOrderById(params.id);
  if (!wo) notFound();

  const aircraft = getAircraftById(wo.aircraftId)!;
  const registration = currentRegistration(aircraft);
  const project = wo.projectId ? getProjectById(wo.projectId) : undefined;
  const workPackage = wo.workPackageId ? getWorkPackageById(wo.workPackageId) : undefined;
  const technician = wo.assignedTechnicianId ? getTechnicianById(wo.assignedTechnicianId) : undefined;
  const requirement = wo.relatedRequirementId ? getRequirementById(wo.relatedRequirementId) : undefined;
  const assessment = wo.relatedAssessmentId ? getAssessmentById(wo.relatedAssessmentId) : undefined;
  const evidence = assessment ? evidenceForAssessment(assessment.id) : [];
  const checklist = getChecklistByWorkOrderId(wo.id);
  const auditEvents = auditEventsForObjectLabelContains(wo.workOrderNumber);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Work Orders", href: "/maintenance/work-orders" },
          { label: wo.workOrderNumber },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{wo.workOrderNumber}</h1>
          <p className="ac-subtitle">{wo.title}</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <StatusBadge {...priorityBadge(wo.priority)} />
          <StatusBadge {...workOrderStatusBadge(wo.status)} />
        </div>
      </div>

      {(requirement || assessment) && (
        <div className="ac-card ac-section" style={{ background: "var(--ac-accent-muted)", border: "1px solid var(--ac-accent)" }}>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Compliance Chain</p>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{registration}</Link>
            {project && <> → <Link href={`/maintenance/projects/${project.id}`} className="ac-mono">{project.title}</Link></>}
            {" → "}
            <span className="ac-mono">{wo.workOrderNumber}</span>
            {technician && <> → {technician.name}</>}
            {requirement && <> → <Link href={`/regulations/${requirement.id}`} className="ac-mono">{requirement.requirementNumber}</Link></>}
            {assessment && <> → <Link href={`/assessments/${assessment.id}`} className="ac-mono">Assessment</Link> → Human Review → Audit Trail</>}
          </p>
        </div>
      )}

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Aircraft</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}><Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{registration}</Link></p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Project / Work Package</p>
          <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>
            {project ? <Link href={`/maintenance/projects/${project.id}`}>{project.title}</Link> : "Ad hoc (no project)"}
            {workPackage && <> · {workPackage.title}</>}
          </p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Due Date</p>
          <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{wo.dueDate}</p>
        </div>
      </div>

      <div className="ac-grid-2 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Assigned Technician</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {technician ? <Link href={`/maintenance/technicians/${technician.id}`}>{technician.name} ({technician.role})</Link> : "Unassigned"}
          </p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Required Tools</p>
          <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>{wo.requiredTools.length > 0 ? wo.requiredTools.join(", ") : "None"}</p>
        </div>
      </div>

      {wo.requiredPartIds.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Required Parts</h2>
          <div className="ac-card">
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {wo.requiredPartIds.map((id) => {
                const p = getPartById(id);
                if (!p) return null;
                return (
                  <li key={id} className="ac-flex ac-justify-between" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)", fontSize: 13 }}>
                    <span className="ac-mono">{p.partNumber} — {p.description}</span>
                    <StatusBadge {...partStatusBadge(p.status)} />
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      )}

      {checklist && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Task Checklist</h2>
          <ChecklistPanel checklist={checklist} />
        </section>
      )}

      {evidence.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence</h2>
          <div className="ac-grid-2">
            {evidence.map((e) => (
              <EvidenceCard key={e.id} evidence={e} />
            ))}
          </div>
        </section>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Activity History</h2>
        <div className="ac-card">
          {auditEvents.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No audit events recorded yet for this work order.</p>
          ) : (
            <Timeline
              entries={auditEvents.map((e) => ({
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
