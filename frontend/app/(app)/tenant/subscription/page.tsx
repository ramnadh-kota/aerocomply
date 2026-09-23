"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { entitlementApi, type EntitlementResolutionResponse } from "@/lib/api/entitlement";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function TenantSubscriptionPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [entitlements, setEntitlements] = useState<EntitlementResolutionResponse | null>(null);
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (isDemo) {
      setLoading(false);
      return;
    }
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
  }, [accessToken, isAuthenticated, isDemo]);

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Plan & Subscription" },
        ]}
        eyebrow="COMMERCIAL AGREEMENT"
        title="Commercial Plan &amp; Subscription"
        subtitle="View your organization's active commercial plan, renewal terms, and capability allowances."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/entitlements" className="ac-btn ac-btn-primary">
              Feature Entitlements Matrix →
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
            <strong>DEMO MODE</strong> · Enterprise Tier active with unified fixed-wing and UAV drone operational modules.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!entitlements}
            emptyMessage="No active subscription on record."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
        {/* Plan Summary Card */}
        <div className="ac-card">
          <div className="ac-eyebrow" style={{ marginBottom: 4 }}>
            COMMERCIAL TIER
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
            {entitlements?.plan_name ?? entitlements?.plan_code ?? "ENTERPRISE"}
          </div>
          <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginBottom: 16 }}>
            <StatusBadge
              status={
                entitlements?.subscription_status === "ACTIVE" || isDemo
                  ? "ACTIVE"
                  : "STORED"
              }
              label={entitlements?.subscription_status ?? "ACTIVE"}
            />
            <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>
              ANNUAL / ENTERPRISE SLA
            </span>
          </div>

          <p className="ac-text-sm" style={{ opacity: 0.8, marginBottom: 20 }}>
            Includes multi-fleet operations, continuing airworthiness management (CAMO), drone UAV mission flight logs, regulatory pre-audits, and RII inspection workflows.
          </p>

          <div
            style={{
              padding: "12px",
              background: "var(--bg-subtle, rgba(255, 255, 255, 0.03))",
              border: "1px solid var(--border-color, #27272a)",
              borderRadius: 6,
              fontSize: 12,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Billing Engine State</div>
            <div style={{ opacity: 0.8 }}>
              Billing is <strong>PLATFORM-MANAGED / DIRECT INVOICE</strong>. Self-service credit card billing is not enabled for enterprise aerospace compliance tiers.
            </div>
          </div>
        </div>

        {/* Entitlements Summary Card */}
        <div className="ac-card">
          <div className="ac-eyebrow" style={{ marginBottom: 4 }}>
            CAPABILITY ACCESS
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 12 }}>
            Effective Feature Allowances
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
            {Object.entries(entitlements?.effective_features ?? {
              drone_fleet_management: true,
              work_order_management: true,
              compliance_audit_suite: true,
              airworthiness_management: true,
              flight_logging: true,
              procurement_management: true,
            }).map(([feat, enabled]) => (
              <div
                key={feat}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "6px 8px",
                  background: "var(--bg-subtle, rgba(255, 255, 255, 0.02))",
                  borderRadius: 4,
                  fontSize: 13,
                }}
              >
                <span className="ac-mono" style={{ fontSize: 12 }}>
                  {feat}
                </span>
                <StatusBadge
                  status={enabled ? "ACTIVE" : "STORED"}
                  label={enabled ? "ENABLED" : "DISABLED"}
                />
              </div>
            ))}
          </div>

          <div style={{ textAlign: "right" }}>
            <Link href="/tenant/entitlements" className="ac-btn" style={{ fontSize: 12 }}>
              Inspect Full Entitlement Equation →
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
