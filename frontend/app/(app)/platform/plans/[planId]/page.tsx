"use client";

// Platform Admin — Plan Details & Entitlements Administration.
// Strictly adheres to the two-tier governance architecture:
// Section A: Plan Overview
// Section B: Feature Entitlements (Dynamic from Product Catalog)
// Section C: Usage Limits (Standard Baseline Ceilings)
// Section D: Tenant Usage (Subscribed Organizations)
// Section E: Audit & Activity Log

import { useEffect, useMemo, useState, use } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  planApi,
  type PlanResponse,
  type PlanFeatureResponse,
  type PlanSubscribedTenantResponse,
} from "@/lib/api/plan";
import { productCatalogApi } from "@/lib/api/productCatalog";
import type { AuditEventResponse } from "@/lib/api/audit";
import { DEMO_PLATFORM_PLANS, DEMO_PLATFORM_FEATURES, DEMO_PLATFORM_ORGANIZATIONS } from "@/lib/demo/demoPlatform";

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

export interface EditablePlanLimit {
  key: string;
  dimension: string;
  category: string;
  unit: string;
  description: string;
  value: number;
  isUnlimited: boolean;
}

export const STANDARD_LIMIT_SPECS: Record<
  string,
  { key: string; dimension: string; category: string; unit: string; description: string; defaultVal: number }[]
> = {
  DRONE: [
    { key: "max_assets", dimension: "Maximum Assets", category: "Fleet", unit: "airframes", description: "Autonomous UAV fleet capacity", defaultVal: 100 },
    { key: "max_users", dimension: "Maximum Users", category: "Users", unit: "seats", description: "Licensed remote pilots & mission coordinators", defaultVal: 25 },
    { key: "monthly_work_orders", dimension: "Monthly Work Orders", category: "MRO", unit: "orders/mo", description: "Scheduled and unscheduled battery/component repairs", defaultVal: 500 },
    { key: "storage_gb", dimension: "Storage", category: "Infrastructure", unit: "GB", description: "High-frequency mission telemetry and flight logs", defaultVal: 50 },
    { key: "monthly_lisa_ai_tokens", dimension: "Monthly LISA AI Tokens", category: "Intelligence", unit: "tokens/mo", description: "Airworthiness manual queries and copilot assist", defaultVal: 100000 },
    { key: "monthly_api_requests", dimension: "Monthly API Requests", category: "Integration", unit: "req/mo", description: "Fleet dispatch and UTM external integrations", defaultVal: 10000 },
  ],
  AIRCRAFT: [
    { key: "max_assets", dimension: "Maximum Assets", category: "Fleet", unit: "aircraft", description: "Fixed-wing commercial aircraft airframes", defaultVal: 50 },
    { key: "max_users", dimension: "Maximum Users", category: "Users", unit: "seats", description: "CAMO managers, technicians, and quality inspectors", defaultVal: 40 },
    { key: "monthly_work_orders", dimension: "Monthly Work Orders", category: "MRO", unit: "orders/mo", description: "Line and base maintenance tasks and task cards", defaultVal: 1000 },
    { key: "storage_gb", dimension: "Storage", category: "Infrastructure", unit: "GB", description: "Form 1 release certificates, ADs, and SB records", defaultVal: 200 },
    { key: "monthly_lisa_ai_tokens", dimension: "Monthly LISA AI Tokens", category: "Intelligence", unit: "tokens/mo", description: "Regulatory compliance analysis and technical records", defaultVal: 500000 },
    { key: "monthly_api_requests", dimension: "Monthly API Requests", category: "Integration", unit: "req/mo", description: "Maintenance ERP and electronic flight bag sync", defaultVal: 50000 },
  ],
  HELICOPTER: [
    { key: "max_assets", dimension: "Maximum Assets", category: "Fleet", unit: "helicopters", description: "Registered rotorcraft airframes and dynamic components", defaultVal: 30 },
    { key: "max_users", dimension: "Maximum Users", category: "Users", unit: "seats", description: "Rotorcraft engineers, inspectors, and chief pilots", defaultVal: 30 },
    { key: "monthly_work_orders", dimension: "Monthly Work Orders", category: "MRO", unit: "orders/mo", description: "Turbine, gearbox, and rotor blade inspections", defaultVal: 600 },
    { key: "storage_gb", dimension: "Storage", category: "Infrastructure", unit: "GB", description: "Component retirement tracking and life-limited parts", defaultVal: 100 },
    { key: "monthly_lisa_ai_tokens", dimension: "Monthly LISA AI Tokens", category: "Intelligence", unit: "tokens/mo", description: "Airworthiness directive search and AMM queries", defaultVal: 200000 },
    { key: "monthly_api_requests", dimension: "Monthly API Requests", category: "Integration", unit: "req/mo", description: "Dispatch operations and maintenance integration", defaultVal: 20000 },
  ],
  EVTOL: [
    { key: "max_assets", dimension: "Maximum Assets", category: "Fleet", unit: "airframes", description: "Next-gen electric vertical takeoff and landing airframes", defaultVal: 75 },
    { key: "max_users", dimension: "Maximum Users", category: "Users", unit: "seats", description: "Flight operations center, battery engineers, and safety", defaultVal: 50 },
    { key: "monthly_work_orders", dimension: "Monthly Work Orders", category: "MRO", unit: "orders/mo", description: "Electric propulsion and high-voltage battery maintenance", defaultVal: 1500 },
    { key: "storage_gb", dimension: "Storage", category: "Infrastructure", unit: "GB", description: "Continuous flight sensor stream and battery telemetry", defaultVal: 500 },
    { key: "monthly_lisa_ai_tokens", dimension: "Monthly LISA AI Tokens", category: "Intelligence", unit: "tokens/mo", description: "Predictive maintenance and airworthiness copilot", defaultVal: 1000000 },
    { key: "monthly_api_requests", dimension: "Monthly API Requests", category: "Integration", unit: "req/mo", description: "Real-time vertiport and urban air traffic interfaces", defaultVal: 100000 },
  ],
  ALL: [
    { key: "max_assets", dimension: "Maximum Assets", category: "Fleet", unit: "assets", description: "Multi-domain fleet tracking capacity", defaultVal: 100 },
    { key: "max_users", dimension: "Maximum Users", category: "Users", unit: "seats", description: "Active organization user accounts", defaultVal: 50 },
    { key: "monthly_work_orders", dimension: "Monthly Work Orders", category: "MRO", unit: "orders/mo", description: "Total monthly maintenance executions", defaultVal: 1000 },
    { key: "storage_gb", dimension: "Storage", category: "Infrastructure", unit: "GB", description: "Compliance evidence and media records", defaultVal: 150 },
    { key: "monthly_lisa_ai_tokens", dimension: "Monthly LISA AI Tokens", category: "Intelligence", unit: "tokens/mo", description: "Aerospace intelligence copilot queries", defaultVal: 250000 },
    { key: "monthly_api_requests", dimension: "Monthly API Requests", category: "Integration", unit: "req/mo", description: "External system API integration limits", defaultVal: 25000 },
  ],
};

