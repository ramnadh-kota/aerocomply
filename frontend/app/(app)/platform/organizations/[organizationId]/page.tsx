"use client";

// Platform Admin — Organization Tenant Control Center.
// Supports both REAL mode (backend-authoritative) and DEMO mode (deterministic synthetic data).
// Organized into 7 structured tabs:
// Overview | Users | Subscription | Entitlements | Usage | Audit | Provisioning

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  platformApi,
  type BackendPlatformOrganization,
  type PlatformUser,
} from "@/lib/api/platform";
import {
  entitlementApi,
  type EntitlementResolutionResponse,
  type TenantFeatureOverrideResponse,
  type TenantUsageLimitResponse,
  getOverrideExpirationState,
} from "@/lib/api/entitlement";
import { subscriptionApi, type SubscriptionResponse } from "@/lib/api/subscription";
import { auditApi, type AuditEventResponse } from "@/lib/api/audit";
import {
  getDemoOrganization,
  getDemoOrganizationUsers,
  getDemoOrganizationSubscriptions,
  getDemoOrganizationEntitlements,
  DEMO_PLATFORM_AUDIT_EVENTS,
  DEMO_PLATFORM_FEATURES,
} from "@/lib/demo/demoPlatform";

export const TABS = [
  "Overview",
  "Users",
  "Subscription",
  "Entitlements",
  "Usage",
  "Audit",
  "Provisioning",
] as const;

export type OrganizationTab = (typeof TABS)[number];

interface FeatureRow {
  feature_key: string;
  name: string;
  enabled: boolean;
  planEnabled: boolean;
  source: "Plan" | "Tenant Override";
  override?: TenantFeatureOverrideResponse;
}

