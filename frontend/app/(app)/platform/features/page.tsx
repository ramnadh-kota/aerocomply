"use client";

// Platform Admin — Feature Registry.
// Contractual system feature keys, categories, descriptions, and commercial plan mappings.

import { useState, useMemo } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { DEMO_PLATFORM_FEATURES, type PlatformFeatureItem } from "@/lib/demo/demoPlatform";

export default function PlatformFeaturesPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");

  const categories = useMemo(() => {
    const cats = new Set(DEMO_PLATFORM_FEATURES.map((f) => f.category));
    return Array.from(cats);
  }, []);

  const filteredFeatures = useMemo(() => {
    return DEMO_PLATFORM_FEATURES.filter((f) => {
      if (categoryFilter !== "ALL" && f.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesKey = f.feature_key.toLowerCase().includes(q);
        const matchesName = f.name.toLowerCase().includes(q);
        const matchesDesc = f.description.toLowerCase().includes(q);
        if (!matchesKey && !matchesName && !matchesDesc) return false;
      }
      return true;
    });
  }, [categoryFilter, searchQuery]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Features Registry" }]} />

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
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform — Feature Registry</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Contractual platform capability keys, functional categories, and commercial plan tier mappings.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="ac-btn" href="/platform/product-catalog">
            View Product Catalog Tree →
          </Link>
          <Link className="ac-btn" href="/platform/plans">
            Manage Plans →
          </Link>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div
        className="ac-card"
        style={{
          padding: "var(--ac-space-3)",
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", flex: 1 }}>
          <input
            className="ac-input"
            style={{ minWidth: 280, flex: "1 1 280px" }}
            placeholder="Search feature key, name, or capability description…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search features"
          />

          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="ac-text-sm ac-text-muted">Category:</span>
            <select
              className="ac-select"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              aria-label="Filter by category"
            >
              <option value="ALL">All Categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="ac-text-sm ac-text-muted">
          Showing {filteredFeatures.length} of {DEMO_PLATFORM_FEATURES.length} feature definitions
        </div>
      </div>

      {/* Features Table */}
      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>Feature Identifier</th>
              <th>Category</th>
              <th>Description</th>
              <th>Included Plans</th>
              <th>Availability</th>
            </tr>
          </thead>
          <tbody>
            {filteredFeatures.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: "center", padding: 24 }} className="ac-text-muted">
                  No features match the active search or category filter.
                </td>
              </tr>
            ) : (
              filteredFeatures.map((feat) => (
                <tr key={feat.feature_key}>
                  <td>
                    <strong>{feat.name}</strong>
                    <div style={{ marginTop: 2 }}>
                      <code style={{ fontSize: 11, background: "rgba(255,255,255,0.06)", padding: "2px 6px", borderRadius: 3 }}>
                        {feat.feature_key}
                      </code>
                    </div>
                  </td>
                  <td>
                    <span className="ac-badge" style={{ fontSize: 11 }}>
                      {feat.category}
                    </span>
                  </td>
                  <td style={{ maxWidth: 360, fontSize: 13, lineHeight: 1.4 }}>
                    {feat.description}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {feat.plans.map((p) => (
                        <span
                          key={p}
                          className="ac-badge"
                          style={{
                            fontSize: 11,
                            background: p === "enterprise" ? "rgba(147, 51, 234, 0.2)" : undefined,
                            borderColor: p === "enterprise" ? "rgba(147, 51, 234, 0.4)" : undefined,
                          }}
                        >
                          {p.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <StatusBadge status="COMPLIANT" label="ACTIVE" />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
