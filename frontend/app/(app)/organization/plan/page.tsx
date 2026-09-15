"use client";

// M17.3 — tenant-facing "Plan & Entitlements" view. REAL-mode only: shows
// exactly what the backend's entitlement resolver (app/services/
// entitlement_service.py, via GET /api/v1/entitlements) returns for the
// signed-in user's own organization. Nothing here is hardcoded — no plan
// name, feature list, or limit is invented client-side; an org with no
// subscription simply shows an honest empty/NO_SUBSCRIPTION state.
//
// This page is read-only by design (see M17.3's Phase 8: tenant admins can
// see their commercial state but never alter it from here) — changing plan/
// subscription/entitlement state is a platform-admin-only operation
// (app/(app)/platform/organizations/[organizationId]/subscriptions).

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { entitlementApi, type EntitlementResolutionResponse } from "@/lib/api/entitlement";

const RESOLUTION_STATUS_LABEL: Record<string, string> = {
  ACTIVE: "Active",
  INACTIVE_PLAN: "Plan Inactive",
  SUSPENDED: "Organization Suspended",
  NO_SUBSCRIPTION: "No Active Subscription",
  AMBIGUOUS: "Subscription Conflict",
  INVALID: "Invalid",
};

export default function OrganizationPlanPage() {
  const { accessToken, isAuthenticated } = useSession();
  const [entitlements, setEntitlements] = useState<EntitlementResolutionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    entitlementApi
      .getMyEntitlements(accessToken)
      .then(setEntitlements)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, isAuthenticated]);

  const enabledFeatures = entitlements
    ? Object.entries(entitlements.effective_features).filter(([, enabled]) => enabled)
    : [];
  const disabledFeatures = entitlements
    ? Object.entries(entitlements.effective_features).filter(([, enabled]) => !enabled)
    : [];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Organization", href: "/organization" }, { label: "Plan & Subscription" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Plan & Subscription</h1>
          <p className="ac-subtitle">Your organization&apos;s current commercial plan, subscription status, and enabled capabilities — read-only.</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Sign in to view your organization&apos;s plan. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel
          loading={loading}
          error={error}
          isEmpty={false}
          emptyMessage=""
        >
          {entitlements && (
            <>
              <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <span className="ac-eyebrow">Current Plan</span>
                    <p className="ac-text-sm" style={{ margin: "4px 0 0", fontWeight: 600 }}>
                      {entitlements.plan_name ?? "No plan assigned"}
                    </p>
                  </div>
                  <StatusBadge
                    {...genericStatusBadge(entitlements.resolution_status)}
                    label={RESOLUTION_STATUS_LABEL[entitlements.resolution_status] ?? entitlements.resolution_status}
                  />
                </div>
                {entitlements.subscription_status && (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
                    Subscription status: <span className="ac-mono">{entitlements.subscription_status}</span>
                  </p>
                )}
                {entitlements.resolution_status === "NO_SUBSCRIPTION" && (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    No active subscription is on file for your organization. Contact your Kota Aerospace account
                    representative to set up or change your plan.
                  </p>
                )}
                {entitlements.resolution_status === "SUSPENDED" && (
                  <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                    Your organization has been suspended by the platform administrator. Contact support.
                  </p>
                )}
              </div>

              <div className="ac-grid-2" style={{ gap: 16 }}>
                <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                  <h2 className="ac-h2" style={{ marginBottom: 10 }}>Enabled Capabilities</h2>
                  {enabledFeatures.length === 0 ? (
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No capabilities are currently enabled.</p>
                  ) : (
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {enabledFeatures.map(([key]) => (
                        <li key={key} className="ac-text-sm">{key}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                  <h2 className="ac-h2" style={{ marginBottom: 10 }}>Not Included in Current Plan</h2>
                  {disabledFeatures.length === 0 ? (
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Every known capability is enabled.</p>
                  ) : (
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {disabledFeatures.map(([key]) => (
                        <li key={key} className="ac-text-sm ac-text-muted">{key}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              {entitlements.usage_limits.length > 0 && (
                <div className="ac-card ac-section" style={{ padding: 0 }}>
                  <h2 className="ac-h2" style={{ padding: "var(--ac-space-4) var(--ac-space-4) 0" }}>Plan Limits</h2>
                  <div className="ac-table-desktop" style={{ overflowX: "auto" }}>
                    <table className="ac-table">
                      <thead>
                        <tr>
                          <th>Feature</th>
                          <th>Limit</th>
                          <th>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {entitlements.usage_limits.map((limit) => (
                          <tr key={`${limit.feature_key}-${limit.limit_key}`}>
                            <td>{limit.feature_key}</td>
                            <td>{limit.limit_key}</td>
                            <td>{limit.is_unlimited ? "Unlimited" : (limit.limit_value ?? "—")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="ac-row-cards">
                    {entitlements.usage_limits.map((limit) => (
                      <div className="ac-row-card" key={`${limit.feature_key}-${limit.limit_key}`}>
                        <div className="ac-row-card-field">
                          <span className="ac-row-card-field-label">Feature</span>
                          <span>{limit.feature_key}</span>
                        </div>
                        <div className="ac-row-card-field">
                          <span className="ac-row-card-field-label">Limit</span>
                          <span>{limit.limit_key}</span>
                        </div>
                        <div className="ac-row-card-field">
                          <span className="ac-row-card-field-label">Value</span>
                          <span>{limit.is_unlimited ? "Unlimited" : (limit.limit_value ?? "—")}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}
