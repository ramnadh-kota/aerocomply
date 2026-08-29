import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { users, getRoleById, type UserAccount } from "@/lib/mock/roles";

const columns: Column<UserAccount>[] = [
  { key: "name", header: "Name", render: (u) => <span style={{ fontWeight: 600 }}>{u.name}</span>, sortValue: (u) => u.name },
  { key: "role", header: "Role", render: (u) => getRoleById(u.roleId)?.name ?? u.roleId, sortValue: (u) => getRoleById(u.roleId)?.name ?? "" },
  { key: "department", header: "Department", render: (u) => u.department, sortValue: (u) => u.department },
  {
    key: "access",
    header: "Assigned Aircraft/Projects",
    render: (u) => `${u.assignedAircraftIds.length} aircraft · ${u.assignedProjectIds.length} projects`,
  },
  { key: "status", header: "Status", render: (u) => <StatusBadge status={u.status === "ACTIVE" ? "ACTIVE" : "STORED"} /> },
  { key: "lastActivity", header: "Last Activity", render: (u) => new Date(u.lastActivity).toLocaleString(), sortValue: (u) => u.lastActivity },
];

export default function UsersPage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization", href: "/organization" }, { label: "Users" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Users</h1>
          <p className="ac-subtitle">
            Prototype user directory. <Link href="/organization/roles">View Roles →</Link>
          </p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={users} getRowHref={(u) => `/organization/users/${u.id}`} />
      </div>
    </div>
  );
}
