"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantDashboardStats } from "@/lib/api/tenant";
import { DEMO_TENANT_DASHBOARD_STATS } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function TenantDashboardPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [stats, setStats] = useState<TenantDashboardStats | null>(
    isDemo ? DEMO_TENANT_DASHBOARD_STATS : null
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (isDemo) {
      setStats(DEMO_TENANT_DASHBOARD_STATS);
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
      .getDashboard(accessToken)
      .then(setStats)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Administration" }, { label: "Tenant Dashboard" }]}
        eyebrow="TENANT CONTROL PLANE"
        title="Tenant Administration"
        subtitle="Operational governance, workforce, fleet assets, and commercial configuration for your organization."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/invitations" className="ac-btn ac-btn-primary">
              + Invite Member
            </Link>
            <Link href="/tenant/facilities" className="ac-btn">
              Facilities
            </Link>
            <Link href="/tenant/audit" className="ac-btn">
              Audit Trail
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
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 13,
            }}
          >
            <span>
              <strong>DEMO ENVIRONMENT</strong> · Isolated synthetic tenant data for KOTA Aerospace Demo Operations.
            </span>
            <span className="ac-mono" style={{ fontSize: 11, opacity: 0.7 }}>
              DEMO-TENANT-AUTONOMOUS
            </span>
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!stats}
            emptyMessage="No tenant telemetry available."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      {stats && (
        <>
          {/* Attention Items Banner */}
          {stats.attention_items.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              {stats.attention_items.map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "12px 16px",
                    marginBottom: 8,
                    borderRadius: 6,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    background:
                      item.severity === "CRITICAL"
                        ? "rgba(239, 68, 68, 0.1)"
                        : item.severity === "WARNING"
                        ? "rgba(245, 158, 11, 0.1)"
                        : "rgba(59, 130, 246, 0.08)",
                    border: `1px solid ${
                      item.severity === "CRITICAL"
                        ? "rgba(239, 68, 68, 0.3)"
                        : item.severity === "WARNING"
                        ? "rgba(245, 158, 11, 0.3)"
                        : "rgba(59, 130, 246, 0.25)"
                    }`,
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{item.title}</div>
                    <div style={{ fontSize: 13, opacity: 0.85 }}>{item.message}</div>
                  </div>
                  {item.link_href && (
                    <Link href={item.link_href} className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>
                      {item.link_label ?? "Inspect →"}
                    </Link>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Key Metrics Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: 16,
              marginBottom: 24,
            }}
          >
            <div className="ac-card">
              <div className="ac-eyebrow" style={{ marginBottom: 6 }}>
                ORGANIZATION
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
                {stats.organization.name}
              </div>
              <div className="ac-flex ac-gap-2 ac-items-center" style={{ fontSize: 12 }}>
                <StatusBadge
                  status={stats.organization.status === "ACTIVE" ? "ACTIVE" : "STORED"}
                  label={stats.organization.status}
                />
                <span className="ac-mono" style={{ opacity: 0.7 }}>
                  {stats.organization.industry ?? "AEROSPACE"}
                </span>
              </div>
              <div style={{ marginTop: 12, fontSize: 12, borderTop: "1px solid var(--border-color, #27272a)", paddingTop: 8 }}>
                <Link href="/tenant/profile" style={{ color: "var(--primary, #3b82f6)" }}>
                  Organization Profile →
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div className="ac-eyebrow" style={{ marginBottom: 6 }}>
                WORKFORCE
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>
                {stats.active_users_count} <span style={{ fontSize: 14, fontWeight: 400, opacity: 0.7 }}>/ {stats.users_count} total</span>
              </div>
              <div style={{ fontSize: 13, opacity: 0.8 }}>
                {stats.pending_invitations_count} pending invitation{stats.pending_invitations_count === 1 ? "" : "s"}
              </div>
              <div style={{ marginTop: 12, fontSize: 12, borderTop: "1px solid var(--border-color, #27272a)", paddingTop: 8 }}>
                <Link href="/tenant/users" style={{ color: "var(--primary, #3b82f6)" }}>
                  Manage Personnel &amp; Roles →
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div className="ac-eyebrow" style={{ marginBottom: 6 }}>
                FLEET ASSETS
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>
                {stats.fleet_count} <span style={{ fontSize: 14, fontWeight: 400, opacity: 0.7 }}>Total</span>
              </div>
              <div style={{ fontSize: 13, opacity: 0.8 }}>
                {stats.aircraft_count} Aircraft · {stats.drone_count} Drones
              </div>
              <div style={{ marginTop: 12, fontSize: 12, borderTop: "1px solid var(--border-color, #27272a)", paddingTop: 8 }}>
                <Link href="/tenant/fleet" style={{ color: "var(--primary, #3b82f6)" }}>
                  Fleet Administration →
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div className="ac-eyebrow" style={{ marginBottom: 6 }}>
                COMMERCIAL PLAN
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
                {stats.current_plan ?? "STANDARD"}
              </div>
              <div className="ac-flex ac-gap-2 ac-items-center" style={{ fontSize: 12 }}>
                <StatusBadge
                  status={stats.subscription_status === "ACTIVE" ? "ACTIVE" : "STORED"}
                  label={stats.subscription_status ?? "ACTIVE"}
                />
                <span style={{ opacity: 0.7 }}>{stats.effective_features_count} Features Enabled</span>
              </div>
              <div style={{ marginTop: 12, fontSize: 12, borderTop: "1px solid var(--border-color, #27272a)", paddingTop: 8 }}>
                <Link href="/tenant/subscription" style={{ color: "var(--primary, #3b82f6)" }}>
                  View Plan &amp; Entitlements →
                </Link>
              </div>
            </div>
          </div>

          {/* Operational Administration Navigation Cards */}
          <h2 className="ac-h2" style={{ marginBottom: 12 }}>
            Tenant Administration Areas
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
              gap: 16,
              marginBottom: 32,
            }}
          >
            <div className="ac-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>Organization &amp; Profile</div>
                <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>LEGAL &amp; METADATA</span>
              </div>
              <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 12 }}>
                Manage organization legal name, aerospace industry sector classification, primary contacts, and administrative defaults.
              </p>
              <div className="ac-flex ac-gap-2">
                <Link href="/tenant/profile" className="ac-btn" style={{ fontSize: 12 }}>
                  Profile Settings
                </Link>
                <Link href="/tenant/settings" className="ac-btn" style={{ fontSize: 12 }}>
                  Operational Defaults
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>Personnel, Roles &amp; Invitations</div>
                <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>RBAC</span>
              </div>
              <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 12 }}>
                Administer user accounts, assign tenant-scoped operational roles, manage onboarding invitations, and configure workforce teams.
              </p>
              <div className="ac-flex ac-gap-2">
                <Link href="/tenant/users" className="ac-btn" style={{ fontSize: 12 }}>
                  User Directory
                </Link>
                <Link href="/tenant/roles" className="ac-btn" style={{ fontSize: 12 }}>
                  Role Grants
                </Link>
                <Link href="/tenant/invitations" className="ac-btn" style={{ fontSize: 12 }}>
                  Invitations ({stats.pending_invitations_count})
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>Facilities &amp; Fleet Bases</div>
                <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>{stats.facility_count} REGISTERED</span>
              </div>
              <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 12 }}>
                Maintain hangars, maintenance stations, vertiports, and workshops where assets are deployed and serviced.
              </p>
              <div className="ac-flex ac-gap-2">
                <Link href="/tenant/facilities" className="ac-btn" style={{ fontSize: 12 }}>
                  Site Registry
                </Link>
                <Link href="/facilities" className="ac-btn" style={{ fontSize: 12 }}>
                  Operational Facilities Floor
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>Workforce Teams</div>
                <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>{stats.team_count} SQUADS</span>
              </div>
              <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 12 }}>
                Operational squads organized by discipline: Flight Ops, Maintenance &amp; CAMO, Quality Inspection, and Regulatory Compliance.
              </p>
              <div className="ac-flex ac-gap-2">
                <Link href="/tenant/teams" className="ac-btn" style={{ fontSize: 12 }}>
                  View Workforce Squads
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>Entitlements &amp; Usage</div>
                <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>COMMERCIAL</span>
              </div>
              <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 12 }}>
                Inspect effective feature entitlements derived from commercial plan and platform overrides. View verified resource utilization.
              </p>
              <div className="ac-flex ac-gap-2">
                <Link href="/tenant/entitlements" className="ac-btn" style={{ fontSize: 12 }}>
                  Effective Features
                </Link>
                <Link href="/tenant/usage" className="ac-btn" style={{ fontSize: 12 }}>
                  Usage Limits
                </Link>
              </div>
            </div>

            <div className="ac-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>Governance &amp; Audit Trail</div>
                <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>IMMUTABLE</span>
              </div>
              <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 12 }}>
                Inspect tenant-scoped administrative mutations, role reassignments, access revocations, and configuration updates.
              </p>
              <div className="ac-flex ac-gap-2">
                <Link href="/tenant/audit" className="ac-btn" style={{ fontSize: 12 }}>
                  Inspect Audit Trail
                </Link>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
