import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { aircraft } from "@/lib/mock/aircraft";
import { users, roles } from "@/lib/mock/roles";
import { workOrders } from "@/lib/mock/workOrders";
import { technicians } from "@/lib/mock/technicians";
import { regulatoryRequirements } from "@/lib/mock/regulations";
import { assessmentsForRequirement } from "@/lib/mock/assessments";
import { getComplianceAnalytics } from "@/lib/mock/ai/analytics";
import { parts } from "@/lib/mock/parts";
import { partReceivingRecords, partCertificates } from "@/lib/mock/partTraceability";
import { auditEvents } from "@/lib/mock/audit";

// M7.9 — Commercial Pilot Readiness. Extends the existing checklist (kept
// as the single readiness page, no second one) with the 9 named categories
// and a 4-value rating instead of a binary done/not-done flag. Every rating
// is derived from real repository counts — never marked Ready when the
// underlying source data does not support it.

type Rating = "READY" | "PARTIAL" | "BLOCKED" | "UNKNOWN";

interface ReadinessCategory {
  category: string;
  rating: Rating;
  detail: string;
  href: string;
}

function ratingBadge(rating: Rating): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (rating) {
    case "READY": return { status: "COMPLIANT", label: "Ready" };
    case "PARTIAL": return { status: "REVIEW_REQUIRED", label: "Partial" };
    case "BLOCKED": return { status: "NON_COMPLIANT", label: "Blocked" };
    default: return { status: "INSUFFICIENT_DATA", label: "Unknown" };
  }
}

export default function PilotReadinessPage() {
  const mappedRequirements = regulatoryRequirements.filter((r) => assessmentsForRequirement(r.id).length > 0).length;
  const compliance = getComplianceAnalytics();
  const evidenceKnown = compliance.totalAssessments - compliance.insufficientData;
  const partsWithReceiving = new Set(partReceivingRecords.map((r) => r.partId)).size;
  const partsWithCertificates = new Set(partCertificates.map((c) => c.partId)).size;

  const categories: ReadinessCategory[] = [
    {
      category: "Operational Setup",
      rating: workOrders.length > 0 && technicians.length > 0 ? "READY" : workOrders.length > 0 || technicians.length > 0 ? "PARTIAL" : "BLOCKED",
      detail: `${workOrders.length} work order(s), ${technicians.length} technician(s) configured.`,
      href: "/maintenance/work-orders",
    },
    {
      category: "Maintenance Data",
      rating: workOrders.length > 0 ? "READY" : "BLOCKED",
      detail: `${workOrders.length} work order(s) tracked.`,
      href: "/maintenance/operations",
    },
    {
      category: "Aircraft Data",
      rating: aircraft.length > 0 ? "READY" : "BLOCKED",
      detail: `${aircraft.length} aircraft in fleet.`,
      href: "/aircraft",
    },
    {
      category: "Parts Data",
      rating: parts.length === 0 ? "BLOCKED" : partsWithReceiving > 0 && partsWithCertificates > 0 ? "PARTIAL" : "BLOCKED",
      detail: `${parts.length} part(s) tracked; ${partsWithReceiving} with a receiving record; ${partsWithCertificates} with a certificate record. Full traceability is not yet seeded for every part.`,
      href: "/maintenance/parts",
    },
    {
      category: "Regulatory Data",
      rating: mappedRequirements === regulatoryRequirements.length && regulatoryRequirements.length > 0 ? "READY" : mappedRequirements > 0 ? "PARTIAL" : "BLOCKED",
      detail: `${mappedRequirements} of ${regulatoryRequirements.length} requirement(s) have an assessment.`,
      href: "/compliance/regulatory-register",
    },
    {
      category: "User Setup",
      rating: users.length > 0 && roles.length > 0 ? "READY" : "BLOCKED",
      detail: `${users.length} user(s), ${roles.length} role(s) defined.`,
      href: "/organization/users",
    },
    {
      category: "Evidence",
      rating: evidenceKnown === compliance.totalAssessments && compliance.totalAssessments > 0 ? "READY" : evidenceKnown > 0 ? "PARTIAL" : "BLOCKED",
      detail: `${evidenceKnown} of ${compliance.totalAssessments} assessment(s) have a known status (not UNKNOWN).`,
      href: "/compliance",
    },
    {
      category: "Audit Readiness",
      rating: auditEvents.length > 0 ? "PARTIAL" : "BLOCKED",
      detail: `${auditEvents.length} seeded audit event(s). Audit Trail is single-source but not yet backed by a persisted, immutable store — see M8 architecture notes.`,
      href: "/audit",
    },
    {
      category: "AI Readiness",
      rating: "PARTIAL",
      detail: "Core reasoning engine functional against current demo data; no AMM/IPC/SRM/CMM/MPD/MEL reference library is integrated, so technical-procedure questions correctly return Insufficient Data rather than a fabricated answer.",
      href: "/ai",
    },
    {
      category: "Training Status",
      rating: "UNKNOWN",
      detail: "Not tracked in current data model — Insufficient source data.",
      href: "/organization/users",
    },
  ];

  const readyCount = categories.filter((c) => c.rating === "READY").length;
  const blockedCount = categories.filter((c) => c.rating === "BLOCKED").length;
  const unknownCount = categories.filter((c) => c.rating === "UNKNOWN").length;
  const pilotVerdict: Rating = blockedCount > 0 ? "BLOCKED" : unknownCount > 0 ? "PARTIAL" : readyCount === categories.length ? "READY" : "PARTIAL";

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization", href: "/organization" }, { label: "Pilot Readiness" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Commercial Pilot Readiness</h1>
          <p className="ac-subtitle">{readyCount} of {categories.length} categories fully Ready by current data.</p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-card">
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Ready for 30-Day Pilot?</p>
          <div className="ac-flex ac-items-center ac-gap-3">
            <StatusBadge {...ratingBadge(pilotVerdict)} label={pilotVerdict === "BLOCKED" ? "Not Ready — Blocked" : pilotVerdict === "READY" ? "Ready" : "Ready With Caveats"} />
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {blockedCount > 0
                ? `${blockedCount} categor${blockedCount === 1 ? "y is" : "ies are"} blocked and must be resolved before a pilot deployment.`
                : "No category is fully blocked, but several are only Partial — a pilot customer should be scoped around the caveats listed below."}
            </p>
          </div>
        </div>
      </section>

      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead><tr><th>Category</th><th>Status</th><th>Detail</th></tr></thead>
          <tbody>
            {categories.map((cat) => (
              <tr key={cat.category}>
                <td><Link href={cat.href}>{cat.category}</Link></td>
                <td><StatusBadge {...ratingBadge(cat.rating)} /></td>
                <td className="ac-text-sm ac-text-muted">{cat.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
