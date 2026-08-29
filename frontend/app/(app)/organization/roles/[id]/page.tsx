import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getRoleById, usersForRole } from "@/lib/mock/roles";

const LEVEL_BADGE: Record<string, { status: "UNKNOWN" | "NOT_APPLICABLE" | "REVIEW_REQUIRED" | "COMPLIANT"; label: string }> = {
  NONE: { status: "NOT_APPLICABLE", label: "No Access" },
  VIEW: { status: "UNKNOWN", label: "View" },
  EDIT: { status: "REVIEW_REQUIRED", label: "Edit" },
  APPROVE: { status: "COMPLIANT", label: "Approve" },
};

export default function RoleDetailPage({ params }: { params: { id: string } }) {
  const role = getRoleById(params.id);
  if (!role) notFound();
  const assignedUsers = usersForRole(role.id);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Organization", href: "/organization" },
          { label: "Roles", href: "/organization/roles" },
          { label: role.name },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{role.name}</h1>
          <p className="ac-subtitle">{role.description}</p>
        </div>
        <StatusBadge status={role.status === "ACTIVE" ? "ACTIVE" : "STORED"} />
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Scope</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{role.scope}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Assigned Users</p>
          <p className="ac-kpi-value">{assignedUsers.length}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">AI Access</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {[role.aiAccess.ask && "Ask", role.aiAccess.analytics && "Analytics", role.aiAccess.reports && "Reports"].filter(Boolean).join(" · ") || "None"}
          </p>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Permission Matrix</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Module</th>
                <th>Access Level</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {role.permissions.map((p) => (
                <tr key={p.module}>
                  <td style={{ fontWeight: 600 }}>{p.module}</td>
                  <td><StatusBadge {...LEVEL_BADGE[p.level]} /></td>
                  <td className="ac-text-sm ac-text-muted">{p.notes ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
          Prototype only — this matrix is for UI demonstration; no permission here is actually enforced by the
          application.
        </p>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Assigned Users</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Department</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {assignedUsers.length === 0 && (
                <tr>
                  <td colSpan={3} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>
                    No users assigned to this role.
                  </td>
                </tr>
              )}
              {assignedUsers.map((u) => (
                <tr key={u.id}>
                  <td><Link href={`/organization/users/${u.id}`}>{u.name}</Link></td>
                  <td>{u.department}</td>
                  <td><StatusBadge status={u.status === "ACTIVE" ? "ACTIVE" : "STORED"} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
