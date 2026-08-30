"use client";

import { useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { Timeline, type TimelineEntry } from "@/components/timeline/Timeline";
import { aircraft, getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { workOrdersForAircraft, isOverdue } from "@/lib/mock/workOrders";
import { findingsForWorkOrder } from "@/lib/mock/findings";
import { defectsForWorkOrder } from "@/lib/mock/defects";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { getInspectorReviewForWorkOrder } from "@/lib/mock/inspectorReviews";
import { getAssessmentById } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getRequirementById } from "@/lib/mock/regulations";
import { partsForWorkOrder } from "@/lib/mock/parts";
import { certificatesForPart } from "@/lib/mock/partTraceability";
import { maintenanceEventsForAircraft } from "@/lib/mock/maintenance";
import { answerQuestion } from "@/lib/mock/ai/engine";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { getUserById } from "@/lib/mock/roles";
import { getTechnicianById } from "@/lib/mock/technicians";

// M9 — Pilot Workflow Workspace. This is AeroComply's primary end-to-end
// customer demonstration surface: Aircraft -> Work Order -> Task -> Finding
// -> Evidence -> Inspection -> Sign-off -> Compliance -> Risk -> AI ->
// Audit, built entirely from existing mock helpers and the existing
// MroStateContext/AI engine/report engine. No new state system, AI engine,
// or approval system is created here — see M9.3/M9.4/M9.5 notes below.

type LinkState = "VERIFIED" | "MISSING" | "NOT_VERIFIED" | "UNKNOWN";

function linkBadge(state: LinkState): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (state) {
    case "VERIFIED": return { status: "COMPLIANT", label: "Verified" };
    case "MISSING": return { status: "NON_COMPLIANT", label: "Missing" };
    case "NOT_VERIFIED": return { status: "UNVERIFIED", label: "Not Verified" };
    default: return { status: "INSUFFICIENT_DATA", label: "Unknown" };
  }
}

// M9.7 — role-specific emphasis, reusing the existing RoleSimContext only
// (no second permission/role system). Determines which sections are called
// out first; every section still renders for every role.
const ROLE_FOCUS: Record<string, { title: string; sections: string[] }> = {
  "role-inspector": { title: "Chief Inspector focus", sections: ["Evidence Completeness", "Findings", "Regulatory Status", "Inspection Decision Gate"] },
  "role-maintenance-manager": { title: "Base Manager focus", sections: ["Turnaround Time", "Blockers", "Technician Capacity", "Parts"] },
  "role-technician": { title: "Line Technician focus", sections: ["Tasks", "Instructions", "Findings", "Evidence", "Sign-off"] },
  "role-compliance-manager": { title: "Quality Director focus", sections: ["Audit Readiness", "Risk", "Compliance", "Trends"] },
  "role-executive": { title: "Quality Director focus", sections: ["Audit Readiness", "Risk", "Compliance", "Trends"] },
};

