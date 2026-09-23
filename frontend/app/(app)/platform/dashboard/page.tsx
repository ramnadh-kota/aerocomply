"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type BackendDashboardStats } from "@/lib/api/platform";
import {
  getDemoPlatformStats,
  type PlatformDashboardKPIs,
} from "@/lib/demo/demoPlatform";

export default function PlatformDashboardPage() {
  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();

  const [stats, setStats] = useState<PlatformDashboardKPIs | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  useEffect(() => {
    if (mode === "DEMO") {
      setStats(getDemoPlatformStats());
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

    platformApi
      .getDashboardStats(accessToken)
      .then((data: BackendDashboardStats) => {
        setStats({
          totalOrganizations: data.total_organizations,
          activeOrganizations: data.active_organizations,
          suspendedOrganizations: data.suspended_organizations,
          pendingProvisioning: data.pending_provisioning,
          activeSubscriptions: data.active_subscriptions,
          trialSubscriptions: data.trial_subscriptions,
          totalUsers: data.total_users,
          totalAircraft: data.total_aircraft,
          totalDrones: data.total_drones,
          organizationsByPlan: data.organizations_by_plan.map((p) => ({
            planCode: p.plan_code,
            planName: p.plan_name,
            count: p.count,
          })),
          enabledFeatureDistribution: [
            { featureKey: "drone_fleet_management", name: "Drone Fleet Operations", orgCount: data.total_organizations },
            { featureKey: "work_order_management", name: "Work Order Management", orgCount: data.total_organizations },
            { featureKey: "compliance_reporting", name: "Compliance & Regulatory Register", orgCount: data.total_organizations },
            { featureKey: "audit_logging", name: "Audit Trail & Verification", orgCount: data.total_organizations },
            { featureKey: "release_readiness", name: "Release to Service Readiness", orgCount: data.active_subscriptions },
          ],
          recentActivity: data.recent_activity,
        });
      })
      .catch((err) => {
        setError(normalizeApiError(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [mode, accessToken, isAuthenticated]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Dashboard" }]} />

      <div className="ac-section-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform Control Plane</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Cross-tenant overview: organizations, subscriptions, fleet metrics, and governance activity.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="ac-btn" href="/platform/organizations/provision">
            + Provision Organization
          </Link>
          <Link className="ac-btn" href="/platform/plans">
            Manage Plans
          </Link>
        </div>
      </div>

      {mode === "REAL" && !isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform administrator. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : mode === "REAL" && !isPlatformUser ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)", borderLeft: "4px solid var(--ac-status-non-compliant)" }}>
          <h3 className="ac-h3" style={{ margin: "0 0 6px" }}>Platform Access Denied</h3>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Your account does not possess the <code>PLATFORM_MANAGE</code> authority required to view or administer tenant control planes.
          </p>
        </div>
      ) : (
        <RealDataPanel
          loading={loading}
          error={error}
          isEmpty={!stats}
          emptyMessage="No platform statistics available."
        >
          {stats && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
              {/* Primary KPI Cards */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                  gap: "var(--ac-space-3, 16px)",
                }}
              >
                <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                  <div className="ac-text-sm ac-text-muted">Total Organizations</div>
                  <div style={{ fontSize: 28, fontWeight: 700, margin: "4px 0" }}>
                    {stats.totalOrganizations}
                  </div>
                  <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
                    <span style={{ color: "var(--ac-status-compliant)" }}>
                      ● {stats.activeOrganizations} Active
                    </span>
                    {stats.suspendedOrganizations > 0 && (
                      <span style={{ color: "var(--ac-status-non-compliant)" }}>
                        ● {stats.suspendedOrganizations} Suspended
                      </span>
                    )}
                  </div>
                </div>

                <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                  <div className="ac-text-sm ac-text-muted">Active Subscriptions</div>
                  <div style={{ fontSize: 28, fontWeight: 700, margin: "4px 0" }}>
                    {stats.activeSubscriptions}
                  </div>
                  <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
                    <span style={{ color: "var(--ac-status-compliant)" }}>
                      ● {stats.trialSubscriptions} In Trial
                    </span>
                    <span style={{ color: "var(--ac-text-muted)" }}>
                      ● {stats.totalOrganizations - stats.activeSubscriptions} Without Current Sub
                    </span>
                  </div>
                </div>

                <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                  <div className="ac-text-sm ac-text-muted">Total Managed Fleet</div>
                  <div style={{ fontSize: 28, fontWeight: 700, margin: "4px 0" }}>
                    {stats.totalAircraft + stats.totalDrones}
                  </div>
                  <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
                    <span>✈ {stats.totalAircraft} Aircraft</span>
                    <span>◆ {stats.totalDrones} Drones</span>
                  </div>
                </div>

                <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                  <div className="ac-text-sm ac-text-muted">Platform Users</div>
                  <div style={{ fontSize: 28, fontWeight: 700, margin: "4px 0" }}>
                    {stats.totalUsers}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ac-text-muted)" }}>
                    Across all customer organizations
                  </div>
                </div>
              </div>

              {/* Middle Section: Plans & Feature Adoption */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
                  gap: "var(--ac-space-3, 16px)",
                }}
              >
                {/* Plan Distribution */}
                <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h2 className="ac-h2" style={{ margin: 0 }}>Organizations by Plan</h2>
                    <Link href="/platform/plans" className="ac-text-sm" style={{ color: "var(--ac-primary, #60a5fa)" }}>
                      View Plans →
                    </Link>
                  </div>
                  {stats.organizationsByPlan.length === 0 ? (
                    <p className="ac-text-sm ac-text-muted">No active plans assigned.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {stats.organizationsByPlan.map((p) => {
                        const pct = stats.totalOrganizations > 0
                          ? Math.round((p.count / stats.totalOrganizations) * 100)
                          : 0;
                        return (
                          <div key={p.planCode} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                              <span><strong>{p.planName}</strong> ({p.planCode})</span>
                              <span>{p.count} orgs ({pct}%)</span>
                            </div>
                            <div style={{ height: 6, background: "rgba(255,255,255,0.08)", borderRadius: 3, overflow: "hidden" }}>
                              <div
                                style={{
                                  height: "100%",
                                  width: `${Math.min(pct, 100)}%`,
                                  background: "var(--ac-primary, #3b82f6)",
                                  borderRadius: 3,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Feature Distribution */}
                <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h2 className="ac-h2" style={{ margin: 0 }}>Feature Distribution</h2>
                    <Link href="/platform/features" className="ac-text-sm" style={{ color: "var(--ac-primary, #60a5fa)" }}>
                      Feature Registry →
                    </Link>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {stats.enabledFeatureDistribution.slice(0, 5).map((f) => (
                      <div key={f.featureKey} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13 }}>
                        <div>
                          <strong>{f.name}</strong>
                          <div className="ac-text-sm ac-text-muted" style={{ fontSize: 11 }}>{f.featureKey}</div>
                        </div>
                        <StatusBadge status="COMPLIANT" label={`${f.orgCount} Orgs`} />
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Bottom Section: Recent Activity & Shortcuts */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
                  gap: "var(--ac-space-3, 16px)",
                }}
              >
                {/* Recent Platform Activity */}
                <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h2 className="ac-h2" style={{ margin: 0 }}>Recent Platform Activity</h2>
                    <Link href="/platform/audit" className="ac-text-sm" style={{ color: "var(--ac-primary, #60a5fa)" }}>
                      Full Audit Log →
                    </Link>
                  </div>
                  {stats.recentActivity.length === 0 ? (
                    <p className="ac-text-sm ac-text-muted">No recent platform actions recorded.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {stats.recentActivity.slice(0, 5).map((ev) => (
                        <div
                          key={ev.id}
                          style={{
                            padding: "8px 10px",
                            background: "rgba(255,255,255,0.02)",
                            borderRadius: 4,
                            border: "1px solid rgba(255,255,255,0.06)",
                            fontSize: 12,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                            <strong style={{ color: "var(--ac-primary, #93c5fd)" }}>{ev.action}</strong>
                            <span className="ac-text-muted">{new Date(ev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                          </div>
                          <div className="ac-text-muted" style={{ display: "flex", justifyContent: "space-between" }}>
                            <span>Entity: {ev.entity_type}</span>
                            <span>Org: {ev.organization_id.slice(0, 8)}…</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Quick Navigation Panel */}
                <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                  <h2 className="ac-h2" style={{ margin: "0 0 12px" }}>Control Plane Quick Links</h2>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 8,
                    }}
                  >
                    <Link
                      href="/platform/organizations"
                      className="ac-card"
                      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4, textDecoration: "none" }}
                    >
                      <span style={{ fontSize: 16 }}>⛨</span>
                      <strong style={{ fontSize: 13 }}>Organizations</strong>
                      <span className="ac-text-muted" style={{ fontSize: 11 }}>Manage customer tenants</span>
                    </Link>

                    <Link
                      href="/platform/users"
                      className="ac-card"
                      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4, textDecoration: "none" }}
                    >
                      <span style={{ fontSize: 16 }}>👥</span>
                      <strong style={{ fontSize: 13 }}>Users & Staff</strong>
                      <span className="ac-text-muted" style={{ fontSize: 11 }}>Directory across tenants</span>
                    </Link>

                    <Link
                      href="/platform/subscriptions"
                      className="ac-card"
                      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4, textDecoration: "none" }}
                    >
                      <span style={{ fontSize: 16 }}>💳</span>
                      <strong style={{ fontSize: 13 }}>Subscriptions</strong>
                      <span className="ac-text-muted" style={{ fontSize: 11 }}>Active & past due ledgers</span>
                    </Link>

                    <Link
                      href="/platform/entitlements"
                      className="ac-card"
                      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4, textDecoration: "none" }}
                    >
                      <span style={{ fontSize: 16 }}>🔒</span>
                      <strong style={{ fontSize: 13 }}>Entitlements</strong>
                      <span className="ac-text-muted" style={{ fontSize: 11 }}>Resolution explorer</span>
                    </Link>

                    <Link
                      href="/platform/usage"
                      className="ac-card"
                      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4, textDecoration: "none" }}
                    >
                      <span style={{ fontSize: 16 }}>📊</span>
                      <strong style={{ fontSize: 13 }}>Usage & Limits</strong>
                      <span className="ac-text-muted" style={{ fontSize: 11 }}>Configured tenant ceilings</span>
                    </Link>

                    <Link
                      href="/platform/monitoring"
                      className="ac-card"
                      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4, textDecoration: "none" }}
                    >
                      <span style={{ fontSize: 16 }}>♥</span>
                      <strong style={{ fontSize: 13 }}>Platform Health</strong>
                      <span className="ac-text-muted" style={{ fontSize: 11 }}>Component latency & status</span>
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}
