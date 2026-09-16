"use client";

// Platform Admin — Organization Entitlement Control Center (M8 + M11).
// REAL-mode only: cross-tenant platform staff tooling, no demo dataset.
// Backend enforces PLATFORM_MANAGE on every call, and PLATFORM_ENTITLEMENT_OVERRIDE
// for expansive mutations (enabling new features, increasing limits, setting unlimited).
//
// Effective feature state always comes directly from `effective_features` in the
// entitlement resolution response (M2 resolver via M3 API) — it is never recomputed
// client-side. Overrides and usage limits are managed directly through M6 APIs,
// triggering immediate re-fetch of effective state on mutation.

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";
import {
  entitlementApi,
  type EntitlementResolutionResponse,
  type TenantFeatureOverrideResponse,
  type TenantUsageLimitResponse,
  getOverrideExpirationState,
} from "@/lib/api/entitlement";

interface FeatureRow {
  feature_key: string;
  enabled: boolean;
  source: "Plan" | "Tenant Override" | "Not Determined";
  override?: TenantFeatureOverrideResponse;
}

function isOverrideApplicable(o: TenantFeatureOverrideResponse, now: Date): boolean {
  if (!o.expires_at) return true;
  const expires = new Date(o.expires_at);
  if (Number.isNaN(expires.getTime())) return false;
  return expires.getTime() > now.getTime();
}

function buildFeatureRows(
  entitlements: EntitlementResolutionResponse,
  overrides: TenantFeatureOverrideResponse[]
): FeatureRow[] {
  const now = new Date();
  const overridesByFeature = new Map<string, TenantFeatureOverrideResponse>();
  for (const o of overrides) {
    if (isOverrideApplicable(o, now)) {
      const existing = overridesByFeature.get(o.feature_key);
      if (!existing || new Date(o.created_at) > new Date(existing.created_at)) {
        overridesByFeature.set(o.feature_key, o);
      }
    }
  }

  return Object.entries(entitlements.effective_features).map(([feature_key, enabled]) => {
    const override = overridesByFeature.get(feature_key);
    return {
      feature_key,
      enabled,
      source: override ? "Tenant Override" : "Plan",
      override,
    };
  });
}

