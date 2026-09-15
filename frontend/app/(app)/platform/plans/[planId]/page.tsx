"use client";

// Platform Admin — Plan Detail. REAL-mode only, mirrors the Organization
// Detail page's structure. Backend enforces PLATFORM_MANAGE on every call
// here (app/api/v1/platform.py, M5) — this page hiding controls from
// non-platform-admin users is a UX convenience, never the security boundary.
//
// Plan-feature mutations are GLOBAL-IMPACT: a feature change here can affect
// every organization subscribed to this plan (see M2's resolver). Every
// state-changing action therefore goes through ConfirmDialog with explicit
// global-impact language, and every mutation re-fetches from the API
// afterward rather than trusting local state (per M9 spec).
//
// No subscription data is shown here — that is explicitly out of scope for
// M9 (see plan spec Phase 6).

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { planApi, type PlanResponse, type PlanFeatureResponse } from "@/lib/api/plan";

function planStatusBadge(isActive: boolean) {
  return isActive
    ? { status: "COMPLIANT" as const, label: "Active" }
    : { status: "UNKNOWN" as const, label: "Inactive" };
}

type PendingAction =
  | { type: "activate" }
  | { type: "deactivate" }
  | { type: "toggle-feature"; feature: PlanFeatureResponse; newEnabled: boolean };

