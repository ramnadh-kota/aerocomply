"use client";

// Platform Admin — Users & Platform Staff Directory.
// Inspects tenant personnel and platform operators across organizations.
// Server-authoritative; no silent or arbitrary role impersonation.

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type PlatformUser, type BackendPlatformOrganization } from "@/lib/api/platform";
import { DEMO_PLATFORM_USERS, DEMO_PLATFORM_ORGANIZATIONS } from "@/lib/demo/demoPlatform";

export default function PlatformUsersPage() {
  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();

  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedOrgId, setSelectedOrgId] = useState<string>("ALL");
  const [selectedRole, setSelectedRole] = useState<string>("ALL");

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  useEffect(() => {
    if (mode === "DEMO") {
      setUsers(DEMO_PLATFORM_USERS);
      setOrgs(DEMO_PLATFORM_ORGANIZATIONS);
      setLoading(false);
      setError(null);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    Promise.allSettled([
      platformApi.listPlatformUsers(accessToken),
      platformApi.listOrganizations(accessToken),
    ]).then(([usersRes, orgsRes]) => {
      if (usersRes.status === "fulfilled") setUsers(usersRes.value);
      else setError(normalizeApiError(usersRes.reason));

      if (orgsRes.status === "fulfilled") setOrgs(orgsRes.value);
      setLoading(false);
    });
  }, [mode, accessToken, isAuthenticated]);

  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      if (selectedOrgId !== "ALL" && u.organization_id !== selectedOrgId) return false;
      if (selectedRole !== "ALL" && !u.roles.includes(selectedRole)) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = u.full_name.toLowerCase().includes(q);
        const matchesEmail = u.email.toLowerCase().includes(q);
        const matchesOrg = (u.organization_name ?? "").toLowerCase().includes(q);
        if (!matchesName && !matchesEmail && !matchesOrg) return false;
      }
      return true;
    });
  }, [users, selectedOrgId, selectedRole, searchQuery]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Users & Staff" }]} />

      <div
        className="ac-section-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div>
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform — Users & Staff Directory</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Inspect users, primary administrators, and platform staff across all organizations.
          </p>
        </div>
      </div>

      {/* Security Governance Notice */}
      <div
        className="ac-card"
        style={{
          padding: "12px 16px",
          background: "rgba(59, 130, 246, 0.05)",
          borderLeft: "4px solid var(--ac-primary, #3b82f6)",
          fontSize: 13,
          lineHeight: 1.4,
        }}
      >
        <strong>Impersonation & Tenant Isolation Policy:</strong> Arbitrary role impersonation is strictly disabled.
        Platform operators inspect user metadata through authorized platform endpoints (<code>PLATFORM_MANAGE</code>)
        without accessing customer operational sessions or credentials.
      </div>

      {mode === "REAL" && !isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : mode === "REAL" && !isPlatformUser ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)", borderLeft: "4px solid var(--ac-status-non-compliant)" }}>
          <h3 className="ac-h3" style={{ margin: "0 0 6px" }}>Platform Access Denied</h3>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Your account does not possess the <code>PLATFORM_MANAGE</code> authority required to view platform user directories.
          </p>
        </div>
      ) : (
        <>
          {/* Filters & Search */}
          <div
            className="ac-card"
            style={{
              padding: "var(--ac-space-3)",
              display: "flex",
              flexWrap: "wrap",
              gap: 12,
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", flex: 1 }}>
              <input
                className="ac-input"
                style={{ minWidth: 260, flex: "1 1 260px" }}
                placeholder="Search user by name, email, or org…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search users"
              />

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="ac-text-sm ac-text-muted">Organization:</span>
                <select
                  className="ac-select"
                  value={selectedOrgId}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                  aria-label="Filter by organization"
                >
                  <option value="ALL">All Organizations</option>
                  {orgs.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="ac-text-sm ac-text-muted">Role:</span>
                <select
                  className="ac-select"
                  value={selectedRole}
                  onChange={(e) => setSelectedRole(e.target.value)}
                  aria-label="Filter by role"
                >
                  <option value="ALL">All Roles</option>
                  <option value="PLATFORM_ADMIN">PLATFORM_ADMIN</option>
                  <option value="PLATFORM_STAFF">PLATFORM_STAFF</option>
                  <option value="ORG_ADMIN">ORG_ADMIN</option>
                  <option value="CAMO_MANAGER">CAMO_MANAGER</option>
                  <option value="CHIEF_PILOT">CHIEF_PILOT</option>
                  <option value="MAINTENANCE_ENGINEER">MAINTENANCE_ENGINEER</option>
                  <option value="VIEWER">VIEWER</option>
                </select>
              </div>
            </div>

            <div className="ac-text-sm ac-text-muted">
              Showing {filteredUsers.length} of {users.length} users
            </div>
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={filteredUsers.length === 0}
            emptyMessage="No users match the active search or filter criteria."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Customer Organization</th>
                    <th>Assigned Roles</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.full_name}</strong>
                        <div className="ac-text-sm ac-text-muted" style={{ fontSize: 11 }}>
                          {u.email}
                        </div>
                      </td>
                      <td>
                        <Link href={`/platform/organizations/${u.organization_id}`}>
                          {u.organization_name ?? u.organization_id}
                        </Link>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {u.roles.map((r) => (
                            <span
                              key={r}
                              className="ac-badge"
                              style={{
                                fontSize: 11,
                                background: r.startsWith("PLATFORM") ? "rgba(59, 130, 246, 0.15)" : undefined,
                                borderColor: r.startsWith("PLATFORM") ? "rgba(59, 130, 246, 0.4)" : undefined,
                              }}
                            >
                              {r}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td>
                        <StatusBadge
                          status={u.is_active ? "COMPLIANT" : "NON_COMPLIANT"}
                          label={u.is_active ? "Active" : "Inactive"}
                        />
                      </td>
                      <td className="ac-text-muted" style={{ fontSize: 12 }}>
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <Link
                          className="ac-btn"
                          style={{ fontSize: 11, padding: "2px 8px" }}
                          href={`/platform/organizations/${u.organization_id}`}
                        >
                          View Org →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}
