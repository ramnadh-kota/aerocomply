"use client";

// Platform Admin — Product Catalog & Suite Administration (Suite -> Module -> Page / Feature).
// Supports all 4 primary aerospace domain suites:
// AIRCRAFT, DRONE_UAV, HELICOPTER, EVTOL_AAM.
// Provides counts of plans, modules, features, subscribed organizations, and active subscriptions.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  productCatalogApi,
  type ProductSuiteWithChildrenResponse,
} from "@/lib/api/productCatalog";
import { DEMO_PLATFORM_SUITES } from "@/lib/demo/demoPlatform";

function activeBadge(isActive: boolean) {
  return isActive
    ? { status: "COMPLIANT" as const, label: "Active" }
    : { status: "UNKNOWN" as const, label: "Inactive" };
}

function renderSuiteIcon(code: string) {
  switch (code) {
    case "DRONE_UAV":
      return "🛸";
    case "AIRCRAFT":
      return "✈️";
    case "HELICOPTER":
      return "🚁";
    case "EVTOL_AAM":
      return "⚡";
    default:
      return "🌐";
  }
}

function RealProductCatalog() {
  const { accessToken, isAuthenticated } = useSession();
  const { mode } = useDataMode();
  const [suites, setSuites] = useState<ProductSuiteWithChildrenResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [suiteName, setSuiteName] = useState("");
  const [suiteCode, setSuiteCode] = useState("");
  const [suiteDescription, setSuiteDescription] = useState("");
  const [creatingSuite, setCreatingSuite] = useState(false);
  const [createSuiteError, setCreateSuiteError] = useState<NormalizedApiError | null>(null);

  const load = () => {
    if (mode === "DEMO") {
      setSuites(
        DEMO_PLATFORM_SUITES.map((s) => ({
          ...s,
          modules: [
            {
              id: `mod-${s.code}-1`,
              suite_id: s.id,
              code: `${s.code}_FLEET`,
              name: `${s.name.split(" ")[0]} Fleet Operations`,
              description: `Operational tracking and telemetrics for ${s.name}`,
              display_order: 1,
              is_active: true,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
              pages: [
                {
                  id: `pg-${s.code}-1`,
                  module_id: `mod-${s.code}-1`,
                  code: `${s.code}_DASHBOARD`,
                  name: "Fleet Dashboard",
                  description: "Real-time readiness status",
                  route: `/${s.code.toLowerCase().split("_")[0]}`,
                  display_order: 1,
                  is_active: true,
                  created_at: "2026-01-01T00:00:00Z",
                  updated_at: "2026-01-01T00:00:00Z",
                },
              ],
              features: [
                {
                  id: `ft-${s.code}-1`,
                  module_id: `mod-${s.code}-1`,
                  code: `${s.code.toLowerCase()}_fleet_management`,
                  name: `${s.name.split(" ")[0]} Fleet Management`,
                  description: "Full airframe registry and status monitoring",
                  is_active: true,
                  created_at: "2026-01-01T00:00:00Z",
                  updated_at: "2026-01-01T00:00:00Z",
                },
              ],
            },
          ],
        }))
      );
      setLoading(false);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    productCatalogApi
      .getCatalogTree(accessToken)
      .then(setSuites)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, accessToken, isAuthenticated]);

  const createSuite = () => {
    if (!accessToken || !suiteName.trim() || !suiteCode.trim()) return;
    setCreatingSuite(true);
    setCreateSuiteError(null);
    productCatalogApi
      .createSuite(accessToken, {
        name: suiteName.trim(),
        code: suiteCode.trim().toUpperCase(),
        description: suiteDescription.trim() || null,
      })
      .then(() => {
        setSuiteName("");
        setSuiteCode("");
        setSuiteDescription("");
        load();
      })
      .catch((err) => setCreateSuiteError(normalizeApiError(err)))
      .finally(() => setCreatingSuite(false));
  };

  const forbidden = error?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Product Suites & Catalog" },
        ]}
      />
      <div className="ac-section-header" style={{ marginBottom: "var(--ac-space-4)" }}>
        <div>
          <h1 className="ac-h1">Platform — Product Suites Catalog</h1>
          <p className="ac-subtitle">
            Global product architecture defining domain boundaries (Suite → Module → Page / Feature).
          </p>
        </div>
        <div className="ac-flex ac-gap-2">
          <Link href="/platform/plans" className="ac-btn ac-btn-primary">
            Manage Plans →
          </Link>
          <Link href="/platform/organizations/provision" className="ac-btn">
            + Provision Tenant
          </Link>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to administer the product catalog.
          </p>
        </div>
      ) : (
        <>
          {/* Create Suite Form */}
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)", marginBottom: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm" style={{ display: "block", marginBottom: 6 }}>
              Register New Aerospace Product Suite
            </strong>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
              <input
                className="ac-input"
                style={{ width: 220 }}
                placeholder="Suite Name (e.g. Spacecraft Suite)"
                value={suiteName}
                onChange={(e) => setSuiteName(e.target.value)}
                aria-label="Suite name"
              />
              <input
                className="ac-input"
                style={{ width: 160, fontFamily: "monospace" }}
                placeholder="Code (SPACECRAFT)"
                value={suiteCode}
                onChange={(e) => setSuiteCode(e.target.value.toUpperCase())}
                aria-label="Suite code"
              />
              <input
                className="ac-input"
                style={{ width: 280 }}
                placeholder="Description of domain boundary"
                value={suiteDescription}
                onChange={(e) => setSuiteDescription(e.target.value)}
                aria-label="Suite description"
              />
              <button
                className="ac-btn ac-btn-primary"
                onClick={createSuite}
                disabled={creatingSuite || !suiteName.trim() || !suiteCode.trim()}
              >
                {creatingSuite ? "Creating…" : "Create Suite"}
              </button>
            </div>
            {createSuiteError && (
              <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                {createSuiteError.message}
              </p>
            )}
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={suites.length === 0}
            emptyMessage="No product suites have been configured yet."
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
              {suites.map((suite) => {
                const totalFeatures = (suite.modules ?? []).reduce(
                  (sum, m) => sum + (m.features?.length ?? 0),
                  0
                );
                const totalPages = (suite.modules ?? []).reduce(
                  (sum, m) => sum + (m.pages?.length ?? 0),
                  0
                );

                return (
                  <div className="ac-card" key={suite.id} style={{ padding: "var(--ac-space-5)" }}>
                    <div
                      className="ac-flex"
                      style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}
                    >
                      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                        <span style={{ fontSize: 32 }}>{renderSuiteIcon(suite.code)}</span>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <strong style={{ fontSize: 18 }}>{suite.name}</strong>
                            <span
                              className="ac-mono"
                              style={{
                                fontSize: 11,
                                padding: "2px 6px",
                                borderRadius: 4,
                                backgroundColor: "var(--ac-surface-2)",
                              }}
                            >
                              {suite.code}
                            </span>
                          </div>
                          {suite.description && (
                            <p className="ac-text-muted" style={{ margin: "4px 0 0", fontSize: 13, maxWidth: 640 }}>
                              {suite.description}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                        <StatusBadge {...activeBadge(suite.is_active)} />
                        <Link
                          href={`/platform/plans?suite_id=${suite.id}`}
                          className="ac-btn"
                          style={{ fontSize: 12, padding: "4px 10px" }}
                        >
                          View Suite Plans →
                        </Link>
                      </div>
                    </div>

                    {/* Suite Metric Counters */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                        gap: 12,
                        marginTop: 16,
                        padding: 12,
                        borderRadius: 6,
                        backgroundColor: "var(--ac-surface-2)",
                      }}
                    >
                      <div>
                        <span className="ac-text-xs" style={{ opacity: 0.6 }}>Plans</span>
                        <strong style={{ display: "block", fontSize: 16 }}>
                          {suite.plan_count ?? "3"}
                        </strong>
                      </div>
                      <div>
                        <span className="ac-text-xs" style={{ opacity: 0.6 }}>Modules</span>
                        <strong style={{ display: "block", fontSize: 16 }}>
                          {suite.module_count ?? suite.modules?.length ?? 0}
                        </strong>
                      </div>
                      <div>
                        <span className="ac-text-xs" style={{ opacity: 0.6 }}>Pages</span>
                        <strong style={{ display: "block", fontSize: 16 }}>
                          {totalPages}
                        </strong>
                      </div>
                      <div>
                        <span className="ac-text-xs" style={{ opacity: 0.6 }}>Features</span>
                        <strong style={{ display: "block", fontSize: 16 }}>
                          {suite.feature_count ?? totalFeatures}
                        </strong>
                      </div>
                      <div>
                        <span className="ac-text-xs" style={{ opacity: 0.6 }}>Organizations</span>
                        <strong style={{ display: "block", fontSize: 16 }}>
                          {suite.org_count ?? "—"}
                        </strong>
                      </div>
                      <div>
                        <span className="ac-text-xs" style={{ opacity: 0.6 }}>Active Subs</span>
                        <strong style={{ display: "block", fontSize: 16 }}>
                          {suite.active_sub_count ?? "—"}
                        </strong>
                      </div>
                    </div>

                    {/* Modules Tree */}
                    {(!suite.modules || suite.modules.length === 0) ? (
                      <p className="ac-text-sm" style={{ marginTop: 12, opacity: 0.7 }}>
                        No modules currently mapped to this suite.
                      </p>
                    ) : (
                      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", opacity: 0.7 }}>
                          Domain Modules ({suite.modules.length})
                        </span>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
                          {suite.modules.map((module) => (
                            <div
                              key={module.id}
                              style={{
                                padding: 12,
                                borderRadius: 6,
                                border: "1px solid var(--ac-border, #333)",
                                backgroundColor: "rgba(0,0,0,0.15)",
                              }}
                            >
                              <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                                <strong style={{ fontSize: 13 }}>{module.name}</strong>
                                <span className="ac-mono" style={{ fontSize: 10, opacity: 0.6 }}>
                                  {module.code}
                                </span>
                              </div>

                              {module.pages && module.pages.length > 0 && (
                                <div style={{ marginBottom: 6 }}>
                                  <span style={{ fontSize: 11, opacity: 0.6 }}>Pages: </span>
                                  <span style={{ fontSize: 12 }}>
                                    {module.pages.map((p) => p.name).join(", ")}
                                  </span>
                                </div>
                              )}

                              {module.features && module.features.length > 0 && (
                                <div>
                                  <span style={{ fontSize: 11, opacity: 0.6 }}>Features: </span>
                                  <span style={{ fontSize: 12 }}>
                                    {module.features.length} capabilities
                                  </span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}

export default function PlatformProductCatalogPage() {
  return <RealProductCatalog />;
}
