"use client";

// Platform Admin — Plan Catalog & Packaging Interface.
// Strictly adheres to the two-tier governance architecture:
// Product Catalog (ProductFeature stable keys) -> Plan/PlanFeature baseline commercial entitlements.
// Backend enforces PLATFORM_MANAGE on every action.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { planApi, type PlanResponse, type PlanFeatureBulkItem } from "@/lib/api/plan";
import { productCatalogApi, type ProductSuiteWithChildrenResponse } from "@/lib/api/productCatalog";
import { DEMO_PLATFORM_PLANS, DEMO_PLATFORM_FEATURES } from "@/lib/demo/demoPlatform";

interface CatalogFeatureItem {
  key: string;
  name: string;
  moduleName: string;
  suiteName: string;
  description: string;
}

const ASSET_SCOPES = [
  { value: "DRONE", label: "Drone / UAS (DRONE)" },
  { value: "AIRCRAFT", label: "Fixed-Wing Aircraft (AIRCRAFT)" },
  { value: "HELICOPTER", label: "Helicopter / Rotorcraft (HELICOPTER)" },
  { value: "EVTOL", label: "eVTOL & AAM (EVTOL)" },
  { value: "ALL", label: "Universal / Multi-Domain (ALL)" },
];

function planStatusBadge(isActive: boolean) {
  return isActive
    ? { status: "COMPLIANT" as const, label: "Active" }
    : { status: "UNKNOWN" as const, label: "Inactive" };
}

function assetScopeBadge(scope?: string | null) {
  const normalized = (scope ?? "ALL").toUpperCase();
  switch (normalized) {
    case "DRONE":
      return <span className="ac-badge" style={{ backgroundColor: "rgba(34, 197, 94, 0.15)", color: "#4ade80", border: "1px solid rgba(34, 197, 94, 0.3)" }}>DRONE</span>;
    case "AIRCRAFT":
      return <span className="ac-badge" style={{ backgroundColor: "rgba(59, 130, 246, 0.15)", color: "#60a5fa", border: "1px solid rgba(59, 130, 246, 0.3)" }}>AIRCRAFT</span>;
    case "HELICOPTER":
      return <span className="ac-badge" style={{ backgroundColor: "rgba(245, 158, 11, 0.15)", color: "#fbbf24", border: "1px solid rgba(245, 158, 11, 0.3)" }}>HELICOPTER</span>;
    case "EVTOL":
      return <span className="ac-badge" style={{ backgroundColor: "rgba(168, 85, 247, 0.15)", color: "#c084fc", border: "1px solid rgba(168, 85, 247, 0.3)" }}>EVTOL</span>;
    default:
      return <span className="ac-badge" style={{ backgroundColor: "rgba(148, 163, 184, 0.15)", color: "#cbd5e1", border: "1px solid rgba(148, 163, 184, 0.3)" }}>UNIVERSAL</span>;
  }
}

