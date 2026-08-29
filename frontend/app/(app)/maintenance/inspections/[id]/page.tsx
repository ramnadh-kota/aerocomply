"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, defectStatusBadge, checklistResultBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { InspectorReviewPanel } from "@/components/maintenance/InspectorReviewPanel";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAssessmentById } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { findingsForWorkOrder } from "@/lib/mock/findings";
import { defectsForWorkOrder } from "@/lib/mock/defects";
import { useChecklistRecord } from "@/lib/mro-state/MroStateContext";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";
import { Timeline } from "@/components/timeline/Timeline";

export default function InspectionDetailPage({ params }: { params: { id: string } }) {
  const wo = getWorkOrderById(params.id);
  if (!wo || !wo.inspectorReviewId) notFound();

  const record = useChecklistRecord(wo.id);
  const aircraft = getAircraftById(wo.aircraftId)!;
  const project = wo.projectId ? getProjectById(wo.projectId) : undefined;
  const technician = wo.assignedTechnicianId ? getTechnicianById(wo.assignedTechnicianId) : undefined;
  const requirement = wo.relatedRequirementId ? getRequirementById(wo.relatedRequirementId) : undefined;
  const assessment = wo.relatedAssessmentId ? getAssessmentById(wo.relatedAssessmentId) : undefined;
  const evidence = assessment ? evidenceForAssessment(assessment.id) : [];
  const checklist = getChecklistByWorkOrderId(wo.id);
  const findings = findingsForWorkOrder(wo.id);
  const defects = defectsForWorkOrder(wo.id);

  const unknownItems = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "UNKNOWN") : [];
  const openCriticalDefects = defects.filter((d) => d.severity === "CRITICAL" && d.status === "OPEN");
  const blockPassReasons: string[] = [];
  if (unknownItems.length > 0) {
    blockPassReasons.push(`${unknownItems.length} checklist item${unknownItems.length > 1 ? "s are" : " is"} marked UNKNOWN (${unknownItems.map((i) => i.label).join(", ")}) — unknown is never treated as pass.`);
  }
  if (openCriticalDefects.length > 0) {
    blockPassReasons.push(`${openCriticalDefects.length} unresolved CRITICAL defect${openCriticalDefects.length > 1 ? "s" : ""} exist on this work order.`);
  }

  const passCount = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "PASS").length : 0;
  const failCount = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "FAIL").length : 0;
  const naCount = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "NOT_APPLICABLE").length : 0;
  const unknownCount = unknownItems.length;

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
        <div className="ac-flex ac-gap-2">
          <StatusBadge {...priorityBadge(wo.priority)} />
          <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-btn">Open Work Order →</Link>
        </div>
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Technician</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{technician ? <Link href={`/maintenance/technicians/${technician.id}`}>{technician.name}</Link> : "Unassigned"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Submitted At</p>
          <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{record?.submittedAt ? new Date(record.submittedAt).toLocaleString() : "—"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Compliance Requirement</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {requirement ? <Link href={`/regulations/${requirement.id}`} className="ac-mono">{requirement.requirementNumber}</Link> : "None linked"}
          </p>
        </div>
      </div>

      {checklist && record && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Submission</h2>
          <div className="ac-card">
            <p style={{ fontWeight: 600, margin: "0 0 6px" }}>{checklist.title}</p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 12px" }}>
              Technician: {technician?.name ?? record.technicianId} · Status: {record.submissionStatus.replace(/_/g, " ")}
            </p>
            <div className="ac-flex ac-gap-6" style={{ flexWrap: "wrap", marginBottom: 14 }}>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("PASS")} label={`${passCount} Pass`} /></span>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("FAIL")} label={`${failCount} Fail`} /></span>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("NOT_APPLICABLE")} label={`${naCount} N/A`} /></span>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("UNKNOWN")} label={`${unknownCount} Unknown`} /></span>
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {checklist.items.map((item) => {
                const state = record.items[item.id];
                return (
                  <li key={item.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                    <div className="ac-flex ac-justify-between ac-items-center">
                      <span className="ac-text-sm">{item.label}</span>
                      <StatusBadge {...checklistResultBadge(state?.result ?? "UNKNOWN")} label={state?.result ? undefined : "Not yet attempted"} />
                    </div>
                    {state?.actualValue && <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>Measurement: {state.actualValue} {item.unit}</p>}
                    {state?.note && <p className="ac-text-sm ac-text-secondary" style={{ margin: "2px 0 0" }}>&ldquo;{state.note}&rdquo;</p>}
                    {state?.evidenceAttached && <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>Evidence attached ✓</p>}
                  </li>
                );
              })}
            </ul>
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>
              This is the technician&rsquo;s actual submission (shared state) — not a separate re-entered copy.
              Technician sign-off: {record.technicianSignOff ? `confirmed by ${record.technicianSignOff.technicianId} at ${new Date(record.technicianSignOff.timestamp).toLocaleString()}` : "not yet signed off"}.
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

      {record && record.inspectorDecisionStatus !== "PENDING_INSPECTION" && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Decision History</h2>
          <div className="ac-card">
            <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 6 }}>
              <StatusBadge {...inspectorReviewStatusBadge(record.inspectorDecisionStatus)} />
              <span className="ac-text-sm ac-text-muted">
                {record.inspectorReviewedAt ? new Date(record.inspectorReviewedAt).toLocaleString() : ""}
              </span>
            </div>
            {record.inspectorComments && <p className="ac-text-sm">{record.inspectorComments}</p>}
          </div>
        </section>
      )}

      <section className="ac-section">
        <InspectorReviewPanel workOrderId={wo.id} inspectorId={wo.inspectorId ?? ""} blockPassReasons={blockPassReasons} />
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Audit Timeline</h2>
        <div className="ac-card">
          {auditEventsForObjectLabelContains(wo.workOrderNumber).length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No audit events recorded yet for this inspection.</p>
          ) : (
            <Timeline
              entries={auditEventsForObjectLabelContains(wo.workOrderNumber).map((e) => ({
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
