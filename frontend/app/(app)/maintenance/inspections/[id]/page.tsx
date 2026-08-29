"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, defectStatusBadge } from "@/components/status/StatusBadge";
import { InspectorReviewPanel } from "@/components/maintenance/InspectorReviewPanel";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getInspectorReviewById } from "@/lib/mock/inspectorReviews";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAssessmentById } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { findingsForWorkOrder } from "@/lib/mock/findings";
import { defectsForWorkOrder } from "@/lib/mock/defects";

export default function InspectionDetailPage({ params }: { params: { id: string } }) {
  const wo = getWorkOrderById(params.id);
  if (!wo || !wo.inspectorReviewId) notFound();

  const review = getInspectorReviewById(wo.inspectorReviewId)!;
  const aircraft = getAircraftById(wo.aircraftId)!;
  const project = wo.projectId ? getProjectById(wo.projectId) : undefined;
  const technician = wo.assignedTechnicianId ? getTechnicianById(wo.assignedTechnicianId) : undefined;
  const requirement = wo.relatedRequirementId ? getRequirementById(wo.relatedRequirementId) : undefined;
  const assessment = wo.relatedAssessmentId ? getAssessmentById(wo.relatedAssessmentId) : undefined;
  const evidence = assessment ? evidenceForAssessment(assessment.id) : [];
  const checklist = getChecklistByWorkOrderId(wo.id);
  const findings = findingsForWorkOrder(wo.id);
  const defects = defectsForWorkOrder(wo.id);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Inspection Queue", href: "/maintenance/inspections" },
          { label: wo.workOrderNumber },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{wo.workOrderNumber} — Inspection</h1>
          <p className="ac-subtitle">
            {wo.title} · <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{currentRegistration(aircraft)}</Link>
            {project && <> · <Link href={`/maintenance/projects/${project.id}`}>{project.projectNumber}</Link></>}
          </p>
        </div>
        <StatusBadge {...priorityBadge(wo.priority)} />
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Technician</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{technician ? <Link href={`/maintenance/technicians/${technician.id}`}>{technician.name}</Link> : "Unassigned"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Submitted At</p>
          <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{wo.signOff ? new Date(wo.signOff.timestamp).toLocaleString() : "—"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Compliance Requirement</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {requirement ? <Link href={`/regulations/${requirement.id}`} className="ac-mono">{requirement.requirementNumber}</Link> : "None linked"}
          </p>
        </div>
      </div>

      {checklist && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Checklist Reference</h2>
          <div className="ac-card">
            <p style={{ fontWeight: 600, margin: "0 0 6px" }}>{checklist.title}</p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>
              Required reference: {checklist.requiredReference} · Acceptance: {checklist.acceptanceCriteria}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
              Full item-by-item checklist and sign-off are on the <Link href={`/maintenance/work-orders/${wo.id}`}>work order page</Link>.
            </p>
          </div>
        </section>
      )}

      {findings.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Findings</h2>
          <div className="ac-card">
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {findings.map((f) => (
                <li key={f.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <span className="ac-text-sm">{f.description}</span>
                  <StatusBadge {...priorityBadge(f.severity)} />
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {defects.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Defect Count: {defects.length}</h2>
          <div className="ac-card">
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {defects.map((d) => (
                <li key={d.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <span className="ac-text-sm">ATA {d.ataChapter} — {d.description}</span>
                  <StatusBadge {...defectStatusBadge(d.status)} />
                </li>
              ))}
            </ul>
          </div>
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
        <InspectorReviewPanel review={review} />
      </section>
    </div>
  );
}
