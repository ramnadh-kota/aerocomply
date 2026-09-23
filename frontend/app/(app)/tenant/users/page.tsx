"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantUser } from "@/lib/api/tenant";
import { DEMO_TENANT_USERS } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const AVAILABLE_TENANT_ROLES = [
  { value: "ORG_ADMIN", label: "Organization Administrator" },
  { value: "CAMO_MANAGER", label: "CAMO Manager" },
  { value: "COMPLIANCE_MANAGER", label: "Compliance Manager" },
  { value: "QUALITY_MANAGER", label: "Quality Manager" },
  { value: "MAINTENANCE_ENGINEER", label: "Maintenance Engineer" },
  { value: "VIEWER", label: "Stakeholder / Viewer" },
];

export default function TenantUsersPage() {
  const { user: currentUser, accessToken, isAuthenticated, isDemo } = useSession();
  const [users, setUsers] = useState<TenantUser[]>(isDemo ? DEMO_TENANT_USERS : []);
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("ALL");

  // Role Edit Modal State
  const [editingUser, setEditingUser] = useState<TenantUser | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [modalSaving, setModalSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const loadUsers = () => {
    if (isDemo) {
      setUsers(DEMO_TENANT_USERS);
      setLoading(false);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    tenantApi
      .listUsers(accessToken)
      .then(setUsers)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo, isAuthenticated, accessToken]);

  const filteredUsers = users.filter((u) => {
    const matchesSearch =
      u.full_name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole =
      roleFilter === "ALL" || u.roles.includes(roleFilter);
    return matchesSearch && matchesRole;
  });

  const handleOpenEdit = (user: TenantUser) => {
    setEditingUser(user);
    setSelectedRoles([...user.roles]);
    setModalError(null);
  };

  const handleToggleRole = (role: string) => {
    setSelectedRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
  };

  const handleSaveRoles = async () => {
    if (!editingUser) return;
    if (selectedRoles.length === 0) {
      setModalError("A user must have at least one role assigned.");
      return;
    }

    setModalSaving(true);
    setModalError(null);

    if (isDemo) {
      setUsers((prev) =>
        prev.map((u) =>
          u.id === editingUser.id ? { ...u, roles: selectedRoles } : u
        )
      );
      setModalSaving(false);
      setEditingUser(null);
      return;
    }

    if (!accessToken) return;
    try {
      const updated = await tenantApi.updateUserRoles(
        accessToken,
        editingUser.id,
        selectedRoles
      );
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      setEditingUser(null);
    } catch (err) {
      setModalError(normalizeApiError(err).message);
    } finally {
      setModalSaving(false);
    }
  };

  const handleToggleStatus = async (targetUser: TenantUser) => {
    if (targetUser.id === currentUser?.id && targetUser.is_active) {
      alert("You cannot deactivate your own account.");
      return;
    }

    const action = targetUser.is_active ? "deactivate" : "activate";
    if (!confirm(`Are you sure you want to ${action} ${targetUser.full_name}?`)) {
      return;
    }

    if (isDemo) {
      setUsers((prev) =>
        prev.map((u) =>
          u.id === targetUser.id ? { ...u, is_active: !u.is_active } : u
        )
      );
      return;
    }

    if (!accessToken) return;
    try {
      const updated = await tenantApi.updateUserStatus(
        accessToken,
        targetUser.id,
        !targetUser.is_active
      );
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      alert(normalizeApiError(err).message);
    }
  };

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Personnel Directory" },
        ]}
        eyebrow="PEOPLE & ACCESS"
        title="Tenant Personnel"
        subtitle="Manage user accounts, assign operational roles, and enforce organization boundaries."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/invitations" className="ac-btn ac-btn-primary">
              + Invite Team Member
            </Link>
            <Link href="/tenant/roles" className="ac-btn">
              Role Grants &amp; Permissions
            </Link>
          </div>
        }
      />

      <div style={{ marginBottom: 16 }}>
        {isDemo ? (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.25)",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            <strong>DEMO MODE</strong> · Showing synthetic organization personnel for KOTA Aerospace Demo Operations.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={filteredUsers.length === 0}
            emptyMessage="No personnel records found."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      {/* Filter and Search Bar */}
      <div
        className="ac-card"
        style={{
          padding: 12,
          marginBottom: 16,
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: 8, flex: 1, minWidth: 260 }}>
          <input
            type="text"
            className="ac-input"
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: "100%", maxWidth: 360 }}
          />
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 13, fontWeight: 500 }}>Filter by Role:</label>
          <select
            className="ac-input"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            style={{ minWidth: 180 }}
          >
            <option value="ALL">All Roles ({users.length})</option>
            {AVAILABLE_TENANT_ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Users Table */}
      <div className="ac-card" style={{ padding: 0 }}>
        <div style={{ overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Personnel</th>
                <th>Assigned Roles</th>
                <th>Status</th>
                <th>Created</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: "32px 16px", opacity: 0.7 }}>
                    No users matching criteria.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{u.full_name}</div>
                      <div className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>
                        {u.email}
                      </div>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {u.roles.map((r) => (
                          <span
                            key={r}
                            style={{
                              fontSize: 11,
                              padding: "2px 6px",
                              borderRadius: 4,
                              background:
                                r === "ORG_ADMIN"
                                  ? "rgba(139, 92, 246, 0.15)"
                                  : "var(--bg-subtle, rgba(255, 255, 255, 0.06))",
                              color: r === "ORG_ADMIN" ? "#a78bfa" : "inherit",
                              border: "1px solid var(--border-color, #27272a)",
                            }}
                          >
                            {r}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <StatusBadge
                        status={u.is_active ? "ACTIVE" : "STORED"}
                        label={u.is_active ? "ACTIVE" : "DEACTIVATED"}
                      />
                    </td>
                    <td className="ac-mono" style={{ fontSize: 12 }}>
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="ac-flex ac-gap-2 ac-items-center" style={{ justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          className="ac-btn"
                          style={{ fontSize: 12, padding: "4px 8px" }}
                          onClick={() => handleOpenEdit(u)}
                        >
                          Edit Roles
                        </button>
                        <button
                          type="button"
                          className="ac-btn"
                          style={{
                            fontSize: 12,
                            padding: "4px 8px",
                            color: u.is_active ? "var(--danger, #ef4444)" : "var(--success, #10b981)",
                          }}
                          onClick={() => handleToggleStatus(u)}
                        >
                          {u.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Role Assignment Modal */}
      {editingUser && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <div className="ac-card" style={{ maxWidth: 480, width: "90%", padding: 24 }}>
            <h3 className="ac-h3" style={{ marginBottom: 4 }}>
              Edit Roles: {editingUser.full_name}
            </h3>
            <p className="ac-text-sm" style={{ opacity: 0.7, marginBottom: 16 }}>
              Select customer tenant roles to assign. Platform administration roles cannot be granted.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
              {AVAILABLE_TENANT_ROLES.map((r) => {
                const checked = selectedRoles.includes(r.value);
                return (
                  <label
                    key={r.value}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "8px 12px",
                      borderRadius: 6,
                      background: checked ? "rgba(59, 130, 246, 0.1)" : "transparent",
                      border: "1px solid var(--border-color, #27272a)",
                      cursor: "pointer",
                      fontSize: 13,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => handleToggleRole(r.value)}
                    />
                    <div>
                      <div style={{ fontWeight: 600 }}>{r.label}</div>
                      <div className="ac-mono" style={{ fontSize: 11, opacity: 0.6 }}>
                        {r.value}
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>

            {modalError && (
              <div
                style={{
                  padding: "8px 12px",
                  background: "rgba(239, 68, 68, 0.15)",
                  color: "var(--danger, #ef4444)",
                  borderRadius: 4,
                  marginBottom: 16,
                  fontSize: 13,
                }}
              >
                ⚠ {modalError}
              </div>
            )}

            <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end" }}>
              <button
                type="button"
                className="ac-btn"
                onClick={() => setEditingUser(null)}
                disabled={modalSaving}
              >
                Cancel
              </button>
              <button
                type="button"
                className="ac-btn ac-btn-primary"
                onClick={handleSaveRoles}
                disabled={modalSaving}
              >
                {modalSaving ? "Saving..." : "Save Roles"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