function RealPlanDetail({ planId }: { planId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [planError, setPlanError] = useState<NormalizedApiError | null>(null);
  const [features, setFeatures] = useState<PlanFeatureResponse[] | null>(null);
  const [featuresError, setFeaturesError] = useState<NormalizedApiError | null>(null);
  const [loading, setLoading] = useState(true);

  // Edit form state
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<NormalizedApiError | null>(null);

  // Add feature form state
  const [newFeatureKey, setNewFeatureKey] = useState("");
  const [newFeatureEnabled, setNewFeatureEnabled] = useState(true);
  const [addFeatureBusy, setAddFeatureBusy] = useState(false);
  const [addFeatureError, setAddFeatureError] = useState<NormalizedApiError | null>(null);

  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setPlanError(null);
    setFeaturesError(null);

    Promise.allSettled([
      planApi.getPlan(accessToken, planId),
      planApi.listPlanFeatures(accessToken, planId),
    ]).then(([planResult, featuresResult]) => {
      if (cancelled) return;
      if (planResult.status === "fulfilled") {
        setPlan(planResult.value);
        setEditName(planResult.value.name);
        setEditCode(planResult.value.code);
        setEditDescription(planResult.value.description ?? "");
      } else {
        setPlanError(normalizeApiError(planResult.reason));
      }

      if (featuresResult.status === "fulfilled") setFeatures(featuresResult.value);
      else setFeaturesError(normalizeApiError(featuresResult.reason));

      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated, planId]);

  const saveEdit = () => {
    if (!accessToken || !plan || !editName.trim() || !editCode.trim()) return;
    setEditBusy(true);
    setEditError(null);
    planApi
      .updatePlan(accessToken, plan.id, {
        name: editName.trim(),
        code: editCode.trim(),
        description: editDescription.trim() || null,
      })
      .then(() => {
        setEditing(false);
        load();
      })
      .catch((err) => setEditError(normalizeApiError(err)))
      .finally(() => setEditBusy(false));
  };

  const confirmAction = () => {
    if (!accessToken || !plan || !pendingAction) return;
    setActionBusy(true);
    setActionError(null);

    let request: Promise<unknown>;
    if (pendingAction.type === "activate") {
      request = planApi.activatePlan(accessToken, plan.id);
    } else if (pendingAction.type === "deactivate") {
      request = planApi.deactivatePlan(accessToken, plan.id);
    } else {
      request = planApi.setPlanFeatureEnabled(
        accessToken,
        plan.id,
        pendingAction.feature.feature_key,
        pendingAction.newEnabled
      );
    }

    request
      .then(() => {
        setPendingAction(null);
        load();
      })
      .catch((err) => setActionError(normalizeApiError(err)))
      .finally(() => setActionBusy(false));
  };

  const addFeature = () => {
    if (!accessToken || !plan || !newFeatureKey.trim()) return;
    setAddFeatureBusy(true);
    setAddFeatureError(null);
    planApi
      .createPlanFeature(accessToken, plan.id, {
        feature_key: newFeatureKey.trim(),
        enabled: newFeatureEnabled,
      })
      .then(() => {
        setNewFeatureKey("");
        setNewFeatureEnabled(true);
        load();
      })
      .catch((err) => setAddFeatureError(normalizeApiError(err)))
      .finally(() => setAddFeatureBusy(false));
  };

  const featureColumns: Column<PlanFeatureResponse>[] = [
    {
      key: "feature",
      header: "Feature Key",
      render: (f) => <span style={{ wordBreak: "break-word" }}>{f.feature_key}</span>,
    },
    {
      key: "state",
      header: "State",
      render: (f) => <StatusBadge status={f.enabled ? "TRUE" : "FALSE"} label={f.enabled ? "Enabled" : "Disabled"} />,
    },
    {
      key: "actions",
      header: "Actions",
      render: (f) => (
        <button
          className="ac-btn"
          style={{ fontSize: 12, padding: "2px 8px" }}
          onClick={() => setPendingAction({ type: "toggle-feature", feature: f, newEnabled: !f.enabled })}
        >
          {f.enabled ? "Disable" : "Enable"}
        </button>
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

  const forbidden = planError?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Plans", href: "/platform/plans" },
          { label: plan?.name ?? planId },
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
            You do not have permission to administer plans.
          </p>
        </div>
      ) : planError && planError.kind === "not_found" ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>{planError.message}</p>
        </div>
      ) : (
        <>
          <div className="ac-section-header">
            <div>
              <h1 className="ac-h1" style={{ wordBreak: "break-word" }}>{plan?.name ?? "Plan"}</h1>
              <p className="ac-subtitle">Plan ID: {planId}</p>
            </div>
          </div>

          {planError && (
            <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Plan details failed to load: {planError.message}
              </p>
            </div>
          )}

          {plan && (
            <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
                <h2 className="ac-h2">Plan Details</h2>
                {!editing && (
                  <button className="ac-btn" onClick={() => setEditing(true)}>
                    Edit
                  </button>
                )}
              </div>

              {editing ? (
                <div style={{ marginTop: 8 }}>
                  <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                    <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      Name
                      <input
                        className="ac-input"
                        style={{ width: 220 }}
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        aria-label="Plan name"
                      />
                    </label>
                    <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      Code
                      <input
                        className="ac-input"
                        style={{ width: 160 }}
                        value={editCode}
                        onChange={(e) => setEditCode(e.target.value)}
                        aria-label="Plan code"
                      />
                    </label>
                    <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 280px" }}>
                      Description
                      <input
                        className="ac-input"
                        value={editDescription}
                        onChange={(e) => setEditDescription(e.target.value)}
                        aria-label="Plan description"
                      />
                    </label>
                  </div>
                  <div className="ac-flex ac-gap-2" style={{ marginTop: 8 }}>
                    <button className="ac-btn" onClick={saveEdit} disabled={editBusy || !editName.trim() || !editCode.trim()}>
                      {editBusy ? "Saving…" : "Save Changes"}
                    </button>
                    <button
                      className="ac-btn"
                      onClick={() => {
                        setEditing(false);
                        setEditError(null);
                        setEditName(plan.name);
                        setEditCode(plan.code);
                        setEditDescription(plan.description ?? "");
                      }}
                      disabled={editBusy}
                    >
                      Cancel
                    </button>
                  </div>
                  {editError && (
                    <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                      {editError.message}
                    </p>
                  )}
                </div>
              ) : (
                <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
                  <StatusBadge {...planStatusBadge(plan.is_active)} />
                  <span className="ac-text-sm">Code: {plan.code}</span>
                  <span className="ac-text-sm ac-text-muted" style={{ wordBreak: "break-word" }}>
                    {plan.description || "No description"}
                  </span>
                </div>
              )}

              <div className="ac-flex ac-gap-2" style={{ marginTop: 12 }}>
                {plan.is_active ? (
                  <button className="ac-btn" onClick={() => setPendingAction({ type: "deactivate" })}>
                    Deactivate
                  </button>
                ) : (
                  <button className="ac-btn" onClick={() => setPendingAction({ type: "activate" })}>
                    Activate
                  </button>
                )}
              </div>
              {actionError && (
                <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                  {actionError.message}
                </p>
              )}
            </section>
          )}

          <section className="ac-card ac-section" style={{ padding: 0 }}>
            <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) 0" }}>
              <h2 className="ac-h2">Plan Features</h2>
              <p className="ac-text-sm ac-text-muted">
                Feature changes are global — they affect every organization subscribed to this plan.
              </p>
            </div>
            <RealDataPanel
              loading={false}
              error={featuresError}
              isEmpty={!featuresError && (features?.length ?? 0) === 0}
              emptyMessage="No features have been configured for this plan yet."
            >
              <div className="ac-table-desktop">
                <DataTable columns={featureColumns} rows={features ?? []} />
              </div>
              <div className="ac-row-cards">
                {(features ?? []).map((f) => (
                  <div className="ac-row-card" key={f.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Feature Key</span>
                      <strong style={{ wordBreak: "break-word" }}>{f.feature_key}</strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">State</span>
                      <StatusBadge status={f.enabled ? "TRUE" : "FALSE"} label={f.enabled ? "Enabled" : "Disabled"} />
                    </div>
                    <div className="ac-row-card-actions">
                      <button
                        className="ac-btn"
                        onClick={() => setPendingAction({ type: "toggle-feature", feature: f, newEnabled: !f.enabled })}
                      >
                        {f.enabled ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </RealDataPanel>

            <div style={{ padding: "var(--ac-space-4)", borderTop: "1px solid var(--ac-border)" }}>
              <strong className="ac-text-sm">Add a plan feature</strong>
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
                <input
                  className="ac-input"
                  style={{ width: 220 }}
                  placeholder="Feature key (e.g. flight-planning)"
                  value={newFeatureKey}
                  onChange={(e) => setNewFeatureKey(e.target.value)}
                  aria-label="New feature key"
                />
                <label className="ac-text-sm ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={newFeatureEnabled}
                    onChange={(e) => setNewFeatureEnabled(e.target.checked)}
                    aria-label="Enabled by default"
                  />
                  Enabled
                </label>
                <button className="ac-btn" onClick={addFeature} disabled={addFeatureBusy || !newFeatureKey.trim()}>
                  {addFeatureBusy ? "Adding…" : "Add Feature"}
                </button>
              </div>
              {addFeatureError && (
                <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                  {addFeatureError.message}
                </p>
              )}
            </div>
          </section>
        </>
      )}

      <ConfirmDialog
        open={pendingAction !== null}
        title={
          pendingAction?.type === "activate"
            ? `Activate ${plan?.name ?? "plan"}?`
            : pendingAction?.type === "deactivate"
              ? `Deactivate ${plan?.name ?? "plan"}?`
              : `${pendingAction?.newEnabled ? "Enable" : "Disable"} feature "${pendingAction?.type === "toggle-feature" ? pendingAction.feature.feature_key : ""}"?`
        }
        body={
          pendingAction?.type === "activate"
            ? `This plan may be assigned to multiple organizations. Activating "${plan?.name ?? ""}" makes it available for subscriptions again and restores its features for any organization already assigned to it.`
            : pendingAction?.type === "deactivate"
              ? `This plan may be assigned to multiple organizations. Deactivating "${plan?.name ?? ""}" does not delete it or its subscriptions, but can change effective entitlement resolution for every organization currently subscribed to it.`
              : pendingAction?.type === "toggle-feature"
                ? `Plan: ${plan?.name ?? ""} — Feature: ${pendingAction.feature.feature_key} — Current: ${pendingAction.feature.enabled ? "Enabled" : "Disabled"} — New: ${pendingAction.newEnabled ? "Enabled" : "Disabled"}. This is a plan-level change and may affect effective entitlements for every organization subscribed to this plan.`
                : ""
        }
        confirmLabel={
          pendingAction?.type === "activate"
            ? "Activate Plan"
            : pendingAction?.type === "deactivate"
              ? "Deactivate Plan"
              : pendingAction?.type === "toggle-feature"
                ? pendingAction.newEnabled
                  ? "Enable Feature"
                  : "Disable Feature"
                : "Confirm"
        }
        cancelLabel="Cancel"
        busy={actionBusy}
        onConfirm={confirmAction}
        onCancel={() => {
          setPendingAction(null);
          setActionError(null);
        }}
      />
    </div>
  );
}

export default function PlatformPlanDetailPage(props: { params: Promise<{ planId: string }> }) {
  const params = use(props.params);
  return <RealPlanDetail planId={params.planId} />;
}
