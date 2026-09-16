"use client";

// Phase 18.2: Platform Admin — Product Catalog (Suite -> Module -> Page /
// Feature). REAL-mode only, same pattern as /platform/plans: this is
// cross-tenant platform staff tooling, not a customer-facing feature, so
// there is no demo dataset. Backend enforces PLATFORM_MANAGE on every call
// here (app/api/v1/product_catalog.py) — this page hiding itself from
// non-platform-admin users (and rendering a permission-denied state on 403)
// is a UX convenience, never the security boundary. Route visibility here
// is informational display only; it is never consulted by any
// authorization check (see backend/app/models/product_catalog.py).

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  productCatalogApi,
  type ProductSuiteWithChildrenResponse,
} from "@/lib/api/productCatalog";

function activeBadge(isActive: boolean) {
  return isActive
    ? { status: "COMPLIANT" as const, label: "Active" }
    : { status: "UNKNOWN" as const, label: "Inactive" };
}

function RealProductCatalog() {
  const { accessToken, isAuthenticated } = useSession();
  const [suites, setSuites] = useState<ProductSuiteWithChildrenResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [suiteName, setSuiteName] = useState("");
  const [suiteCode, setSuiteCode] = useState("");
  const [suiteDescription, setSuiteDescription] = useState("");
  const [creatingSuite, setCreatingSuite] = useState(false);
  const [createSuiteError, setCreateSuiteError] = useState<NormalizedApiError | null>(null);

  const load = () => {
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
  }, [accessToken, isAuthenticated]);

  const createSuite = () => {
    if (!accessToken || !suiteName.trim() || !suiteCode.trim()) return;
    setCreatingSuite(true);
    setCreateSuiteError(null);
    productCatalogApi
      .createSuite(accessToken, {
        name: suiteName.trim(),
        code: suiteCode.trim(),
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
          { label: "Dashboard", href: "/dashboard" },
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Product Catalog" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Platform — Product Catalog</h1>
          <p className="ac-subtitle">
            Global product hierarchy (Suite → Module → Page / Feature). Not visible to customer users.
          </p>
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
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Create a suite</strong>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
              <input
                className="ac-input"
                style={{ width: 220 }}
                placeholder="Suite name"
                value={suiteName}
                onChange={(e) => setSuiteName(e.target.value)}
                aria-label="Suite name"
              />
              <input
                className="ac-input"
                style={{ width: 160 }}
                placeholder="Suite code"
                value={suiteCode}
                onChange={(e) => setSuiteCode(e.target.value)}
                aria-label="Suite code"
              />
              <input
                className="ac-input"
                style={{ width: 280 }}
                placeholder="Description (optional)"
                value={suiteDescription}
                onChange={(e) => setSuiteDescription(e.target.value)}
                aria-label="Suite description"
              />
              <button
                className="ac-btn"
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
              {suites.map((suite) => (
                <div className="ac-card" key={suite.id} style={{ padding: "var(--ac-space-4)" }}>
                  <div
                    className="ac-flex"
                    style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}
                  >
                    <div>
                      <strong style={{ wordBreak: "break-word" }}>{suite.name}</strong>
                      <span className="ac-text-sm" style={{ marginLeft: 8, opacity: 0.7 }}>
                        {suite.code}
                      </span>
                      {suite.description && (
                        <p className="ac-text-sm" style={{ margin: "4px 0 0", opacity: 0.8 }}>
                          {suite.description}
                        </p>
                      )}
                    </div>
                    <StatusBadge {...activeBadge(suite.is_active)} />
                  </div>

                  {suite.modules.length === 0 ? (
                    <p className="ac-text-sm" style={{ marginTop: 12, opacity: 0.7 }}>
                      No modules yet under this suite.
                    </p>
                  ) : (
                    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 12 }}>
                      {suite.modules.map((module) => (
                        <div
                          key={module.id}
                          style={{
                            borderLeft: "2px solid var(--ac-border, #ddd)",
                            paddingLeft: 12,
                          }}
                        >
                          <div className="ac-flex" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                            <div>
                              <strong className="ac-text-sm" style={{ wordBreak: "break-word" }}>
                                {module.name}
                              </strong>
                              <span className="ac-text-sm" style={{ marginLeft: 8, opacity: 0.7 }}>
                                {module.code}
                              </span>
                            </div>
                            <StatusBadge {...activeBadge(module.is_active)} />
                          </div>

                          {module.pages.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <span className="ac-text-sm" style={{ opacity: 0.6 }}>
                                Pages:
                              </span>
                              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                                {module.pages.map((page) => (
                                  <li key={page.id} className="ac-text-sm">
                                    {page.name} <span style={{ opacity: 0.6 }}>({page.code})</span>
                                    {page.route && <span style={{ opacity: 0.6 }}> — {page.route}</span>}
                                    {!page.is_active && (
                                      <span style={{ marginLeft: 6 }}>
                                        <StatusBadge {...activeBadge(page.is_active)} />
                                      </span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {module.features.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <span className="ac-text-sm" style={{ opacity: 0.6 }}>
                                Features:
                              </span>
                              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                                {module.features.map((feature) => (
                                  <li key={feature.id} className="ac-text-sm">
                                    {feature.name} <span style={{ opacity: 0.6 }}>({feature.code})</span>
                                    {!feature.is_active && (
                                      <span style={{ marginLeft: 6 }}>
                                        <StatusBadge {...activeBadge(feature.is_active)} />
                                      </span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
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
