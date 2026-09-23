"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantRoleInfo } from "@/lib/api/tenant";
import { DEMO_TENANT_ROLES, DEMO_TENANT_USERS } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function TenantRolesPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [roles, setRoles] = useState<TenantRoleInfo[]>(isDemo ? DEMO_TENANT_ROLES : []);
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [expandedRole, setExpandedRole] = useState<string | null>(null);

  useEffect(() => {
    if (isDemo) {
      setRoles(DEMO_TENANT_ROLES);
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
      .listRoles(accessToken)
      .then(setRoles)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Roles & Permissions" },
        ]}
        eyebrow="ACCESS CONTROL"
        title="Roles &amp; Permission Grants"
        subtitle="Inspect supported operational roles, permission assignments, and authority boundaries."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/users" className="ac-btn">
              ← Personnel Directory
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
            <strong>DEMO MODE</strong> · Viewing catalog of tenant-assignable roles.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={roles.length === 0}
            emptyMessage="No roles available."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
          gap: 16,
          marginBottom: 24,
        }}
      >
        {roles.map((r) => {
          const isExpanded = expandedRole === r.role_name;
          const assignedCount = isDemo
            ? DEMO_TENANT_USERS.filter((u) => u.roles.includes(r.role_name)).length
            : null;

          return (
            <div key={r.role_name} className="ac-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16 }}>{r.display_name}</div>
                  <div className="ac-mono" style={{ fontSize: 12, opacity: 0.6 }}>
                    {r.role_name}
                  </div>
                </div>
                <StatusBadge status="ACTIVE" label="SYSTEM ROLE" />
              </div>

              <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 16, minHeight: 40 }}>
                {r.description}
              </p>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  fontSize: 12,
                  padding: "8px 0",
                  borderTop: "1px solid var(--border-color, #27272a)",
                  borderBottom: "1px solid var(--border-color, #27272a)",
                  marginBottom: 12,
                }}
              >
                <span>
                  <strong>{r.permissions.length}</strong> Granted Permissions
                </span>
                {assignedCount !== null && (
                  <span>
                    <strong>{assignedCount}</strong> Users Assigned
                  </span>
                )}
              </div>

              <button
                type="button"
                className="ac-btn"
                style={{ fontSize: 12, width: "100%", textAlign: "center" }}
                onClick={() => setExpandedRole(isExpanded ? null : r.role_name)}
              >
                {isExpanded ? "Hide Permissions ▲" : "View Permissions ▼"}
              </button>

              {isExpanded && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 10,
                    background: "var(--bg-subtle, rgba(0, 0, 0, 0.2))",
                    borderRadius: 4,
                    maxHeight: 180,
                    overflowY: "auto",
                  }}
                >
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {r.permissions.map((p) => (
                      <span
                        key={p}
                        className="ac-mono"
                        style={{
                          fontSize: 11,
                          padding: "2px 6px",
                          borderRadius: 3,
                          background: "var(--bg-card, #18181b)",
                          border: "1px solid var(--border-color, #27272a)",
                        }}
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div
        className="ac-card"
        style={{
          background: "var(--bg-subtle, rgba(255, 255, 255, 0.02))",
          border: "1px dashed var(--border-color, #27272a)",
        }}
      >
        <h3 className="ac-h3" style={{ fontSize: 14, marginBottom: 4 }}>
          Tenant RBAC Guardrails
        </h3>
        <p className="ac-text-sm" style={{ opacity: 0.8, margin: 0 }}>
          Customer tenant roles are bound strictly to your organization boundary. Tenant administrators cannot assign platform staff privileges (<span className="ac-mono">PLATFORM_ADMIN</span> or <span className="ac-mono">PLATFORM_STAFF</span>) or alter system permission definitions.
        </p>
      </div>
    </div>
  );
}
