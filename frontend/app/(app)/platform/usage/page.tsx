"use client";

// Platform Admin — Usage & Tenant Ceilings Explorer.
// Strictly adheres to Rule 15: unmetered dimensions are labeled NOT TRACKED rather than fabricating numbers.

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";
import { entitlementApi, type TenantUsageLimitResponse } from "@/lib/api/entitlement";
import { DEMO_PLATFORM_ORGANIZATIONS } from "@/lib/demo/demoPlatform";

interface TrackedDimension {
  name: string;
  category: string;
  source: string;
  status: "LIVE DB TRACKED" | "NOT TRACKED";
  description: string;
}

const PLATFORM_DIMENSIONS: TrackedDimension[] = [
  {
    name: "User Seats",
    category: "Personnel",
    source: "users (count by org)",
    status: "LIVE DB TRACKED",
    description: "Active tenant users registered within the organization boundary.",
  },
  {
    name: "Fixed-Wing Aircraft",
    category: "Fleet Assets",
    source: "aircraft (count by org)",
    status: "LIVE DB TRACKED",
    description: "Registered fixed-wing aircraft managed under CAMO/MRO.",
  },
  {
    name: "Unmanned Drones (UAS)",
    category: "Fleet Assets",
    source: "assets (asset_type=DRONE)",
    status: "LIVE DB TRACKED",
    description: "Multi-rotor, fixed-wing, and eVTOL autonomous drone assets.",
  },
  {
    name: "Work Orders",
    category: "MRO",
    source: "work_orders (count by org)",
    status: "LIVE DB TRACKED",
    description: "Open and closed maintenance work orders in the tenant ledger.",
  },
  {
    name: "Evidence Documents",
    category: "Compliance",
    source: "evidence (count by org)",
    status: "LIVE DB TRACKED",
    description: "Verified compliance inspection evidence records and sign-offs.",
  },
  {
    name: "Blob Storage Capacity (GB)",
    category: "Infrastructure",
    source: "N/A (No storage meter)",
    status: "NOT TRACKED",
    description: "Object storage volume is currently unmetered. Not tracked in this phase.",
  },
  {
    name: "API Query Bandwidth",
    category: "Infrastructure",
    source: "N/A (No API rate meter)",
    status: "NOT TRACKED",
    description: "API call consumption rate is currently unmetered. Not tracked in this phase.",
  },
  {
    name: "LISA AI Tokens",
    category: "Intelligence",
    source: "N/A (No token meter)",
    status: "NOT TRACKED",
    description: "LLM token consumption is currently unmetered. Not tracked in this phase.",
  },
];

