"use client";

// Platform Admin — Organization Entitlement Control Center. REAL-mode only,
// same as the organization list page: this is cross-tenant platform staff
// tooling, not a customer-facing feature, so there is no demo dataset.
// Backend enforces PLATFORM_MANAGE on every call here — this page hiding
// itself from non-platform-admin users (and rendering a permission-denied
// state on 403) is a UX convenience, never the security boundary.
//
// READ-ONLY: this page never mutates organization status, subscription,
// plan, features, overrides, or usage limits. It only displays what the
// M2 resolver (via the M3 API) and M6 override API already return.
//
// Effective feature state always comes directly from
// `effective_features` in the entitlement resolution response — it is
// never recomputed here by combining plan + override data client-side.
// That would duplicate the M2 resolver. Overrides are used ONLY to derive
// a provenance label ("Source: Tenant Override" vs "Source: Plan") for
// display, per the M7.1 design decision not to add a backend provenance
// field.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";
import {
  entitlementApi,
  type EntitlementResolutionResponse,
  type TenantFeatureOverrideResponse,
} from "@/lib/api/entitlement";

interface FeatureRow {
  feature_key: string;
  enabled: boolean;
  source: "Plan" | "Tenant Override" | "Not Determined";
  override?: TenantFeatureOverrideResponse;
}

/**
 * An override is "applicable" (currently in effect) using the exact same
 * expiry semantics as the M2 resolver
 * (app/services/entitlement_service.py: `o.expires_at is None or
 * o.expires_at > resolved_as_of`) — null expiry means it never expires,
 * otherwise it must still be in the future relative to now. This is a
 * presence/expiry check on already-resolved data, not a re-implementation
 * of the resolution algorithm.
 */
function isOverrideApplicable(o: TenantFeatureOverrideResponse, now: Date): boolean {
  if (!o.expires_at) return true;
  const expires = new Date(o.expires_at);
  if (Number.isNaN(expires.getTime())) return false;
  return expires.getTime() > now.getTime();
}

