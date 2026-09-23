"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantUsage } from "@/lib/api/tenant";
import { DEMO_TENANT_USAGE } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function TenantUsagePage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [usage, setUsage] = useState<TenantUsage | null>(
    isDemo ? DEMO_TENANT_USAGE : null
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (isDemo) {
      setUsage(DEMO_TENANT_USAGE);
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
      .getUsage(accessToken)
      .then(setUsage)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Resource Usage & Limits" },
        ]}
        eyebrow="CAPACITY & BOUNDARIES"
        title="Resource Usage &amp; Limits"
        subtitle="Live accounting of tenant resource consumption against commercial plan limits."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/subscription" className="ac-btn">
              View Plan Allowances →
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
            <strong>DEMO MODE</strong> · Showing synthetic usage consumption and honest tracking disclosures.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!usage || usage.metrics.length === 0}
            emptyMessage="No usage telemetry available."
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
          Metric Tracking Integrity Notice
        </div>
        <p className="ac-text-sm" style={{ opacity: 0.8, margin: 0 }}>
          KOTA Aerospace follows strict reporting integrity: dimensions backed by real database records (user seats, aircraft, drones, facilities) report verified counts. Dimensions without metering infrastructure (storage volumes, API queries, AI inference tokens) are explicitly reported as <strong>NOT TRACKED</strong> rather than displaying fabricated estimates.
        </p>
      </div>

      {usage && (
        <div className="ac-card" style={{ padding: 0 }}>
          <div style={{ overflowX: "auto" }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Resource Dimension</th>
                  <th>Current Consumption</th>
                  <th>Configured Plan Limit</th>
                  <th>Utilization</th>
                  <th>Tracking Status</th>
                </tr>
              </thead>
              <tbody>
                {usage.metrics.map((m) => {
                  const percent =
                    m.tracked && m.value !== null && m.limit && m.limit > 0
                      ? Math.min(100, Math.round((m.value / m.limit) * 100))
                      : null;

                  return (
                    <tr key={m.key}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{m.label}</div>
                        <div className="ac-mono" style={{ fontSize: 11, opacity: 0.6 }}>
                          {m.key}
                        </div>
                      </td>
                      <td>
                        {m.tracked && m.value !== null ? (
                          <span style={{ fontSize: 16, fontWeight: 700 }}>
                            {m.value} <span style={{ fontSize: 12, fontWeight: 400, opacity: 0.7 }}>{m.unit}</span>
                          </span>
                        ) : (
                          <span className="ac-mono" style={{ fontSize: 12, opacity: 0.5 }}>
                            NOT TRACKED
                          </span>
                        )}
                      </td>
                      <td>
                        {m.tracked ? (
                          m.is_unlimited ? (
                            <span className="ac-mono" style={{ fontSize: 12 }}>UNLIMITED</span>
                          ) : m.limit !== null ? (
                            <span className="ac-mono" style={{ fontSize: 13 }}>
                              {m.limit} {m.unit}
                            </span>
                          ) : (
                            <span className="ac-mono" style={{ fontSize: 12, opacity: 0.5 }}>—</span>
                          )
                        ) : (
                          <span className="ac-mono" style={{ fontSize: 12, opacity: 0.5 }}>UNMETERED</span>
                        )}
                      </td>
                      <td style={{ minWidth: 160 }}>
                        {percent !== null ? (
                          <div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 4 }}>
                              <span>{percent}%</span>
                              <span style={{ opacity: 0.6 }}>
                                {m.value}/{m.limit}
                              </span>
                            </div>
                            <div
                              style={{
                                width: "100%",
                                height: 6,
                                background: "var(--border-color, #27272a)",
                                borderRadius: 3,
                                overflow: "hidden",
                              }}
                            >
                              <div
                                style={{
                                  width: `${percent}%`,
                                  height: "100%",
                                  background:
                                    percent >= 90
                                      ? "var(--danger, #ef4444)"
                                      : percent >= 75
                                      ? "var(--warning, #f59e0b)"
                                      : "var(--primary, #3b82f6)",
                                }}
                              />
                            </div>
                          </div>
                        ) : (
                          <span style={{ fontSize: 12, opacity: 0.4 }}>—</span>
                        )}
                      </td>
                      <td>
                        {m.tracked ? (
                          <StatusBadge status="ACTIVE" label="LIVE DB TRACKED" />
                        ) : (
                          <span
                            style={{
                              fontSize: 11,
                              padding: "2px 6px",
                              borderRadius: 4,
                              background: "rgba(100, 116, 139, 0.15)",
                              color: "#94a3b8",
                              border: "1px solid rgba(100, 116, 139, 0.3)",
                            }}
                          >
                            NOT TRACKED
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
