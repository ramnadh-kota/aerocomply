"use client";

import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { ReportView } from "@/components/reports/ReportView";
import type { ReportData, ReportSection } from "@/lib/mock/reports";
import { aircraft, getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { workOrdersForAircraft, MOCK_TODAY } from "@/lib/mock/workOrders";
import { findingsForWorkOrder } from "@/lib/mock/findings";
import { defectsForAircraft } from "@/lib/mock/defects";
import { partsForAircraft } from "@/lib/mock/parts";
import { getInspectorReviewForWorkOrder } from "@/lib/mock/inspectorReviews";
import { assessmentsForAircraft } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { requirementLabel } from "@/lib/mock/ai/analytics";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";
import { useMroState } from "@/lib/mro-state/MroStateContext";

export default function PreAuditDossierPage() {
  const { submissions } = useMroState();
  const [aircraftId, setAircraftId] = useState(aircraft[0]?.id ?? "");
  const [dossier, setDossier] = useState<ReportData | null>(null);

  function generate() {
    const a = getAircraftById(aircraftId);
    if (!a) return;
    const registration = currentRegistration(a);
    const wos = workOrdersForAircraft(a.id);
    const findings = wos.flatMap((w) => findingsForWorkOrder(w.id));
    const defects = defectsForAircraft(a.id);
    const parts = partsForAircraft(a.id);
    const assessments = assessmentsForAircraft(a.id);
    const evidence = assessments.flatMap((asmt) => evidenceForAssessment(asmt.id));
    const auditEvents = auditEventsForObjectLabelContains(registration);

    const unknownItems: string[] = [];
    const signOffs: string[] = [];
    const inspections: string[] = [];
    for (const w of wos) {
      const record = submissions[w.id];
      if (record) {
        const unknown = Object.entries(record.items).filter(([, i]) => i.result === "UNKNOWN");
        for (const [itemId] of unknown) unknownItems.push(`${w.workOrderNumber} — item ${itemId}: UNKNOWN`);
        if (record.technicianSignOff) {
          signOffs.push(`${w.workOrderNumber}: signed off ${new Date(record.technicianSignOff.timestamp).toLocaleString()}`);
        } else {
          signOffs.push(`${w.workOrderNumber}: not yet signed off — Insufficient source data.`);
        }
      }
      const review = getInspectorReviewForWorkOrder(w.id);
      inspections.push(`${w.workOrderNumber}: ${review ? review.status.replace(/_/g, " ") : "no inspection record — Insufficient source data."}`);
    }

    const openGaps = assessments.filter((asmt) => asmt.finalStatus === "NON_COMPLIANT" || asmt.finalStatus === "REVIEW_REQUIRED" || asmt.finalStatus === "INSUFFICIENT_DATA");

    const sections: ReportSection[] = [
      { heading: "Executive Summary", body: [`Dossier for ${registration}, generated ${MOCK_TODAY}. Covers ${wos.length} work order(s), ${assessments.length} assessment(s), ${findings.length} finding(s), ${defects.length} defect(s).`] },
      { heading: "Work History", body: wos.length > 0 ? wos.map((w) => `${w.workOrderNumber}: ${w.title} — ${w.status.replace(/_/g, " ")} (due ${w.dueDate})`) : ["Insufficient source data."] },
      { heading: "Tasks / Findings", body: findings.length > 0 ? findings.map((f) => `[${f.severity}] ${f.description}${f.requiresDefect ? " (defect raised)" : ""}`) : ["Insufficient source data."] },
      { heading: "Inspections", body: inspections.length > 0 ? inspections : ["Insufficient source data."] },
      { heading: "Technician Sign-offs", body: signOffs.length > 0 ? signOffs : ["Insufficient source data."] },
      { heading: "Evidence", body: evidence.length > 0 ? evidence.map((e) => `${e.sourceLabel} (${e.verificationStatus})`) : ["Insufficient source data."] },
      { heading: "Parts", body: parts.length > 0 ? parts.map((p) => `${p.partNumber} — ${p.description} (${p.status.replace(/_/g, " ")})`) : ["Insufficient source data."] },
      { heading: "Regulatory Mappings", body: assessments.length > 0 ? assessments.map((asmt) => `${requirementLabel(asmt.regulatoryRequirementId)}: ${asmt.finalStatus.replace(/_/g, " ")}`) : ["Insufficient source data."] },
      { heading: "Open Gaps", body: openGaps.length > 0 ? openGaps.map((asmt) => `${requirementLabel(asmt.regulatoryRequirementId)}: ${asmt.finalStatus.replace(/_/g, " ")}`) : ["No open compliance gaps identified."] },
      { heading: "UNKNOWN Items", body: unknownItems.length > 0 ? unknownItems : ["No UNKNOWN checklist items recorded."] },
      { heading: "Audit Events", body: auditEvents.length > 0 ? auditEvents.slice(0, 15).map((e) => `${e.timestamp}: ${e.action.replace(/_/g, " ")} — ${e.objectLabel} (${e.actor})`) : ["Insufficient source data."] },
      { heading: "AI-Generated Summary", body: [openGaps.length > 0 || unknownItems.length > 0 ? `This dossier contains ${openGaps.length} open compliance gap(s) and ${unknownItems.length} UNKNOWN item(s) requiring human review before use in an audit response.` : "No open gaps or UNKNOWN items were found for this aircraft in the current demo dataset.", "AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required.", "AI-assisted analysis — non-authoritative. Verify against source records before operational decisions."] },
    ];

    setDossier({
      id: `pre-audit-${a.id}`,
      title: `${registration} Pre-Audit Dossier`,
      type: "AUDIT_DOSSIER",
      scope: registration,
      generatedDate: MOCK_TODAY,
      generatedFrom: "Pre-Audit Dossier Builder",
      sourceModules: ["Work Orders", "Findings", "Defects", "Parts", "Assessments", "Evidence", "Inspector Reviews", "Audit Trail"],
      aiSummary: sections[sections.length - 1].body,
      sections,
    });
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compliance", href: "/compliance" }, { label: "Pre-Audit Dossier" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Pre-Audit Dossier</h1>
          <p className="ac-subtitle">Generate a structured, traceable audit dossier for a single aircraft from current demo data. No evidence is invented.</p>
        </div>
      </div>

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="ac-flex ac-flex-col ac-gap-2">
            <span className="ac-text-sm ac-text-muted">Aircraft</span>
            <select className="ac-input" style={{ width: 220 }} value={aircraftId} onChange={(e) => setAircraftId(e.target.value)}>
              {aircraft.map((a) => (
                <option key={a.id} value={a.id}>{currentRegistration(a)}</option>
              ))}
            </select>
          </label>
          <button className="ac-btn ac-btn-primary" onClick={generate}>Generate Dossier</button>
        </div>
      </div>

      {dossier ? (
        <ReportView report={dossier} />
      ) : (
        <p className="ac-text-sm ac-text-muted">Select an aircraft and click Generate Dossier.</p>
      )}
    </div>
  );
}
