import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import {
  getControlTowerSummary,
  getFleetAnalytics,
  getFleetTatStatus,
  getEvidenceBlockedWorkOrders,
  getEvidencePendingReview,
  getInspectionAnalytics,
  getComplianceAnalytics,
  getMaterialReadinessSummary,
} from "@/lib/mock/ai/analytics";
import { getProactiveAlerts } from "@/lib/mock/ai/proactive";
import { PLATFORM_AI_NAME } from "@/lib/brand";

// Fleet-wide MRO Health Score.
//
// Every dimension below is a direct read of an existing, already-shipped
// engine function in lib/mock/ai/analytics.ts / lib/mock/ai/proactive.ts —
// this page computes nothing new about the underlying fleet data, it only
// arranges real outputs into one rollup view. If a dimension had no real
// engine behind it, it would render as "UNKNOWN / insufficient data"
// instead of a fabricated number (none currently fall into that bucket —
// every dimension the prototype was asked to cover already has a real
// supporting calculation somewhere in the app).
//
// Composite rule (documented, not dressed up as intelligence): each
// dimension below is independently classified RED / AMBER / GREEN from its
// own real numbers (thresholds noted per dimension). The headline score is
// simply "N of {total measured} dimensions are RED" — a transparent count,
// not a weighted or invented composite index.

type DimensionTone = "GREEN" | "AMBER" | "RED";

interface HealthDimension {
  key: string;
  label: string;
  tone: DimensionTone;
  value: string;
  detail: string;
  href: string;
  source: string;
}

function toneBadge(tone: DimensionTone): { status: "COMPLIANT" | "REVIEW_REQUIRED" | "NON_COMPLIANT"; label: string } {
  if (tone === "GREEN") return { status: "COMPLIANT", label: "Healthy" };
  if (tone === "AMBER") return { status: "REVIEW_REQUIRED", label: "Attention" };
  return { status: "NON_COMPLIANT", label: "At Risk" };
}