function buildFeatureRows(
  entitlements: EntitlementResolutionResponse,
  overrides: TenantFeatureOverrideResponse[]
): FeatureRow[] {
  const now = new Date();
  const overridesByFeature = new Map<string, TenantFeatureOverrideResponse>();
  for (const o of overrides) {
    if (isOverrideApplicable(o, now)) {
      // If multiple applicable overrides exist for the same feature (should
      // not happen under normal M6 semantics), prefer the most recently
      // created rather than guessing further.
      const existing = overridesByFeature.get(o.feature_key);
      if (!existing || new Date(o.created_at) > new Date(existing.created_at)) {
        overridesByFeature.set(o.feature_key, o);
      }
    }
  }

  return Object.entries(entitlements.effective_features).map(([feature_key, enabled]) => {
    const override = overridesByFeature.get(feature_key);
    return {
      feature_key,
      enabled,
      source: override ? "Tenant Override" : "Plan",
      override,
    };
  });
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

function RealOrganizationDetail({ organizationId }: { organizationId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [org, setOrg] = useState<BackendPlatformOrganization | null>(null);
  const [orgError, setOrgError] = useState<NormalizedApiError | null>(null);
  const [entitlements, setEntitlements] = useState<EntitlementResolutionResponse | null>(null);
  const [entitlementsError, setEntitlementsError] = useState<NormalizedApiError | null>(null);
  const [overrides, setOverrides] = useState<TenantFeatureOverrideResponse[] | null>(null);
  const [overridesError, setOverridesError] = useState<NormalizedApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setOrgError(null);
    setEntitlementsError(null);
    setOverridesError(null);

    Promise.allSettled([
      platformApi.getOrganization(accessToken, organizationId),
      entitlementApi.getEntitlements(accessToken, organizationId),
      entitlementApi.listFeatureOverrides(accessToken, organizationId),
    ]).then(([orgResult, entResult, ovResult]) => {
      if (cancelled) return;
      if (orgResult.status === "fulfilled") setOrg(orgResult.value);
      else setOrgError(normalizeApiError(orgResult.reason));

      if (entResult.status === "fulfilled") setEntitlements(entResult.value);
      else setEntitlementsError(normalizeApiError(entResult.reason));

      if (ovResult.status === "fulfilled") setOverrides(ovResult.value);
      else setOverridesError(normalizeApiError(ovResult.reason));

      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [accessToken, isAuthenticated, organizationId]);

  const featureRows = entitlements && overrides ? buildFeatureRows(entitlements, overrides) : [];

  const featureColumns: Column<FeatureRow>[] = [
    { key: "feature", header: "Feature", render: (r) => <span style={{ wordBreak: "break-word" }}>{r.feature_key}</span> },
    {
      key: "state",
      header: "Effective State",
      render: (r) => <StatusBadge status={r.enabled ? "TRUE" : "FALSE"} label={r.enabled ? "Enabled" : "Disabled"} />,
    },
    {
      key: "source",
      header: "Source",
      render: (r) => (
        <span className="ac-text-sm">
          Source: {r.source}
          {r.override?.reason ? ` — ${r.override.reason}` : ""}
        </span>
      ),
    },
  ];

  const overrideColumns: Column<TenantFeatureOverrideResponse>[] = [
    { key: "feature", header: "Feature", render: (o) => <span style={{ wordBreak: "break-word" }}>{o.feature_key}</span> },
    {
      key: "state",
      header: "Override State",
      render: (o) => <StatusBadge status={o.enabled ? "TRUE" : "FALSE"} label={o.enabled ? "Enabled" : "Disabled"} />,
    },
    { key: "reason", header: "Reason", render: (o) => <span style={{ wordBreak: "break-word" }}>{o.reason ?? "—"}</span> },
    {
      key: "expires",
      header: "Expires",
      render: (o) => {
        if (!o.expires_at) return "Never";
        const expires = new Date(o.expires_at);
        const applicable = isOverrideApplicable(o, new Date());
        return (
          <span>
            {expires.toLocaleString()}
            {!applicable && (
              <>
                {" "}
                <StatusBadge status="UNKNOWN" label="Expired" />
              </>
            )}
          </span>
        );
      },
    },
  ];

  const limitColumns: Column<EntitlementResolutionResponse["usage_limits"][number]>[] = [
    { key: "feature", header: "Feature", render: (l) => <span style={{ wordBreak: "break-word" }}>{l.feature_key}</span> },
    { key: "limit_key", header: "Limit", render: (l) => l.limit_key },
    {
      key: "value",
      header: "Configured Value",
      render: (l) => (l.is_unlimited ? <StatusBadge status="UNKNOWN" label="Unlimited" /> : String(l.limit_value ?? "—")),
    },
  ];

  if (!isAuthenticated) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
        </p>
      </div>
    );
  }

  // A 403 on the org fetch (or entitlements fetch) means this signed-in user
  // is not a platform admin for this resource — surface a clear
  // permission-denied state rather than a generic error or a crash. Backend
  // authorization (PLATFORM_MANAGE) remains the actual security boundary;
  // this is UX only.
  const forbidden = orgError?.kind === "forbidden" || entitlementsError?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Organizations", href: "/platform/organizations" },
          { label: org?.name ?? organizationId },
        ]}
      />

      {loading ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Loading from the connected backend…</p>
        </div>
      ) : forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view this organization&apos;s entitlement data.
          </p>
        </div>
      ) : orgError && orgError.kind === "not_found" ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>{orgError.message}</p>
        </div>
      ) : (
        <>
          <div className="ac-section-header">
            <div>
              <h1 className="ac-h1">{org?.name ?? "Organization"}</h1>
              <p className="ac-subtitle">Organization ID: {organizationId}</p>
            </div>
            <Link className="ac-btn" href={`/platform/organizations/${organizationId}/subscriptions`}>
              Manage Subscription
            </Link>
          </div>

          {orgError && (
            <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Organization details failed to load: {orgError.message}
              </p>
            </div>
          )}

          {org && (
            <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <h2 className="ac-h2">Organization</h2>
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center" }}>
                <StatusBadge {...genericStatusBadge(org.status)} />
                <span className="ac-text-sm ac-text-muted">
                  Created {new Date(org.created_at).toLocaleDateString()} · {org.user_count} users · {org.aircraft_count} aircraft
                </span>
              </div>
            </section>
          )}

          <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between", flexWrap: "wrap", alignItems: "center" }}>
              <h2 className="ac-h2">Subscription</h2>
              <Link className="ac-btn" href={`/platform/organizations/${organizationId}/subscriptions`}>
                Subscription Administration
              </Link>
            </div>
            {entitlementsError ? (
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Subscription data failed to load: {entitlementsError.message}
              </p>
            ) : !entitlements ? (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No data.</p>
            ) : entitlements.resolution_status === "NO_SUBSCRIPTION" ? (
              <div className="ac-flex ac-gap-2" style={{ alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                <p className="ac-text-sm" style={{ margin: 0 }}>No Active Subscription</p>
                <Link className="ac-btn" href={`/platform/organizations/${organizationId}/subscriptions`}>
                  Create Subscription →
                </Link>
              </div>
            ) : entitlements.resolution_status === "AMBIGUOUS" ? (
              <p className="ac-text-sm" style={{ margin: 0 }}>Subscription Configuration Ambiguous — {entitlements.reason}</p>
            ) : entitlements.subscription_status ? (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center" }}>
                <StatusBadge {...subscriptionStatusBadge(entitlements.subscription_status)} />
                <span className="ac-text-sm">
                  Plan: {entitlements.plan_name ?? entitlements.plan_code ?? "—"}
                </span>
              </div>
            ) : (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No subscription information available.</p>
            )}
          </section>

          <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <h2 className="ac-h2">Resolution Status</h2>
            {entitlements ? (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                <StatusBadge {...resolutionStatusBadge(entitlements.resolution_status)} />
                <span className="ac-text-sm">{entitlements.reason}</span>
              </div>
            ) : (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Unavailable.</p>
            )}
            {entitlements?.resolution_status === "SUSPENDED" && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                This reflects the organization&apos;s operational suspension, which is independent of the underlying
                subscription&apos;s billing status.
              </p>
            )}
            {entitlements?.resolution_status === "INACTIVE_PLAN" && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                The assigned plan is inactive. Feature values below still reflect what the backend currently returns.
              </p>
            )}
            {entitlements?.resolution_status === "INVALID" && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                Entitlement configuration for this organization could not be safely resolved.
              </p>
            )}
          </section>

          <section className="ac-card ac-section" style={{ padding: 0 }}>
            <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) 0" }}>
              <h2 className="ac-h2">Effective Entitlements</h2>
            </div>
            <RealDataPanel
              loading={false}
              error={entitlementsError}
              isEmpty={!entitlementsError && featureRows.length === 0}
              emptyMessage="No effective features are configured for this organization."
            >
              <div className="ac-table-desktop">
                <DataTable columns={featureColumns} rows={featureRows} />
              </div>
              <div className="ac-row-cards">
                {featureRows.map((r) => (
                  <div className="ac-row-card" key={r.feature_key}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Feature</span>
                      <strong style={{ wordBreak: "break-word" }}>{r.feature_key}</strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Effective State</span>
                      <StatusBadge status={r.enabled ? "TRUE" : "FALSE"} label={r.enabled ? "Enabled" : "Disabled"} />
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Source</span>
                      <span>Source: {r.source}</span>
                    </div>
                  </div>
                ))}
              </div>
            </RealDataPanel>
          </section>

          <section className="ac-card ac-section" style={{ padding: 0 }}>
            <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) 0" }}>
              <h2 className="ac-h2">Feature Override Context</h2>
              <p className="ac-text-sm ac-text-muted">Read-only. Overrides are managed elsewhere; this lists what currently exists.</p>
            </div>
            <RealDataPanel
              loading={false}
              error={overridesError}
              isEmpty={!overridesError && (overrides?.length ?? 0) === 0}
              emptyMessage="No feature overrides configured for this organization."
            >
              <div className="ac-table-desktop">
                <DataTable columns={overrideColumns} rows={overrides ?? []} />
              </div>
              <div className="ac-row-cards">
                {(overrides ?? []).map((o) => (
                  <div className="ac-row-card" key={o.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Feature</span>
                      <strong style={{ wordBreak: "break-word" }}>{o.feature_key}</strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Override State</span>
                      <StatusBadge status={o.enabled ? "TRUE" : "FALSE"} label={o.enabled ? "Enabled" : "Disabled"} />
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Reason</span>
                      <span style={{ wordBreak: "break-word" }}>{o.reason ?? "—"}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Expires</span>
                      <span>{o.expires_at ? new Date(o.expires_at).toLocaleString() : "Never"}</span>
                    </div>
                  </div>
                ))}
              </div>
            </RealDataPanel>
          </section>

          <section className="ac-card ac-section" style={{ padding: 0 }}>
            <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) 0" }}>
              <h2 className="ac-h2">Usage Limits</h2>
              <p className="ac-text-sm ac-text-muted">Configured limits only — no consumption/usage metering exists yet.</p>
            </div>
            <RealDataPanel
              loading={false}
              error={entitlementsError}
              isEmpty={!entitlementsError && (entitlements?.usage_limits.length ?? 0) === 0}
              emptyMessage="No usage limits configured for this organization."
            >
              <div className="ac-table-desktop">
                <DataTable columns={limitColumns} rows={entitlements?.usage_limits ?? []} />
              </div>
              <div className="ac-row-cards">
                {(entitlements?.usage_limits ?? []).map((l, idx) => (
                  <div className="ac-row-card" key={`${l.feature_key}-${l.limit_key}-${idx}`}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Feature</span>
                      <strong style={{ wordBreak: "break-word" }}>{l.feature_key}</strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Limit</span>
                      <span>{l.limit_key}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Configured Value</span>
                      {l.is_unlimited ? <StatusBadge status="UNKNOWN" label="Unlimited" /> : <span>{l.limit_value ?? "—"}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </RealDataPanel>
          </section>
        </>
      )}
    </div>
  );
}

export default function PlatformOrganizationDetailPage({ params }: { params: { organizationId: string } }) {
  return <RealOrganizationDetail organizationId={params.organizationId} />;
}
