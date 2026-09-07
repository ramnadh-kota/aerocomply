"use client";

import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { ReportView } from "@/components/reports/ReportView";
import type { ReportData, ReportSection } from "@/lib/mock/reports";
import { aircraft, getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { workOrdersForAircraft, MOCK_TODAY, isOverdue } from "@/lib/mock/workOrders";
import { findingsForWorkOrder } from "@/lib/mock/findings";
import { defectsForAircraft } from "@/lib/mock/defects";
import { partsForAircraft } from "@/lib/mock/parts";
import { getInspectorReviewForWorkOrder } from "@/lib/mock/inspectorReviews";
import { assessmentsForAircraft } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { requirementLabel } from "@/lib/mock/ai/analytics";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";
import { getRequirementById } from "@/lib/mock/regulations";
import {
  receivingRecordForPart,
  certificatesForPart,
  installationsForPart,
  removalsForPart,
  traceabilityStatusForPart,
} from "@/lib/mock/partTraceability";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { AI_DEMO_DATA_FOOTER } from "@/lib/brand";

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

    // M7.5 — Parts Traceability, Certificate Evidence, Receiving, and
    // Installation/Removal History, using the same helpers as the parts
    // traceability workspace (no duplicate data or logic).
    const partsTraceability = parts.map((p) => `${p.partNumber} (${p.description}): traceability ${traceabilityStatusForPart(p.id).replace(/_/g, " ")}`);
    const receivingRecords = parts.map((p) => {
      const r = receivingRecordForPart(p.id);
      return r ? `${p.partNumber}: received ${r.receivedDate} from ${r.source} (qty ${r.quantityReceived})` : `${p.partNumber}: Insufficient source data — no receiving record.`;
    });
    const certificateEvidence = parts.flatMap((p) => {
      const certs = certificatesForPart(p.id);
      if (certs.length === 0) return [`${p.partNumber}: Insufficient source data — no certificate record.`];
      return certs.map((c) => `${p.partNumber}: ${c.certificateType.replace(/_/g, " ")} — ${c.verificationStatus.replace(/_/g, " ")}${c.certificateReference ? ` (${c.certificateReference})` : ""}`);
    });
    const installRemoveHistory = parts.flatMap((p) => {
      const installs = installationsForPart(p.id);
      const removes = removalsForPart(p.id);
      const lines = installs.map((i) => `${p.partNumber}: installed ${i.installationDate} on aircraft ${i.aircraftId}`);
      lines.push(...removes.map((r) => `${p.partNumber}: removed ${r.removalDate} — ${r.reason}`));
      return lines.length > 0 ? lines : [`${p.partNumber}: Insufficient source data — no installation/removal record.`];
    });

    // AD/SB linkage — every assessment against an AD/SB requirement for this aircraft.
    const adSbAssessments = assessments.filter((asmt) => {
      const req = getRequirementById(asmt.regulatoryRequirementId);
      return req?.requirementType === "AD" || req?.requirementType === "SB";
    });
    const adSbLinkage = adSbAssessments.length > 0
      ? adSbAssessments.map((asmt) => `${requirementLabel(asmt.regulatoryRequirementId)}: ${asmt.finalStatus.replace(/_/g, " ")}`)
      : ["Insufficient source data — no AD/SB assessments recorded for this aircraft."];

    // Audit Risk Concentration — ranked by explainable drivers only
    // (severity, recurrence, missing evidence, overdue work); never a
    // black-box score.
    const overdueWos = wos.filter((w) => isOverdue(w));
    const riskItems = [
      ...findings.map((f) => ({ label: `Finding: ${f.description}`, severity: f.severity === "CRITICAL" ? 4 : f.severity === "HIGH" ? 3 : f.severity === "MEDIUM" ? 2 : 1, reason: `Severity ${f.severity}` })),
      ...openGaps.map((asmt) => ({ label: `Open gap: ${requirementLabel(asmt.regulatoryRequirementId)}`, severity: asmt.finalStatus === "NON_COMPLIANT" ? 4 : asmt.finalStatus === "REVIEW_REQUIRED" ? 3 : 2, reason: `Status: ${asmt.finalStatus.replace(/_/g, " ")}` })),
      ...overdueWos.map((w) => ({ label: `Overdue work order: ${w.workOrderNumber}`, severity: 3, reason: `Due ${w.dueDate}, not completed` })),
      ...certificateEvidence.filter((c) => c.includes("MISSING") || c.includes("Insufficient source data")).map((c) => ({ label: c, severity: 2, reason: "Certificate evidence gap" })),
    ].sort((a, b) => b.severity - a.severity);
    const auditRiskConcentration = riskItems.length > 0
      ? riskItems.slice(0, 10).map((r) => `[Severity ${r.severity}] ${r.label} — ${r.reason}`)
      : ["No ranked risk items identified from current source data."];

    const sections: ReportSection[] = [
      { heading: "Executive Summary", body: [`Dossier for ${registration}, generated ${MOCK_TODAY}. Covers ${wos.length} work order(s), ${assessments.length} assessment(s), ${findings.length} finding(s), ${defects.length} defect(s).`] },
      { heading: "Work History", body: wos.length > 0 ? wos.map((w) => `${w.workOrderNumber}: ${w.title} — ${w.status.replace(/_/g, " ")} (due ${w.dueDate})`) : ["Insufficient source data."] },
      { heading: "Tasks / Findings", body: findings.length > 0 ? findings.map((f) => `[${f.severity}] ${f.description}${f.requiresDefect ? " (defect raised)" : ""}`) : ["Insufficient source data."] },
      { heading: "Inspections", body: inspections.length > 0 ? inspections : ["Insufficient source data."] },
      { heading: "Technician Sign-offs", body: signOffs.length > 0 ? signOffs : ["Insufficient source data."] },
      { heading: "Evidence", body: evidence.length > 0 ? evidence.map((e) => `${e.sourceLabel} (${e.verificationStatus})`) : ["Insufficient source data."] },
      { heading: "Parts", body: parts.length > 0 ? parts.map((p) => `${p.partNumber} — ${p.description} (${p.status.replace(/_/g, " ")})`) : ["Insufficient source data."] },
      { heading: "Parts Traceability", body: partsTraceability.length > 0 ? partsTraceability : ["Insufficient source data."] },
      { heading: "Receiving Records", body: receivingRecords },
      { heading: "Certificate Evidence", body: certificateEvidence },
      { heading: "Installation / Removal History", body: installRemoveHistory },
      { heading: "AD/SB Linkage", body: adSbLinkage },
      { heading: "Regulatory Mappings", body: assessments.length > 0 ? assessments.map((asmt) => `${requirementLabel(asmt.regulatoryRequirementId)}: ${asmt.finalStatus.replace(/_/g, " ")}`) : ["Insufficient source data."] },
      { heading: "Open Gaps", body: openGaps.length > 0 ? openGaps.map((asmt) => `${requirementLabel(asmt.regulatoryRequirementId)}: ${asmt.finalStatus.replace(/_/g, " ")}`) : ["No open compliance gaps identified."] },
      { heading: "Audit Risk Concentration", body: auditRiskConcentration },
      { heading: "UNKNOWN Items", body: unknownItems.length > 0 ? unknownItems : ["No UNKNOWN checklist items recorded."] },
      { heading: "Audit Events", body: auditEvents.length > 0 ? auditEvents.slice(0, 15).map((e) => `${e.timestamp}: ${e.action.replace(/_/g, " ")} — ${e.objectLabel} (${e.actor})`) : ["Insufficient source data."] },
      { heading: "AI-Generated Summary", body: [openGaps.length > 0 || unknownItems.length > 0 ? `This dossier contains ${openGaps.length} open compliance gap(s) and ${unknownItems.length} UNKNOWN item(s) requiring human review before use in an audit response.` : "No open gaps or UNKNOWN items were found for this aircraft in the current demo dataset.", AI_DEMO_DATA_FOOTER, "AI-assisted analysis — non-authoritative. Verify against source records before operational decisions."] },
    ];

    setDossier({
      id: `pre-audit-${a.id}`,
      title: `${registration} Pre-Audit Dossier`,
      type: "AUDIT_DOSSIER",
      scope: registration,
      generatedDate: MOCK_TODAY,
      generatedFrom: "Pre-Audit Dossier Builder",
      sourceModules: ["Work Orders", "Findings", "Defects", "Parts", "Parts Traceability", "Assessments", "Evidence", "Inspector Reviews", "Audit Trail"],
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
