// Mock report history + report content builder. Reports are generated
// client-side from the same analytics builders the AI assistant uses
// (lib/mock/ai/analytics.ts), so a number in a report always matches the
// number an AI answer gave for the same scope. Nothing here is persisted to
// a backend — "generated" reports are prototype records only.

import { getProjectAnalytics, getAircraftAnalytics, getFleetAnalytics, getInspectionAnalytics, getComplianceAnalytics, getMaintenanceAnalytics, requirementLabel } from "./ai/analytics";
import { getProjectById, workPackagesForProject } from "./maintenanceProjects";
import { getAircraftById } from "./aircraft";
import { workOrdersForProject, workOrdersForAircraft, MOCK_TODAY } from "./workOrders";
import { technicians } from "./technicians";
import { partsForWorkOrder } from "./parts";
import { defectsForAircraft } from "./defects";
import { findingsForWorkOrder } from "./findings";
import { getInspectorReviewForWorkOrder } from "./inspectorReviews";
import { evidenceForAssessment } from "./evidence";
import { assessmentsForAircraft } from "./assessments";
import { auditEventsForObjectLabelContains } from "./audit";

export type ReportType = "PROJECT" | "AIRCRAFT" | "FLEET_RISK" | "INSPECTION_QUEUE" | "COMPLIANCE_WEEKLY";

export interface ReportRecord {
  id: string;
  title: string;
  type: ReportType;
  generatedBy: string;
  scope: string;
  generatedDate: string;
  status: "READY" | "GENERATING";
}

export const reportHistory: ReportRecord[] = [
  { id: "project-proj-1", title: "Project PRJ-2026-001 Monthly Operations Report", type: "PROJECT", generatedBy: "Ananya Rao", scope: "VT-ABC — C-Check", generatedDate: "2026-03-16", status: "READY" },
  { id: "aircraft-ac-3", title: "N412MX Compliance Exposure Report", type: "AIRCRAFT", generatedBy: "Elena Petrov", scope: "N412MX", generatedDate: "2026-03-15", status: "READY" },
  { id: "fleet-risk", title: "Fleet Maintenance Risk Report", type: "FLEET_RISK", generatedBy: "Wei Zhang", scope: "Fleet-wide", generatedDate: "2026-03-14", status: "READY" },
  { id: "inspection-queue", title: "Inspection Queue Summary", type: "INSPECTION_QUEUE", generatedBy: "Diego Alvarez", scope: "Open inspections", generatedDate: "2026-03-17", status: "READY" },
  { id: "compliance-weekly", title: "Weekly Compliance Report", type: "COMPLIANCE_WEEKLY", generatedBy: "Priya Nair", scope: "Organization-wide", generatedDate: "2026-03-10", status: "READY" },
];

export function getReportRecord(id: string): ReportRecord | undefined {
  return reportHistory.find((r) => r.id === id);
}

function parseReportId(id: string): { type: ReportType; scopeId: string } | null {
  if (id.startsWith("project-")) return { type: "PROJECT", scopeId: id.slice("project-".length) };
  if (id.startsWith("aircraft-")) return { type: "AIRCRAFT", scopeId: id.slice("aircraft-".length) };
  if (id === "fleet-risk") return { type: "FLEET_RISK", scopeId: "" };
  if (id === "inspection-queue") return { type: "INSPECTION_QUEUE", scopeId: "" };
  if (id === "compliance-weekly") return { type: "COMPLIANCE_WEEKLY", scopeId: "" };
  return null;
}

export interface ReportSection {
  heading: string;
  body: string[];
  kpis?: { label: string; value: string; tone?: string }[];
  bars?: { label: string; percent: number }[];
  distribution?: { label: string; count: number }[];
  table?: { columns: string[]; rows: (string | number)[][] };
  chain?: string[];
}

export interface ReportData {
  id: string;
  title: string;
  type: ReportType;
  scope: string;
  generatedDate: string;
  aiSummary: string[];
  sections: ReportSection[];
}

