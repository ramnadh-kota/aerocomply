"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { entitlementApi, type EntitlementResolutionResponse } from "@/lib/api/entitlement";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const FEATURE_CATALOG = [
  {
    key: "drone_fleet_management",
    name: "Drone Fleet Operations",
    category: "FLIGHT_OPS",
    description: "Multi-drone registry, battery cycles, deployment readiness, and autonomous flight logging.",
  },
  {
    key: "work_order_management",
    name: "MRO Work Orders & Tasks",
    category: "MAINTENANCE",
    description: "Scheduled maintenance, task card execution, RII inspector sign-offs, and return-to-service checks.",
  },
  {
    key: "compliance_audit_suite",
    name: "Regulatory Pre-Audit & Compliance",
    category: "COMPLIANCE",
    description: "Assessment intelligence, regulatory registers (CAA / EASA / FAA), and non-compliance finding tracking.",
  },
  {
    key: "airworthiness_management",
    name: "Continuing Airworthiness (CAMO)",
    category: "AIRWORTHINESS",
    description: "Continuing airworthiness tracking, defect discrepancy tracking, and MEL item deferrals.",
  },
  {
    key: "procurement_management",
    name: "Aero Procurement & Parts Stock",
    category: "LOGISTICS",
    description: "Warehouse stock management, procurement approvals, and vendor part availability.",
  },
  {
    key: "flight_logging",
    name: "Operational Mission & Flight Records",
    category: "FLIGHT_OPS",
    description: "Pilot flight records, mission flight hours, cycle counters, and airframe telemetry history.",
  },
  {
    key: "lisa_ai_copilot",
    name: "LISA AI Assistant",
    category: "INTELLIGENCE",
    description: "Domain-constrained AI copilot providing deterministic maintenance guidance without hallucination.",
  },
  {
    key: "analytics_advanced",
    name: "Advanced Operational Analytics",
    category: "INTELLIGENCE",
    description: "Turnaround time (TAT) risk forecasting, technician capacity analytics, and fleet reliability trends.",
  },
];

export default function TenantEntitlementsPage() {
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

  const effectiveMap: Record<string, boolean> = useMemo(() => {
    if (isDemo || !entitlements) {
      return {
        drone_fleet_management: true,
        work_order_management: true,
        compliance_audit_suite: true,
        airworthiness_management: true,
        flight_logging: true,
        procurement_management: true,
        lisa_ai_copilot: true,
        analytics_advanced: true,
      };
    }
    return entitlements.effective_features;
  }, [isDemo, entitlements]);

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Plan & Subscription", href: "/tenant/subscription" },
          { label: "Feature Entitlements" },
        ]}
        eyebrow="CAPABILITY MATRIX"
        title="Effective Feature Entitlements"
        subtitle="Authoritative resolution of operational capabilities enabled for your organization."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/subscription" className="ac-btn">
              ← Commercial Subscription
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
            <strong>DEMO MODE</strong> · Viewing all active enterprise capabilities for KOTA Aerospace Demo Operations.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={Object.keys(effectiveMap).length === 0}
            emptyMessage="No features resolved."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      <div
        className="ac-card"
        style={{
          padding: 14,
          marginBottom: 20,
          background: "var(--bg-subtle, rgba(255, 255, 255, 0.02))",
          border: "1px solid var(--border-color, #27272a)",
        }}
      >
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
          Authoritative Entitlement Equation:
        </div>
        <div className="ac-mono" style={{ fontSize: 13, color: "var(--primary, #3b82f6)" }}>
          Plan Baseline + Platform Tenant Feature Override = Effective Capability
        </div>
        <p className="ac-text-sm" style={{ opacity: 0.75, margin: "6px 0 0 0" }}>
          Feature access is enforced server-side on every API call. Frontend UI controls reflect backend entitlements but never dictate access authority.
        </p>
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <div style={{ overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Feature Key</th>
                <th>Category</th>
                <th>Description</th>
                <th>Effective Status</th>
                <th>Resolution Source</th>
              </tr>
            </thead>
            <tbody>
              {FEATURE_CATALOG.map((f) => {
                const isEnabled = effectiveMap[f.key] ?? false;
                return (
                  <tr key={f.key}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{f.name}</div>
                      <div className="ac-mono" style={{ fontSize: 11, opacity: 0.6 }}>
                        {f.key}
                      </div>
                    </td>
                    <td>
                      <span
                        className="ac-mono"
                        style={{
                          fontSize: 10,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: "var(--bg-subtle, rgba(255, 255, 255, 0.06))",
                          border: "1px solid var(--border-color, #27272a)",
                        }}
                      >
                        {f.category}
                      </span>
                    </td>
                    <td className="ac-text-sm" style={{ opacity: 0.8, maxWidth: 360 }}>
                      {f.description}
                    </td>
                    <td>
                      <StatusBadge
                        status={isEnabled ? "ACTIVE" : "STORED"}
                        label={isEnabled ? "ENABLED" : "DISABLED"}
                      />
                    </td>
                    <td className="ac-text-sm" style={{ opacity: 0.7 }}>
                      {isEnabled ? "Plan Default" : "Restricted by Plan"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