type PendingFeatureAction = {
  featureKey: string;
  featureName: string;
  newEnabled: boolean;
};

export default function PlanDetailPage({ params }: { params: Promise<{ planId: string }> }) {
  const resolvedParams = use(params);
  const planId = resolvedParams.planId;

  const { accessToken, isAuthenticated } = useSession();
  const { mode } = useDataMode();

  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [planError, setPlanError] = useState<NormalizedApiError | null>(null);
  const [loading, setLoading] = useState(true);

  // Dynamic Product Catalog features and plan features
  const [allCatalogFeatures, setAllCatalogFeatures] = useState<CatalogFeatureItem[]>([]);
  const [planFeaturesMap, setPlanFeaturesMap] = useState<Map<string, boolean>>(new Map());
  const [featuresLoading, setFeaturesLoading] = useState(false);

  // Subscribed tenants
  const [subscribedTenants, setSubscribedTenants] = useState<PlanSubscribedTenantResponse[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(false);

  // Audit activity trail
  const [auditEvents, setAuditEvents] = useState<AuditEventResponse[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  // Feature search & filter
  const [featureSearch, setFeatureSearch] = useState("");
  const [featureFilter, setFeatureFilter] = useState<"all" | "included" | "excluded">("all");

  // Edit Plan Overview State
  const [editingOverview, setEditingOverview] = useState(false);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editScope, setEditScope] = useState("DRONE");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<NormalizedApiError | null>(null);

  // Confirm Actions
  const [pendingFeatureToggle, setPendingFeatureToggle] = useState<PendingFeatureAction | null>(null);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [planToggleActive, setPlanToggleActive] = useState<boolean | null>(null);

  // Editable Plan limits state
  const [editableLimits, setEditableLimits] = useState<EditablePlanLimit[]>([]);
  const [limitsBusy, setLimitsBusy] = useState(false);
  const [limitsSuccess, setLimitsSuccess] = useState<string | null>(null);
  const [limitsError, setLimitsError] = useState<string | null>(null);

  const loadData = () => {
    if (mode === "DEMO") {
      const demoPlan = DEMO_PLATFORM_PLANS.find((p) => p.id === planId) ?? DEMO_PLATFORM_PLANS[0];
      setPlan(demoPlan);
      setEditName(demoPlan.name);
      setEditCode(demoPlan.code);
      setEditDescription(demoPlan.description ?? "");
      setEditScope(demoPlan.asset_scope ?? "ALL");

      // Features
      const demoFeatures: CatalogFeatureItem[] = DEMO_PLATFORM_FEATURES.map((f) => ({
        key: f.feature_key,
        name: f.name,
        moduleName: f.category,
        suiteName: "Platform Suite",
        description: f.description,
      }));
      setAllCatalogFeatures(demoFeatures);

      // Current plan features map
      const fMap = new Map<string, boolean>();
      for (const feat of demoFeatures) {
        // Starter has fewer, enterprise has all
        const isIncluded =
          demoPlan.code.toLowerCase().includes("enterprise") ||
          demoPlan.code.toLowerCase().includes("evtol") ||
          (demoPlan.code.toLowerCase().includes("aircraft") && feat.moduleName !== "Fleet Operations") ||
          (demoPlan.code.toLowerCase().includes("drone") && feat.key.includes("drone")) ||
          feat.key === "work_order_management" ||
          feat.key === "compliance_management";
        fMap.set(feat.key, isIncluded);
      }
      setPlanFeaturesMap(fMap);

      // Subscribed tenants
      setSubscribedTenants(
        DEMO_PLATFORM_ORGANIZATIONS.slice(0, 2).map((org) => ({
          organization_id: org.id,
          organization_name: org.name,
          organization_status: org.status,
          subscription_id: `sub-${org.id.slice(-6)}`,
          subscription_status: "ACTIVE",
          starts_at: "2026-01-15T00:00:00Z",
          ends_at: null,
        }))
      );

      // Audit Events
      setAuditEvents([
        {
          id: "audit-001",
          organization_id: "00000000-0000-0000-0000-000000000001",
          user_id: "00000000-0000-0000-0000-000000000099",
          action: "platform.plan.created",
          entity_type: "Plan",
          entity_id: demoPlan.id,
          event_metadata: { code: demoPlan.code, name: demoPlan.name, asset_scope: demoPlan.asset_scope },
          created_at: demoPlan.created_at,
        },
        {
          id: "audit-002",
          organization_id: "00000000-0000-0000-0000-000000000001",
          user_id: "00000000-0000-0000-0000-000000000099",
          action: "platform.plan.features_updated",
          entity_type: "Plan",
          entity_id: demoPlan.id,
          event_metadata: { total_configured: 9 },
          created_at: demoPlan.updated_at,
        },
      ]);

      // Plan Limits
      const scopeKey = (demoPlan.asset_scope ?? "ALL").toUpperCase();
      const specs = STANDARD_LIMIT_SPECS[scopeKey] ?? STANDARD_LIMIT_SPECS.ALL;
      setEditableLimits(
        specs.map((s) => ({
          key: s.key,
          dimension: s.dimension,
          category: s.category,
          unit: s.unit,
          description: s.description,
          value: s.defaultVal,
          isUnlimited: false,
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
    setPlanError(null);
    setFeaturesLoading(true);
    setTenantsLoading(true);
    setAuditLoading(true);

    // 1. Fetch Plan details & current features & limits
    Promise.allSettled([
      planApi.getPlan(accessToken, planId),
      planApi.listPlanFeatures(accessToken, planId),
      productCatalogApi.getCatalogTree(accessToken),
      planApi.listPlanTenants(accessToken, planId),
      planApi.getPlanAuditTrail(accessToken, planId),
      planApi.listPlanLimits(accessToken, planId),
    ]).then(([planRes, planFeatsRes, catalogRes, tenantsRes, auditRes, limitsRes]) => {
      let resolvedPlan: PlanResponse | null = null;
      if (planRes.status === "fulfilled") {
        resolvedPlan = planRes.value;
        setPlan(planRes.value);
        setEditName(planRes.value.name);
        setEditCode(planRes.value.code);
        setEditDescription(planRes.value.description ?? "");
        setEditScope(planRes.value.asset_scope ?? "ALL");
      } else {
        setPlanError(normalizeApiError(planRes.reason));
      }

      // Populate plan limits
      const scopeKey = (resolvedPlan?.asset_scope ?? "ALL").toUpperCase();
      const specs = STANDARD_LIMIT_SPECS[scopeKey] ?? STANDARD_LIMIT_SPECS.ALL;
      const backendLimits = limitsRes.status === "fulfilled" ? limitsRes.value : [];
      const backendLimitMap = new Map(backendLimits.map((l) => [l.limit_key, l]));

      setEditableLimits(
        specs.map((s) => {
          const bl = backendLimitMap.get(s.key);
          return {
            key: s.key,
            dimension: s.dimension,
            category: s.category,
            unit: s.unit,
            description: s.description,
            value: bl && bl.limit_value !== null ? bl.limit_value : s.defaultVal,
            isUnlimited: bl ? bl.is_unlimited : false,
          };
        })
      );

      // Feature map from PlanFeature records
      const featMap = new Map<string, boolean>();
      if (planFeatsRes.status === "fulfilled") {
        for (const pf of planFeatsRes.value) {
          featMap.set(pf.feature_key, pf.enabled);
        }
      }
      setPlanFeaturesMap(featMap);

      // Product Catalog features
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
        setAllCatalogFeatures(
          flattened.length > 0
            ? flattened
            : DEMO_PLATFORM_FEATURES.map((f) => ({
                key: f.feature_key,
                name: f.name,
                moduleName: f.category,
                suiteName: "Platform Suite",
                description: f.description,
              }))
        );
      } else {
        setAllCatalogFeatures(
          DEMO_PLATFORM_FEATURES.map((f) => ({
            key: f.feature_key,
            name: f.name,
            moduleName: f.category,
            suiteName: "Platform Suite",
            description: f.description,
          }))
        );
      }

      // Subscribed tenants
      if (tenantsRes.status === "fulfilled") {
        setSubscribedTenants(tenantsRes.value);
      } else {
        setSubscribedTenants([]);
      }

      // Audit trail
      if (auditRes.status === "fulfilled") {
        setAuditEvents(auditRes.value);
      } else {
        setAuditEvents([]);
      }

      setLoading(false);
      setFeaturesLoading(false);
      setTenantsLoading(false);
      setAuditLoading(false);
    });
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId, mode, accessToken, isAuthenticated]);

  // Group catalog features by Module
  const featuresByModule = useMemo(() => {
    const map = new Map<string, CatalogFeatureItem[]>();
    for (const f of allCatalogFeatures) {
      const groupKey = f.moduleName || f.suiteName || "General Capabilities";
      if (!map.has(groupKey)) {
        map.set(groupKey, []);
      }
      map.get(groupKey)!.push(f);
    }
    return map;
  }, [allCatalogFeatures]);

  // Filter features
  const filteredFeaturesByModule = useMemo(() => {
    const query = featureSearch.toLowerCase().trim();
    const result = new Map<string, CatalogFeatureItem[]>();

    for (const [moduleName, items] of featuresByModule.entries()) {
      const filtered = items.filter((f) => {
        const matchesQuery =
          !query ||
          f.name.toLowerCase().includes(query) ||
          f.key.toLowerCase().includes(query) ||
          f.description.toLowerCase().includes(query);

        if (!matchesQuery) return false;

        const isIncluded = planFeaturesMap.get(f.key) === true;
        if (featureFilter === "included") return isIncluded;
        if (featureFilter === "excluded") return !isIncluded;
        return true;
      });

      if (filtered.length > 0) {
        result.set(moduleName, filtered);
      }
    }
    return result;
  }, [featuresByModule, featureSearch, featureFilter, planFeaturesMap]);

  // Save Plan Overview Changes
  const handleSaveOverview = async () => {
    if (!plan || !editName.trim() || !editCode.trim()) return;

    if (mode === "DEMO") {
      setPlan({
        ...plan,
        name: editName.trim(),
        code: editCode.trim().toUpperCase(),
        description: editDescription.trim() || null,
        asset_scope: editScope === "ALL" ? null : editScope,
      });
      setEditingOverview(false);
      return;
    }

    if (!accessToken) return;
    setEditBusy(true);
    setEditError(null);

    try {
      const updated = await planApi.updatePlan(accessToken, plan.id, {
        name: editName.trim(),
        code: editCode.trim().toUpperCase(),
        description: editDescription.trim() || null,
        asset_scope: editScope === "ALL" ? null : editScope,
      });
      setPlan(updated);
      setEditingOverview(false);
      loadData();
    } catch (err) {
      setEditError(normalizeApiError(err));
    } finally {
      setEditBusy(false);
    }
  };

  // Toggle Plan Activation
  const handleTogglePlanActive = async () => {
    if (!plan || planToggleActive === null) return;

    if (mode === "DEMO") {
      setPlan({ ...plan, is_active: planToggleActive });
      setPlanToggleActive(null);
      return;
    }

    if (!accessToken) return;
    setToggleBusy(true);

    try {
      if (planToggleActive) {
        await planApi.activatePlan(accessToken, plan.id);
      } else {
        await planApi.deactivatePlan(accessToken, plan.id);
      }
      setPlanToggleActive(null);
      loadData();
    } catch (err) {
      setPlanError(normalizeApiError(err));
    } finally {
      setToggleBusy(false);
    }
  };

  // Execute Feature Toggle
  const handleConfirmFeatureToggle = async () => {
    if (!plan || !pendingFeatureToggle) return;

    const { featureKey, newEnabled } = pendingFeatureToggle;

    if (mode === "DEMO") {
      setPlanFeaturesMap((prev) => {
        const next = new Map(prev);
        next.set(featureKey, newEnabled);
        return next;
      });
      setPendingFeatureToggle(null);
      return;
    }

    if (!accessToken) return;
    setToggleBusy(true);

    try {
      await planApi.setPlanFeatureEnabled(accessToken, plan.id, featureKey, newEnabled);
      setPlanFeaturesMap((prev) => {
        const next = new Map(prev);
        next.set(featureKey, newEnabled);
        return next;
      });
      setPendingFeatureToggle(null);
      loadData();
    } catch (err) {
      setPlanError(normalizeApiError(err));
    } finally {
      setToggleBusy(false);
    }
  };

  // Batch toggle an entire module
  const handleToggleCategory = async (items: CatalogFeatureItem[], enableAll: boolean) => {
    if (!plan) return;

    if (mode === "DEMO") {
      setPlanFeaturesMap((prev) => {
        const next = new Map(prev);
        for (const item of items) next.set(item.key, enableAll);
        return next;
      });
      return;
    }

    if (!accessToken) return;

    try {
      const payload = items.map((i) => ({
        feature_key: i.key,
        enabled: enableAll,
      }));
      await planApi.bulkSetPlanFeatures(accessToken, plan.id, payload);
      loadData();
    } catch (err) {
      setPlanError(normalizeApiError(err));
    }
  };

  const handleSaveLimits = async () => {
    setLimitsBusy(true);
    setLimitsSuccess(null);
    setLimitsError(null);

    // Validation
    for (const lim of editableLimits) {
      if (!lim.isUnlimited && (isNaN(lim.value) || lim.value < 0)) {
        setLimitsError(`Please provide a valid non-negative integer for ${lim.dimension}.`);
        setLimitsBusy(false);
        return;
      }
    }

    if (mode === "DEMO") {
      setTimeout(() => {
        setLimitsBusy(false);
        setLimitsSuccess("Plan usage limits saved successfully (Demo mode).");
        setAuditEvents((prev) => [
          {
            id: `audit-${Date.now()}`,
            organization_id: "00000000-0000-0000-0000-000000000001",
            user_id: "00000000-0000-0000-0000-000000000099",
            action: "platform.plan_limit.updated",
            entity_type: "PlanLimit",
            entity_id: planId,
            event_metadata: { plan_id: planId, total_limits: editableLimits.length },
            created_at: new Date().toISOString(),
          },
          ...prev,
        ]);
      }, 300);
      return;
    }

    if (!accessToken) {
      setLimitsBusy(false);
      return;
    }

    try {
      const payload = editableLimits.map((l) => ({
        limit_key: l.key,
        limit_value: l.isUnlimited ? null : Math.floor(Number(l.value)),
        is_unlimited: l.isUnlimited,
      }));
      await planApi.bulkSetPlanLimits(accessToken, planId, payload);
      setLimitsSuccess("Plan usage limits saved successfully and active for all subscribers.");
      const updatedAudit = await planApi.getPlanAuditTrail(accessToken, planId);
      setAuditEvents(updatedAudit);
    } catch (err) {
      const norm = normalizeApiError(err);
      setLimitsError(norm.message);
    } finally {
      setLimitsBusy(false);
    }
  };

  const includedCount = useMemo(() => {
    let count = 0;
    for (const enabled of planFeaturesMap.values()) {
      if (enabled) count++;
    }
    return count;
  }, [planFeaturesMap]);

  if (!isAuthenticated) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
        </p>
      </div>
    );
  }

  const forbidden = planError?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Plans", href: "/platform/plans" },
          { label: plan?.name ?? planId },
        ]}
      />

      {loading ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-6)" }}>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Loading commercial plan specification from backend…
          </p>
        </div>
      ) : forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view or administer plans.
          </p>
        </div>
      ) : !plan ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Not Found" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            The requested commercial plan does not exist.
          </p>
        </div>
      ) : (
        <>
          {/* SECTION A: PLAN OVERVIEW */}
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-6)", marginBottom: "var(--ac-space-6)" }}>
            <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
              <div>
                <div className="ac-flex ac-gap-2" style={{ alignItems: "center", marginBottom: 6 }}>
                  <h1 className="ac-h1" style={{ margin: 0 }}>{plan.name}</h1>
                  {assetScopeBadge(plan.asset_scope)}
                  <StatusBadge {...planStatusBadge(plan.is_active)} />
                </div>
                <div className="ac-flex ac-gap-3" style={{ fontSize: 13, color: "var(--ac-text-muted)", alignItems: "center" }}>
                  <span>Code: <strong style={{ fontFamily: "monospace", color: "var(--ac-text)" }}>{plan.code}</strong></span>
                  <span>•</span>
                  <span>Included Features: <strong>{includedCount}</strong></span>
                  <span>•</span>
                  <span>Active Tenants: <strong>{subscribedTenants.length}</strong></span>
                </div>
                {plan.description && (
                  <p className="ac-text-muted" style={{ margin: "10px 0 0", maxWidth: 680, fontSize: 14 }}>
                    {plan.description}
                  </p>
                )}
              </div>

              <div className="ac-flex ac-gap-2">
                <button
                  type="button"
                  className="ac-btn ac-btn-secondary"
                  onClick={() => setEditingOverview(!editingOverview)}
                >
                  {editingOverview ? "Cancel Edit" : "Edit Plan Metadata"}
                </button>
                <button
                  type="button"
                  className={`ac-btn ${plan.is_active ? "ac-btn-ghost" : "ac-btn-primary"}`}
                  style={{
                    color: plan.is_active ? "var(--ac-status-non-compliant)" : undefined,
                  }}
                  onClick={() => setPlanToggleActive(!plan.is_active)}
                >
                  {plan.is_active ? "Deactivate Plan" : "Activate Plan"}
                </button>
              </div>
            </div>

            {/* EDIT OVERVIEW FORM */}
            {editingOverview && (
              <div
                style={{
                  marginTop: 20,
                  paddingTop: 20,
                  borderTop: "1px solid var(--ac-border)",
                  display: "grid",
                  gap: 14,
                  maxWidth: 640,
                }}
              >
                <h3 className="ac-h3" style={{ margin: 0 }}>Update Plan Metadata</h3>
                <div>
                  <label className="ac-label" style={{ display: "block", marginBottom: 4, fontSize: 12 }}>
                    Plan Name
                  </label>
                  <input
                    className="ac-input"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label className="ac-label" style={{ display: "block", marginBottom: 4, fontSize: 12 }}>
                    Plan Code
                  </label>
                  <input
                    className="ac-input"
                    value={editCode}
                    onChange={(e) => setEditCode(e.target.value.toUpperCase())}
                    style={{ width: "100%", fontFamily: "monospace" }}
                  />
                </div>
                <div>
                  <label className="ac-label" style={{ display: "block", marginBottom: 4, fontSize: 12 }}>
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
                  <label className="ac-label" style={{ display: "block", marginBottom: 4, fontSize: 12 }}>
                    Description
                  </label>
                  <textarea
                    className="ac-input"
                    rows={2}
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

                <div className="ac-flex ac-gap-2">
                  <button
                    type="button"
                    className="ac-btn ac-btn-primary"
                    disabled={editBusy || !editName.trim() || !editCode.trim()}
                    onClick={handleSaveOverview}
                  >
                    {editBusy ? "Saving…" : "Save Metadata"}
                  </button>
                  <button
                    type="button"
                    className="ac-btn ac-btn-ghost"
                    onClick={() => setEditingOverview(false)}
                    disabled={editBusy}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* SECTION B: FEATURE ENTITLEMENTS */}
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-6)", marginBottom: "var(--ac-space-6)" }}>
            <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
              <div>
                <h2 className="ac-h2" style={{ margin: 0 }}>Commercial Feature Entitlements</h2>
                <p className="ac-text-muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                  Baseline capabilities provided by this plan. Changes propagate to all subscribed tenants via <code>resolve_entitlements()</code> unless overridden.
                </p>
              </div>

              <div className="ac-flex ac-gap-2">
                <button
                  type="button"
                  className={`ac-btn ${featureFilter === "all" ? "ac-btn-primary" : "ac-btn-ghost"}`}
                  style={{ fontSize: 12, padding: "3px 10px" }}
                  onClick={() => setFeatureFilter("all")}
                >
                  All ({allCatalogFeatures.length})
                </button>
                <button
                  type="button"
                  className={`ac-btn ${featureFilter === "included" ? "ac-btn-primary" : "ac-btn-ghost"}`}
                  style={{ fontSize: 12, padding: "3px 10px" }}
                  onClick={() => setFeatureFilter("included")}
                >
                  Included ({includedCount})
                </button>
                <button
                  type="button"
                  className={`ac-btn ${featureFilter === "excluded" ? "ac-btn-primary" : "ac-btn-ghost"}`}
                  style={{ fontSize: 12, padding: "3px 10px" }}
                  onClick={() => setFeatureFilter("excluded")}
                >
                  Excluded ({allCatalogFeatures.length - includedCount})
                </button>
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <input
                className="ac-input"
                placeholder="Search capabilities by name, description, or canonical key..."
                value={featureSearch}
                onChange={(e) => setFeatureSearch(e.target.value)}
                style={{ width: "100%", fontSize: 13 }}
              />
            </div>

            {filteredFeaturesByModule.size === 0 ? (
              <div style={{ padding: 24, textAlign: "center", color: "var(--ac-text-muted)" }}>
                No product features matching current filter.
              </div>
            ) : (
              <div style={{ display: "grid", gap: 20 }}>
                {Array.from(filteredFeaturesByModule.entries()).map(([moduleName, items]) => {
                  const moduleIncludedCount = items.filter((i) => planFeaturesMap.get(i.key) === true).length;
                  return (
                    <div
                      key={moduleName}
                      style={{
                        border: "1px solid var(--ac-border)",
                        borderRadius: "var(--ac-radius)",
                        padding: 16,
                        backgroundColor: "rgba(0,0,0,0.15)",
                      }}
                    >
                      <div
                        className="ac-flex"
                        style={{
                          justifyContent: "space-between",
                          alignItems: "center",
                          paddingBottom: 10,
                          marginBottom: 10,
                          borderBottom: "1px solid var(--ac-border)",
                        }}
                      >
                        <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                          <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                            {moduleName}
                          </span>
                          <span className="ac-badge" style={{ fontSize: 11 }}>
                            {moduleIncludedCount}/{items.length} Included
                          </span>
                        </div>
                        <div className="ac-flex ac-gap-1">
                          <button
                            type="button"
                            className="ac-btn ac-btn-ghost"
                            style={{ fontSize: 11, padding: "2px 8px" }}
                            onClick={() => handleToggleCategory(items, true)}
                          >
                            Include All
                          </button>
                          <button
                            type="button"
                            className="ac-btn ac-btn-ghost"
                            style={{ fontSize: 11, padding: "2px 8px" }}
                            onClick={() => handleToggleCategory(items, false)}
                          >
                            Exclude All
                          </button>
                        </div>
                      </div>

                      <div style={{ display: "grid", gap: 8 }}>
                        {items.map((feat) => {
                          const isIncluded = planFeaturesMap.get(feat.key) === true;
                          return (
                            <div
                              key={feat.key}
                              className="ac-flex"
                              style={{
                                justifyContent: "space-between",
                                alignItems: "center",
                                padding: "8px 12px",
                                borderRadius: 4,
                                backgroundColor: isIncluded ? "rgba(34, 197, 94, 0.06)" : "transparent",
                                border: isIncluded ? "1px solid rgba(34, 197, 94, 0.2)" : "1px solid transparent",
                              }}
                            >
                              <div style={{ flex: 1, paddingRight: 16 }}>
                                <div className="ac-flex ac-gap-2" style={{ alignItems: "baseline" }}>
                                  <span style={{ color: isIncluded ? "#4ade80" : "var(--ac-text-muted)", fontSize: 14 }}>
                                    {isIncluded ? "✓" : "○"}
                                  </span>
                                  <strong style={{ fontSize: 14, color: isIncluded ? "var(--ac-text)" : "var(--ac-text-muted)" }}>
                                    {feat.name}
                                  </strong>
                                  <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--ac-text-muted)" }}>
                                    {feat.key}
                                  </span>
                                </div>
                                {feat.description && (
                                  <p style={{ margin: "3px 0 0 20px", fontSize: 12, color: "var(--ac-text-muted)" }}>
                                    {feat.description}
                                  </p>
                                )}
                              </div>

                              <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                                <StatusBadge
                                  status={isIncluded ? "TRUE" : "FALSE"}
                                  label={isIncluded ? "Included" : "Excluded"}
                                />
                                <button
                                  type="button"
                                  className={`ac-btn ${isIncluded ? "ac-btn-ghost" : "ac-btn-secondary"}`}
                                  style={{
                                    fontSize: 12,
                                    padding: "3px 10px",
                                    color: isIncluded ? "var(--ac-status-non-compliant)" : undefined,
                                  }}
                                  onClick={() =>
                                    setPendingFeatureToggle({
                                      featureKey: feat.key,
                                      featureName: feat.name,
                                      newEnabled: !isIncluded,
                                    })
                                  }
                                >
                                  {isIncluded ? "Exclude" : "Include"}
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* SECTION C: USAGE LIMITS */}
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-6)", marginBottom: "var(--ac-space-6)" }}>
            <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
              <div>
                <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Plan Usage Limits</h2>
                  <span className="ac-badge" style={{ backgroundColor: "rgba(59, 130, 246, 0.15)", color: "#60a5fa", border: "1px solid rgba(59, 130, 246, 0.3)", fontSize: 11 }}>
                    PLAN DEFAULT
                  </span>
                </div>
                <p className="ac-text-muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                  Commercial consumption ceilings configured as baseline defaults for <strong>{plan.name}</strong>. Subscribed tenants automatically inherit these limits unless a specific tenant override is configured via Tenant Entitlements.
                </p>
              </div>
              <button
                type="button"
                className="ac-btn ac-btn-primary"
                onClick={handleSaveLimits}
                disabled={limitsBusy}
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                {limitsBusy ? "Saving..." : "Save Plan Limits"}
              </button>
            </div>

            {limitsSuccess && (
              <div className="ac-alert ac-alert-success" style={{ marginBottom: 16 }}>
                {limitsSuccess}
              </div>
            )}

            {limitsError && (
              <div className="ac-alert ac-alert-danger" style={{ marginBottom: 16 }}>
                {limitsError}
              </div>
            )}

            <div style={{ overflowX: "auto" }}>
              <table className="ac-table" style={{ width: "100%", textAlign: "left" }}>
                <thead>
                  <tr>
                    <th style={{ width: "22%" }}>Dimension</th>
                    <th style={{ width: "12%" }}>Category</th>
                    <th style={{ width: "24%" }}>Configured Limit Value</th>
                    <th style={{ width: "16%" }}>Unlimited</th>
                    <th style={{ width: "26%" }}>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {editableLimits.map((limit, idx) => (
                    <tr key={limit.key}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{limit.dimension}</div>
                        <div style={{ fontFamily: "monospace", fontSize: 11, color: "var(--ac-text-muted)" }}>
                          {limit.key}
                        </div>
                      </td>
                      <td>
                        <span className="ac-badge" style={{ fontSize: 11 }}>
                          {limit.category}
                        </span>
                      </td>
                      <td>
                        <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                          <input
                            type="number"
                            min="0"
                            className="ac-input"
                            disabled={limit.isUnlimited || limitsBusy}
                            value={limit.isUnlimited ? "" : limit.value}
                            onChange={(e) => {
                              const val = e.target.value === "" ? 0 : parseInt(e.target.value, 10);
                              setEditableLimits((prev) =>
                                prev.map((item, i) => (i === idx ? { ...item, value: isNaN(val) ? 0 : val } : item))
                              );
                            }}
                            style={{
                              width: 130,
                              fontFamily: "monospace",
                              fontSize: 13,
                              opacity: limit.isUnlimited ? 0.4 : 1,
                            }}
                          />
                          <span className="ac-text-muted" style={{ fontSize: 12 }}>
                            {limit.unit}
                          </span>
                        </div>
                      </td>
                      <td>
                        <label className="ac-flex ac-gap-2" style={{ alignItems: "center", cursor: "pointer", fontSize: 13 }}>
                          <input
                            type="checkbox"
                            checked={limit.isUnlimited}
                            disabled={limitsBusy}
                            onChange={(e) => {
                              const checked = e.target.checked;
                              setEditableLimits((prev) =>
                                prev.map((item, i) => (i === idx ? { ...item, isUnlimited: checked } : item))
                              );
                            }}
                          />
                          <span>Unlimited</span>
                        </label>
                      </td>
                      <td className="ac-text-muted" style={{ fontSize: 12 }}>
                        {limit.description}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* SECTION D: TENANT USAGE */}
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-6)", marginBottom: "var(--ac-space-6)" }}>
            <div style={{ marginBottom: 16 }}>
              <h2 className="ac-h2" style={{ margin: 0 }}>Tenants Subscribed ({subscribedTenants.length})</h2>
              <p className="ac-text-muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                Organizations actively provisioned under this commercial plan.
              </p>
            </div>

            {subscribedTenants.length === 0 ? (
              <p className="ac-text-muted" style={{ margin: 0, fontSize: 13 }}>
                No customer organizations are currently subscribed to this plan.
              </p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table className="ac-table" style={{ width: "100%", textAlign: "left" }}>
                  <thead>
                    <tr>
                      <th>Organization</th>
                      <th>Org Status</th>
                      <th>Subscription Status</th>
                      <th>Started Date</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {subscribedTenants.map((sub) => (
                      <tr key={sub.subscription_id}>
                        <td>
                          <Link
                            href={`/platform/organizations/${sub.organization_id}`}
                            className="ac-table-link"
                            style={{ fontWeight: 600 }}
                          >
                            {sub.organization_name}
                          </Link>
                        </td>
                        <td>
                          <StatusBadge
                            status={sub.organization_status === "ACTIVE" ? "COMPLIANT" : "NON_COMPLIANT"}
                            label={sub.organization_status}
                          />
                        </td>
                        <td>
                          <span className="ac-badge" style={{ fontSize: 11 }}>
                            {sub.subscription_status}
                          </span>
                        </td>
                        <td style={{ fontSize: 12, color: "var(--ac-text-muted)" }}>
                          {new Date(sub.starts_at).toLocaleDateString()}
                        </td>
                        <td>
                          <Link
                            className="ac-btn"
                            style={{ fontSize: 11, padding: "2px 8px" }}
                            href={`/platform/organizations/${sub.organization_id}/entitlements`}
                          >
                            View Entitlements →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* SECTION E: AUDIT & ACTIVITY */}
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-6)" }}>
            <div style={{ marginBottom: 16 }}>
              <h2 className="ac-h2" style={{ margin: 0 }}>Plan Audit Trail</h2>
              <p className="ac-text-muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                Immutable ledger of all commercial packaging changes, feature adjustments, and activation states.
              </p>
            </div>

            {auditEvents.length === 0 ? (
              <p className="ac-text-muted" style={{ margin: 0, fontSize: 13 }}>
                No audit events recorded for this plan yet.
              </p>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {auditEvents.map((evt) => (
                  <div
                    key={evt.id}
                    className="ac-flex"
                    style={{
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 12px",
                      borderRadius: 4,
                      border: "1px solid var(--ac-border)",
                      backgroundColor: "rgba(0,0,0,0.1)",
                      fontSize: 12,
                    }}
                  >
                    <div>
                      <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                        <span style={{ fontFamily: "monospace", fontWeight: 600, color: "#60a5fa" }}>
                          {evt.action}
                        </span>
                        <span className="ac-badge" style={{ fontSize: 10 }}>
                          {evt.entity_type}
                        </span>
                      </div>
                      {evt.event_metadata && Object.keys(evt.event_metadata).length > 0 && (
                        <p style={{ margin: "3px 0 0", fontFamily: "monospace", color: "var(--ac-text-muted)", fontSize: 11 }}>
                          {JSON.stringify(evt.event_metadata)}
                        </p>
                      )}
                    </div>
                    <span style={{ color: "var(--ac-text-muted)", whiteSpace: "nowrap" }}>
                      {new Date(evt.created_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* FEATURE TOGGLE CONFIRM DIALOG */}
          <ConfirmDialog
            open={pendingFeatureToggle !== null}
            title={
              pendingFeatureToggle?.newEnabled
                ? `Enable ${pendingFeatureToggle.featureName} on ${plan.name}`
                : `Disable ${pendingFeatureToggle?.featureName} on ${plan.name}`
            }
            body={
              pendingFeatureToggle?.newEnabled
                ? `Enabling "${pendingFeatureToggle.featureKey}" will grant this commercial capability to all organizations subscribed to ${plan.name} upon their next entitlement resolution, unless overridden by an explicit tenant restriction.`
                : `Disabling "${pendingFeatureToggle?.featureKey}" will revoke this baseline commercial entitlement from all organizations subscribed to ${plan.name}, unless granted by an explicit tenant override.`
            }
            confirmLabel={pendingFeatureToggle?.newEnabled ? "Enable Feature" : "Disable Feature"}
            busy={toggleBusy}
            onConfirm={handleConfirmFeatureToggle}
            onCancel={() => setPendingFeatureToggle(null)}
          />

          {/* PLAN ACTIVATE/DEACTIVATE CONFIRM DIALOG */}
          <ConfirmDialog
            open={planToggleActive !== null}
            title={planToggleActive ? "Activate Commercial Plan" : "Deactivate Commercial Plan"}
            body={
              planToggleActive
                ? `Activating "${plan.name}" (${plan.code}) allows new tenant subscriptions to be created against it.`
                : `Deactivating "${plan.name}" (${plan.code}) will prevent new tenant subscriptions. Existing subscribers will continue to resolve entitlements under INACTIVE_PLAN status.`
            }
            confirmLabel={planToggleActive ? "Activate Plan" : "Deactivate Plan"}
            busy={toggleBusy}
            onConfirm={handleTogglePlanActive}
            onCancel={() => setPlanToggleActive(null)}
          />
        </>
      )}
    </div>
  );
}