export default function PlatformPlansPage() {
  const { accessToken, isAuthenticated } = useSession();
  const { mode } = useDataMode();

  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // Dynamic Product Features catalog from backend
  const [availableFeatures, setAvailableFeatures] = useState<CatalogFeatureItem[]>([]);
  const [featuresLoading, setFeaturesLoading] = useState(false);

  // Create Modal & Form State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createCode, setCreateCode] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createScope, setCreateScope] = useState("DRONE");
  const [createIsActive, setCreateIsActive] = useState(true);
  const [selectedFeatureKeys, setSelectedFeatureKeys] = useState<Set<string>>(new Set());

  // Search and filter for features during create
  const [featureSearch, setFeatureSearch] = useState("");
  const [featureFilter, setFeatureFilter] = useState<"all" | "included" | "excluded">("all");

  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<NormalizedApiError | null>(null);

  // Quick Edit Modal
  const [editingPlan, setEditingPlan] = useState<PlanResponse | null>(null);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editScope, setEditScope] = useState("DRONE");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<NormalizedApiError | null>(null);

  // Activation Confirm State
  const [planToToggle, setPlanToToggle] = useState<PlanResponse | null>(null);
  const [toggleBusy, setToggleBusy] = useState(false);

  // Load plans & catalog features
  const load = () => {
    if (mode === "DEMO") {
      setPlans(DEMO_PLATFORM_PLANS);
      setLoading(false);
      setError(null);

      // Populate features from demo
      const demoFeatures: CatalogFeatureItem[] = DEMO_PLATFORM_FEATURES.map((f) => ({
        key: f.feature_key,
        name: f.name,
        moduleName: f.category,
        suiteName: "Platform Suite",
        description: f.description,
      }));
      setAvailableFeatures(demoFeatures);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setFeaturesLoading(true);

    Promise.allSettled([
      planApi.listPlans(accessToken),
      productCatalogApi.getCatalogTree(accessToken),
    ]).then(([plansRes, catalogRes]) => {
      if (plansRes.status === "fulfilled") {
        setPlans(plansRes.value);
      } else {
        setError(normalizeApiError(plansRes.reason));
      }

      if (catalogRes.status === "fulfilled" && catalogRes.value.length > 0) {
        const flattened: CatalogFeatureItem[] = [];
        for (const suite of catalogRes.value) {
          for (const mod of suite.modules ?? []) {
            for (const feat of mod.features ?? []) {
              if (feat.is_active) {
                flattened.push({
                  key: feat.code,
                  name: feat.name,
                  moduleName: mod.name,
                  suiteName: suite.name,
                  description: feat.description ?? "",
                });
              }
            }
          }
        }
        if (flattened.length > 0) {
          setAvailableFeatures(flattened);
        } else {
          // Fallback if catalog has suites but no active features yet
          setAvailableFeatures(
            DEMO_PLATFORM_FEATURES.map((f) => ({
              key: f.feature_key,
              name: f.name,
              moduleName: f.category,
              suiteName: "Platform Suite",
              description: f.description,
            }))
          );
        }
      } else {
        // Fallback to demo items if catalog endpoints are empty
        setAvailableFeatures(
          DEMO_PLATFORM_FEATURES.map((f) => ({
            key: f.feature_key,
            name: f.name,
            moduleName: f.category,
            suiteName: "Platform Suite",
            description: f.description,
          }))
        );
      }
      setLoading(false);
      setFeaturesLoading(false);
    });
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, accessToken, isAuthenticated]);

  // Group available features by module
  const featuresByModule = useMemo(() => {
    const map = new Map<string, CatalogFeatureItem[]>();
    for (const f of availableFeatures) {
      const groupKey = f.moduleName || f.suiteName || "Core Platform";
      if (!map.has(groupKey)) {
        map.set(groupKey, []);
      }
      map.get(groupKey)!.push(f);
    }
    return map;
  }, [availableFeatures]);

  // Filter features based on search & filter tabs
  const filteredFeaturesByModule = useMemo(() => {
    const query = featureSearch.toLowerCase().trim();
    const result = new Map<string, CatalogFeatureItem[]>();

    for (const [moduleName, items] of featuresByModule.entries()) {
      const filteredItems = items.filter((f) => {
        const matchesQuery =
          !query ||
          f.name.toLowerCase().includes(query) ||
          f.key.toLowerCase().includes(query) ||
          f.description.toLowerCase().includes(query);

        if (!matchesQuery) return false;

        const isIncluded = selectedFeatureKeys.has(f.key);
        if (featureFilter === "included") return isIncluded;
        if (featureFilter === "excluded") return !isIncluded;
        return true;
      });

      if (filteredItems.length > 0) {
        result.set(moduleName, filteredItems);
      }
    }
    return result;
  }, [featuresByModule, featureSearch, featureFilter, selectedFeatureKeys]);

  const toggleFeatureKey = (key: string) => {
    setSelectedFeatureKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectAllInModule = (items: CatalogFeatureItem[]) => {
    setSelectedFeatureKeys((prev) => {
      const next = new Set(prev);
      for (const item of items) next.add(item.key);
      return next;
    });
  };

  const clearAllInModule = (items: CatalogFeatureItem[]) => {
    setSelectedFeatureKeys((prev) => {
      const next = new Set(prev);
      for (const item of items) next.delete(item.key);
      return next;
    });
  };

  const handleCreatePlan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createName.trim() || !createCode.trim()) return;

    if (mode === "DEMO") {
      const syntheticPlan: PlanResponse = {
        id: `10000000-0000-0000-0000-${String(plans.length + 10).padStart(12, "0")}`,
        name: createName.trim(),
        code: createCode.trim().toUpperCase(),
        description: createDescription.trim() || null,
        asset_scope: createScope === "ALL" ? null : createScope,
        included_features_count: selectedFeatureKeys.size,
        tenant_count: 0,
        is_active: createIsActive,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      };
      setPlans([syntheticPlan, ...plans]);
      setShowCreateModal(false);
      resetCreateForm();
      return;
    }

    if (!accessToken) return;
    setCreating(true);
    setCreateError(null);

    try {
      const createdPlan = await planApi.createPlan(accessToken, {
        name: createName.trim(),
        code: createCode.trim().toUpperCase(),
        description: createDescription.trim() || null,
        asset_scope: createScope === "ALL" ? null : createScope,
        is_active: createIsActive,
      });

      // Bulk configure features on the newly created plan
      if (availableFeatures.length > 0) {
        const featurePayload: PlanFeatureBulkItem[] = availableFeatures.map((f) => ({
          feature_key: f.key,
          enabled: selectedFeatureKeys.has(f.key),
        }));
        await planApi.bulkSetPlanFeatures(accessToken, createdPlan.id, featurePayload);
      }

      setShowCreateModal(false);
      resetCreateForm();
      load();
    } catch (err) {
      setCreateError(normalizeApiError(err));
    } finally {
      setCreating(false);
    }
  };

  const resetCreateForm = () => {
    setCreateName("");
    setCreateCode("");
    setCreateDescription("");
    setCreateScope("DRONE");
    setCreateIsActive(true);
    setSelectedFeatureKeys(new Set());
    setFeatureSearch("");
    setFeatureFilter("all");
    setCreateError(null);
  };

  const handleOpenEdit = (plan: PlanResponse) => {
    setEditingPlan(plan);
    setEditName(plan.name);
    setEditCode(plan.code);
    setEditDescription(plan.description ?? "");
    setEditScope(plan.asset_scope ?? "ALL");
    setEditError(null);
  };

  const handleSaveEdit = async () => {
    if (!editingPlan || !editName.trim() || !editCode.trim()) return;

    if (mode === "DEMO") {
      setPlans((prev) =>
        prev.map((p) =>
          p.id === editingPlan.id
            ? {
                ...p,
                name: editName.trim(),
                code: editCode.trim().toUpperCase(),
                description: editDescription.trim() || null,
                asset_scope: editScope === "ALL" ? null : editScope,
              }
            : p
        )
      );
      setEditingPlan(null);
      return;
    }

    if (!accessToken) return;
    setEditBusy(true);
    setEditError(null);

    try {
      await planApi.updatePlan(accessToken, editingPlan.id, {
        name: editName.trim(),
        code: editCode.trim().toUpperCase(),
        description: editDescription.trim() || null,
        asset_scope: editScope === "ALL" ? null : editScope,
      });
      setEditingPlan(null);
      load();
    } catch (err) {
      setEditError(normalizeApiError(err));
    } finally {
      setEditBusy(false);
    }
  };

  const handleToggleActive = async () => {
    if (!planToToggle) return;

    if (mode === "DEMO") {
      setPlans((prev) =>
        prev.map((p) => (p.id === planToToggle.id ? { ...p, is_active: !p.is_active } : p))
      );
      setPlanToToggle(null);
      return;
    }

    if (!accessToken) return;
    setToggleBusy(true);

    try {
      if (planToToggle.is_active) {
        await planApi.deactivatePlan(accessToken, planToToggle.id);
      } else {
        await planApi.activatePlan(accessToken, planToToggle.id);
      }
      setPlanToToggle(null);
      load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setToggleBusy(false);
    }
  };

  const columns: Column<PlanResponse>[] = [
    {
      key: "name",
      header: "Plan Name",
      render: (p) => (
        <div>
          <Link href={`/platform/plans/${p.id}`} className="ac-table-link" style={{ fontWeight: 600 }}>
            {p.name}
          </Link>
          {p.description && (
            <p className="ac-text-muted" style={{ fontSize: 12, margin: "2px 0 0", maxWidth: 320 }}>
              {p.description}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "code",
      header: "Plan Code",
      render: (p) => (
        <span style={{ fontFamily: "monospace", fontSize: 13, wordBreak: "break-all" }}>
          {p.code}
        </span>
      ),
    },
    {
      key: "asset_scope",
      header: "Asset Domain / Scope",
      render: (p) => assetScopeBadge(p.asset_scope),
    },
    {
      key: "features",
      header: "Included Features",
      render: (p) => (
        <span style={{ fontWeight: 500, fontSize: 13 }}>
          {p.included_features_count ?? 0} features
        </span>
      ),
    },
    {
      key: "tenants",
      header: "Tenant Count",
      render: (p) => (
        <span style={{ fontWeight: 500, fontSize: 13 }}>
          {p.tenant_count ?? 0} tenants
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (p) => <StatusBadge {...planStatusBadge(p.is_active)} />,
    },
    {
      key: "actions",
      header: "Actions",
      render: (p) => (
        <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
          <Link
            className="ac-btn"
            style={{ fontSize: 12, padding: "3px 10px" }}
            href={`/platform/plans/${p.id}`}
          >
            View
          </Link>
          <button
            type="button"
            className="ac-btn ac-btn-secondary"
            style={{ fontSize: 12, padding: "3px 10px" }}
            onClick={(e) => {
              e.stopPropagation();
              handleOpenEdit(p);
            }}
          >
            Edit
          </button>
          <button
            type="button"
            className="ac-btn ac-btn-ghost"
            style={{
              fontSize: 12,
              padding: "3px 10px",
              color: p.is_active ? "var(--ac-status-non-compliant)" : "var(--ac-status-compliant)",
            }}
            onClick={(e) => {
              e.stopPropagation();
              setPlanToToggle(p);
            }}
          >
            {p.is_active ? "Deactivate" : "Activate"}
          </button>
        </div>
      ),
    },
  ];

  const forbidden = error?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Plans" },
        ]}
      />

      <div className="ac-section-header" style={{ marginBottom: "var(--ac-space-4)" }}>
        <div>
          <h1 className="ac-h1">Platform — Commercial Plan Catalog</h1>
          <p className="ac-subtitle">
            Configure commercial baseline entitlements, asset domains, and feature packages according to Kota Aerospace governance.
          </p>
        </div>
        <div className="ac-flex ac-gap-2">
          <button
            className="ac-btn ac-btn-primary"
            onClick={() => {
              resetCreateForm();
              setShowCreateModal(true);
            }}
          >
            + Create New Plan
          </button>
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
            You do not have permission to administer plans. Only PLATFORM_ADMIN holds this privilege.
          </p>
        </div>
      ) : (
        <>
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={plans.length === 0}
            emptyMessage="No commercial plans configured yet."
          >
            <div className="ac-card" style={{ padding: 0, overflow: "hidden" }}>
              <div className="ac-table-desktop">
                <DataTable columns={columns} rows={plans} getRowHref={(p) => `/platform/plans/${p.id}`} />
              </div>
              <div className="ac-row-cards">
                {plans.map((p) => (
                  <div className="ac-row-card" key={p.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Name</span>
                      <strong style={{ wordBreak: "break-word" }}>
                        <Link href={`/platform/plans/${p.id}`}>{p.name}</Link>
                      </strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Code</span>
                      <span style={{ fontFamily: "monospace" }}>{p.code}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Asset Domain</span>
                      {assetScopeBadge(p.asset_scope)}
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Included Features</span>
                      <span>{p.included_features_count ?? 0} features</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Tenants</span>
                      <span>{p.tenant_count ?? 0} tenants</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Status</span>
                      <StatusBadge {...planStatusBadge(p.is_active)} />
                    </div>
                    <div className="ac-row-card-actions ac-flex ac-gap-2">
                      <Link className="ac-btn" href={`/platform/plans/${p.id}`}>
                        View Details
                      </Link>
                      <button
                        type="button"
                        className="ac-btn ac-btn-secondary"
                        onClick={() => handleOpenEdit(p)}
                      >
                        Edit
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </RealDataPanel>

          {/* CREATE PLAN MODAL */}
          {showCreateModal && (
            <div
              className="ac-modal-overlay"
              style={{
                position: "fixed",
                inset: 0,
                backgroundColor: "rgba(0, 0, 0, 0.75)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1000,
                padding: "var(--ac-space-4)",
              }}
            >
              <div
                className="ac-card"
                style={{
                  width: "100%",
                  maxWidth: 840,
                  maxHeight: "90vh",
                  overflowY: "auto",
                  padding: "var(--ac-space-6)",
                  boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
                }}
              >
                <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                  <div>
                    <h2 className="ac-h2" style={{ margin: 0 }}>Create Commercial Plan</h2>
                    <p className="ac-text-muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                      Define commercial packaging, asset vertical scope, and dynamic ProductFeature entitlements.
                    </p>
                  </div>
                  <button
                    type="button"
                    className="ac-btn ac-btn-ghost"
                    onClick={() => setShowCreateModal(false)}
                    style={{ fontSize: 18, lineHeight: 1 }}
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleCreatePlan}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                    <div>
                      <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
                        Plan Name *
                      </label>
                      <input
                        className="ac-input"
                        placeholder="e.g. Kota Drone Enterprise"
                        value={createName}
                        onChange={(e) => setCreateName(e.target.value)}
                        required
                        style={{ width: "100%" }}
                      />
                    </div>
                    <div>
                      <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
                        Plan Code * (Stable Identifier)
                      </label>
                      <input
                        className="ac-input"
                        placeholder="e.g. DRONE_001"
                        value={createCode}
                        onChange={(e) => setCreateCode(e.target.value.toUpperCase())}
                        required
                        style={{ width: "100%", fontFamily: "monospace" }}
                      />
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 16 }}>
                    <div>
                      <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
                        Asset Domain / Scope
                      </label>
                      <select
                        className="ac-input"
                        value={createScope}
                        onChange={(e) => setCreateScope(e.target.value)}
                        style={{ width: "100%" }}
                      >
                        {ASSET_SCOPES.map((scope) => (
                          <option key={scope.value} value={scope.value}>
                            {scope.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
                        Initial Status
                      </label>
                      <select
                        className="ac-input"
                        value={createIsActive ? "ACTIVE" : "INACTIVE"}
                        onChange={(e) => setCreateIsActive(e.target.value === "ACTIVE")}
                        style={{ width: "100%" }}
                      >
                        <option value="ACTIVE">Active (Available for subscriptions)</option>
                        <option value="INACTIVE">Inactive (Draft / Archived)</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ marginBottom: 20 }}>
                    <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13, fontWeight: 500 }}>
                      Description
                    </label>
                    <textarea
                      className="ac-input"
                      rows={2}
                      placeholder="Commercial terms, target customer tier, or intended airworthiness operational vertical."
                      value={createDescription}
                      onChange={(e) => setCreateDescription(e.target.value)}
                      style={{ width: "100%", resize: "vertical" }}
                    />
                  </div>

                  {/* FEATURE ENTITLEMENTS SECTION */}
                  <div
                    style={{
                      borderTop: "1px solid var(--ac-border)",
                      paddingTop: 16,
                      marginBottom: 20,
                    }}
                  >
                    <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                      <div>
                        <strong className="ac-text-sm" style={{ display: "block" }}>
                          Feature Entitlements ({selectedFeatureKeys.size} selected)
                        </strong>
                        <span className="ac-text-muted" style={{ fontSize: 12 }}>
                          Dynamically loaded from Product Catalog. Select baseline capabilities granted under this plan.
                        </span>
                      </div>
                      <div className="ac-flex ac-gap-2">
                        <button
                          type="button"
                          className={`ac-btn ${featureFilter === "all" ? "ac-btn-primary" : "ac-btn-ghost"}`}
                          style={{ fontSize: 11, padding: "2px 8px" }}
                          onClick={() => setFeatureFilter("all")}
                        >
                          All ({availableFeatures.length})
                        </button>
                        <button
                          type="button"
                          className={`ac-btn ${featureFilter === "included" ? "ac-btn-primary" : "ac-btn-ghost"}`}
                          style={{ fontSize: 11, padding: "2px 8px" }}
                          onClick={() => setFeatureFilter("included")}
                        >
                          Included ({selectedFeatureKeys.size})
                        </button>
                        <button
                          type="button"
                          className={`ac-btn ${featureFilter === "excluded" ? "ac-btn-primary" : "ac-btn-ghost"}`}
                          style={{ fontSize: 11, padding: "2px 8px" }}
                          onClick={() => setFeatureFilter("excluded")}
                        >
                          Excluded ({availableFeatures.length - selectedFeatureKeys.size})
                        </button>
                      </div>
                    </div>

                    <div style={{ marginBottom: 12 }}>
                      <input
                        className="ac-input"
                        placeholder="Search product capabilities by name, description, or stable key..."
                        value={featureSearch}
                        onChange={(e) => setFeatureSearch(e.target.value)}
                        style={{ width: "100%", fontSize: 13 }}
                      />
                    </div>

                    {/* Features List grouped by module */}
                    <div
                      style={{
                        maxHeight: 280,
                        overflowY: "auto",
                        border: "1px solid var(--ac-border)",
                        borderRadius: "var(--ac-radius)",
                        padding: 12,
                        backgroundColor: "rgba(0,0,0,0.2)",
                      }}
                    >
                      {filteredFeaturesByModule.size === 0 ? (
                        <p className="ac-text-muted" style={{ margin: "16px 0", textAlign: "center", fontSize: 13 }}>
                          No features matching criteria.
                        </p>
                      ) : (
                        Array.from(filteredFeaturesByModule.entries()).map(([moduleName, items]) => (
                          <div key={moduleName} style={{ marginBottom: 16 }}>
                            <div
                              className="ac-flex"
                              style={{
                                justifyContent: "space-between",
                                alignItems: "center",
                                paddingBottom: 6,
                                marginBottom: 6,
                                borderBottom: "1px solid var(--ac-border)",
                              }}
                            >
                              <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                                <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                                  {moduleName}
                                </span>
                                <span className="ac-badge" style={{ fontSize: 10 }}>
                                  {items.filter((i) => selectedFeatureKeys.has(i.key)).length}/{items.length}
                                </span>
                              </div>
                              <div className="ac-flex ac-gap-1">
                                <button
                                  type="button"
                                  className="ac-btn ac-btn-ghost"
                                  style={{ fontSize: 11, padding: "1px 6px" }}
                                  onClick={() => selectAllInModule(items)}
                                >
                                  Select all
                                </button>
                                <button
                                  type="button"
                                  className="ac-btn ac-btn-ghost"
                                  style={{ fontSize: 11, padding: "1px 6px" }}
                                  onClick={() => clearAllInModule(items)}
                                >
                                  Clear
                                </button>
                              </div>
                            </div>

                            <div style={{ display: "grid", gap: 6 }}>
                              {items.map((feat) => {
                                const isIncluded = selectedFeatureKeys.has(feat.key);
                                return (
                                  <label
                                    key={feat.key}
                                    style={{
                                      display: "flex",
                                      alignItems: "flex-start",
                                      gap: 10,
                                      padding: "6px 8px",
                                      borderRadius: 4,
                                      backgroundColor: isIncluded ? "rgba(34, 197, 94, 0.08)" : "transparent",
                                      cursor: "pointer",
                                    }}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isIncluded}
                                      onChange={() => toggleFeatureKey(feat.key)}
                                      style={{ marginTop: 3 }}
                                    />
                                    <div style={{ flex: 1 }}>
                                      <div className="ac-flex ac-gap-2" style={{ alignItems: "baseline" }}>
                                        <strong style={{ fontSize: 13 }}>{feat.name}</strong>
                                        <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--ac-text-muted)" }}>
                                          {feat.key}
                                        </span>
                                      </div>
                                      {feat.description && (
                                        <p style={{ margin: "2px 0 0", fontSize: 11, color: "var(--ac-text-muted)" }}>
                                          {feat.description}
                                        </p>
                                      )}
                                    </div>
                                    <span style={{ fontSize: 11, fontWeight: 600, color: isIncluded ? "#4ade80" : "var(--ac-text-muted)" }}>
                                      {isIncluded ? "Included" : "Excluded"}
                                    </span>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {createError && (
                    <div style={{ padding: "8px 12px", marginBottom: 16, backgroundColor: "rgba(239, 68, 68, 0.15)", borderRadius: 4, border: "1px solid rgba(239, 68, 68, 0.3)" }}>
                      <p style={{ margin: 0, fontSize: 13, color: "#f87171" }}>{createError.message}</p>
                    </div>
                  )}

                  <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end" }}>
                    <button
                      type="button"
                      className="ac-btn ac-btn-ghost"
                      onClick={() => setShowCreateModal(false)}
                      disabled={creating}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="ac-btn ac-btn-primary"
                      disabled={creating || !createName.trim() || !createCode.trim()}
                    >
                      {creating ? "Creating Plan…" : "Save & Create Plan"}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* QUICK EDIT MODAL */}
          {editingPlan && (
            <div
              className="ac-modal-overlay"
              style={{
                position: "fixed",
                inset: 0,
                backgroundColor: "rgba(0, 0, 0, 0.75)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1000,
                padding: "var(--ac-space-4)",
              }}
            >
              <div
                className="ac-card"
                style={{
                  width: "100%",
                  maxWidth: 540,
                  padding: "var(--ac-space-6)",
                  boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
                }}
              >
                <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Edit Plan Metadata</h2>
                  <button
                    type="button"
                    className="ac-btn ac-btn-ghost"
                    onClick={() => setEditingPlan(null)}
                  >
                    ✕
                  </button>
                </div>

                <div style={{ display: "grid", gap: 14 }}>
                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13 }}>
                      Plan Name *
                    </label>
                    <input
                      className="ac-input"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </div>

                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13 }}>
                      Plan Code *
                    </label>
                    <input
                      className="ac-input"
                      value={editCode}
                      onChange={(e) => setEditCode(e.target.value.toUpperCase())}
                      style={{ width: "100%", fontFamily: "monospace" }}
                    />
                  </div>

                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13 }}>
                      Asset Domain / Scope
                    </label>
                    <select
                      className="ac-input"
                      value={editScope}
                      onChange={(e) => setEditScope(e.target.value)}
                      style={{ width: "100%" }}
                    >
                      {ASSET_SCOPES.map((scope) => (
                        <option key={scope.value} value={scope.value}>
                          {scope.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 6, fontSize: 13 }}>
                      Description
                    </label>
                    <textarea
                      className="ac-input"
                      rows={3}
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      style={{ width: "100%", resize: "vertical" }}
                    />
                  </div>

                  {editError && (
                    <p style={{ margin: 0, fontSize: 13, color: "var(--ac-status-non-compliant)" }}>
                      {editError.message}
                    </p>
                  )}

                  <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end", marginTop: 8 }}>
                    <button
                      type="button"
                      className="ac-btn ac-btn-ghost"
                      onClick={() => setEditingPlan(null)}
                      disabled={editBusy}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="ac-btn ac-btn-primary"
                      onClick={handleSaveEdit}
                      disabled={editBusy || !editName.trim() || !editCode.trim()}
                    >
                      {editBusy ? "Saving…" : "Save Changes"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ACTIVATE / DEACTIVATE CONFIRM DIALOG */}
          <ConfirmDialog
            open={planToToggle !== null}
            title={planToToggle?.is_active ? "Deactivate Commercial Plan" : "Activate Commercial Plan"}
            body={
              planToToggle?.is_active
                ? `Deactivating "${planToToggle.name}" (${planToToggle.code}) will prevent any new tenant subscriptions. Existing subscribers will retain their current plan entitlements under INACTIVE_PLAN resolution.`
                : `Activating "${planToToggle?.name}" (${planToToggle?.code}) will make it available for new customer subscriptions.`
            }
            confirmLabel={planToToggle?.is_active ? "Deactivate Plan" : "Activate Plan"}
            busy={toggleBusy}
            onConfirm={handleToggleActive}
            onCancel={() => setPlanToToggle(null)}
          />
        </>
      )}
    </div>
  );
}
