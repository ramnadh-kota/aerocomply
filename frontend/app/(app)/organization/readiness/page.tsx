import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { aircraft } from "@/lib/mock/aircraft";
import { users, roles } from "@/lib/mock/roles";
import { workOrders } from "@/lib/mock/workOrders";
import { regulatoryRequirements } from "@/lib/mock/regulations";
import { assessmentsForRequirement } from "@/lib/mock/assessments";
import { getComplianceAnalytics } from "@/lib/mock/ai/analytics";

interface ReadinessItem {
  label: string;
  done: boolean;
  detail: string;
  href: string;
}

export default function PilotReadinessPage() {
  const mappedRequirements = regulatoryRequirements.filter((r) => assessmentsForRequirement(r.id).length > 0).length;
  const compliance = getComplianceAnalytics();
  const evidenceKnown = compliance.totalAssessments - compliance.insufficientData;

  // M6.5 — Founding Partner / pilot-customer readiness checklist. Every
  // check is derived from real repository data, not a fabricated onboarding
  // status.
  const items: ReadinessItem[] = [
    { label: "Aircraft configured", done: aircraft.length > 0, detail: `${aircraft.length} aircraft in fleet`, href: "/aircraft" },
    { label: "Users configured", done: users.length > 0, detail: `${users.length} user(s)`, href: "/organization/users" },
    { label: "Roles configured", done: roles.length > 0, detail: `${roles.length} role(s) defined`, href: "/organization/roles" },
    { label: "Work orders configured", done: workOrders.length > 0, detail: `${workOrders.length} work order(s)`, href: "/maintenance/work-orders" },
    { label: "Regulations mapped", done: mappedRequirements > 0, detail: `${mappedRequirements} of ${regulatoryRequirements.length} requirement(s) have an assessment`, href: "/compliance/regulatory-register" },
    { label: "Evidence availability", done: evidenceKnown > 0, detail: `${evidenceKnown} of ${compliance.totalAssessments} assessment(s) have a known status (not UNKNOWN)`, href: "/compliance" },
    { label: "Training status", done: false, detail: "Not tracked in current data model — Insufficient source data.", href: "/organization/users" },
  ];

  const completedCount = items.filter((i) => i.done).length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization", href: "/organization" }, { label: "Pilot Readiness" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Founding Partner Readiness</h1>
          <p className="ac-subtitle">{completedCount} of {items.length} onboarding checks satisfied by current data.</p>
        </div>
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.label}>
                <td><Link href={item.href}>{item.label}</Link></td>
                <td><StatusBadge status={item.done ? "COMPLIANT" : "INSUFFICIENT_DATA"} label={item.done ? "Ready" : "Gap"} /></td>
                <td className="ac-text-sm ac-text-muted">{item.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