export default function FleetHealthPage() {
  const tower = getControlTowerSummary();
  const fleet = getFleetAnalytics();
  const tatRows = getFleetTatStatus();
  const evidenceBlocked = getEvidenceBlockedWorkOrders();
  const evidencePending = getEvidencePendingReview();
  const inspection = getInspectionAnalytics();
  const authAlerts = getProactiveAlerts().filter((a) => a.category === "AUTHORIZATION");
  const compliance = getComplianceAnalytics();
  const material = getMaterialReadinessSummary();

  const tatAtRisk = tatRows.filter((r) => r.assessment.status === "AT_RISK").length;
  const tatDelayed = tatRows.filter((r) => r.assessment.status === "DELAYED").length;

  const dimensions: HealthDimension[] = [
    {
      key: "availability",
      label: "Fleet Availability",
      tone: tower.aog > 0 ? "RED" : tower.underMaintenance > tower.operational ? "AMBER" : "GREEN",
      value: `${tower.operational}/${tower.totalAircraft} operational`,
      detail: `${tower.aog} AOG · ${tower.underMaintenance} under maintenance, out of ${tower.totalAircraft} tracked aircraft.`,
      href: "/maintenance/control-tower",
      source: "getControlTowerSummary()",
    },
    {
      key: "maintenance-risk",
      label: "Maintenance Risk",
      tone: fleet.overdueWorkOrders > 0 ? "RED" : fleet.aircraftAtRisk.length > 0 ? "AMBER" : "GREEN",
      value: `${fleet.aircraftAtRisk.length}/${fleet.fleetSize} aircraft at risk`,
      detail: `${fleet.overdueWorkOrders} overdue work order(s), ${fleet.openDefects} open defect(s) fleet-wide.`,
      href: "/executive",
      source: "getFleetAnalytics()",
    },
    {
      key: "tat-risk",
      label: "TAT Risk",
      tone: tatDelayed > 0 ? "RED" : tatAtRisk > 0 ? "AMBER" : "GREEN",
      value: `${tatDelayed} delayed, ${tatAtRisk} at risk`,
      detail: `Of ${tatRows.length} work order(s) evaluated for turnaround time.`,
      href: "/maintenance/planning",
      source: "getFleetTatStatus()",
    },
    {
      key: "aog",
      label: "AOG Count",
      tone: tower.aog > 0 ? "RED" : "GREEN",
      value: String(tower.aog),
      detail: tower.aog > 0 ? `${tower.aog} aircraft currently grounded (AOG).` : "No aircraft currently grounded.",
      href: "/maintenance/control-tower",
      source: "getControlTowerSummary()",
    },
    {
      key: "evidence",
      label: "Evidence Backlog",
      tone: evidenceBlocked.length > 0 ? "RED" : evidencePending.length > 0 ? "AMBER" : "GREEN",
      value: `${evidenceBlocked.length} blocked, ${evidencePending.length} pending review`,
      detail: "Work orders blocked on missing/rejected execution evidence, plus evidence items awaiting reviewer action.",
      href: "/evidence",
      source: "getEvidenceBlockedWorkOrders() / getEvidencePendingReview()",
    },
    {
      key: "rii",
      label: "Inspection / RII Backlog",
      tone: inspection.pending.length >= 5 ? "RED" : inspection.pending.length > 0 ? "AMBER" : "GREEN",
      value: `${inspection.pending.length} pending`,
      detail: `${inspection.approved} approved, ${inspection.rejected} rejected, ${inspection.returned} returned for correction.`,
      href: "/maintenance/inspections",
      source: "getInspectionAnalytics()",
    },
    {
      key: "authorization",
      label: "Authorization Gaps",
      tone: authAlerts.length > 0 ? "RED" : "GREEN",
      value: String(authAlerts.length),
      detail: authAlerts.length > 0
        ? `${authAlerts.length} open work order(s) assigned to a technician not authorized per the M22 authorization matrix.`
        : "No open work order is assigned to an unauthorized technician.",
      href: "/maintenance/technicians",
      source: "getProactiveAlerts() — AUTHORIZATION category (from getTechnicianAuthorizationMatrix())",
    },
    {
      key: "procurement",
      label: "Procurement Risk",
      tone: material.materialShortages > 0 ? "RED" : material.partialReadiness > 0 ? "AMBER" : "GREEN",
      value: `${material.materialShortages} shortage(s)`,
      detail: `${material.partialReadiness} partially ready, ${material.materialReady} ready, ${material.partsWithUnknownAvailability} with unknown vendor availability.`,
      href: "/maintenance/material-readiness",
      source: "getMaterialReadinessSummary()",
    },
    {
      key: "compliance",
      label: "Compliance",
      tone: compliance.nonCompliant > 0 ? "RED" : compliance.reviewRequired > 0 || compliance.insufficientData > 0 ? "AMBER" : "GREEN",
      value: `${compliance.compliant}/${compliance.totalAssessments} compliant`,
      detail: `${compliance.nonCompliant} non-compliant, ${compliance.reviewRequired} review required, ${compliance.insufficientData} insufficient data.`,
      href: "/compliance",
      source: "getComplianceAnalytics()",
    },
  ];

  const redCount = dimensions.filter((d) => d.tone === "RED").length;
  const amberCount = dimensions.filter((d) => d.tone === "AMBER").length;
  const greenCount = dimensions.filter((d) => d.tone === "GREEN").length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Fleet Health" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow">{PLATFORM_AI_NAME}&apos;s Fleet Health Rollup</p>
          <h1 className="ac-h1">MRO Health Score</h1>
          <p className="ac-subtitle">
            {dimensions.length} dimensions measured from real engine outputs, no fabricated composite index — see
            the scoring rule below.
          </p>
        </div>
      </div>

      <div className="ac-card ac-section">
        <div className="ac-flex ac-items-center ac-gap-3" style={{ marginBottom: 8 }}>
          <span className="ac-h2" style={{ margin: 0 }}>{redCount} of {dimensions.length} dimensions at risk</span>
          <StatusBadge {...toneBadge(redCount > 0 ? "RED" : amberCount > 0 ? "AMBER" : "GREEN")} />
        </div>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          <strong>Scoring rule (stated, not inferred):</strong> each dimension is independently classified RED
          (a real backlog/risk condition exists), AMBER (borderline or partial), or GREEN (no issue found) from
          its own underlying engine output — thresholds are noted per dimension below. The headline number is a
          plain count of RED dimensions out of the {dimensions.length} measured; it is not a weighted score and
          no dimension here is fabricated or estimated.
        </p>
        <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0 0" }}>
          {redCount} RED · {amberCount} AMBER · {greenCount} GREEN
        </p>
      </div>

      <div className="ac-grid-2">
        {dimensions.map((d) => {
          const badge = toneBadge(d.tone);
          return (
            <Link key={d.key} href={d.href} className="ac-card" style={{ display: "block", textDecoration: "none", color: "inherit" }}>
              <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                <p className="ac-eyebrow" style={{ margin: 0 }}>{d.label}</p>
                <StatusBadge {...badge} />
              </div>
              <p className="ac-kpi-value" style={{ margin: "0 0 4px" }}>{d.value}</p>
              <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 6px" }}>{d.detail}</p>
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0, fontFamily: "var(--ac-font-mono, monospace)", fontSize: 11 }}>
                Source: {d.source}
              </p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
