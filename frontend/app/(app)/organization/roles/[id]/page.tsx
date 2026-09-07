"use client";

import { useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getRoleById, usersForRole, roleAccessSummary, updateRole } from "@/lib/mock/roles";
import { SimulateRoleButton } from "@/components/organization/SimulateRoleButton";
import { RoleForm } from "@/components/organization/RoleForm";
import { useMroState } from "@/lib/mro-state/MroStateContext";

const LEVEL_BADGE: Record<string, { status: "UNKNOWN" | "NOT_APPLICABLE" | "REVIEW_REQUIRED" | "COMPLIANT"; label: string }> = {
  NONE: { status: "NOT_APPLICABLE", label: "No Access" },
  VIEW: { status: "UNKNOWN", label: "View" },
  EDIT: { status: "REVIEW_REQUIRED", label: "Edit" },
  APPROVE: { status: "COMPLIANT", label: "Approve" },
};

export default function RoleDetailPage({ params }: { params: { id: string } }) {
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState(false);
  const { addAuditEvent } = useMroState();
  const role = getRoleById(params.id);
  if (!role) notFound();
  const assignedUsers = usersForRole(role.id);
  const access = roleAccessSummary(role);
  void version; // forces re-render after an in-place mutation via updateRole()

  if (editing) {
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
            <h1 className="ac-h1">Edit Role — {role.name}</h1>
          </div>
        </div>
        <RoleForm
          initial={role}
          submitLabel="Save Changes"
          onCancel={() => setEditing(false)}
          onSubmit={(value) => {
            const previousName = role.name;
            updateRole(role.id, value);
            addAuditEvent({
              actor: "Prototype User",
              actorRole: "Organization Admin",
              action: "role.updated",
              objectType: "Role",
              objectLabel: value.name,
              previousState: previousName,
              newState: value.name,
            });
            setEditing(false);
            setVersion((v) => v + 1);
          }}
        />
      </div>
    );
  }

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
        <div className="ac-flex ac-gap-2 ac-items-center">
          <StatusBadge status={role.status === "ACTIVE" ? "ACTIVE" : "STORED"} />
          <button className="ac-btn" onClick={() => setEditing(true)}>Edit Role</button>
          <SimulateRoleButton roleId={role.id} />
        </div>
      </div>
      <p className="ac-text-sm ac-text-muted" style={{ marginTop: -8, marginBottom: 12 }}>
        Prototype simulation — permissions are not enforced.
      </p>

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
          <div style={{ overflowX: "auto" }}>
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
        </div>
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
          Prototype only — this matrix is for UI demonstration; no permission here is actually enforced by the
          application.
        </p>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>What This Role Can Access</h2>
        <div className="ac-card">
          {access.approve.length > 0 && (
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}><strong>Can approve:</strong> {access.approve.join(", ")}</p>
          )}
          {access.edit.length > 0 && (
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}><strong>Can edit:</strong> {access.edit.join(", ")}</p>
          )}
          {access.view.length > 0 && (
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}><strong>Can view only:</strong> {access.view.join(", ")}</p>
          )}
          {access.none.length > 0 && (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}><strong>No access:</strong> {access.none.join(", ")}</p>
          )}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Assigned Users</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <div style={{ overflowX: "auto" }}>
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
        </div>
      </section>
    </div>
  );
}
