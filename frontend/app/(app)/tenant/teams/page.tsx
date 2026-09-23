"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantTeam } from "@/lib/api/tenant";
import { DEMO_TENANT_TEAMS } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function TenantTeamsPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [teams, setTeams] = useState<TenantTeam[]>(
    isDemo ? DEMO_TENANT_TEAMS : []
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (isDemo) {
      setTeams(DEMO_TENANT_TEAMS);
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
      .listTeams(accessToken)
      .then(setTeams)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Workforce Teams" },
        ]}
        eyebrow="WORKFORCE STRUCTURE"
        title="Workforce Teams &amp; Squads"
        subtitle="Operational teams aligned by aerospace discipline across flight ops, maintenance, quality, and compliance."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/users" className="ac-btn ac-btn-primary">
              Manage Personnel &amp; Roles →
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
            <strong>DEMO MODE</strong> · Showing synthetic functional workforce squads for KOTA Aerospace Demo Operations.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={teams.length === 0}
            emptyMessage="No workforce teams found."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
          gap: 20,
          marginBottom: 32,
        }}
      >
        {teams.map((team) => (
          <div key={team.id} className="ac-card" style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
              <div>
                <h3 className="ac-h3" style={{ fontSize: 17, marginBottom: 2 }}>
                  {team.name}
                </h3>
                <span className="ac-mono" style={{ fontSize: 11, opacity: 0.6 }}>
                  LEAD ROLE: {team.lead_role}
                </span>
              </div>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  padding: "3px 8px",
                  borderRadius: 4,
                  background: "var(--bg-subtle, rgba(255, 255, 255, 0.06))",
                  border: "1px solid var(--border-color, #27272a)",
                }}
              >
                {team.member_count} member{team.member_count === 1 ? "" : "s"}
              </span>
            </div>

            <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 16 }}>
              {team.description}
            </p>

            <div
              style={{
                marginTop: "auto",
                borderTop: "1px solid var(--border-color, #27272a)",
                paddingTop: 12,
              }}
            >
              <div className="ac-eyebrow" style={{ marginBottom: 8, fontSize: 10 }}>
                ASSIGNED PERSONNEL
              </div>
              {team.members.length === 0 ? (
                <div className="ac-text-sm" style={{ opacity: 0.5, fontStyle: "italic" }}>
                  No personnel currently assigned to this operational squad.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {team.members.map((m) => (
                    <div
                      key={m.user_id}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: 13,
                        padding: "4px 8px",
                        background: "var(--bg-subtle, rgba(255, 255, 255, 0.02))",
                        borderRadius: 4,
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600 }}>{m.full_name}</div>
                        <div className="ac-mono" style={{ fontSize: 11, opacity: 0.6 }}>
                          {m.email}
                        </div>
                      </div>
                      <span
                        className="ac-mono"
                        style={{
                          fontSize: 10,
                          padding: "1px 5px",
                          borderRadius: 3,
                          background: "rgba(59, 130, 246, 0.12)",
                          color: "var(--primary, #3b82f6)",
                          border: "1px solid rgba(59, 130, 246, 0.25)",
                        }}
                      >
                        {m.role}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