export default function PlatformUsagePage() {
  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();

  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("ALL");
  const [limits, setLimits] = useState<{ orgName: string; limit: TenantUsageLimitResponse }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  useEffect(() => {
    if (mode === "DEMO") {
      setOrgs(DEMO_PLATFORM_ORGANIZATIONS);
      setLimits([
        {
          orgName: "KOTA Aerospace Demo Operations",
          limit: {
            id: "60000000-0000-0000-0000-000000000001",
            organization_id: "00000000-0000-0000-0000-000000000001",
            feature_key: "fleet_limits",
            limit_key: "max_drones",
            limit_value: 20,
            is_unlimited: false,
            created_at: "2026-01-15T00:00:00Z",
            updated_at: "2026-01-15T00:00:00Z",
          },
        },
        {
          orgName: "KOTA Aerospace Demo Operations",
          limit: {
            id: "60000000-0000-0000-0000-000000000002",
            organization_id: "00000000-0000-0000-0000-000000000001",
            feature_key: "user_seats",
            limit_key: "max_users",
            limit_value: 15,
            is_unlimited: false,
            created_at: "2026-01-15T00:00:00Z",
            updated_at: "2026-01-15T00:00:00Z",
          },
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

    platformApi
      .listOrganizations(accessToken)
      .then(async (orgList) => {
        setOrgs(orgList);
        const orgMap = new Map(orgList.map((o) => [o.id, o.name]));

        const results = await Promise.allSettled(
          orgList.map((o) => entitlementApi.listUsageLimits(accessToken, o.id))
        );

        const allLimits: { orgName: string; limit: TenantUsageLimitResponse }[] = [];
        results.forEach((res, idx) => {
          if (res.status === "fulfilled") {
            const orgId = orgList[idx].id;
            res.value.forEach((l) => {
              allLimits.push({ orgName: orgMap.get(orgId) ?? orgId, limit: l });
            });
          }
        });
        setLimits(allLimits);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [mode, accessToken, isAuthenticated]);

  const filteredLimits = useMemo(() => {
    if (selectedOrgId === "ALL") return limits;
    return limits.filter((l) => l.limit.organization_id === selectedOrgId);
  }, [limits, selectedOrgId]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Usage & Limits" }]} />

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
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform — Usage & Limits</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Configured tenant ceilings and metric tracking status across KOTA Aerospace.
          </p>
        </div>
      </div>

      {mode === "REAL" && !isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : mode === "REAL" && !isPlatformUser ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)", borderLeft: "4px solid var(--ac-status-non-compliant)" }}>
          <h3 className="ac-h3" style={{ margin: "0 0 6px" }}>Platform Access Denied</h3>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Your account does not possess the <code>PLATFORM_MANAGE</code> authority required to view platform usage metrics.
          </p>
        </div>
      ) : (
        <>
          {/* Tracking Architecture Matrix */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <h2 className="ac-h2" style={{ margin: "0 0 8px" }}>Platform Metric Tracking Boundaries</h2>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 16px" }}>
              To prevent fabricated data, metrics are strictly classified as either backed by live database records or explicitly labeled <strong>NOT TRACKED</strong>.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
              {PLATFORM_DIMENSIONS.map((dim) => (
                <div
                  key={dim.name}
                  style={{
                    padding: "12px 14px",
                    background: "rgba(255,255,255,0.02)",
                    borderRadius: 6,
                    border: "1px solid rgba(255,255,255,0.06)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong>{dim.name}</strong>
                    <StatusBadge
                      status={dim.status === "LIVE DB TRACKED" ? "COMPLIANT" : "INSUFFICIENT_DATA"}
                      label={dim.status}
                    />
                  </div>
                  <div className="ac-text-sm ac-text-muted" style={{ fontSize: 12 }}>
                    Category: {dim.category} · Backend: <code>{dim.source}</code>
                  </div>
                  <div style={{ fontSize: 12, lineHeight: 1.4 }}>{dim.description}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Configured Ceilings Table */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
              <div>
                <h2 className="ac-h2" style={{ margin: 0 }}>Configured Tenant Usage Ceilings</h2>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                  Per-tenant limits configured in <code>tenant_usage_limits</code> table.
                </p>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="ac-text-sm ac-text-muted">Filter Organization:</span>
                <select
                  className="ac-select"
                  value={selectedOrgId}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                >
                  <option value="ALL">All Organizations</option>
                  {orgs.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <RealDataPanel
              loading={loading}
              error={error}
              isEmpty={filteredLimits.length === 0}
              emptyMessage="No explicit limit ceilings configured for the selected organization(s)."
            >
              <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th>Customer Organization</th>
                    <th>Feature Identifier</th>
                    <th>Limit Key</th>
                    <th>Ceiling Value</th>
                    <th>Tracking State</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLimits.map(({ orgName, limit: l }) => (
                    <tr key={l.id}>
                      <td>
                        <strong>
                          <Link href={`/platform/organizations/${l.organization_id}`}>
                            {orgName}
                          </Link>
                        </strong>
                      </td>
                      <td><code>{l.feature_key}</code></td>
                      <td>{l.limit_key}</td>
                      <td>
                        <strong>{l.is_unlimited ? "Unlimited" : l.limit_value}</strong>
                      </td>
                      <td>
                        <StatusBadge status="COMPLIANT" label="Configured" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </RealDataPanel>
          </div>
        </>
      )}
    </div>
  );
}
