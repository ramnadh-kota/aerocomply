import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { organizations } from "@/lib/mock/organizations";
import { aircraft, currentRegistration } from "@/lib/mock/aircraft";
import { workOrdersForAircraft } from "@/lib/mock/workOrders";
import { getAircraftAnalytics } from "@/lib/mock/ai/analytics";

export default function OrganizationPage() {
  // M6.0/M6.1/M6.2 — multi-organization rollup. "Site" and "Hangar" are not
  // yet distinct entities in the domain model (only Organization -> Aircraft
  // exists via Aircraft.operatorOrgId), so this shows the real hierarchy
  // that does exist rather than fabricating sites/hangars.
  const rollup = organizations.map((o) => {
    const orgAircraft = aircraft.filter((a) => a.operatorOrgId === o.id);
    const openWorkOrders = orgAircraft.reduce((sum, a) => sum + workOrdersForAircraft(a.id).filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED").length, 0);
    const atRisk = orgAircraft.filter((a) => getAircraftAnalytics(a.id)?.complianceRisk !== "LOW").length;
    return { org: o, orgAircraft, openWorkOrders, atRisk };
  });

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization" }]} />
      <h1 className="ac-h1">Organization</h1>
      <p className="ac-subtitle" style={{ marginBottom: 12 }}>Tenant organizations visible in this prototype (mock data). Organization → Aircraft is the only hierarchy currently modeled; Site/Hangar are a planned architecture extension.</p>
      <div className="ac-flex ac-gap-2" style={{ marginBottom: 20 }}>
        <Link href="/organization/users" className="ac-btn">Users</Link>
        <Link href="/organization/roles" className="ac-btn">Roles</Link>
        <Link href="/organization/usage" className="ac-btn">Usage Intelligence</Link>
        <Link href="/organization/readiness" className="ac-btn">Pilot Readiness</Link>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Aircraft</th>
              <th>Open Work Orders</th>
              <th>Aircraft at Risk</th>
            </tr>
          </thead>
          <tbody>
            {rollup.map(({ org, orgAircraft, openWorkOrders, atRisk }) => (
              <tr key={org.id}>
                <td>{org.name}</td>
                <td><StatusBadge status="ACTIVE" label={org.orgType} /></td>
                <td className="ac-text-sm">
                  {orgAircraft.length === 0 ? "Insufficient source data." : orgAircraft.map((a, idx) => (
                    <span key={a.id}>{idx > 0 && ", "}<Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link></span>
                  ))}
                </td>
                <td>{openWorkOrders}</td>
                <td>{atRisk > 0 ? <StatusBadge status="NON_COMPLIANT" label={String(atRisk)} /> : <StatusBadge status="COMPLIANT" label="0" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
