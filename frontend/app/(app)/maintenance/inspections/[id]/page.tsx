"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, defectStatusBadge, checklistResultBadge } from "@/components/status/StatusBadge";
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
import type { ChecklistItemResult } from "@/lib/mock/types";

const RESULT_OPTIONS: ChecklistItemResult[] = ["PASS", "FAIL", "NOT_APPLICABLE", "UNKNOWN"];

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

  // Technician execution summary shown to the inspector before a decision.
  // This is a review-time re-display of what the technician recorded — local
  // state only, seeded from findings (an item with a linked finding defaults
  // to FAIL) or PASS otherwise, never persisted. The inspector can correct it
  // here if their own review of the evidence disagrees (e.g. marking an item
  // UNKNOWN when required information turns out to be missing) — UNKNOWN is
  // never silently treated as PASS or FAIL.
  const [itemResults, setItemResults] = useState<Record<string, ChecklistItemResult>>(() => {
    if (!checklist) return {};
    return Object.fromEntries(
      checklist.items.map((item) => [item.id, findings.some((f) => f.checklistItemId === item.id) ? "FAIL" : "PASS"])
    );
  });

  const unknownItems = checklist ? checklist.items.filter((i) => itemResults[i.id] === "UNKNOWN") : [];
  const openCriticalDefects = defects.filter((d) => d.severity === "CRITICAL" && d.status === "OPEN");

  const blockPassReasons = useMemo(() => {
    const reasons: string[] = [];
    if (unknownItems.length > 0) {
      reasons.push(`${unknownItems.length} checklist item${unknownItems.length > 1 ? "s are" : " is"} marked UNKNOWN (${unknownItems.map((i) => i.label).join(", ")}) — unknown is never treated as pass.`);
    }
    if (openCriticalDefects.length > 0) {
      reasons.push(`${openCriticalDefects.length} unresolved CRITICAL defect${openCriticalDefects.length > 1 ? "s" : ""} exist on this work order.`);
    }
    return reasons;
  }, [unknownItems, openCriticalDefects]);

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
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Execution — Checklist Results</h2>
          <div className="ac-card">
            <p style={{ fontWeight: 600, margin: "0 0 6px" }}>{checklist.title}</p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 12px" }}>
              Required reference: {checklist.requiredReference} · Acceptance: {checklist.acceptanceCriteria}
            </p>
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {checklist.items.map((item) => (
                <li key={item.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                    <span className="ac-text-sm" style={{ fontWeight: 600 }}>{item.label}</span>
                    <StatusBadge {...checklistResultBadge(itemResults[item.id] ?? "UNKNOWN")} />
                  </div>
                  <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                    {RESULT_OPTIONS.map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        className="ac-btn"
                        style={itemResults[item.id] === opt ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined}
                        onClick={() => setItemResults((s) => ({ ...s, [item.id]: opt }))}
                      >
                        {opt.replace(/_/g, " ")}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>
              Full checklist definition and the technician&rsquo;s own sign-off flow are on the{" "}
              <Link href={`/maintenance/work-orders/${wo.id}`}>work order page</Link>. This is the inspector&rsquo;s
              review-time re-check — local state only, not persisted.
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
        <InspectorReviewPanel review={review} blockPassReasons={blockPassReasons} />
      </section>
    </div>
  );
}
