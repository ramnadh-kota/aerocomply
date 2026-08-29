import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { organizations } from "@/lib/mock/organizations";

export default function OrganizationPage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization" }]} />
      <h1 className="ac-h1">Organization</h1>
      <p className="ac-subtitle" style={{ marginBottom: 12 }}>Tenant organizations visible in this prototype (mock data).</p>
      <div className="ac-flex ac-gap-2" style={{ marginBottom: 20 }}>
        <Link href="/organization/users" className="ac-btn">Users</Link>
        <Link href="/organization/roles" className="ac-btn">Roles</Link>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {organizations.map((o) => (
              <tr key={o.id}>
                <td>{o.name}</td>
                <td>
                  <StatusBadge status="ACTIVE" label={o.orgType} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
