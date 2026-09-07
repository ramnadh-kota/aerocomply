"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { roles, usersForRole, type Role } from "@/lib/mock/roles";
import { PLATFORM_NAME } from "@/lib/brand";

const columns: Column<Role>[] = [
  { key: "role", header: "Role", render: (r) => <span style={{ fontWeight: 600 }}>{r.name}</span>, sortValue: (r) => r.name },
  { key: "users", header: "Users", render: (r) => usersForRole(r.id).length, sortValue: (r) => usersForRole(r.id).length },
  { key: "scope", header: "Scope", render: (r) => r.scope, sortValue: (r) => r.scope },
  {
    key: "permissions",
    header: "Permissions",
    render: (r) => `${r.permissions.filter((p) => p.level !== "NONE").length}/${r.permissions.length} modules`,
  },
  { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status === "ACTIVE" ? "ACTIVE" : "STORED"} /> },
  { key: "lastUpdated", header: "Last Updated", render: (r) => r.lastUpdated, sortValue: (r) => r.lastUpdated },
];

export default function RolesPage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization", href: "/organization" }, { label: "Roles" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Roles</h1>
          <p className="ac-subtitle">
            Prototype role &amp; access management. This demonstrates how {PLATFORM_NAME} could control access — no real
            authorization is enforced here.
          </p>
        </div>
        <Link href="/organization/roles/new" className="ac-btn ac-btn-primary">Add Role</Link>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={roles} getRowHref={(r) => `/organization/roles/${r.id}`} />
      </div>
    </div>
  );
}
