// Proactive intelligence layer for Lisa. Everything here READS the existing
// canonical engines in ./analytics.ts (and the regulations/procurement/parts
// mock stores) — it never recomputes a business rule and never invents a
// condition that isn't backed by a real record. This is the single place
// that turns those engine outputs into a prioritized, deduplicated alert
// feed, consumed by the Topbar notification panel, the dashboard's Daily
// Brief card, and the AI console's "Lisa noticed…" strip — so all three
// surfaces can never disagree about what Lisa is proactively flagging.

import {
  getFleetTatStatus,
  getAogRecoveryAnalysis,
  getControlTowerFleet,
  getEvidenceBlockedWorkOrders,
  getEvidencePendingReview,
  getInspectionRequirement,
  getTechnicianAuthorizationMatrix,
  getReleaseQueue,
  getComplianceAnalytics,
  getPartsAtRisk,
} from "./analytics";
import { workOrders, MOCK_TODAY } from "../workOrders";
import { getAircraftById, currentRegistration } from "../aircraft";
import { regulatoryDocuments, regulatoryRequirements } from "../regulations";
import { scoreVendorOptionsForPart } from "../procurement";
import { parts as allParts } from "../parts";

export type AlertSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type AlertCategory =
  | "AOG"
  | "TAT"
  | "EVIDENCE"
  | "RII"
  | "AUTHORIZATION"
  | "PART"
  | "VENDOR"
  | "REGULATORY"
  | "RELEASE";

export interface ProactiveAlert {
  id: string;
  severity: AlertSeverity;
  category: AlertCategory;
  title: string;
  message: string;
  relatedEntity: { type: "AIRCRAFT" | "WORK_ORDER" | "PART" | "REGULATORY_DOCUMENT"; id: string };
  href: string;
}

const SEVERITY_RANK: Record<AlertSeverity, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function daysBetween(a: string, b: string): number {
  return Math.round((new Date(a).getTime() - new Date(b).getTime()) / 86400000);
}

// Window used to decide "recently published" / "effective soon" for
// regulatory documents — same style of fixed window the TAT engine already
// uses (TAT_AT_RISK_WINDOW_DAYS in analytics.ts), applied here to
// publication/effective dates rather than due dates.
const REGULATORY_RECENT_WINDOW_DAYS = 14;
const REGULATORY_EFFECTIVE_SOON_WINDOW_DAYS = 14;

/**
 * Scans every canonical engine and produces a deduplicated, severity-ranked
 * list of proactive alerts. Every alert is directly traceable to a real
 * condition returned by an existing engine — nothing here is randomly
 * generated or fabricated.
 */
