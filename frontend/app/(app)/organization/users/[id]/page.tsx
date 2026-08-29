import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { Timeline } from "@/components/timeline/Timeline";
import { getUserById, getRoleById } from "@/lib/mock/roles";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import { auditEvents } from "@/lib/mock/audit";

const LEVEL_BADGE: Record<string, { status: "UNKNOWN" | "NOT_APPLICABLE" | "REVIEW_REQUIRED" | "COMPLIANT"; label: string }> = {
  NONE: { status: "NOT_APPLICABLE", label: "No Access" },
  VIEW: { status: "UNKNOWN", label: "View" },
  EDIT: { status: "REVIEW_REQUIRED", label: "Edit" },
  APPROVE: { status: "COMPLIANT", label: "Approve" },
};

export default function UserDetailPage({ params }: { params: { id: string } }) {
  const user = getUserById(params.id);
  if (!user) notFound();
  const role = getRoleById(user.roleId);
  const userAuditEvents = auditEvents.filter((e) => e.actor === user.name);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Organization", href: "/organization" },
          { label: "Users", href: "/organization/users" },
          { label: user.name },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{user.name}</h1>
          <p className="ac-subtitle">
            {user.department} · Role: {role ? <Link href={`/organization/roles/${role.id}`}>{role.name}</Link> : user.roleId}
          </p>
        </div>
        <StatusBadge status={user.status === "ACTIVE" ? "ACTIVE" : "STORED"} />
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Permissions (Inherited from Role)</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr><th>Module</th><th>Access Level</th></tr>
            </thead>
            <tbody>
              {role?.permissions.map((p) => (
                <tr key={p.module}>
                  <td style={{ fontWeight: 600 }}>{p.module}</td>
                  <td><StatusBadge {...LEVEL_BADGE[p.level]} /></td>
                </tr>
              )) ?? (
                <tr><td colSpan={2} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No role assigned.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Aircraft Access</p>
          {user.assignedAircraftIds.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>None assigned.</p>}
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {user.assignedAircraftIds.map((id) => {
              const a = getAircraftById(id);
              return <li key={id} className="ac-text-sm"><Link href={`/aircraft/${id}`}>{a ? currentRegistration(a) : id}</Link></li>;
            })}
          </ul>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Project Access</p>
          {user.assignedProjectIds.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>None assigned.</p>}
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {user.assignedProjectIds.map((id) => {
              const p = getProjectById(id);
              return <li key={id} className="ac-text-sm"><Link href={`/maintenance/projects/${id}`}>{p ? p.projectNumber : id}</Link></li>;
            })}
          </ul>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Audit History</h2>
        <div className="ac-card">
          {userAuditEvents.length === 0 ? (
            <p className="ac-text-sm ac-text-muted">No audit events recorded for this user in the demo dataset.</p>
          ) : (
            <Timeline
              entries={userAuditEvents.map((e) => ({
                id: e.id,
                date: new Date(e.timestamp).toLocaleString(),
                title: e.action.replace(/_/g, " ").replace(/\./g, " — "),
                detail: e.objectLabel,
              }))}
            />
          )}
        </div>
      </section>
    </div>
  );
}