export function buildReportData(id: string): ReportData | null {
  const parsed = parseReportId(id);
  if (!parsed) return null;
  const record = getReportRecord(id);
  const generatedDate = record?.generatedDate ?? MOCK_TODAY;

  if (parsed.type === "PROJECT") {
    const project = getProjectById(parsed.scopeId);
    const analytics = getProjectAnalytics(parsed.scopeId);
    if (!project || !analytics) return null;
    const wos = workOrdersForProject(project.id);
    const wps = workPackagesForProject(project.id);

    const sections: ReportSection[] = [
      { heading: "Executive Summary", body: [`Overall health: ${analytics.health.replace(/_/g, " ")}.`, `Compliance exposure: ${analytics.complianceExposure}.`], kpis: analytics.kpis },
      { heading: "Project Overview", body: [`${project.projectNumber} — ${project.title}`, `Type: ${project.projectType.replace(/_/g, " ")} · Priority: ${project.priority} · Manager: ${project.projectManager}`, `Planned: ${project.startDate} → ${project.targetCompletionDate}`] },
      { heading: "Aircraft", body: [`${analytics.aircraftRegistration} (${project.aircraftId})`] },
      { heading: "Work Package Progress", body: [], bars: wps.map((wp) => ({ label: wp.title, percent: wp.completionPercent })) },
      { heading: "Work Order Status", body: [], distribution: analytics.workOrderStatusDistribution },
      {
        heading: "Technician Utilization",
        body: [],
        table: {
          columns: ["Technician", "Assigned Work Orders"],
          rows: technicians
            .map((t) => [t.name, wos.filter((w) => w.assignedTechnicianId === t.id).length] as [string, number])
            .filter(([, n]) => (n as number) > 0),
        },
      },
      {
        heading: "Parts Availability",
        body: [],
        table: { columns: ["Part", "Status", "Work Order"], rows: wos.flatMap((w) => partsForWorkOrder(w.id).map((p) => [p.partNumber, p.status.replace(/_/g, " "), w.workOrderNumber])) },
      },
      {
        heading: "Defects",
        body: [],
        table: { columns: ["Defect", "Severity", "Status"], rows: defectsForAircraft(project.aircraftId).map((d) => [d.description, d.severity, d.status]) },
      },
      {
        heading: "Inspection Status",
        body: wos.filter((w) => w.inspectorReviewId).map((w) => {
          const r = getInspectorReviewForWorkOrder(w.id);
          return `${w.workOrderNumber}: ${r ? r.status.replace(/_/g, " ") : "no review"}`;
        }),
      },
      { heading: "Compliance Exposure", body: [`Exposure level: ${analytics.complianceExposure}`], chain: ["Requirement", "Work Order", "Assessment", "Evidence"] },
      {
        heading: "Evidence",
        body: [],
        table: { columns: ["Work Order", "Findings"], rows: wos.map((w) => [w.workOrderNumber, findingsForWorkOrder(w.id).length]) },
      },
      { heading: "Risk Analysis", body: analytics.risks.map((r) => `[${r.level}] ${r.label} — ${r.detail}`) },
      { heading: "Recommended Actions", body: analytics.recommendedActions },
      {
        heading: "Audit / Traceability",
        body: auditEventsForObjectLabelContains(project.aircraftId.toUpperCase()).slice(0, 5).map((e) => `${e.timestamp}: ${e.action.replace(/_/g, " ")} — ${e.objectLabel}`),
      },
      {
        heading: "AI-Generated Summary",
        body: [
          `${project.projectNumber} is ${analytics.health.replace(/_/g, " ").toLowerCase()} with ${analytics.risks.length} identified risk item(s) and ${analytics.complianceExposure.toLowerCase()} compliance exposure.`,
          "AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required.",
        ],
      },
    ];

    return { id, title: `${project.projectNumber} Operations Report`, type: parsed.type, scope: `${project.title}`, generatedDate, aiSummary: sections[sections.length - 1].body, sections };
  }

  if (parsed.type === "AIRCRAFT") {
    const a = getAircraftById(parsed.scopeId);
    const analytics = getAircraftAnalytics(parsed.scopeId);
    if (!a || !analytics) return null;
    const wos = workOrdersForAircraft(a.id);
    const assessments = assessmentsForAircraft(a.id);
    const sections: ReportSection[] = [
      { heading: "Executive Summary", body: [`Compliance risk: ${analytics.complianceRisk}.`], kpis: analytics.kpis },
      { heading: "Aircraft", body: [`${analytics.registration} (${a.id}) · Status: ${a.status}`] },
      { heading: "Work Orders", body: [], table: { columns: ["Work Order", "Status", "Priority"], rows: wos.map((w) => [w.workOrderNumber, w.status.replace(/_/g, " "), w.priority]) } },
      { heading: "Defects", body: [], table: { columns: ["Defect", "Severity", "Status"], rows: defectsForAircraft(a.id).map((d) => [d.description, d.severity, d.status]) } },
      {
        heading: "Compliance Exposure",
        body: assessments.map((asmt) => `${requirementLabel(asmt.regulatoryRequirementId)}: ${asmt.finalStatus.replace(/_/g, " ")}`),
        chain: ["Requirement", "Assessment", "Evidence"],
      },
      { heading: "Evidence", body: assessments.flatMap((asmt) => evidenceForAssessment(asmt.id)).map((e) => e.sourceLabel) },
      { heading: "Risk Analysis", body: analytics.reasons },
      { heading: "Recommended Actions", body: analytics.complianceRisk !== "LOW" ? ["Review open defects and non-compliant/review-required assessments before next dispatch."] : ["No immediate action required."] },
      { heading: "Audit / Traceability", body: auditEventsForObjectLabelContains(analytics.registration).slice(0, 5).map((e) => `${e.timestamp}: ${e.action.replace(/_/g, " ")}`) },
      { heading: "AI-Generated Summary", body: [`${analytics.registration} shows ${analytics.complianceRisk.toLowerCase()} compliance risk. ${analytics.reasons[0] ?? ""}`, "AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required."] },
    ];
    return { id, title: `${analytics.registration} Compliance Exposure Report`, type: parsed.type, scope: analytics.registration, generatedDate, aiSummary: sections[sections.length - 1].body, sections };
  }

  if (parsed.type === "FLEET_RISK") {
    const f = getFleetAnalytics();
    const sections: ReportSection[] = [
      { heading: "Executive Summary", body: [`${f.aircraftAtRisk.length} of ${f.fleetSize} aircraft show elevated risk.`], kpis: f.kpis },
      { heading: "Aircraft At Risk", body: [], table: { columns: ["Aircraft", "Risk"], rows: f.aircraftAtRisk.map((a) => [a.registration, a.risk]) } },
      { heading: "Risk Analysis", body: f.aircraftAtRisk.map((a) => `${a.registration}: ${a.risk} risk`) },
      { heading: "Recommended Actions", body: f.aircraftAtRisk.length > 0 ? ["Prioritize review of HIGH-risk aircraft before next scheduled check."] : ["No fleet-wide action required."] },
      { heading: "AI-Generated Summary", body: [`Fleet-wide, ${f.aircraftAtRisk.length} aircraft require attention out of ${f.fleetSize}.`, "AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required."] },
    ];
    return { id, title: "Fleet Maintenance Risk Report", type: parsed.type, scope: "Fleet-wide", generatedDate, aiSummary: sections[sections.length - 1].body, sections };
  }

  if (parsed.type === "INSPECTION_QUEUE") {
    const insp = getInspectionAnalytics();
    const sections: ReportSection[] = [
      { heading: "Executive Summary", body: [`${insp.pending.length} inspection(s) currently pending review.`], kpis: insp.kpis },
      { heading: "Inspection Queue", body: [], table: { columns: ["Work Order", "Priority"], rows: insp.pending.map((p) => [p.label, p.priority]) } },
      { heading: "Recommended Actions", body: insp.pending.length > 0 ? ["Review CRITICAL/HIGH priority work orders first."] : ["Queue is clear."] },
      { heading: "AI-Generated Summary", body: [`${insp.pending.length} inspection(s) pending, ${insp.approved} approved, ${insp.rejected} rejected, ${insp.returned} returned this period.`, "AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required."] },
    ];
    return { id, title: "Inspection Queue Summary", type: parsed.type, scope: "Open inspections", generatedDate, aiSummary: sections[sections.length - 1].body, sections };
  }

  // COMPLIANCE_WEEKLY
  const c = getComplianceAnalytics();
  const m = getMaintenanceAnalytics();
  const sections: ReportSection[] = [
    { heading: "Executive Summary", body: ["Organization-wide compliance snapshot."], kpis: c.kpis },
    { heading: "Compliance Exposure", body: [`${c.nonCompliant} non-compliant, ${c.reviewRequired} review required, ${c.insufficientData} insufficient data, out of ${c.totalAssessments} assessments.`] },
    { heading: "Maintenance Snapshot", body: [], kpis: m.kpis },
    { heading: "Recommended Actions", body: c.nonCompliant + c.reviewRequired > 0 ? ["Prioritize assessments in Review Required / Non-Compliant status."] : ["No action required this week."] },
    { heading: "AI-Generated Summary", body: [`${c.compliant}/${c.totalAssessments} assessments are compliant fleet-wide.`, "AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required."] },
  ];
  return { id, title: "Weekly Compliance Report", type: "COMPLIANCE_WEEKLY", scope: "Organization-wide", generatedDate, aiSummary: sections[sections.length - 1].body, sections };
}