export function getProactiveAlerts(): ProactiveAlert[] {
  const alerts: ProactiveAlert[] = [];

  // --- AOG (Control Tower fleet AOG rows → getAogRecoveryAnalysis) ---
  const aogFleetRows = getControlTowerFleet().filter((r) => r.operationalStatus === "AOG");
  for (const row of aogFleetRows) {
    const recovery = getAogRecoveryAnalysis(row.aircraftId);
    alerts.push({
      id: `aog-${row.aircraftId}`,
      severity: "CRITICAL",
      category: "AOG",
      title: `${row.registration} is AOG`,
      message: row.aogReason ?? recovery?.aogReason ?? "Aircraft grounded by an open HIGH/CRITICAL defect.",
      relatedEntity: { type: "AIRCRAFT", id: row.aircraftId },
      href: `/aircraft/${row.aircraftId}`,
    });
  }

  // --- TAT (delayed / at-risk work orders) ---
  for (const row of getFleetTatStatus()) {
    if (row.assessment.status === "DELAYED") {
      alerts.push({
        id: `tat-delayed-${row.workOrderId}`,
        severity: "HIGH",
        category: "TAT",
        title: `${row.workOrderNumber} is delayed`,
        message: `${row.assessment.reason} (${row.aircraftRegistration}).`,
        relatedEntity: { type: "WORK_ORDER", id: row.workOrderId },
        href: `/maintenance/work-orders/${row.workOrderId}`,
      });
    } else if (row.assessment.status === "AT_RISK") {
      alerts.push({
        id: `tat-at-risk-${row.workOrderId}`,
        severity: "MEDIUM",
        category: "TAT",
        title: `${row.workOrderNumber} is at risk of missing TAT`,
        message: `${row.assessment.reason} (${row.aircraftRegistration}).`,
        relatedEntity: { type: "WORK_ORDER", id: row.workOrderId },
        href: `/maintenance/work-orders/${row.workOrderId}`,
      });
    }
  }

  // --- EVIDENCE (blocked work orders + records pending review) ---
  for (const w of getEvidenceBlockedWorkOrders()) {
    const a = getAircraftById(w.aircraftId);
    alerts.push({
      id: `evidence-blocked-${w.id}`,
      severity: "HIGH",
      category: "EVIDENCE",
      title: `${w.workOrderNumber} blocked on execution evidence`,
      message: `Required execution evidence is missing or rejected${a ? ` for ${currentRegistration(a)}` : ""}.`,
      relatedEntity: { type: "WORK_ORDER", id: w.id },
      href: `/maintenance/work-orders/${w.id}`,
    });
  }
  const pendingReview = getEvidencePendingReview();
  if (pendingReview.length > 0) {
    const byWorkOrder = new Map<string, number>();
    for (const rec of pendingReview) byWorkOrder.set(rec.workOrderId, (byWorkOrder.get(rec.workOrderId) ?? 0) + 1);
    for (const [workOrderId, count] of byWorkOrder.entries()) {
      const w = workOrders.find((x) => x.id === workOrderId);
      alerts.push({
        id: `evidence-pending-${workOrderId}`,
        severity: "MEDIUM",
        category: "EVIDENCE",
        title: `${w?.workOrderNumber ?? workOrderId} has evidence awaiting review`,
        message: `${count} evidence item(s) submitted and awaiting reviewer action.`,
        relatedEntity: { type: "WORK_ORDER", id: workOrderId },
        href: `/maintenance/work-orders/${workOrderId}`,
      });
    }
  }

  // --- RII (independent inspection required but blocked) ---
  const openWos = workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  for (const w of openWos) {
    const req = getInspectionRequirement(w.id);
    if (req.status === "BLOCKED") {
      alerts.push({
        id: `rii-blocked-${w.id}`,
        severity: "HIGH",
        category: "RII",
        title: `${w.workOrderNumber} needs an independent inspector`,
        message: req.reason,
        relatedEntity: { type: "WORK_ORDER", id: w.id },
        href: `/maintenance/work-orders/${w.id}`,
      });
    }
  }

  // --- AUTHORIZATION (work orders with an assigned technician who is
  // NOT_AUTHORIZED per the M22 authorization matrix) ---
  for (const w of openWos) {
    if (!w.assignedTechnicianId) continue;
    const matrix = getTechnicianAuthorizationMatrix(w.id);
    const assignedResult = matrix.find((m) => m.technicianId === w.assignedTechnicianId);
    if (assignedResult && assignedResult.status === "NOT_AUTHORIZED") {
      alerts.push({
        id: `auth-blocked-${w.id}`,
        severity: "HIGH",
        category: "AUTHORIZATION",
        title: `${w.workOrderNumber} assigned to an unauthorized technician`,
        message: `${assignedResult.name}: ${assignedResult.reasons[assignedResult.reasons.length - 1] ?? "Not authorized for this work order."}`,
        relatedEntity: { type: "WORK_ORDER", id: w.id },
        href: `/maintenance/work-orders/${w.id}`,
      });
    }
  }

  // --- PART (material shortages tied to an open work order) ---
  const partsAtRisk = getPartsAtRisk();
  for (const p of partsAtRisk) {
    if (!p.workOrderId) continue;
    const w = workOrders.find((x) => x.id === p.workOrderId);
    if (!w || w.status === "COMPLETED" || w.status === "CANCELLED") continue;
    alerts.push({
      id: `part-shortage-${p.partNumber}-${p.workOrderId}`,
      severity: p.status === "OUT_OF_STOCK" ? "HIGH" : "MEDIUM",
      category: "PART",
      title: `${p.partNumber} unavailable for ${w.workOrderNumber}`,
      message: `${p.description} — status ${p.status.replace(/_/g, " ")}.`,
      relatedEntity: { type: "WORK_ORDER", id: w.id },
      href: `/maintenance/work-orders/${w.id}`,
    });

    // --- VENDOR (no scoreable vendor option exists for a shorted part) ---
    const part = allParts.find((x) => x.partNumber === p.partNumber);
    const partIdForScoring = part?.id ?? null;
    if (partIdForScoring) {
      const options = scoreVendorOptionsForPart(partIdForScoring);
      if (options.length === 0) {
        alerts.push({
          id: `vendor-none-${p.partNumber}-${w.id}`,
          severity: "MEDIUM",
          category: "VENDOR",
          title: `No vendor option on file for ${p.partNumber}`,
          message: `${w.workOrderNumber} is blocked on ${p.partNumber} and no vendor availability record exists to source it.`,
          relatedEntity: { type: "PART", id: partIdForScoring },
          href: `/maintenance/material-readiness`,
        });
      }
    }
  }

  // --- REGULATORY (recently published / effective-soon documents) ---
  for (const doc of regulatoryDocuments) {
    const publishedDaysAgo = daysBetween(MOCK_TODAY, doc.publicationDate);
    const effectiveInDays = daysBetween(doc.effectiveDate, MOCK_TODAY);
    if (publishedDaysAgo >= 0 && publishedDaysAgo <= REGULATORY_RECENT_WINDOW_DAYS) {
      alerts.push({
        id: `regulatory-published-${doc.id}`,
        severity: "LOW",
        category: "REGULATORY",
        title: `${doc.docNumber} recently published`,
        message: `${doc.title} — published ${doc.publicationDate}, effective ${doc.effectiveDate}.`,
        relatedEntity: { type: "REGULATORY_DOCUMENT", id: doc.id },
        href: `/regulations`,
      });
    } else if (effectiveInDays >= 0 && effectiveInDays <= REGULATORY_EFFECTIVE_SOON_WINDOW_DAYS) {
      alerts.push({
        id: `regulatory-effective-soon-${doc.id}`,
        severity: "MEDIUM",
        category: "REGULATORY",
        title: `${doc.docNumber} becomes effective soon`,
        message: `${doc.title} — effective ${doc.effectiveDate} (in ${effectiveInDays} day(s)).`,
        relatedEntity: { type: "REGULATORY_DOCUMENT", id: doc.id },
        href: `/regulations`,
      });
    }
  }
  // Keep regulatoryRequirements import meaningful even though the current
  // heuristic only needs document-level dates — reserved for a future
  // requirement-level alert without a second regulatory data source.
  void regulatoryRequirements;

  // --- RELEASE (work orders sitting in the release queue) ---
  for (const r of getReleaseQueue()) {
    alerts.push({
      id: `release-queue-${r.workOrderId}`,
      severity: "MEDIUM",
      category: "RELEASE",
      title: `${r.workOrderNumber} awaiting release`,
      message: `Execution state is ${r.executionState.replace(/_/g, " ")} for ${r.aircraftRegistration} — not yet released.`,
      relatedEntity: { type: "WORK_ORDER", id: r.workOrderId },
      href: `/maintenance/work-orders/${r.workOrderId}`,
    });
  }

  // Deduplicate by id (defensive — some engines could theoretically overlap
  // if a work order appears in more than one pass with the same id) and
  // sort by severity, most severe first.
  const seen = new Set<string>();
  const deduped = alerts.filter((a) => (seen.has(a.id) ? false : (seen.add(a.id), true)));
  deduped.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  return deduped;
}