function subscriptionStatusBadge(status: string) {
  const map: Record<string, Parameters<typeof StatusBadge>[0]["status"]> = {
    TRIALING: "REVIEW_REQUIRED",
    ACTIVE: "COMPLIANT",
    PAST_DUE: "REVIEW_REQUIRED",
    CANCELED: "UNKNOWN",
    SCHEDULED: "INSUFFICIENT_DATA",
  };
  return { status: map[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

function resolutionStatusBadge(status: string) {
  const map: Record<string, Parameters<typeof StatusBadge>[0]["status"]> = {
    ACTIVE: "COMPLIANT",
    INACTIVE_PLAN: "REVIEW_REQUIRED",
    SUSPENDED: "NON_COMPLIANT",
    NO_SUBSCRIPTION: "INSUFFICIENT_DATA",
    AMBIGUOUS: "REVIEW_REQUIRED",
    INVALID: "NON_COMPLIANT",
  };
  return { status: map[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

export default function PlatformOrganizationDetailPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}) {
  const resolvedParams = use(params);
  const organizationId = resolvedParams.organizationId;

  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();

  const [activeTab, setActiveTab] = useState<OrganizationTab>("Overview");

  // State
  const [org, setOrg] = useState<BackendPlatformOrganization | null>(null);
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionResponse[]>([]);
  const [entitlements, setEntitlements] = useState<EntitlementResolutionResponse | null>(null);
  const [overrides, setOverrides] = useState<TenantFeatureOverrideResponse[]>([]);
  const [limits, setLimits] = useState<TenantUsageLimitResponse[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventResponse[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // Invite Admin State
  const [showInviteAdmin, setShowInviteAdmin] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteFullName, setInviteFullName] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteError, setInviteError] = useState<NormalizedApiError | null>(null);
  const [inviteSuccess, setInviteSuccess] = useState(false);

  // Lifecycle & Status Action
  const [confirmSuspend, setConfirmSuspend] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);

  // Feature Override Form State
  const [showCreateOverride, setShowCreateOverride] = useState(false);
  const [overrideFeatureKey, setOverrideFeatureKey] = useState("");
  const [overrideEnabled, setOverrideEnabled] = useState(true);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideExpiresAt, setOverrideExpiresAt] = useState("");
  const [overrideBusy, setOverrideBusy] = useState(false);
  const [overrideError, setOverrideError] = useState<NormalizedApiError | null>(null);

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  const loadData = () => {
    if (mode === "DEMO") {
      const demoOrg = getDemoOrganization(organizationId) ?? {
        id: organizationId,
        name: "Demo Organization",
        status: "ACTIVE",
        industry: "DRONE_UAV",
        created_at: new Date().toISOString(),
        user_count: 4,
        aircraft_count: 2,
        drone_count: 6,
      };
      setOrg(demoOrg);
      setUsers(getDemoOrganizationUsers(organizationId));
      setSubscriptions(getDemoOrganizationSubscriptions(organizationId));
      setEntitlements(getDemoOrganizationEntitlements(organizationId));
      setAuditEvents(
        DEMO_PLATFORM_AUDIT_EVENTS.filter((e) => e.organization_id === organizationId || true).slice(0, 8)
      );
      setOverrides([
        {
          id: "50000000-0000-0000-0000-000000000001",
          organization_id: organizationId,
          feature_key: "battery_analytics",
          enabled: true,
          reason: "Trial authorization for drone fleet evaluation",
          expires_at: null,
          created_at: "2026-02-20T10:15:00Z",
        },
      ]);
      setLimits([
        {
          id: "60000000-0000-0000-0000-000000000001",
          organization_id: organizationId,
          feature_key: "fleet_limits",
          limit_key: "max_drones",
          limit_value: 20,
          is_unlimited: false,
          created_at: "2026-01-15T00:00:00Z",
          updated_at: "2026-01-15T00:00:00Z",
        },
      ]);
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
      platformApi.getOrganization(accessToken, organizationId),
      platformApi.listOrganizationUsers(accessToken, organizationId),
      subscriptionApi.listForOrganization(accessToken, organizationId),
      entitlementApi.getEntitlements(accessToken, organizationId),
      entitlementApi.listFeatureOverrides(accessToken, organizationId),
      entitlementApi.listUsageLimits(accessToken, organizationId),
      auditApi.listAuditEvents(accessToken, { organization_id: organizationId, limit: 20 }),
    ]).then(([orgRes, userRes, subRes, entRes, ovRes, limRes, audRes]) => {
      if (orgRes.status === "fulfilled") setOrg(orgRes.value);
      else setError(normalizeApiError(orgRes.reason));

      if (userRes.status === "fulfilled") setUsers(userRes.value);
      if (subRes.status === "fulfilled") setSubscriptions(subRes.value);
      if (entRes.status === "fulfilled") setEntitlements(entRes.value);
      if (ovRes.status === "fulfilled") setOverrides(ovRes.value);
      if (limRes.status === "fulfilled") setLimits(limRes.value);
      if (audRes.status === "fulfilled") setAuditEvents(audRes.value.items);

      setLoading(false);
    });
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, accessToken, isAuthenticated, organizationId]);

  const handleToggleOrgStatus = () => {
    if (mode === "DEMO") {
      if (org) {
        setOrg({ ...org, status: org.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE" });
      }
      setConfirmSuspend(false);
      return;
    }

    if (!accessToken || !org) return;
    setActionBusy(true);

    const call =
      org.status === "ACTIVE"
        ? platformApi.suspendOrganization(accessToken, org.id)
        : platformApi.activateOrganization(accessToken, org.id);

    call
      .then((updated) => {
        setOrg(updated);
        setConfirmSuspend(false);
        loadData();
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setActionBusy(false));
  };

  const handleInviteAdmin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !inviteFullName.trim()) return;

    if (mode === "DEMO") {
      const syntheticUser: PlatformUser = {
        id: `30000000-0000-0000-0000-${String(Date.now()).slice(-12)}`,
        organization_id: organizationId,
        email: inviteEmail.trim(),
        full_name: inviteFullName.trim(),
        is_active: true,
        roles: ["ORG_ADMIN"],
        created_at: new Date().toISOString(),
      };
      setUsers([syntheticUser, ...users]);
      setInviteSuccess(true);
      setTimeout(() => {
        setShowInviteAdmin(false);
        setInviteSuccess(false);
        setInviteEmail("");
        setInviteFullName("");
      }, 1000);
      return;
    }

    if (!accessToken) return;
    setInviteBusy(true);
    setInviteError(null);

    platformApi
      .inviteOrganizationAdmin(accessToken, organizationId, {
        email: inviteEmail.trim(),
        full_name: inviteFullName.trim(),
      })
      .then(() => {
        setInviteSuccess(true);
        loadData();
        setTimeout(() => {
          setShowInviteAdmin(false);
          setInviteSuccess(false);
          setInviteEmail("");
          setInviteFullName("");
        }, 1200);
      })
      .catch((err) => setInviteError(normalizeApiError(err)))
      .finally(() => setInviteBusy(false));
  };

  const handleCreateOverride = (e: React.FormEvent) => {
    e.preventDefault();
    if (!overrideFeatureKey.trim()) return;

    if (mode === "DEMO") {
      const newOv: TenantFeatureOverrideResponse = {
        id: `50000000-0000-0000-0000-${String(Date.now()).slice(-12)}`,
        organization_id: organizationId,
        feature_key: overrideFeatureKey.trim(),
        enabled: overrideEnabled,
        reason: overrideReason.trim() || null,
        expires_at: overrideExpiresAt ? new Date(overrideExpiresAt).toISOString() : null,
        created_at: new Date().toISOString(),
      };
      setOverrides([newOv, ...overrides]);
      setShowCreateOverride(false);
      setOverrideFeatureKey("");
      setOverrideReason("");
      setOverrideExpiresAt("");
      return;
    }

    if (!accessToken) return;
    setOverrideBusy(true);
    setOverrideError(null);

    entitlementApi
      .createFeatureOverride(accessToken, organizationId, {
        feature_key: overrideFeatureKey.trim(),
        enabled: overrideEnabled,
        reason: overrideReason.trim() || undefined,
        expires_at: overrideExpiresAt ? new Date(overrideExpiresAt).toISOString() : undefined,
      })
      .then(() => {
        setShowCreateOverride(false);
        setOverrideFeatureKey("");
        setOverrideReason("");
        setOverrideExpiresAt("");
        loadData();
      })
      .catch((err) => setOverrideError(normalizeApiError(err)))
      .finally(() => setOverrideBusy(false));
  };

  const handleRemoveOverride = (featureKey: string) => {
    if (mode === "DEMO") {
      setOverrides(overrides.filter((o) => o.feature_key !== featureKey));
      return;
    }
    if (!accessToken) return;
    entitlementApi
      .removeFeatureOverride(accessToken, organizationId, featureKey)
      .then(loadData)
      .catch((err) => setError(normalizeApiError(err)));
  };

  // Build 3-source feature rows
  const featureRows: FeatureRow[] = DEMO_PLATFORM_FEATURES.map((feat) => {
    const override = overrides.find((o) => o.feature_key === feat.feature_key);
    const planEnabled =
      entitlements?.plan_code === "enterprise"
        ? true
        : entitlements?.plan_code === "professional"
        ? feat.plans.includes("professional") || feat.plans.includes("starter")
        : feat.plans.includes("starter");

    const effective = override ? override.enabled : planEnabled;

    return {
      feature_key: feat.feature_key,
      name: feat.name,
      enabled: effective,
      planEnabled,
      source: override ? "Tenant Override" : "Plan",
      override,
    };
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/dashboard" },
          { label: "Organizations", href: "/platform/organizations" },
          { label: org?.name ?? organizationId },
        ]}
      />

      {/* Header with Title and Quick Actions */}
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
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 className="ac-h1" style={{ margin: 0 }}>
              {org?.name ?? "Organization Control"}
            </h1>
            {org && <StatusBadge {...genericStatusBadge(org.status)} />}
          </div>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Tenant ID: <code>{organizationId}</code> · Created:{" "}
            {org ? new Date(org.created_at).toLocaleDateString() : "—"}
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {org && (
            <button
              className="ac-btn"
              onClick={() => {
                if (org.status === "ACTIVE") setConfirmSuspend(true);
                else handleToggleOrgStatus();
              }}
              disabled={actionBusy}
            >
              {org.status === "ACTIVE" ? "Suspend Organization" : "Activate Organization"}
            </button>
          )}
          <Link className="ac-btn" href={`/platform/organizations/${organizationId}/subscriptions`}>
            Manage Subscriptions →
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
        <RealDataPanel loading={loading} error={error} isEmpty={!org} emptyMessage="Organization not found.">
          {org && (
            <>
              {/* Tab Navigation Navigation Bar */}
              <div
                style={{
                  display: "flex",
                  gap: 4,
                  borderBottom: "1px solid rgba(255,255,255,0.1)",
                  paddingBottom: 0,
                  overflowX: "auto",
                }}
              >
                {TABS.map((tab) => {
                  const isActive = activeTab === tab;
                  return (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      style={{
                        background: "none",
                        border: "none",
                        borderBottom: isActive ? "2px solid var(--ac-primary, #3b82f6)" : "2px solid transparent",
                        color: isActive ? "var(--ac-text-primary, #ffffff)" : "var(--ac-text-muted, #94a3b8)",
                        padding: "10px 16px",
                        fontSize: 14,
                        fontWeight: isActive ? 600 : 500,
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {tab}
                      {tab === "Users" && ` (${users.length})`}
                      {tab === "Entitlements" && overrides.length > 0 && ` (${overrides.length})`}
                    </button>
                  );
                })}
              </div>

              {/* TAB 1: OVERVIEW */}
              {activeTab === "Overview" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
                      gap: 16,
                    }}
                  >
                    {/* Organization Metadata Card */}
                    <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                      <h2 className="ac-h2" style={{ margin: "0 0 12px" }}>Tenant Metadata</h2>
                      <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Organization Name</span>
                          <strong>{org.name}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Tenant UUID</span>
                          <code>{org.id}</code>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Status</span>
                          <StatusBadge {...genericStatusBadge(org.status)} />
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Vertical Industry</span>
                          <span className="ac-badge">{org.industry ?? "NOT SPECIFIED"}</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Tenant Created</span>
                          <span>{new Date(org.created_at).toLocaleString()}</span>
                        </div>
                      </div>
                    </div>

                    {/* Commercial & Entitlement Card */}
                    <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                      <h2 className="ac-h2" style={{ margin: "0 0 12px" }}>Commercial Snapshot</h2>
                      <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Assigned Plan</span>
                          <strong>{entitlements?.plan_name ?? entitlements?.plan_code ?? "None"}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Subscription State</span>
                          {entitlements?.subscription_status ? (
                            <StatusBadge {...subscriptionStatusBadge(entitlements.subscription_status)} />
                          ) : (
                            <span className="ac-text-muted">No Subscription</span>
                          )}
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Resolution Status</span>
                          {entitlements ? (
                            <StatusBadge {...resolutionStatusBadge(entitlements.resolution_status)} />
                          ) : (
                            <span className="ac-text-muted">—</span>
                          )}
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Enabled Features</span>
                          <strong>
                            {entitlements
                              ? Object.values(entitlements.effective_features).filter(Boolean).length
                              : 0}{" "}
                            features
                          </strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Custom Overrides</span>
                          <span>{overrides.length} active</span>
                        </div>
                      </div>
                    </div>

                    {/* Fleet & Resource Metrics */}
                    <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                      <h2 className="ac-h2" style={{ margin: "0 0 12px" }}>Fleet & Users</h2>
                      <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Tenant Users</span>
                          <strong>{org.user_count} members</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Fixed-Wing Aircraft</span>
                          <strong>✈ {org.aircraft_count} aircraft</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Unmanned Drones</span>
                          <strong>◆ {org.drone_count ?? 0} drones</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span className="ac-text-muted">Primary Admin</span>
                          <span>{users[0]?.full_name ?? "No admin provisioned"}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Recent Activity for this tenant */}
                  <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                      <h2 className="ac-h2" style={{ margin: 0 }}>Recent Activity for this Tenant</h2>
                      <button className="ac-btn" style={{ fontSize: 12 }} onClick={() => setActiveTab("Audit")}>
                        View Full Audit Log →
                      </button>
                    </div>
                    {auditEvents.length === 0 ? (
                      <p className="ac-text-sm ac-text-muted">No audit events recorded for this organization.</p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {auditEvents.slice(0, 5).map((ev) => (
                          <div
                            key={ev.id}
                            style={{
                              padding: "8px 12px",
                              background: "rgba(255,255,255,0.02)",
                              borderRadius: 4,
                              border: "1px solid rgba(255,255,255,0.06)",
                              fontSize: 12,
                              display: "flex",
                              justifyContent: "space-between",
                            }}
                          >
                            <div>
                              <strong style={{ color: "var(--ac-primary, #93c5fd)" }}>{ev.action}</strong>
                              <span className="ac-text-muted" style={{ marginLeft: 8 }}>
                                Entity: {ev.entity_type}
                              </span>
                            </div>
                            <span className="ac-text-muted">{new Date(ev.created_at).toLocaleString()}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 2: USERS */}
              {activeTab === "Users" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                    <div>
                      <h2 className="ac-h2" style={{ margin: 0 }}>Tenant Personnel & Administrators</h2>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                        Inspecting tenant users without cross-tenant operational data exposure.
                      </p>
                    </div>
                    <button className="ac-btn" onClick={() => setShowInviteAdmin(!showInviteAdmin)}>
                      {showInviteAdmin ? "Cancel" : "+ Invite Org Admin"}
                    </button>
                  </div>

                  {showInviteAdmin && (
                    <div className="ac-card" style={{ padding: "var(--ac-space-3)", background: "rgba(255,255,255,0.03)" }}>
                      <h3 className="ac-h3" style={{ margin: "0 0 10px", fontSize: 14 }}>
                        Invite Administrator by Email (Passwordless Onboarding)
                      </h3>
                      <form onSubmit={handleInviteAdmin} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                        <div>
                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Full Name</label>
                          <input
                            className="ac-input"
                            style={{ width: 220 }}
                            placeholder="Alex Morgan"
                            value={inviteFullName}
                            onChange={(e) => setInviteFullName(e.target.value)}
                            required
                          />
                        </div>
                        <div>
                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Work Email</label>
                          <input
                            type="email"
                            className="ac-input"
                            style={{ width: 260 }}
                            placeholder="admin@tenant.com"
                            value={inviteEmail}
                            onChange={(e) => setInviteEmail(e.target.value)}
                            required
                          />
                        </div>
                        <button className="ac-btn" type="submit" disabled={inviteBusy}>
                          {inviteBusy ? "Sending Invitation…" : "Send Invitation"}
                        </button>
                        {inviteSuccess && (
                          <span className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>
                            ✓ Invitation sent successfully.
                          </span>
                        )}
                        {inviteError && (
                          <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>
                            {inviteError.message}
                          </span>
                        )}
                      </form>
                    </div>
                  )}

                  <div className="ac-card" style={{ padding: 0 }}>
                    <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th>User</th>
                          <th>Email</th>
                          <th>Roles</th>
                          <th>Status</th>
                          <th>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {users.length === 0 ? (
                          <tr>
                            <td colSpan={5} style={{ textAlign: "center", padding: 24 }} className="ac-text-muted">
                              No users found in this organization.
                            </td>
                          </tr>
                        ) : (
                          users.map((u) => (
                            <tr key={u.id}>
                              <td><strong>{u.full_name}</strong></td>
                              <td>{u.email}</td>
                              <td>
                                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                                  {u.roles.map((r) => (
                                    <span key={r} className="ac-badge" style={{ fontSize: 11 }}>
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
                              <td className="ac-text-muted">{new Date(u.created_at).toLocaleDateString()}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 3: SUBSCRIPTION */}
              {activeTab === "Subscription" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <h2 className="ac-h2" style={{ margin: 0 }}>Subscription History & Plan State</h2>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                        Historical immutable ledger of tenant subscription periods.
                      </p>
                    </div>
                    <Link
                      className="ac-btn"
                      href={`/platform/organizations/${organizationId}/subscriptions`}
                    >
                      + Schedule New Subscription
                    </Link>
                  </div>

                  <div className="ac-card" style={{ padding: 0 }}>
                    <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th>Plan ID</th>
                          <th>Status</th>
                          <th>Starts At</th>
                          <th>Ends At</th>
                          <th>Created At</th>
                        </tr>
                      </thead>
                      <tbody>
                        {subscriptions.length === 0 ? (
                          <tr>
                            <td colSpan={5} style={{ textAlign: "center", padding: 24 }} className="ac-text-muted">
                              No subscription records found for this organization.
                            </td>
                          </tr>
                        ) : (
                          subscriptions.map((s) => (
                            <tr key={s.id}>
                              <td><code>{s.plan_id}</code></td>
                              <td>
                                <StatusBadge {...subscriptionStatusBadge(s.status)} />
                              </td>
                              <td>{new Date(s.starts_at).toLocaleDateString()}</td>
                              <td>{s.ends_at ? new Date(s.ends_at).toLocaleDateString() : "Open-ended"}</td>
                              <td className="ac-text-muted">{new Date(s.created_at).toLocaleDateString()}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 4: ENTITLEMENTS */}
              {activeTab === "Entitlements" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                    <div>
                      <h2 className="ac-h2" style={{ margin: 0 }}>Effective Tenant Entitlements</h2>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                        Base Plan Features + Tenant Feature Overrides = Effective Entitlement.
                      </p>
                    </div>
                    <button className="ac-btn" onClick={() => setShowCreateOverride(!showCreateOverride)}>
                      {showCreateOverride ? "Cancel" : "+ Add Feature Override"}
                    </button>
                  </div>

                  {showCreateOverride && (
                    <div className="ac-card" style={{ padding: "var(--ac-space-3)", background: "rgba(255,255,255,0.03)" }}>
                      <h3 className="ac-h3" style={{ margin: "0 0 10px", fontSize: 14 }}>
                        Create Tenant Feature Override
                      </h3>
                      <form onSubmit={handleCreateOverride} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        <div>
                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Feature Key</label>
                          <input
                            className="ac-input"
                            style={{ width: "100%", maxWidth: 400 }}
                            placeholder="e.g. battery_analytics"
                            value={overrideFeatureKey}
                            onChange={(e) => setOverrideFeatureKey(e.target.value)}
                            required
                          />
                        </div>
                        <div>
                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Override State</label>
                          <select
                            className="ac-select"
                            value={overrideEnabled ? "true" : "false"}
                            onChange={(e) => setOverrideEnabled(e.target.value === "true")}
                          >
                            <option value="true">Enabled (Allow)</option>
                            <option value="false">Disabled (Deny)</option>
                          </select>
                        </div>
                        <div>
                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>Reason / Justification</label>
                          <input
                            className="ac-input"
                            style={{ width: "100%", maxWidth: 500 }}
                            placeholder="Commercial trial exception approved by staff"
                            value={overrideReason}
                            onChange={(e) => setOverrideReason(e.target.value)}
                          />
                        </div>
                        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                          <button className="ac-btn" type="submit" disabled={overrideBusy}>
                            {overrideBusy ? "Applying…" : "Save Override"}
                          </button>
                          {overrideError && (
                            <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>
                              {overrideError.message}
                            </span>
                          )}
                        </div>
                      </form>
                    </div>
                  )}

                  <div className="ac-card" style={{ padding: 0 }}>
                    <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th>Capability Feature</th>
                          <th>Plan Value</th>
                          <th>Tenant Override</th>
                          <th>Effective Entitlement</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {featureRows.map((f) => (
                          <tr key={f.feature_key}>
                            <td>
                              <strong>{f.name}</strong>
                              <div className="ac-text-sm ac-text-muted" style={{ fontSize: 11 }}>{f.feature_key}</div>
                            </td>
                            <td>
                              <StatusBadge
                                status={f.planEnabled ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={f.planEnabled ? "Included" : "Excluded"}
                              />
                            </td>
                            <td>
                              {f.override ? (
                                <div>
                                  <StatusBadge
                                    status={f.override.enabled ? "COMPLIANT" : "NON_COMPLIANT"}
                                    label={f.override.enabled ? "Override: Allowed" : "Override: Blocked"}
                                  />
                                  {f.override.reason && (
                                    <div className="ac-text-sm ac-text-muted" style={{ fontSize: 11 }}>
                                      {f.override.reason}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="ac-text-muted">None (Inherited)</span>
                              )}
                            </td>
                            <td>
                              <StatusBadge
                                status={f.enabled ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={f.enabled ? "ENABLED" : "DISABLED"}
                              />
                            </td>
                            <td>
                              {f.override && (
                                <button
                                  className="ac-btn"
                                  style={{ fontSize: 11, padding: "2px 8px" }}
                                  onClick={() => handleRemoveOverride(f.feature_key)}
                                >
                                  Remove Override
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 5: USAGE */}
              {activeTab === "Usage" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <h2 className="ac-h2" style={{ margin: 0 }}>Tenant Usage Ceilings & Tracking</h2>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                      Explicit tracking status. Dimensions without live telemetry metering are labeled <strong>NOT TRACKED</strong>.
                    </p>
                  </div>

                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                      gap: 12,
                    }}
                  >
                    <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                      <div className="ac-text-sm ac-text-muted">User Seats</div>
                      <div style={{ fontSize: 24, fontWeight: 700, margin: "4px 0" }}>{org.user_count}</div>
                      <div className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>● TRACKED (Real DB)</div>
                    </div>

                    <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                      <div className="ac-text-sm ac-text-muted">Aircraft Units</div>
                      <div style={{ fontSize: 24, fontWeight: 700, margin: "4px 0" }}>{org.aircraft_count}</div>
                      <div className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>● TRACKED (Real DB)</div>
                    </div>

                    <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                      <div className="ac-text-sm ac-text-muted">Drone Fleet Units</div>
                      <div style={{ fontSize: 24, fontWeight: 700, margin: "4px 0" }}>{org.drone_count ?? 0}</div>
                      <div className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>● TRACKED (Real DB)</div>
                    </div>

                    <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                      <div className="ac-text-sm ac-text-muted">Storage & Artifacts</div>
                      <div style={{ fontSize: 24, fontWeight: 700, margin: "4px 0" }}>—</div>
                      <div className="ac-text-sm ac-text-muted">○ NOT TRACKED</div>
                    </div>

                    <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                      <div className="ac-text-sm ac-text-muted">API Queries</div>
                      <div style={{ fontSize: 24, fontWeight: 700, margin: "4px 0" }}>—</div>
                      <div className="ac-text-sm ac-text-muted">○ NOT TRACKED</div>
                    </div>
                  </div>

                  <h3 className="ac-h3" style={{ margin: "8px 0 0" }}>Configured Usage Ceilings (TenantUsageLimit)</h3>
                  <div className="ac-card" style={{ padding: 0 }}>
                    <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th>Feature</th>
                          <th>Dimension (Limit Key)</th>
                          <th>Configured Ceiling</th>
                          <th>Tracking Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {limits.length === 0 ? (
                          <tr>
                            <td colSpan={4} style={{ textAlign: "center", padding: 20 }} className="ac-text-muted">
                              No explicit limit ceilings configured. Operating under standard plan allowances.
                            </td>
                          </tr>
                        ) : (
                          limits.map((l) => (
                            <tr key={l.id}>
                              <td><code>{l.feature_key}</code></td>
                              <td>{l.limit_key}</td>
                              <td>{l.is_unlimited ? "Unlimited" : l.limit_value}</td>
                              <td>
                                <span className="ac-badge" style={{ fontSize: 11 }}>
                                  CONFIGURED
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 6: AUDIT */}
              {activeTab === "Audit" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <h2 className="ac-h2" style={{ margin: 0 }}>Organization Audit Trail</h2>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                      Immutable ledger of administrative actions and tenant lifecycle changes.
                    </p>
                  </div>

                  <div className="ac-card" style={{ padding: 0 }}>
                    <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr>
                          <th>Timestamp</th>
                          <th>Action</th>
                          <th>Entity Type</th>
                          <th>Entity ID</th>
                          <th>Metadata</th>
                        </tr>
                      </thead>
                      <tbody>
                        {auditEvents.length === 0 ? (
                          <tr>
                            <td colSpan={5} style={{ textAlign: "center", padding: 24 }} className="ac-text-muted">
                              No audit records found for this organization.
                            </td>
                          </tr>
                        ) : (
                          auditEvents.map((e) => (
                            <tr key={e.id}>
                              <td className="ac-text-muted" style={{ whiteSpace: "nowrap" }}>
                                {new Date(e.created_at).toLocaleString()}
                              </td>
                              <td>
                                <strong style={{ color: "var(--ac-primary, #93c5fd)" }}>{e.action}</strong>
                              </td>
                              <td>{e.entity_type}</td>
                              <td><code>{e.entity_id ? e.entity_id.slice(0, 8) + "…" : "—"}</code></td>
                              <td>
                                <code style={{ fontSize: 11 }}>
                                  {JSON.stringify(e.event_metadata ?? {})}
                                </code>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 7: PROVISIONING */}
              {activeTab === "Provisioning" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <h2 className="ac-h2" style={{ margin: 0 }}>Tenant Onboarding & Admin Credentials</h2>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                      Inspect onboarding state, resend invitation emails, or revoke pending invitations.
                    </p>
                  </div>

                  <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                          <strong>Organization Admin Onboarding State</strong>
                          <div className="ac-text-sm ac-text-muted">
                            {users.length > 0
                              ? `Admin user ${users[0].email} is registered.`
                              : "No organization admin user found."}
                          </div>
                        </div>
                        {users.length > 0 && (
                          <StatusBadge
                            status={users[0].is_active ? "COMPLIANT" : "REVIEW_REQUIRED"}
                            label={users[0].is_active ? "Active Member" : "Invitation Pending"}
                          />
                        )}
                      </div>

                      {users.length > 0 && (
                        <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                          <button
                            className="ac-btn"
                            onClick={() => {
                              if (mode === "REAL" && accessToken) {
                                platformApi.resendAdminInvitation(accessToken, users[0].id);
                              }
                              alert("Invitation email resent.");
                            }}
                          >
                            Resend Invitation Email
                          </button>
                          <button
                            className="ac-btn"
                            style={{ color: "var(--ac-status-non-compliant)" }}
                            onClick={() => {
                              if (confirm("Revoke pending invitation for this admin?")) {
                                if (mode === "REAL" && accessToken) {
                                  platformApi.revokeAdminInvitation(accessToken, users[0].id);
                                }
                                alert("Invitation revoked.");
                              }
                            }}
                          >
                            Revoke Pending Invitation
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </RealDataPanel>
      )}

      {/* Confirmation Dialog for Suspension */}
      <ConfirmDialog
        open={confirmSuspend}
        title={`Suspend ${org?.name ?? "Organization"}?`}
        body={`This immediately suspends operational access for "${org?.name ?? ""}". Every user in this tenant will be refused login until reactivated. This action is fully reversible.`}
        confirmLabel="Suspend Organization"
        cancelLabel="Cancel"
        busy={actionBusy}
        onConfirm={handleToggleOrgStatus}
        onCancel={() => setConfirmSuspend(false)}
      />
    </div>
  );
}
