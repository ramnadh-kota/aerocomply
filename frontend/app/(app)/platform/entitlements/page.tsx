"use client";

// Platform Admin — Effective Entitlements Explorer.
// Renders the transparent equation:
// Plan + PlanFeature + TenantFeatureOverride + TenantUsageLimit = Effective Tenant Entitlements.
// Backend resolver remains authoritative.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";
import {
  entitlementApi,
  type EntitlementResolutionResponse,
  type TenantFeatureOverrideResponse,
} from "@/lib/api/entitlement";
import {
  DEMO_PLATFORM_ORGANIZATIONS,
  DEMO_PLATFORM_FEATURES,
  getDemoOrganizationEntitlements,
} from "@/lib/demo/demoPlatform";

interface EntitlementExplanationRow {
  feature_key: string;
  name: string;
  category: string;
  planValue: boolean;
  overrideValue: boolean | null;
  overrideReason: string | null;
  effectiveValue: boolean;
  source: "Plan Baseline" | "Tenant Override";
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

export default function PlatformEntitlementsPage() {
  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();

  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [entitlements, setEntitlements] = useState<EntitlementResolutionResponse | null>(null);
  const [overrides, setOverrides] = useState<TenantFeatureOverrideResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  // Load organizations list
  useEffect(() => {
    if (mode === "DEMO") {
      setOrgs(DEMO_PLATFORM_ORGANIZATIONS);
      if (!selectedOrgId && DEMO_PLATFORM_ORGANIZATIONS.length > 0) {
        setSelectedOrgId(DEMO_PLATFORM_ORGANIZATIONS[0].id);
      }
      setLoading(false);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }

    platformApi
      .listOrganizations(accessToken)
      .then((data) => {
        setOrgs(data);
        if (!selectedOrgId && data.length > 0) {
          setSelectedOrgId(data[0].id);
        }
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [mode, accessToken, isAuthenticated]);

  // Load entitlements for selected organization
  useEffect(() => {
    if (!selectedOrgId) return;

    if (mode === "DEMO") {
      setEntitlements(getDemoOrganizationEntitlements(selectedOrgId));
      if (selectedOrgId === "00000000-0000-0000-0000-000000000001") {
        setOverrides([
          {
            id: "50000000-0000-0000-0000-000000000001",
            organization_id: selectedOrgId,
            feature_key: "battery_analytics",
            enabled: true,
            reason: "Enterprise trial request",
            expires_at: null,
            created_at: "2026-02-20T10:15:00Z",
          },
        ]);
      } else {
        setOverrides([]);
      }
      return;
    }

    if (!isAuthenticated || !accessToken) return;

    setLoading(true);
    Promise.allSettled([
      entitlementApi.getEntitlements(accessToken, selectedOrgId),
      entitlementApi.listFeatureOverrides(accessToken, selectedOrgId),
    ])
      .then(([entRes, ovRes]) => {
        if (entRes.status === "fulfilled") setEntitlements(entRes.value);
        else setError(normalizeApiError(entRes.reason));

        if (ovRes.status === "fulfilled") setOverrides(ovRes.value);
      })
      .finally(() => setLoading(false));
  }, [selectedOrgId, mode, accessToken, isAuthenticated]);

  const selectedOrg = orgs.find((o) => o.id === selectedOrgId);

  // Compute explanation matrix
  const explanationRows: EntitlementExplanationRow[] = DEMO_PLATFORM_FEATURES.map((feat) => {
    const override = overrides.find((o) => o.feature_key === feat.feature_key);
    const planEnabled =
      entitlements?.plan_code === "enterprise"
        ? true
        : entitlements?.plan_code === "professional"
        ? feat.plans.includes("professional") || feat.plans.includes("starter")
        : feat.plans.includes("starter");

    const effective =
      entitlements?.resolution_status === "SUSPENDED"
        ? false
        : override
        ? override.enabled
        : planEnabled;

    return {
      feature_key: feat.feature_key,
      name: feat.name,
      category: feat.category,
      planValue: planEnabled,
      overrideValue: override ? override.enabled : null,
      overrideReason: override ? override.reason : null,
      effectiveValue: effective,
      source: override ? "Tenant Override" : "Plan Baseline",
    };
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Entitlements" }]} />

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
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform — Effective Entitlements Explorer</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Inspect why a customer organization has or lacks a capability. Backend resolver remains authoritative.
          </p>
        </div>
        {selectedOrg && (
          <Link className="ac-btn" href={`/platform/organizations/${selectedOrg.id}`}>
            Manage Tenant Overrides →
          </Link>
        )}
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
            Your account does not possess the <code>PLATFORM_MANAGE</code> authority required to view tenant entitlements.
          </p>
        </div>
      ) : (
        <>
          {/* Tenant Selector & Architecture Formula */}
          <div
            className="ac-card"
            style={{
              padding: "var(--ac-space-4)",
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
              <label htmlFor="tenant-select" className="ac-text-sm" style={{ fontWeight: 600 }}>
                Select Tenant Organization:
              </label>
              <select
                id="tenant-select"
                className="ac-select"
                style={{ minWidth: 320 }}
                value={selectedOrgId}
                onChange={(e) => setSelectedOrgId(e.target.value)}
              >
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name} ({o.status})
                  </option>
                ))}
              </select>
            </div>

            {/* Formula Display Box */}
            <div
              style={{
                padding: "12px 16px",
                background: "rgba(255,255,255,0.02)",
                borderRadius: 6,
                border: "1px solid rgba(255,255,255,0.08)",
                fontSize: 13,
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span className="ac-badge" style={{ fontSize: 11 }}>Plan Features</span>
              <span style={{ color: "var(--ac-text-muted)" }}>+</span>
              <span className="ac-badge" style={{ fontSize: 11 }}>Tenant Overrides</span>
              <span style={{ color: "var(--ac-text-muted)" }}>+</span>
              <span className="ac-badge" style={{ fontSize: 11 }}>Usage Limits</span>
              <span style={{ color: "var(--ac-text-muted)" }}>=</span>
              <strong style={{ color: "var(--ac-primary, #60a5fa)" }}>Effective Tenant Entitlements</strong>
            </div>

            {/* Tenant Resolution Summary */}
            {selectedOrg && entitlements && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: 12,
                  paddingTop: 8,
                }}
              >
                <div>
                  <div className="ac-text-sm ac-text-muted">Customer Organization</div>
                  <strong>{selectedOrg.name}</strong>
                </div>
                <div>
                  <div className="ac-text-sm ac-text-muted">Tenant Status</div>
                  <StatusBadge {...genericStatusBadge(selectedOrg.status)} />
                </div>
                <div>
                  <div className="ac-text-sm ac-text-muted">Subscription Plan</div>
                  <strong>{entitlements.plan_name ?? entitlements.plan_code ?? "None"}</strong>
                </div>
                <div>
                  <div className="ac-text-sm ac-text-muted">Resolution State</div>
                  <StatusBadge {...resolutionStatusBadge(entitlements.resolution_status)} />
                </div>
              </div>
            )}
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!selectedOrg || !entitlements}
            emptyMessage="Select an organization above to inspect effective entitlements."
          >
            {entitlements && (
              <div className="ac-card" style={{ padding: 0 }}>
                <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th>Capability Feature</th>
                      <th>Category</th>
                      <th>Plan Baseline</th>
                      <th>Tenant Override</th>
                      <th>Effective Entitlement</th>
                      <th>Resolution Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {explanationRows.map((row) => (
                      <tr key={row.feature_key}>
                        <td>
                          <strong>{row.name}</strong>
                          <div style={{ marginTop: 2 }}>
                            <code style={{ fontSize: 11 }}>{row.feature_key}</code>
                          </div>
                        </td>
                        <td>
                          <span className="ac-badge" style={{ fontSize: 11 }}>
                            {row.category}
                          </span>
                        </td>
                        <td>
                          <StatusBadge
                            status={row.planValue ? "COMPLIANT" : "NON_COMPLIANT"}
                            label={row.planValue ? "ENABLED" : "DISABLED"}
                          />
                        </td>
                        <td>
                          {row.overrideValue !== null ? (
                            <div>
                              <StatusBadge
                                status={row.overrideValue ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={row.overrideValue ? "OVERRIDE: ENABLED" : "OVERRIDE: DISABLED"}
                              />
                              {row.overrideReason && (
                                <div className="ac-text-sm ac-text-muted" style={{ fontSize: 11, marginTop: 2 }}>
                                  {row.overrideReason}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="ac-text-muted">None (Inherits Plan)</span>
                          )}
                        </td>
                        <td>
                          <StatusBadge
                            status={row.effectiveValue ? "COMPLIANT" : "NON_COMPLIANT"}
                            label={row.effectiveValue ? "ENABLED" : "DISABLED"}
                          />
                        </td>
                        <td>
                          <span style={{ fontSize: 12, fontWeight: 500 }}>
                            {row.source}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </RealDataPanel>
        </>
      )}
    </div>
  );
}