export interface DailyBrief {
  generatedAt: string;
  fleet: {
    aircraftCount: number;
    aogCount: number;
    maintenanceDueCount: number;
    tatAtRiskCount: number;
  };
  topPriorities: ProactiveAlert[];
  procurement: { criticalPartsCount: number };
  compliance: { recentRegulatoryCount: number };
  recommendedActions: string[];
}

/**
 * Fleet-wide morning summary for the dashboard's "Lisa's Daily Brief" card.
 * Reuses getProactiveAlerts() for priorities so the brief and the
 * notification panel can never disagree about what's urgent.
 */
export function getDailyBrief(topN = 5): DailyBrief {
  const alerts = getProactiveAlerts();
  const fleet = getControlTowerFleet();
  const aogCount = fleet.filter((r) => r.operationalStatus === "AOG").length;
  const maintenanceDueCount = fleet.filter((r) => r.operationalStatus === "UNDER_MAINTENANCE").length;
  const tatAtRiskCount = getFleetTatStatus().filter(
    (r) => r.assessment.status === "AT_RISK" || r.assessment.status === "DELAYED"
  ).length;
  const criticalPartsCount = getPartsAtRisk().filter((p) => p.status === "OUT_OF_STOCK").length;
  const recentRegulatoryCount = alerts.filter((a) => a.category === "REGULATORY").length;

  const topPriorities = alerts.slice(0, topN);
  const recommendedActions = topPriorities.map((a) => `${a.title}: ${a.message}`);

  return {
    generatedAt: MOCK_TODAY,
    fleet: {
      aircraftCount: fleet.length,
      aogCount,
      maintenanceDueCount,
      tatAtRiskCount,
    },
    topPriorities,
    procurement: { criticalPartsCount },
    compliance: { recentRegulatoryCount },
    recommendedActions: recommendedActions.length > 0 ? recommendedActions : ["No urgent action indicated by current data."],
  };
}