function subscriptionStatusBadge(status: string) {
  const map: Record<string, Parameters<typeof StatusBadge>[0]["status"]> = {
    TRIALING: "REVIEW_REQUIRED",
    ACTIVE: "COMPLIANT",
    PAST_DUE: "REVIEW_REQUIRED",
    CANCELED: "UNKNOWN",
    SCHEDULED: "INSUFFICIENT_DATA",
  };
  return { status: map[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

function resolutionStatusBadge(status: string) {
  const map: Record<string, Parameters<typeof StatusBadge>[0]["status"]> = {
    ACTIVE: "COMPLIANT",
    INACTIVE_PLAN: "REVIEW_REQUIRED",
    SUSPENDED: "NON_COMPLIANT",
    NO_SUBSCRIPTION: "INSUFFICIENT_DATA",
    AMBIGUOUS: "REVIEW_REQUIRED",
    INVALID: "NON_COMPLIANT",
  };
  return { status: map[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

function toDateTimeLocalValue(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type PendingOverrideAction =
  | {
      type: "create_override";
      feature_key: string;
      enabled: boolean;
      reason: string;
      expires_at: string | null;
      currentEffective: boolean | null;
    }
  | {
      type: "update_override";
      override: TenantFeatureOverrideResponse;
      enabled: boolean;
      reason: string;
      expires_at: string | null;
    }
  | {
      type: "toggle_override";
      override: TenantFeatureOverrideResponse;
      newEnabled: boolean;
    }
  | {
      type: "remove_override";
      override: TenantFeatureOverrideResponse;
    };

type PendingLimitAction =
  | {
      type: "create_limit";
      feature_key: string;
      limit_key: string;
      limit_value: number | null;
      is_unlimited: boolean;
      currentLimit: string;
    }
  | {
      type: "update_limit";
      limit: TenantUsageLimitResponse;
      limit_value: number | null;
      is_unlimited: boolean;
    }
  | {
      type: "remove_limit";
      limit: TenantUsageLimitResponse;
    };

function RealOrganizationDetail({ organizationId }: { organizationId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [org, setOrg] = useState<BackendPlatformOrganization | null>(null);
  const [orgError, setOrgError] = useState<NormalizedApiError | null>(null);
  const [entitlements, setEntitlements] = useState<EntitlementResolutionResponse | null>(null);
  const [entitlementsError, setEntitlementsError] = useState<NormalizedApiError | null>(null);
  const [overrides, setOverrides] = useState<TenantFeatureOverrideResponse[] | null>(null);
  const [overridesError, setOverridesError] = useState<NormalizedApiError | null>(null);
  const [limits, setLimits] = useState<TenantUsageLimitResponse[] | null>(null);
  const [limitsError, setLimitsError] = useState<NormalizedApiError | null>(null);
  const [loading, setLoading] = useState(true);

  // Feature Override Create State
  const [showCreateOverride, setShowCreateOverride] = useState(false);
  const [newOverrideFeature, setNewOverrideFeature] = useState("");
  const [newOverrideEnabled, setNewOverrideEnabled] = useState(true);
  const [newOverrideReason, setNewOverrideReason] = useState("");
  const [newOverrideExpiresAt, setNewOverrideExpiresAt] = useState("");

  // Feature Override Edit State
  const [editingOverrideKey, setEditingOverrideKey] = useState<string | null>(null);
  const [editOverrideEnabled, setEditOverrideEnabled] = useState(true);
  const [editOverrideReason, setEditOverrideReason] = useState("");
  const [editOverrideExpiresAt, setEditOverrideExpiresAt] = useState("");

  // Usage Limit Create State
  const [showCreateLimit, setShowCreateLimit] = useState(false);
  const [newLimitFeature, setNewLimitFeature] = useState("");
  const [newLimitKey, setNewLimitKey] = useState("");
  const [newLimitIsUnlimited, setNewLimitIsUnlimited] = useState(false);
  const [newLimitValue, setNewLimitValue] = useState<string>("");

  // Usage Limit Edit State
  const [editingLimitId, setEditingLimitId] = useState<string | null>(null);
  const [editLimitIsUnlimited, setEditLimitIsUnlimited] = useState(false);
  const [editLimitValue, setEditLimitValue] = useState<string>("");

  // Action Dialog State
  const [pendingOverrideAction, setPendingOverrideAction] = useState<PendingOverrideAction | null>(null);
  const [pendingLimitAction, setPendingLimitAction] = useState<PendingLimitAction | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);

  const loadAll = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setOrgError(null);
    setEntitlementsError(null);
    setOverridesError(null);
    setLimitsError(null);

    Promise.allSettled([
      platformApi.getOrganization(accessToken, organizationId),
      entitlementApi.getEntitlements(accessToken, organizationId),
      entitlementApi.listFeatureOverrides(accessToken, organizationId),
      entitlementApi.listUsageLimits(accessToken, organizationId),
    ]).then(([orgResult, entResult, ovResult, limResult]) => {
      if (cancelled) return;
      if (orgResult.status === "fulfilled") setOrg(orgResult.value);
      else setOrgError(normalizeApiError(orgResult.reason));

      if (entResult.status === "fulfilled") setEntitlements(entResult.value);
      else setEntitlementsError(normalizeApiError(entResult.reason));

      if (ovResult.status === "fulfilled") setOverrides(ovResult.value);
      else setOverridesError(normalizeApiError(ovResult.reason));

      if (limResult.status === "fulfilled") setLimits(limResult.value);
      else setLimitsError(normalizeApiError(limResult.reason));

      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated, organizationId]);

  const featureRows = entitlements && overrides ? buildFeatureRows(entitlements, overrides) : [];

  // Suggestions for feature keys from effective features
  const knownFeatureKeys = Object.keys(entitlements?.effective_features ?? {});

  // Handlers for Overrides
  const submitCreateOverride = () => {
    if (!newOverrideFeature.trim()) return;
    const currentEffective = entitlements?.effective_features?.[newOverrideFeature.trim()] ?? null;
    setPendingOverrideAction({
      type: "create_override",
      feature_key: newOverrideFeature.trim(),
      enabled: newOverrideEnabled,
      reason: newOverrideReason.trim(),
      expires_at: newOverrideExpiresAt ? new Date(newOverrideExpiresAt).toISOString() : null,
      currentEffective,
    });
  };

  const startEditOverride = (o: TenantFeatureOverrideResponse) => {
    setEditingOverrideKey(o.feature_key);
    setEditOverrideEnabled(o.enabled);
    setEditOverrideReason(o.reason ?? "");
    setEditOverrideExpiresAt(o.expires_at ? toDateTimeLocalValue(o.expires_at) : "");
  };

  const submitEditOverride = (o: TenantFeatureOverrideResponse) => {
    setPendingOverrideAction({
      type: "update_override",
      override: o,
      enabled: editOverrideEnabled,
      reason: editOverrideReason.trim(),
      expires_at: editOverrideExpiresAt ? new Date(editOverrideExpiresAt).toISOString() : null,
    });
  };

  const confirmOverrideAction = () => {
    if (!accessToken || !pendingOverrideAction) return;
    setActionBusy(true);
    setActionError(null);

    let request: Promise<unknown>;
    if (pendingOverrideAction.type === "create_override") {
      request = entitlementApi.createFeatureOverride(accessToken, organizationId, {
        feature_key: pendingOverrideAction.feature_key,
        enabled: pendingOverrideAction.enabled,
        reason: pendingOverrideAction.reason || null,
        expires_at: pendingOverrideAction.expires_at,
      });
    } else if (pendingOverrideAction.type === "update_override") {
      request = entitlementApi.updateFeatureOverride(
        accessToken,
        organizationId,
        pendingOverrideAction.override.feature_key,
        {
          enabled: pendingOverrideAction.enabled,
          reason: pendingOverrideAction.reason || null,
          expires_at: pendingOverrideAction.expires_at,
        }
      );
    } else if (pendingOverrideAction.type === "toggle_override") {
      request = entitlementApi.updateFeatureOverride(
        accessToken,
        organizationId,
        pendingOverrideAction.override.feature_key,
        {
          enabled: pendingOverrideAction.newEnabled,
        }
      );
    } else {
      request = entitlementApi.removeFeatureOverride(
        accessToken,
        organizationId,
        pendingOverrideAction.override.feature_key
      );
    }

    request
      .then(() => {
        setPendingOverrideAction(null);
        setEditingOverrideKey(null);
        setShowCreateOverride(false);
        setNewOverrideFeature("");
        setNewOverrideReason("");
        setNewOverrideExpiresAt("");
        loadAll();
      })
      .catch((err) => setActionError(normalizeApiError(err)))
      .finally(() => setActionBusy(false));
  };

  // Handlers for Usage Limits
  const submitCreateLimit = () => {
    if (!newLimitFeature.trim() || !newLimitKey.trim()) return;
    const currentLimitObj = (limits ?? []).find(
      (l) => l.feature_key === newLimitFeature.trim() && l.limit_key === newLimitKey.trim()
    );
    const currentLimit = currentLimitObj
      ? currentLimitObj.is_unlimited
        ? "Unlimited"
        : String(currentLimitObj.limit_value ?? "—")
      : "None";

    setPendingLimitAction({
      type: "create_limit",
      feature_key: newLimitFeature.trim(),
      limit_key: newLimitKey.trim(),
      is_unlimited: newLimitIsUnlimited,
      limit_value: newLimitIsUnlimited ? null : newLimitValue ? parseInt(newLimitValue, 10) : null,
      currentLimit,
    });
  };

  const startEditLimit = (l: TenantUsageLimitResponse) => {
    setEditingLimitId(l.id);
    setEditLimitIsUnlimited(l.is_unlimited);
    setEditLimitValue(l.limit_value !== null ? String(l.limit_value) : "");
  };

  const submitEditLimit = (l: TenantUsageLimitResponse) => {
    setPendingLimitAction({
      type: "update_limit",
      limit: l,
      is_unlimited: editLimitIsUnlimited,
      limit_value: editLimitIsUnlimited ? null : editLimitValue ? parseInt(editLimitValue, 10) : null,
    });
  };

  const confirmLimitAction = () => {
    if (!accessToken || !pendingLimitAction) return;
    setActionBusy(true);
    setActionError(null);

    let request: Promise<unknown>;
    if (pendingLimitAction.type === "create_limit") {
      request = entitlementApi.createUsageLimit(accessToken, organizationId, {
        feature_key: pendingLimitAction.feature_key,
        limit_key: pendingLimitAction.limit_key,
        is_unlimited: pendingLimitAction.is_unlimited,
        limit_value: pendingLimitAction.limit_value,
      });
    } else if (pendingLimitAction.type === "update_limit") {
      request = entitlementApi.updateUsageLimit(
        accessToken,
        organizationId,
        pendingLimitAction.limit.feature_key,
        pendingLimitAction.limit.limit_key,
        {
          is_unlimited: pendingLimitAction.is_unlimited,
          limit_value: pendingLimitAction.limit_value,
        }
      );
    } else {
      request = entitlementApi.removeUsageLimit(
        accessToken,
        organizationId,
        pendingLimitAction.limit.feature_key,
        pendingLimitAction.limit.limit_key
      );
    }

    request
      .then(() => {
        setPendingLimitAction(null);
        setEditingLimitId(null);
        setShowCreateLimit(false);
        setNewLimitFeature("");
        setNewLimitKey("");
        setNewLimitIsUnlimited(false);
        setNewLimitValue("");
        loadAll();
      })
      .catch((err) => setActionError(normalizeApiError(err)))
      .finally(() => setActionBusy(false));
  };

  // Dialog Bodies
  const buildOverrideDialogBody = () => {
    if (!pendingOverrideAction) return "";
    let base = "";
    if (pendingOverrideAction.type === "create_override") {
      const isExpansive = pendingOverrideAction.enabled && pendingOverrideAction.currentEffective !== true;
      base =
        `Organization: ${organizationId}\n` +
        `Feature: ${pendingOverrideAction.feature_key}\n` +
        `Current Effective Baseline: ${pendingOverrideAction.currentEffective === true ? "Enabled" : pendingOverrideAction.currentEffective === false ? "Disabled" : "Not configured"}\n` +
        `Requested Override: ${pendingOverrideAction.enabled ? "Enabled" : "Disabled"}\n` +
        `Expiration: ${pendingOverrideAction.expires_at ? new Date(pendingOverrideAction.expires_at).toLocaleString() : "Never (Permanent)"}\n` +
        `Reason: ${pendingOverrideAction.reason || "None specified"}\n\n` +
        (isExpansive
          ? "This change is EXPANSIVE (enabling an otherwise unavailable feature). The backend strictly requires PLATFORM_ENTITLEMENT_OVERRIDE permission."
          : "This change will restrict or modify this organization's effective entitlement.");
    } else if (pendingOverrideAction.type === "update_override") {
      base =
        `Organization: ${organizationId}\n` +
        `Feature: ${pendingOverrideAction.override.feature_key}\n` +
        `Current Override: ${pendingOverrideAction.override.enabled ? "Enabled" : "Disabled"}\n` +
        `New Override: ${pendingOverrideAction.enabled ? "Enabled" : "Disabled"}\n` +
        `Expiration: ${pendingOverrideAction.expires_at ? new Date(pendingOverrideAction.expires_at).toLocaleString() : "Never (Permanent)"}\n` +
        `Reason: ${pendingOverrideAction.reason || "None specified"}\n\n` +
        "This change may alter the organization's effective entitlements. If expansive, PLATFORM_ENTITLEMENT_OVERRIDE is required.";
    } else if (pendingOverrideAction.type === "toggle_override") {
      base =
        `Organization: ${organizationId}\n` +
        `Feature: ${pendingOverrideAction.override.feature_key}\n` +
        `Current State: ${pendingOverrideAction.override.enabled ? "Enabled" : "Disabled"}\n` +
        `New State: ${pendingOverrideAction.newEnabled ? "Enabled" : "Disabled"}\n\n` +
        (pendingOverrideAction.newEnabled
          ? "Enabling this feature override may expand access. If expansive, PLATFORM_ENTITLEMENT_OVERRIDE is required."
          : "This will restrict this organization's effective entitlement for this feature.");
    } else if (pendingOverrideAction.type === "remove_override") {
      base =
        `Organization: ${organizationId}\n` +
        `Feature: ${pendingOverrideAction.override.feature_key}\n` +
        `Current Override: ${pendingOverrideAction.override.enabled ? "Enabled" : "Disabled"}\n\n` +
        "Removing this override will revert this feature's resolution back to the organization's plan baseline.";
    }
    if (actionError) {
      return `Backend Error: ${actionError.message}\n\n${base}`;
    }
    return base;
  };

  const buildLimitDialogBody = () => {
    if (!pendingLimitAction) return "";
    let base = "";
    if (pendingLimitAction.type === "create_limit") {
      const newValue = pendingLimitAction.is_unlimited ? "Unlimited" : String(pendingLimitAction.limit_value ?? "None");
      base =
        `Organization: ${organizationId}\n` +
        `Feature: ${pendingLimitAction.feature_key}\n` +
        `Limit Key: ${pendingLimitAction.limit_key}\n` +
        `Current Value: ${pendingLimitAction.currentLimit}\n` +
        `New Value: ${newValue}\n\n` +
        "This change may alter the organization's entitlement capacity. If expansive (setting unlimited or increasing capacity), PLATFORM_ENTITLEMENT_OVERRIDE is required.";
    } else if (pendingLimitAction.type === "update_limit") {
      const curVal = pendingLimitAction.limit.is_unlimited ? "Unlimited" : String(pendingLimitAction.limit.limit_value ?? "—");
      const newVal = pendingLimitAction.is_unlimited ? "Unlimited" : String(pendingLimitAction.limit_value ?? "—");
      base =
        `Organization: ${organizationId}\n` +
        `Feature: ${pendingLimitAction.limit.feature_key}\n` +
        `Limit Key: ${pendingLimitAction.limit.limit_key}\n` +
        `Current: ${curVal}\n` +
        `New: ${newVal}\n\n` +
        (pendingLimitAction.is_unlimited || (pendingLimitAction.limit_value ?? 0) > (pendingLimitAction.limit.limit_value ?? 0)
          ? "This may expand the organization's entitlement capacity. Expansive limit increases require PLATFORM_ENTITLEMENT_OVERRIDE."
          : `Reduce capacity from ${curVal} to ${newVal}? This will restrict the organization's usage limit capacity.`);
    } else if (pendingLimitAction.type === "remove_limit") {
      base =
        `Organization: ${organizationId}\n` +
        `Feature: ${pendingLimitAction.limit.feature_key}\n` +
        `Limit Key: ${pendingLimitAction.limit.limit_key}\n\n` +
        "Removing this usage limit override will remove the organization-specific limit for this feature.";
    }
    if (actionError) {
      return `Backend Error: ${actionError.message}\n\n${base}`;
    }
    return base;
  };

  const featureColumns: Column<FeatureRow>[] = [
    { key: "feature", header: "Feature", render: (r) => <span style={{ wordBreak: "break-word" }}>{r.feature_key}</span> },
    {
      key: "state",
      header: "Effective State",
      render: (r) => <StatusBadge status={r.enabled ? "TRUE" : "FALSE"} label={r.enabled ? "Enabled" : "Disabled"} />,
    },
    {
      key: "source",
      header: "Source",
      render: (r) => (
        <span className="ac-text-sm">
          Source: {r.source}
          {r.override?.reason ? ` — ${r.override.reason}` : ""}
        </span>
      ),
    },
  ];

  const overrideColumns: Column<TenantFeatureOverrideResponse>[] = [
    { key: "feature", header: "Feature", render: (o) => <strong style={{ wordBreak: "break-word" }}>{o.feature_key}</strong> },
    {
      key: "state",
      header: "Override State",
      render: (o) => <StatusBadge status={o.enabled ? "TRUE" : "FALSE"} label={o.enabled ? "Enabled" : "Disabled"} />,
    },
    { key: "reason", header: "Reason", render: (o) => <span style={{ wordBreak: "break-word" }}>{o.reason ?? "—"}</span> },
    {
      key: "expires",
      header: "Expiration",
      render: (o) => {
        const expInfo = getOverrideExpirationState(o);
        const badgeStatus =
          expInfo.state === "PERMANENT"
            ? "INSUFFICIENT_DATA"
            : expInfo.state === "ACTIVE"
            ? "COMPLIANT"
            : expInfo.state === "EXPIRING_SOON"
            ? "REVIEW_REQUIRED"
            : "NON_COMPLIANT";
        return (
          <div>
            <div className="ac-flex ac-gap-2" style={{ alignItems: "center", flexWrap: "wrap" }}>
              <StatusBadge status={badgeStatus} label={expInfo.label} />
              {o.expires_at && <span className="ac-text-sm ac-text-muted">{new Date(o.expires_at).toLocaleString()}</span>}
            </div>
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "Actions",
      render: (o) => (
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px" }}
            onClick={() => setPendingOverrideAction({ type: "toggle_override", override: o, newEnabled: !o.enabled })}
          >
            {o.enabled ? "Disable" : "Enable"}
          </button>
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px" }}
            onClick={() => startEditOverride(o)}
          >
            Edit
          </button>
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px", borderColor: "var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)" }}
            onClick={() => setPendingOverrideAction({ type: "remove_override", override: o })}
          >
            Remove
          </button>
        </div>
      ),
    },
  ];

  const limitColumns: Column<TenantUsageLimitResponse>[] = [
    { key: "feature", header: "Feature", render: (l) => <strong style={{ wordBreak: "break-word" }}>{l.feature_key}</strong> },
    { key: "limit_key", header: "Limit Key", render: (l) => <span style={{ wordBreak: "break-word" }}>{l.limit_key}</span> },
    {
      key: "value",
      header: "Configured Value",
      render: (l) => (l.is_unlimited ? <StatusBadge status="COMPLIANT" label="Unlimited" /> : <span>{l.limit_value ?? "—"}</span>),
    },
    {
      key: "actions",
      header: "Actions",
      render: (l) => (
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px" }}
            onClick={() => startEditLimit(l)}
          >
            Edit
          </button>
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px", borderColor: "var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)" }}
            onClick={() => setPendingLimitAction({ type: "remove_limit", limit: l })}
          >
            Remove
          </button>
        </div>
      ),
    },
  ];

  if (!isAuthenticated) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
        </p>
      </div>
    );
  }

  const forbidden = orgError?.kind === "forbidden" || entitlementsError?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Organizations", href: "/platform/organizations" },
          { label: org?.name ?? organizationId },
        ]}
      />

      {loading ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Loading from the connected backend…</p>
        </div>
      ) : forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view this organization&apos;s entitlement data.
          </p>
        </div>
      ) : orgError && orgError.kind === "not_found" ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>{orgError.message}</p>
        </div>
      ) : (
        <>
          <div className="ac-section-header">
            <div>
              <h1 className="ac-h1">{org?.name ?? "Organization"}</h1>
              <p className="ac-subtitle">Organization ID: {organizationId}</p>
            </div>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
              <Link className="ac-btn" href={`/platform/organizations/${organizationId}/subscriptions`}>
                Manage Subscription
              </Link>
            </div>
          </div>

          {actionError && !pendingOverrideAction && !pendingLimitAction && (
            <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)", borderColor: "var(--ac-status-non-compliant)" }}>
              <strong className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>Operation failed</strong>
              <p className="ac-text-sm" style={{ margin: "4px 0 0" }}>{actionError.message}</p>
            </div>
          )}

          {orgError && (
            <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Organization details failed to load: {orgError.message}
              </p>
            </div>
          )}

          {org && (
            <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <h2 className="ac-h2">Organization</h2>
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center" }}>
                <StatusBadge {...genericStatusBadge(org.status)} />
                <span className="ac-text-sm ac-text-muted">
                  Created {new Date(org.created_at).toLocaleDateString()} · {org.user_count} users · {org.aircraft_count} aircraft
                </span>
              </div>
            </section>
          )}

          <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between", flexWrap: "wrap", alignItems: "center" }}>
              <h2 className="ac-h2">Subscription Context</h2>
              <Link className="ac-btn" href={`/platform/organizations/${organizationId}/subscriptions`}>
                View / Manage Subscriptions →
              </Link>
            </div>
            {entitlementsError ? (
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Subscription data failed to load: {entitlementsError.message}
              </p>
            ) : !entitlements ? (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No data.</p>
            ) : entitlements.resolution_status === "NO_SUBSCRIPTION" ? (
              <div className="ac-flex ac-gap-2" style={{ alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                <div>
                  <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>No Active Subscription</p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                    Tenant overrides will not result in active entitlement unless an eligible subscription is active.
                  </p>
                </div>
                <Link className="ac-btn" href={`/platform/organizations/${organizationId}/subscriptions`}>
                  Create Subscription →
                </Link>
              </div>
            ) : entitlements.resolution_status === "AMBIGUOUS" ? (
              <p className="ac-text-sm" style={{ margin: 0 }}>Subscription Configuration Ambiguous — {entitlements.reason}</p>
            ) : entitlements.subscription_status ? (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center" }}>
                <StatusBadge {...subscriptionStatusBadge(entitlements.subscription_status)} />
                <span className="ac-text-sm">
                  Plan: {entitlements.plan_name ?? entitlements.plan_code ?? "—"}
                </span>
              </div>
            ) : (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No subscription information available.</p>
            )}
          </section>

          <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <h2 className="ac-h2">Resolution Status</h2>
            {entitlements ? (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                <StatusBadge {...resolutionStatusBadge(entitlements.resolution_status)} />
                <span className="ac-text-sm">{entitlements.reason}</span>
              </div>
            ) : (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Unavailable.</p>
            )}
            {entitlements?.resolution_status === "SUSPENDED" && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                This reflects the organization&apos;s operational suspension, which is independent of the underlying
                subscription&apos;s billing status. Feature overrides remain configured but operational access is suspended.
              </p>
            )}
            {entitlements?.resolution_status === "INACTIVE_PLAN" && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                The assigned plan is inactive. Effective feature values below reflect what the canonical M2 resolver returns.
              </p>
            )}
            {entitlements?.resolution_status === "INVALID" && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                Entitlement configuration for this organization could not be safely resolved.
              </p>
            )}
          </section>

          {/* Section: Feature Overrides Administration (M11) */}
          <section className="ac-card ac-section" style={{ padding: 0 }}>
            <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) var(--ac-space-2)" }}>
              <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
                <div>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Tenant Feature Overrides</h2>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                    Tenant-scoped overrides that supersede plan features. Expansive changes require PLATFORM_ENTITLEMENT_OVERRIDE.
                  </p>
                </div>
                <button
                  className="ac-btn"
                  onClick={() => setShowCreateOverride(!showCreateOverride)}
                  aria-expanded={showCreateOverride}
                >
                  {showCreateOverride ? "Cancel" : "+ Add Feature Override"}
                </button>
              </div>

              {showCreateOverride && (
                <div
                  className="ac-card"
                  style={{
                    margin: "var(--ac-space-3) 0 0",
                    padding: "var(--ac-space-3)",
                    background: "var(--ac-bg-secondary, rgba(255,255,255,0.03))",
                  }}
                >
                  <h3 className="ac-h3" style={{ fontSize: 14, margin: "0 0 var(--ac-space-2)" }}>
                    Configure New Feature Override
                  </h3>
                  <div className="ac-flex ac-gap-2" style={{ flexDirection: "column" }}>
                    <div>
                      <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>
                        Feature Key <span style={{ color: "var(--ac-status-non-compliant)" }}>*</span>
                      </label>
                      <input
                        list="available-feature-keys"
                        type="text"
                        className="ac-input"
                        style={{ width: "100%", maxWidth: 400 }}
                        placeholder="e.g. maintenance.inspection"
                        value={newOverrideFeature}
                        onChange={(e) => setNewOverrideFeature(e.target.value)}
                      />
                      <datalist id="available-feature-keys">
                        {knownFeatureKeys.map((k) => (
                          <option key={k} value={k} />
                        ))}
                      </datalist>
                    </div>

                    <div>
                      <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>
                        Override State
                      </label>
                      <select
                        className="ac-select"
                        style={{ width: "100%", maxWidth: 200 }}
                        value={newOverrideEnabled ? "true" : "false"}
                        onChange={(e) => setNewOverrideEnabled(e.target.value === "true")}
                      >
                        <option value="true">Enabled</option>
                        <option value="false">Disabled</option>
                      </select>
                    </div>

                    <div>
                      <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>
                        Reason / Justification
                      </label>
                      <input
                        type="text"
                        className="ac-input"
                        style={{ width: "100%", maxWidth: 500 }}
                        placeholder="e.g. Customer requested early access trial"
                        value={newOverrideReason}
                        onChange={(e) => setNewOverrideReason(e.target.value)}
                      />
                    </div>

                    <div>
                      <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>
                        Expiration Date & Time (Optional)
                      </label>
                      <input
                        type="datetime-local"
                        className="ac-input"
                        style={{ width: "100%", maxWidth: 300 }}
                        value={newOverrideExpiresAt}
                        onChange={(e) => setNewOverrideExpiresAt(e.target.value)}
                      />
                      <span className="ac-text-sm ac-text-muted" style={{ display: "block", marginTop: 2 }}>
                        Leave blank for permanent override without expiration.
                      </span>
                    </div>

                    <div style={{ marginTop: "var(--ac-space-2)" }}>
                      <button
                        className="ac-btn"
                        onClick={submitCreateOverride}
                        disabled={!newOverrideFeature.trim()}
                      >
                        Review and Apply Override
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <RealDataPanel
              loading={false}
              error={overridesError}
              isEmpty={!overridesError && (overrides?.length ?? 0) === 0}
              emptyMessage="No feature overrides configured for this organization."
            >
              <div className="ac-table-desktop">
                <DataTable columns={overrideColumns} rows={overrides ?? []} />
              </div>
              <div className="ac-row-cards">
                {(overrides ?? []).map((o) => {
                  const expInfo = getOverrideExpirationState(o);
                  const isEditing = editingOverrideKey === o.feature_key;
                  return (
                    <div className="ac-row-card" key={o.id}>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Feature</span>
                        <strong style={{ wordBreak: "break-word" }}>{o.feature_key}</strong>
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Override State</span>
                        <StatusBadge status={o.enabled ? "TRUE" : "FALSE"} label={o.enabled ? "Enabled" : "Disabled"} />
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Reason</span>
                        <span style={{ wordBreak: "break-word" }}>{o.reason ?? "—"}</span>
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Expiration</span>
                        <div>
                          <span>{expInfo.label}</span>
                          {o.expires_at && <div className="ac-text-sm ac-text-muted">{new Date(o.expires_at).toLocaleString()}</div>}
                        </div>
                      </div>

                      {isEditing ? (
                        <div
                          style={{
                            marginTop: "var(--ac-space-2)",
                            padding: "var(--ac-space-2)",
                            borderTop: "1px solid rgba(255,255,255,0.1)",
                          }}
                        >
                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 2 }}>
                            Override State
                          </label>
                          <select
                            className="ac-select"
                            value={editOverrideEnabled ? "true" : "false"}
                            onChange={(e) => setEditOverrideEnabled(e.target.value === "true")}
                            style={{ marginBottom: 6, width: "100%" }}
                          >
                            <option value="true">Enabled</option>
                            <option value="false">Disabled</option>
                          </select>

                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 2 }}>
                            Reason
                          </label>
                          <input
                            type="text"
                            className="ac-input"
                            value={editOverrideReason}
                            onChange={(e) => setEditOverrideReason(e.target.value)}
                            style={{ marginBottom: 6, width: "100%" }}
                          />

                          <label className="ac-text-sm" style={{ display: "block", marginBottom: 2 }}>
                            Expiration
                          </label>
                          <input
                            type="datetime-local"
                            className="ac-input"
                            value={editOverrideExpiresAt}
                            onChange={(e) => setEditOverrideExpiresAt(e.target.value)}
                            style={{ marginBottom: 8, width: "100%" }}
                          />

                          <div className="ac-flex ac-gap-2">
                            <button className="ac-btn" onClick={() => submitEditOverride(o)}>
                              Save
                            </button>
                            <button className="ac-btn" onClick={() => setEditingOverrideKey(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="ac-row-card-field" style={{ marginTop: "var(--ac-space-2)" }}>
                          <span className="ac-row-card-field-label">Actions</span>
                          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                            <button
                              className="ac-btn"
                              style={{ fontSize: 12, padding: "2px 8px" }}
                              onClick={() =>
                                setPendingOverrideAction({ type: "toggle_override", override: o, newEnabled: !o.enabled })
                              }
                            >
                              {o.enabled ? "Disable" : "Enable"}
                            </button>
                            <button
                              className="ac-btn"
                              style={{ fontSize: 12, padding: "2px 8px" }}
                              onClick={() => startEditOverride(o)}
                            >
                              Edit
                            </button>
                            <button
                              className="ac-btn"
                              style={{
                                fontSize: 12,
                                padding: "2px 8px",
                                borderColor: "var(--ac-status-non-compliant)",
                                color: "var(--ac-status-non-compliant)",
                              }}
                              onClick={() => setPendingOverrideAction({ type: "remove_override", override: o })}
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </RealDataPanel>

            {/* Desktop Inline Edit Modal/Card */}
            {editingOverrideKey && (
              <div
                style={{
                  padding: "var(--ac-space-3)",
                  margin: "var(--ac-space-3)",
                  border: "1px solid var(--ac-border, rgba(255,255,255,0.1))",
                  borderRadius: "var(--ac-radius-sm, 4px)",
                }}
              >
                <h4 className="ac-h3" style={{ fontSize: 14, margin: "0 0 var(--ac-space-2)" }}>
                  Editing Override: {editingOverrideKey}
                </h4>
                <div className="ac-flex ac-gap-2" style={{ flexDirection: "column" }}>
                  <div>
                    <label className="ac-text-sm" style={{ display: "block", marginBottom: 2 }}>State</label>
                    <select
                      className="ac-select"
                      value={editOverrideEnabled ? "true" : "false"}
                      onChange={(e) => setEditOverrideEnabled(e.target.value === "true")}
                      style={{ maxWidth: 200 }}
                    >
                      <option value="true">Enabled</option>
                      <option value="false">Disabled</option>
                    </select>
                  </div>
                  <div>
                    <label className="ac-text-sm" style={{ display: "block", marginBottom: 2 }}>Reason</label>
                    <input
                      type="text"
                      className="ac-input"
                      value={editOverrideReason}
                      onChange={(e) => setEditOverrideReason(e.target.value)}
                      style={{ width: "100%", maxWidth: 500 }}
                    />
                  </div>
                  <div>
                    <label className="ac-text-sm" style={{ display: "block", marginBottom: 2 }}>Expiration</label>
                    <input
                      type="datetime-local"
                      className="ac-input"
                      value={editOverrideExpiresAt}
                      onChange={(e) => setEditOverrideExpiresAt(e.target.value)}
                      style={{ maxWidth: 300 }}
                    />
                  </div>
                  <div className="ac-flex ac-gap-2" style={{ marginTop: "var(--ac-space-2)" }}>
                    {overrides?.find((o) => o.feature_key === editingOverrideKey) && (
                      <button
                        className="ac-btn"
                        onClick={() =>
                          submitEditOverride(overrides.find((o) => o.feature_key === editingOverrideKey)!)
                        }
                      >
                        Save Changes
                      </button>
                    )}
                    <button className="ac-btn" onClick={() => setEditingOverrideKey(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Section: Usage Limits Administration (M11) */}
          <section className="ac-card ac-section" style={{ padding: 0 }}>
            <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) var(--ac-space-2)" }}>
              <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
                <div>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Tenant Usage Limits</h2>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                    Tenant-scoped capacity limits. Increasing limits or setting Unlimited requires PLATFORM_ENTITLEMENT_OVERRIDE.
                  </p>
                </div>
                <button
                  className="ac-btn"
                  onClick={() => setShowCreateLimit(!showCreateLimit)}
                  aria-expanded={showCreateLimit}
                >
                  {showCreateLimit ? "Cancel" : "+ Add Usage Limit"}
                </button>
              </div>

              {showCreateLimit && (
                <div
                  className="ac-card"
                  style={{
                    margin: "var(--ac-space-3) 0 0",
                    padding: "var(--ac-space-3)",
                    background: "var(--ac-bg-secondary, rgba(255,255,255,0.03))",
                  }}
                >
                  <h3 className="ac-h3" style={{ fontSize: 14, margin: "0 0 var(--ac-space-2)" }}>
                    Configure New Usage Limit
                  </h3>
                  <div className="ac-flex ac-gap-2" style={{ flexDirection: "column" }}>
                    <div>
                      <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>
                        Feature Key <span style={{ color: "var(--ac-status-non-compliant)" }}>*</span>
                      </label>
                      <input
                        list="limit-feature-keys"
                        type="text"
                        className="ac-input"
                        style={{ width: "100%", maxWidth: 400 }}
                        placeholder="e.g. maintenance.inspection"
                        value={newLimitFeature}
                        onChange={(e) => setNewLimitFeature(e.target.value)}
                      />
                      <datalist id="limit-feature-keys">
                        {knownFeatureKeys.map((k) => (
                          <option key={k} value={k} />
                        ))}
                      </datalist>
                    </div>

                    <div>
                      <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>
                        Limit Key <span style={{ color: "var(--ac-status-non-compliant)" }}>*</span>
                      </label>
                      <input
                        type="text"
                        className="ac-input"
                        style={{ width: "100%", maxWidth: 400 }}
                        placeholder="e.g. monthly_runs, max_aircraft, api_calls"
                        value={newLimitKey}
                        onChange={(e) => setNewLimitKey(e.target.value)}
                      />
                    </div>

                    <div>
                      <label className="ac-flex ac-gap-2" style={{ alignItems: "center", cursor: "pointer" }}>
                        <input
                          type="checkbox"
                          checked={newLimitIsUnlimited}
                          onChange={(e) => setNewLimitIsUnlimited(e.target.checked)}
                        />
                        <span className="ac-text-sm">Unlimited Capacity</span>
                      </label>
                    </div>

                    {!newLimitIsUnlimited && (
                      <div>
                        <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }}>
                          Configured Limit Value
                        </label>
                        <input
                          type="number"
                          min="0"
                          step="1"
                          className="ac-input"
                          style={{ width: "100%", maxWidth: 200 }}
                          placeholder="e.g. 500"
                          value={newLimitValue}
                          onChange={(e) => setNewLimitValue(e.target.value)}
                        />
                      </div>
                    )}

                    <div style={{ marginTop: "var(--ac-space-2)" }}>
                      <button
                        className="ac-btn"
                        onClick={submitCreateLimit}
                        disabled={!newLimitFeature.trim() || !newLimitKey.trim()}
                      >
                        Review and Save Limit
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <RealDataPanel
              loading={false}
              error={limitsError}
              isEmpty={!limitsError && (limits?.length ?? 0) === 0}
              emptyMessage="No usage limits configured for this organization."
            >
              <div className="ac-table-desktop">
                <DataTable columns={limitColumns} rows={limits ?? []} />
              </div>
              <div className="ac-row-cards">
                {(limits ?? []).map((l) => {
                  const isEditing = editingLimitId === l.id;
                  return (
                    <div className="ac-row-card" key={l.id}>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Feature</span>
                        <strong style={{ wordBreak: "break-word" }}>{l.feature_key}</strong>
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Limit Key</span>
                        <span style={{ wordBreak: "break-word" }}>{l.limit_key}</span>
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Configured Value</span>
                        {l.is_unlimited ? (
                          <StatusBadge status="COMPLIANT" label="Unlimited" />
                        ) : (
                          <span>{l.limit_value ?? "—"}</span>
                        )}
                      </div>

                      {isEditing ? (
                        <div
                          style={{
                            marginTop: "var(--ac-space-2)",
                            padding: "var(--ac-space-2)",
                            borderTop: "1px solid rgba(255,255,255,0.1)",
                          }}
                        >
                          <label className="ac-flex ac-gap-2" style={{ alignItems: "center", marginBottom: 6 }}>
                            <input
                              type="checkbox"
                              checked={editLimitIsUnlimited}
                              onChange={(e) => setEditLimitIsUnlimited(e.target.checked)}
                            />
                            <span className="ac-text-sm">Unlimited</span>
                          </label>
                          {!editLimitIsUnlimited && (
                            <input
                              type="number"
                              min="0"
                              step="1"
                              className="ac-input"
                              value={editLimitValue}
                              onChange={(e) => setEditLimitValue(e.target.value)}
                              style={{ marginBottom: 8, width: "100%" }}
                            />
                          )}
                          <div className="ac-flex ac-gap-2">
                            <button className="ac-btn" onClick={() => submitEditLimit(l)}>
                              Save
                            </button>
                            <button className="ac-btn" onClick={() => setEditingLimitId(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="ac-row-card-field" style={{ marginTop: "var(--ac-space-2)" }}>
                          <span className="ac-row-card-field-label">Actions</span>
                          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                            <button
                              className="ac-btn"
                              style={{ fontSize: 12, padding: "2px 8px" }}
                              onClick={() => startEditLimit(l)}
                            >
                              Edit
                            </button>
                            <button
                              className="ac-btn"
                              style={{
                                fontSize: 12,
                                padding: "2px 8px",
                                borderColor: "var(--ac-status-non-compliant)",
                                color: "var(--ac-status-non-compliant)",
                              }}
                              onClick={() => setPendingLimitAction({ type: "remove_limit", limit: l })}
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </RealDataPanel>

            {/* Desktop Inline Limit Edit */}
            {editingLimitId && (
              <div
                style={{
                  padding: "var(--ac-space-3)",
                  margin: "var(--ac-space-3)",
                  border: "1px solid var(--ac-border, rgba(255,255,255,0.1))",
                  borderRadius: "var(--ac-radius-sm, 4px)",
                }}
              >
                {(() => {
                  const limitObj = limits?.find((l) => l.id === editingLimitId);
                  if (!limitObj) return null;
                  return (
                    <>
                      <h4 className="ac-h3" style={{ fontSize: 14, margin: "0 0 var(--ac-space-2)" }}>
                        Editing Limit: {limitObj.feature_key} / {limitObj.limit_key}
                      </h4>
                      <div className="ac-flex ac-gap-2" style={{ flexDirection: "column" }}>
                        <div>
                          <label className="ac-flex ac-gap-2" style={{ alignItems: "center", cursor: "pointer" }}>
                            <input
                              type="checkbox"
                              checked={editLimitIsUnlimited}
                              onChange={(e) => setEditLimitIsUnlimited(e.target.checked)}
                            />
                            <span className="ac-text-sm">Unlimited</span>
                          </label>
                        </div>
                        {!editLimitIsUnlimited && (
                          <div>
                            <label className="ac-text-sm" style={{ display: "block", marginBottom: 2 }}>
                              Limit Value
                            </label>
                            <input
                              type="number"
                              min="0"
                              step="1"
                              className="ac-input"
                              value={editLimitValue}
                              onChange={(e) => setEditLimitValue(e.target.value)}
                              style={{ maxWidth: 200 }}
                            />
                          </div>
                        )}
                        <div className="ac-flex ac-gap-2" style={{ marginTop: "var(--ac-space-2)" }}>
                          <button className="ac-btn" onClick={() => submitEditLimit(limitObj)}>
                            Save Changes
                          </button>
                          <button className="ac-btn" onClick={() => setEditingLimitId(null)}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>
            )}
          </section>

          {/* Section: Effective Entitlements (Canonical M2 Resolver via M3 API) */}
          <section className="ac-card ac-section" style={{ padding: 0 }}>
            <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) 0" }}>
              <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
                <div>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Effective Entitlements</h2>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                    Canonical effective state calculated by the M2 resolver (Plan Features + Active Tenant Overrides).
                  </p>
                </div>
                <button className="ac-btn" onClick={loadAll} title="Re-fetch canonical entitlements">
                  Refresh Entitlements
                </button>
              </div>
            </div>
            <RealDataPanel
              loading={false}
              error={entitlementsError}
              isEmpty={!entitlementsError && featureRows.length === 0}
              emptyMessage="No effective features are configured for this organization."
            >
              <div className="ac-table-desktop">
                <DataTable columns={featureColumns} rows={featureRows} />
              </div>
              <div className="ac-row-cards">
                {featureRows.map((r) => (
                  <div className="ac-row-card" key={r.feature_key}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Feature</span>
                      <strong style={{ wordBreak: "break-word" }}>{r.feature_key}</strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Effective State</span>
                      <StatusBadge status={r.enabled ? "TRUE" : "FALSE"} label={r.enabled ? "Enabled" : "Disabled"} />
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Source</span>
                      <span>Source: {r.source}</span>
                    </div>
                  </div>
                ))}
              </div>
            </RealDataPanel>
          </section>
        </>
      )}

      {/* Confirmation Dialogs for Overrides & Usage Limits */}
      <ConfirmDialog
        open={pendingOverrideAction !== null}
        title={
          pendingOverrideAction?.type === "create_override"
            ? "Create Feature Override"
            : pendingOverrideAction?.type === "update_override"
            ? "Update Feature Override"
            : pendingOverrideAction?.type === "toggle_override"
            ? `${pendingOverrideAction.newEnabled ? "Enable" : "Disable"} Feature Override`
            : "Remove Feature Override"
        }
        body={buildOverrideDialogBody()}
        confirmLabel={
          pendingOverrideAction?.type === "remove_override" ? "Remove Override" : "Confirm Override"
        }
        busy={actionBusy}
        onConfirm={confirmOverrideAction}
        onCancel={() => {
          setPendingOverrideAction(null);
          setActionError(null);
        }}
      />

      <ConfirmDialog
        open={pendingLimitAction !== null}
        title={
          pendingLimitAction?.type === "create_limit"
            ? "Configure Usage Limit"
            : pendingLimitAction?.type === "update_limit"
            ? "Update Usage Limit"
            : "Remove Usage Limit"
        }
        body={buildLimitDialogBody()}
        confirmLabel={
          pendingLimitAction?.type === "remove_limit" ? "Remove Limit" : "Confirm Limit"
        }
        busy={actionBusy}
        onConfirm={confirmLimitAction}
        onCancel={() => {
          setPendingLimitAction(null);
          setActionError(null);
        }}
      />
    </div>
  );
}

export default function PlatformOrganizationDetailPage(props: { params: Promise<{ organizationId: string }> }) {
  const params = use(props.params);
  return <RealOrganizationDetail organizationId={params.organizationId} />;
}