export default function PilotWorkflowPage() {
  const { submissions } = useMroState();
  const { roleId } = useRoleSim();
  const [aircraftId, setAircraftId] = useState(aircraft[0]?.id ?? "");
  const ac = getAircraftById(aircraftId);
  const allWos = ac ? workOrdersForAircraft(ac.id) : [];
  const defaultWoId = (allWos.find((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED") ?? allWos[0])?.id ?? "";
  const [workOrderId, setWorkOrderId] = useState(defaultWoId);

  // If the aircraft changes, keep the work order selection in sync.
  const wo = allWos.find((w) => w.id === workOrderId) ?? (allWos.find((w) => w.id === defaultWoId));

  const findings = wo ? findingsForWorkOrder(wo.id) : [];
  const defects = wo ? defectsForWorkOrder(wo.id) : [];
  const checklist = wo ? getChecklistByWorkOrderId(wo.id) : undefined;
  const record = wo ? submissions[wo.id] : undefined;
  const inspectorReview = wo ? getInspectorReviewForWorkOrder(wo.id) : undefined;
  const assessment = wo?.relatedAssessmentId ? getAssessmentById(wo.relatedAssessmentId) : undefined;
  const requirement = wo?.relatedRequirementId ? getRequirementById(wo.relatedRequirementId) : undefined;
  const evidence = assessment ? evidenceForAssessment(assessment.id) : [];
  const woParts = wo ? partsForWorkOrder(wo.id) : [];
  const maintenanceEvents = ac ? maintenanceEventsForAircraft(ac.id) : [];
  const currentMaintenanceEvent = maintenanceEvents.find((e) => e.relatedRequirementId === wo?.relatedRequirementId) ?? maintenanceEvents[0];

  const criticalDefects = defects.filter((d) => d.status === "OPEN" && (d.severity === "HIGH" || d.severity === "CRITICAL"));

  // --- M9.1 Maintenance Event Timeline — every stamp is a real field or
  // "Insufficient source data.", never invented. Not wrapped in useMemo:
  // its inputs (findings/evidence/record) are freshly derived on every
  // render anyway, so memoizing would only add complexity with no benefit.
  const timeline: TimelineEntry[] = (() => {
    if (!wo) return [];
    const entries: TimelineEntry[] = [
      { id: "planned", date: wo.plannedStartDate, title: "Work Order Planned Start", detail: `${wo.workOrderNumber} — ${wo.title}` },
    ];
    if (wo.assignedTechnicianId) {
      const tech = getTechnicianById(wo.assignedTechnicianId);
      entries.push({ id: "assigned", date: "Insufficient source data.", title: "Task Assigned", detail: `Technician: ${tech?.name ?? wo.assignedTechnicianId} (assignment timestamp not tracked)` });
    }
    if (record?.submissionStatus) {
      entries.push({ id: "executed", date: record.submittedAt ?? "Insufficient source data.", title: "Task Executed / Checklist Submitted", detail: `Status: ${record.submissionStatus.replace(/_/g, " ")}` });
    }
    if (findings.length > 0) {
      entries.push({ id: "finding", date: "Insufficient source data.", title: "Finding Identified", detail: findings.map((f) => `[${f.severity}] ${f.description}`).join("; ") });
    }
    if (evidence.length > 0) {
      entries.push({ id: "evidence", date: evidence[0].uploadedOrReferencedAt, title: "Evidence Attached", detail: evidence.map((e) => e.sourceLabel).join("; ") });
    }
    if (record?.technicianSignOff) {
      entries.push({ id: "signoff", date: record.technicianSignOff.timestamp, title: "Technician Signed", detail: `Confirmed: ${record.technicianSignOff.confirmed ? "Yes" : "No"}`, accent: "highlight" });
    }
    if (record?.submissionStatus === "SUBMITTED") {
      entries.push({ id: "inspection_requested", date: record.submittedAt ?? "Insufficient source data.", title: "Inspection Requested", detail: record.inspectorId ? `Assigned inspector: ${getUserById(record.inspectorId)?.name ?? record.inspectorId}` : "Insufficient source data." });
    }
    if (inspectorReview || record?.inspectorReviewedAt) {
      entries.push({
        id: "inspector_review",
        date: inspectorReview?.reviewedAt ?? record?.inspectorReviewedAt ?? "Insufficient source data.",
        title: "Inspector Review",
        detail: `Status: ${(inspectorReview?.status ?? record?.inspectorDecisionStatus ?? "UNKNOWN").replace(/_/g, " ")}`,
        accent: "highlight",
      });
    }
    const finalStatus = wo.status === "COMPLETED" ? "CLOSED" : wo.status === "CANCELLED" ? "CANCELLED" : wo.status === "WAITING_PARTS" || wo.status === "WAITING_INSPECTION" ? "BLOCKED" : "OPEN";
    entries.push({ id: "final", date: wo.completionDate ?? "Insufficient source data.", title: `Compliance Decision — ${finalStatus}`, detail: `Current work order status: ${wo.status.replace(/_/g, " ")}` });
    return entries;
  })();

  // --- M9.2 Evidence Completeness matrix ---
  const evidenceMatrix: { link: string; state: LinkState; note: string }[] = wo
    ? [
        { link: "Work Order", state: "VERIFIED", note: wo.workOrderNumber },
        { link: "Task / Checklist", state: checklist ? "VERIFIED" : "MISSING", note: checklist ? checklist.title : "Insufficient source data." },
        { link: "Finding", state: findings.length > 0 ? "VERIFIED" : "UNKNOWN", note: findings.length > 0 ? `${findings.length} finding(s)` : "No findings recorded — not necessarily a gap." },
        { link: "Evidence", state: evidence.length > 0 ? (evidence.every((e) => e.verificationStatus === "VERIFIED") ? "VERIFIED" : "NOT_VERIFIED") : "MISSING", note: evidence.length > 0 ? evidence.map((e) => e.sourceLabel).join("; ") : "Insufficient source data." },
        { link: "Inspection", state: inspectorReview ? (inspectorReview.status === "APPROVED" ? "VERIFIED" : "NOT_VERIFIED") : "MISSING", note: inspectorReview ? inspectorReview.status.replace(/_/g, " ") : "Insufficient source data." },
        { link: "Sign-off", state: record?.technicianSignOff?.confirmed ? "VERIFIED" : "MISSING", note: record?.technicianSignOff ? `${record.technicianSignOff.timestamp}` : "Insufficient source data." },
      ]
    : [];

  // --- M9.3 Inspection Decision Gate — pure derivation from real state,
  // never assumed. UNKNOWN can never become READY; missing mandatory
  // evidence/sign-off/inspection or critical defects force BLOCKED.
  type GateState = "READY" | "BLOCKED" | "REQUIRES_REVIEW" | "UNKNOWN";
  const gate: GateState = !wo
    ? "UNKNOWN"
    : criticalDefects.length > 0
    ? "BLOCKED"
    : !record?.technicianSignOff?.confirmed
    ? "BLOCKED"
    : !inspectorReview
    ? "REQUIRES_REVIEW"
    : inspectorReview.status === "REJECTED"
    ? "BLOCKED"
    : inspectorReview.status === "APPROVED"
    ? "READY"
    : "REQUIRES_REVIEW";

  // --- M9.4 AI Decision Trace — reuses the SAME engine, no second one.
  const aiResponse = wo ? answerQuestion(`What should happen next for ${wo.workOrderNumber}?`, { aircraftId: ac?.id }) : undefined;

  const roleFocus = ROLE_FOCUS[roleId];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Pilot Workflow" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Pilot Workflow</h1>
          <p className="ac-subtitle">End-to-end demonstration: Aircraft → Work Order → Task → Finding → Evidence → Inspection → Compliance → Risk → AI → Audit. All values are drawn from current demo data.</p>
        </div>
      </div>

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="ac-flex ac-flex-col ac-gap-2">
            <span className="ac-text-sm ac-text-muted">Aircraft</span>
            <select className="ac-input" style={{ width: 200 }} value={aircraftId} onChange={(e) => { setAircraftId(e.target.value); const wos = workOrdersForAircraft(e.target.value); setWorkOrderId((wos.find((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED") ?? wos[0])?.id ?? ""); }}>
              {aircraft.map((a) => <option key={a.id} value={a.id}>{currentRegistration(a)}</option>)}
            </select>
          </label>
          <label className="ac-flex ac-flex-col ac-gap-2">
            <span className="ac-text-sm ac-text-muted">Work Order</span>
            <select className="ac-input" style={{ width: 240 }} value={workOrderId} onChange={(e) => setWorkOrderId(e.target.value)}>
              {allWos.length === 0 && <option value="">Insufficient source data.</option>}
              {allWos.map((w) => <option key={w.id} value={w.id}>{w.workOrderNumber} — {w.title}</option>)}
            </select>
          </label>
        </div>
      </div>

      {roleFocus && (
        <section className="ac-section">
          <div className="ac-card" style={{ borderStyle: "dashed" }}>
            <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{roleFocus.title} (Role Simulation)</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Prioritize: {roleFocus.sections.join(", ")}. Every section below still shows the full picture — switch roles from the sidebar to change this emphasis.</p>
          </div>
        </section>
      )}

      {!wo || !ac ? (
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No work order available for this aircraft.</p></div>
      ) : (
        <>
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>1–3. Aircraft, Maintenance Event, Work Order</h2>
            <div className="ac-kpi-grid">
              <Link href={`/aircraft/${ac.id}`} className="ac-kpi-card" style={{ display: "block" }}>
                <p className="ac-kpi-label">Aircraft</p>
                <p className="ac-kpi-value" style={{ fontSize: 18 }}>{currentRegistration(ac)}</p>
              </Link>
              <div className="ac-kpi-card">
                <p className="ac-kpi-label">Maintenance Event</p>
                <p className="ac-kpi-value" style={{ fontSize: 14 }}>{currentMaintenanceEvent ? `${currentMaintenanceEvent.date} — ${currentMaintenanceEvent.description}` : "Insufficient source data."}</p>
              </div>
              <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-kpi-card" style={{ display: "block" }}>
                <p className="ac-kpi-label">Work Order</p>
                <p className="ac-kpi-value" style={{ fontSize: 16 }}>{wo.workOrderNumber}</p>
              </Link>
              <div className="ac-kpi-card">
                <p className="ac-kpi-label">Status</p>
                <p className="ac-kpi-value" style={{ fontSize: 16 }}>{wo.status.replace(/_/g, " ")}{isOverdue(wo) && " (Overdue)"}</p>
              </div>
            </div>
          </section>

          <div className="ac-grid-2 ac-section">
            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>4–6. Tasks, Findings, Defects</h2>
              <div className="ac-card">
                <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>Checklist: {checklist ? checklist.title : "Insufficient source data."} ({checklist ? `${checklist.items.length} item(s)` : "0"})</p>
                <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>Findings: {findings.length === 0 ? "None recorded." : findings.map((f) => `[${f.severity}] ${f.description}`).join("; ")}</p>
                <p className="ac-text-sm" style={{ margin: 0 }}>
                  Open HIGH/CRITICAL defects: {criticalDefects.length === 0 ? "None." : <Link href="/maintenance/defects">{criticalDefects.map((d) => d.id).join(", ")}</Link>}
                </p>
              </div>
            </section>
            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance Event Timeline (M9.1)</h2>
              <div className="ac-card">
                <Timeline entries={timeline} />
              </div>
            </section>
          </div>

          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence Completeness (M9.2)</h2>
            <div className="ac-card" style={{ padding: 0 }}>
              <table className="ac-table">
                <thead><tr><th>Link</th><th>Status</th><th>Detail</th></tr></thead>
                <tbody>
                  {evidenceMatrix.map((row) => (
                    <tr key={row.link}>
                      <td>{row.link}</td>
                      <td><StatusBadge {...linkBadge(row.state)} /></td>
                      <td className="ac-text-sm ac-text-muted">{row.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>
              Requirement: {requirement ? <Link href={`/regulations/${requirement.id}`} className="ac-mono">{requirement.requirementNumber}</Link> : "Insufficient source data."}
            </p>
          </section>

          <div className="ac-grid-2 ac-section">
            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Inspection Decision Gate (M9.3)</h2>
              <div className="ac-card">
                <StatusBadge
                  status={gate === "READY" ? "COMPLIANT" : gate === "BLOCKED" ? "NON_COMPLIANT" : gate === "REQUIRES_REVIEW" ? "REVIEW_REQUIRED" : "INSUFFICIENT_DATA"}
                  label={gate.replace(/_/g, " ")}
                />
                <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 13 }}>
                  <li>Technician status: {record?.technicianSignOff?.confirmed ? "Signed" : "Not signed — Insufficient source data."}</li>
                  <li>Inspector status: {inspectorReview ? inspectorReview.status.replace(/_/g, " ") : "Insufficient source data."}</li>
                  <li>Evidence status: {evidence.length > 0 ? `${evidence.filter((e) => e.verificationStatus === "VERIFIED").length}/${evidence.length} verified` : "Insufficient source data."}</li>
                  <li>Findings status: {findings.length > 0 ? `${findings.length} recorded` : "None recorded"}</li>
                  <li>Compliance status: {assessment ? assessment.finalStatus.replace(/_/g, " ") : "Insufficient source data."}</li>
                </ul>
              </div>
            </section>

            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>AI Decision Trace (M9.4)</h2>
              <div className="ac-card">
                {aiResponse && (
                  <>
                    <p className="ac-text-sm" style={{ margin: "0 0 6px", fontWeight: 600 }}>{aiResponse.headline}</p>
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                      {aiResponse.narrative.map((line, i) => <li key={i}>{line}</li>)}
                    </ul>
                  </>
                )}
              </div>
            </section>
          </div>

          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Parts &amp; Certificates</h2>
            <div className="ac-card">
              {woParts.length === 0 ? (
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No parts linked to this work order.</p>
              ) : (
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                  {woParts.map((p) => {
                    const certs = certificatesForPart(p.id);
                    return (
                      <li key={p.id}>
                        <Link href={`/maintenance/parts/${p.id}`} className="ac-mono">{p.partNumber}</Link> — {p.status.replace(/_/g, " ")} — Certificate: {certs.length > 0 ? certs.map((c) => c.verificationStatus.replace(/_/g, " ")).join(", ") : "Insufficient source data."}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </section>

          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Executive Audit View (M9.5) &amp; One-Click Audit Journey (M9.6)</h2>
            <div className="ac-card">
              <div className="ac-kpi-grid" style={{ marginBottom: 12 }}>
                <div className="ac-kpi-card"><p className="ac-kpi-label">Compliance Status</p><p className="ac-kpi-value" style={{ fontSize: 15 }}>{assessment ? assessment.finalStatus.replace(/_/g, " ") : "Insufficient source data."}</p></div>
                <div className="ac-kpi-card"><p className="ac-kpi-label">Risk Level</p><p className="ac-kpi-value" style={{ fontSize: 15 }}>{criticalDefects.length > 0 ? "HIGH" : isOverdue(wo) ? "MEDIUM" : "LOW"}</p></div>
                <div className="ac-kpi-card"><p className="ac-kpi-label">Audit Readiness</p><p className="ac-kpi-value" style={{ fontSize: 15 }}>{gate === "READY" ? "Ready" : gate === "BLOCKED" ? "Blocked" : gate.replace(/_/g, " ")}</p></div>
              </div>
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-btn">1. Work Order</Link>
                <Link href="/maintenance/inspections" className="ac-btn">2. Inspection</Link>
                <Link href="/evidence" className="ac-btn">3. Evidence</Link>
                <Link href="/compliance" className="ac-btn">4. Compliance</Link>
                <Link href="/compliance/pre-audit" className="ac-btn ac-btn-primary">5. Generate Pre-Audit Dossier →</Link>
              </div>
              <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8, marginBottom: 0 }}>
                &ldquo;Generate Pre-Audit Dossier&rdquo; opens the existing Pre-Audit Dossier builder (same report engine used across Compliance) — select {currentRegistration(ac)} there to produce the full dossier for this aircraft.
              </p>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
