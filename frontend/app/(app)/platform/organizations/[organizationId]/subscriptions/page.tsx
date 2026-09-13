"use client";

// Platform Admin — Subscription Administration (M10). REAL-mode only, same
// as the rest of platform admin: cross-tenant staff tooling, no demo
// dataset. Backend enforces PLATFORM_MANAGE on every call here
// (app/api/v1/platform.py, M6) — this page hiding controls from
// non-platform-admin users is a UX convenience, never the security
// boundary.
//
// This page never decides which subscription is "current" for the
// organization, never recomputes entitlement resolution, and never
// invents its own lifecycle rules. "Current" vs "future" vs "historical"
// below is derived only from the real fields the backend returns
// (status + starts_at/ends_at compared to now), and every state
// transition offered in the UI mirrors
// app/services/subscription_service.py's `_ALLOWED_TRANSITIONS` table
// exactly — the backend remains the actual source of truth and will
// reject (409 invalid_transition / ambiguous_subscription_state) anything
// this page gets wrong. Effective entitlements are never computed here;
// this page only links to the existing M8 Organization Detail page, which
// reads them from the M2 resolver via the M3 API.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { planApi, type PlanResponse } from "@/lib/api/plan";
import {
  subscriptionApi,
  type SubscriptionResponse,
  ALLOWED_TRANSITIONS,
  CREATABLE_STATUSES,
  groupSubscription,
} from "@/lib/api/subscription";

function statusBadge(status: string) {
  const map: Record<string, Parameters<typeof StatusBadge>[0]["status"]> = {
    TRIALING: "REVIEW_REQUIRED",
    ACTIVE: "COMPLIANT",
    PAST_DUE: "REVIEW_REQUIRED",
    CANCELED: "UNKNOWN",
    SCHEDULED: "INSUFFICIENT_DATA",
  };
  return { status: map[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

function toDateTimeLocalValue(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type PendingAction =
  | { type: "create"; plan_id: string; status: string; starts_at: string; ends_at: string | null }
  | { type: "transition"; sub: SubscriptionResponse; newStatus: string }
  | { type: "cancel"; sub: SubscriptionResponse }
  | {
      type: "edit";
      sub: SubscriptionResponse;
      plan_id: string;
      starts_at: string;
      ends_at: string | null;
    };

function RealSubscriptionAdmin({ organizationId }: { organizationId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [subs, setSubs] = useState<SubscriptionResponse[] | null>(null);
  const [subsError, setSubsError] = useState<NormalizedApiError | null>(null);
  const [plans, setPlans] = useState<PlanResponse[] | null>(null);
  const [plansError, setPlansError] = useState<NormalizedApiError | null>(null);
  const [loading, setLoading] = useState(true);

  // Create form state
  const [newPlanId, setNewPlanId] = useState("");
  const [newStatus, setNewStatus] = useState<string>("ACTIVE");
  const [newStartsAt, setNewStartsAt] = useState("");
  const [newEndsAt, setNewEndsAt] = useState("");
  const [createError, setCreateError] = useState<NormalizedApiError | null>(null);

  // Edit form state (per-row, keyed by subscription id)
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editPlanId, setEditPlanId] = useState("");
  const [editStartsAt, setEditStartsAt] = useState("");
  const [editEndsAt, setEditEndsAt] = useState("");
  const [editError, setEditError] = useState<NormalizedApiError | null>(null);

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
    setSubsError(null);
    setPlansError(null);

    Promise.allSettled([
      subscriptionApi.listForOrganization(accessToken, organizationId),
      planApi.listPlans(accessToken),
    ]).then(([subsResult, plansResult]) => {
      if (cancelled) return;
      if (subsResult.status === "fulfilled") setSubs(subsResult.value);
      else setSubsError(normalizeApiError(subsResult.reason));

      if (plansResult.status === "fulfilled") setPlans(plansResult.value);
      else setPlansError(normalizeApiError(plansResult.reason));

      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  };

  // Load once on mount / when auth or org changes.
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated, organizationId]);

  const planName = (planId: string) => plans?.find((p) => p.id === planId)?.name ?? planId;

  const submitCreate = () => {
    if (!newPlanId || !newStartsAt) return;
    setPendingAction({
      type: "create",
      plan_id: newPlanId,
      status: newStatus,
      starts_at: new Date(newStartsAt).toISOString(),
      ends_at: newEndsAt ? new Date(newEndsAt).toISOString() : null,
    });
  };

  const startEdit = (sub: SubscriptionResponse) => {
    setEditingId(sub.id);
    setEditPlanId(sub.plan_id);
    setEditStartsAt(toDateTimeLocalValue(sub.starts_at));
    setEditEndsAt(sub.ends_at ? toDateTimeLocalValue(sub.ends_at) : "");
    setEditError(null);
  };

  const submitEdit = (sub: SubscriptionResponse) => {
    if (!editStartsAt) return;
    setPendingAction({
      type: "edit",
      sub,
      plan_id: editPlanId,
      starts_at: new Date(editStartsAt).toISOString(),
      ends_at: editEndsAt ? new Date(editEndsAt).toISOString() : null,
    });
  };

  const confirmAction = () => {
    if (!accessToken || !pendingAction) return;
    setActionBusy(true);
    setActionError(null);

    let request: Promise<unknown>;
    if (pendingAction.type === "create") {
      request = subscriptionApi.create(accessToken, organizationId, {
        plan_id: pendingAction.plan_id,
        status: pendingAction.status,
        starts_at: pendingAction.starts_at,
        ends_at: pendingAction.ends_at,
      });
    } else if (pendingAction.type === "transition") {
      request = subscriptionApi.update(accessToken, pendingAction.sub.id, {
        status: pendingAction.newStatus,
      });
    } else if (pendingAction.type === "cancel") {
      request = subscriptionApi.cancel(accessToken, pendingAction.sub.id);
    } else {
      request = subscriptionApi.update(accessToken, pendingAction.sub.id, {
        plan_id: pendingAction.plan_id !== pendingAction.sub.plan_id ? pendingAction.plan_id : undefined,
        starts_at: pendingAction.starts_at,
        ends_at: pendingAction.ends_at,
      });
    }

    request
      .then(() => {
        setPendingAction(null);
        setEditingId(null);
        if (pendingAction.type === "create") {
          setNewPlanId("");
          setNewStartsAt("");
          setNewEndsAt("");
        }
        load();
      })
      .catch((err) => setActionError(normalizeApiError(err)))
      .finally(() => setActionBusy(false));
  };

  const columns: Column<SubscriptionResponse>[] = [
    {
      key: "plan",
      header: "Plan",
      render: (s) => <span style={{ wordBreak: "break-word" }}>{planName(s.plan_id)}</span>,
    },
    { key: "status", header: "Status", render: (s) => <StatusBadge {...statusBadge(s.status)} /> },
    { key: "starts", header: "Starts", render: (s) => new Date(s.starts_at).toLocaleString() },
    { key: "ends", header: "Ends", render: (s) => (s.ends_at ? new Date(s.ends_at).toLocaleString() : "Open-ended") },
    {
      key: "actions",
      header: "Actions",
      render: (s) => {
        const transitions = ALLOWED_TRANSITIONS[s.status] ?? [];
        return (
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            {transitions
              .filter((t) => t !== "CANCELED")
              .map((t) => (
                <button
                  key={t}
                  className="ac-btn"
                  style={{ fontSize: 12, padding: "2px 8px" }}
                  onClick={() => setPendingAction({ type: "transition", sub: s, newStatus: t })}
                >
                  Move to {t.replace(/_/g, " ")}
                </button>
              ))}
            {transitions.includes("CANCELED") && (
              <button
                className="ac-btn"
                style={{ fontSize: 12, padding: "2px 8px", borderColor: "var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)" }}
                onClick={() => setPendingAction({ type: "cancel", sub: s })}
              >
                Cancel
              </button>
            )}
            {s.status !== "CANCELED" && (
              <button className="ac-btn" style={{ fontSize: 12, padding: "2px 8px" }} onClick={() => startEdit(s)}>
                Edit
              </button>
            )}
          </div>
        );
      },
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

  const forbidden = subsError?.kind === "forbidden" || plansError?.kind === "forbidden";
  const notFound = subsError?.kind === "not_found";

  const now = new Date();
  const current = (subs ?? []).filter((s) => groupSubscription(s, now) === "Current");
  const upcoming = (subs ?? []).filter((s) => groupSubscription(s, now) === "Upcoming");
  const historical = (subs ?? []).filter((s) => groupSubscription(s, now) === "Historical");

  const buildDialogBody = () => {
    if (!pendingAction) return "";
    let base = "";
    if (pendingAction.type === "create") {
      const isSched = pendingAction.status === "SCHEDULED";
      base =
        `Organization: ${organizationId}\n` +
        `Plan: ${planName(pendingAction.plan_id)}\n` +
        `Status: ${pendingAction.status.replace(/_/g, " ")}\n` +
        `Starts: ${new Date(pendingAction.starts_at).toLocaleString()}\n` +
        `Ends: ${pendingAction.ends_at ? new Date(pendingAction.ends_at).toLocaleString() : "Open-ended"}\n\n` +
        (isSched
          ? "This is a future subscription and does not grant current entitlement."
          : "This subscription may change the organization's effective entitlements. If this status is TRIALING, ACTIVE, or PAST_DUE and overlaps another eligible subscription, the backend will reject the creation to prevent an ambiguous state.");
    } else if (pendingAction.type === "transition") {
      base =
        `Organization: ${organizationId}\n` +
        `Plan: ${planName(pendingAction.sub.plan_id)}\n` +
        `Current Status: ${pendingAction.sub.status.replace(/_/g, " ")}\n` +
        `New Status: ${pendingAction.newStatus.replace(/_/g, " ")}\n` +
        `Starts: ${new Date(pendingAction.sub.starts_at).toLocaleString()}\n` +
        `Ends: ${pendingAction.sub.ends_at ? new Date(pendingAction.sub.ends_at).toLocaleString() : "Open-ended"}\n\n` +
        `Moving this subscription to ${pendingAction.newStatus.replace(/_/g, " ")} may change the organization's effective entitlements.`;
    } else if (pendingAction.type === "cancel") {
      base =
        `Organization: ${organizationId}\n` +
        `Plan: ${planName(pendingAction.sub.plan_id)}\n` +
        `Current Status: ${pendingAction.sub.status.replace(/_/g, " ")}\n` +
        `Action: Permanent Cancellation\n\n` +
        `This permanently and irreversibly cancels the subscription. CANCELED is a terminal state according to the backend and cannot be reactivated afterward. Canceling this subscription may immediately reduce the organization's effective entitlements.`;
    } else if (pendingAction.type === "edit") {
      base =
        `Organization: ${organizationId}\n` +
        `Plan: ${planName(pendingAction.plan_id)} (was: ${planName(pendingAction.sub.plan_id)})\n` +
        `Starts: ${new Date(pendingAction.starts_at).toLocaleString()}\n` +
        `Ends: ${pendingAction.ends_at ? new Date(pendingAction.ends_at).toLocaleString() : "Open-ended"}\n\n` +
        `Updating the plan or active dates may change the organization's effective entitlements.`;
    }
    if (actionError) {
      return `Backend Error: ${actionError.message}\n\n${base}`;
    }
    return base;
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Organizations", href: "/platform/organizations" },
          { label: organizationId, href: `/platform/organizations/${organizationId}` },
          { label: "Subscriptions" },
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
            You do not have permission to administer this organization&apos;s subscriptions.
          </p>
        </div>
      ) : notFound ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>{subsError?.message}</p>
        </div>
      ) : (
        <>
          <div className="ac-section-header">
            <div>
              <h1 className="ac-h1">Subscriptions</h1>
              <p className="ac-subtitle">
                Organization ID: {organizationId} ·{" "}
                <Link href={`/platform/organizations/${organizationId}`}>← Back to Organization & Effective Entitlements</Link>
              </p>
            </div>
          </div>

          {actionError && !pendingAction && (
            <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)", borderColor: "var(--ac-status-non-compliant)" }}>
              <strong className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>Operation failed</strong>
              <p className="ac-text-sm" style={{ margin: "4px 0 0" }}>{actionError.message}</p>
            </div>
          )}

          {subsError && (
            <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Subscription history failed to load: {subsError.message}
              </p>
            </div>
          )}
          {plansError && (
            <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
              <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                Plan catalog failed to load, so a new subscription cannot be created right now: {plansError.message}
              </p>
            </div>
          )}

          {[
            { title: "Current", rows: current, empty: "No currently-active subscription for this organization." },
            { title: "Upcoming", rows: upcoming, empty: "No scheduled or future-dated subscriptions." },
            { title: "Historical", rows: historical, empty: "No historical (canceled/ended) subscriptions." },
          ].map((group) => (
            <section className="ac-card ac-section" style={{ padding: 0 }} key={group.title}>
              <div style={{ padding: "var(--ac-space-4) var(--ac-space-4) 0" }}>
                <h2 className="ac-h2">{group.title}</h2>
              </div>
              <RealDataPanel loading={false} error={null} isEmpty={group.rows.length === 0} emptyMessage={group.empty}>
                <div className="ac-table-desktop">
                  <DataTable columns={columns} rows={group.rows} />
                </div>
                <div className="ac-row-cards">
                  {group.rows.map((s) => (
                    <div className="ac-row-card" key={s.id}>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Plan</span>
                        <strong style={{ wordBreak: "break-word" }}>{planName(s.plan_id)}</strong>
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Status</span>
                        <StatusBadge {...statusBadge(s.status)} />
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Starts</span>
                        <span>{new Date(s.starts_at).toLocaleString()}</span>
                      </div>
                      <div className="ac-row-card-field">
                        <span className="ac-row-card-field-label">Ends</span>
                        <span>{s.ends_at ? new Date(s.ends_at).toLocaleString() : "Open-ended"}</span>
                      </div>
                      <div className="ac-row-card-actions">{columns[columns.length - 1].render(s)}</div>
                    </div>
                  ))}
                </div>
              </RealDataPanel>

              {group.title !== "Historical" &&
                group.rows.map(
                  (s) =>
                    editingId === s.id && (
                      <div key={`edit-${s.id}`} style={{ padding: "var(--ac-space-4)", borderTop: "1px solid var(--ac-border)" }}>
                        <strong className="ac-text-sm">Edit subscription ({planName(s.plan_id)})</strong>
                        <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 8px" }}>
                          Changing the plan or dates can change effective entitlements for this organization.
                        </p>
                        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
                          <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            Plan
                            <select className="ac-input" value={editPlanId} onChange={(e) => setEditPlanId(e.target.value)} aria-label="Edit plan">
                              {(plans ?? []).map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name} {p.is_active ? "" : "(inactive)"}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            Starts
                            <input
                              className="ac-input"
                              type="datetime-local"
                              value={editStartsAt}
                              onChange={(e) => setEditStartsAt(e.target.value)}
                              aria-label="Edit starts at"
                            />
                          </label>
                          <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            Ends (optional)
                            <input
                              className="ac-input"
                              type="datetime-local"
                              value={editEndsAt}
                              onChange={(e) => setEditEndsAt(e.target.value)}
                              aria-label="Edit ends at"
                            />
                          </label>
                          <button className="ac-btn" onClick={() => submitEdit(s)} disabled={!editStartsAt}>
                            Save Changes
                          </button>
                          <button className="ac-btn" onClick={() => setEditingId(null)}>
                            Cancel
                          </button>
                        </div>
                        {editError && (
                          <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                            {editError.message}
                          </p>
                        )}
                      </div>
                    )
                )}
            </section>
          ))}

          <section className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <h2 className="ac-h2">Create Subscription</h2>
            <p className="ac-text-sm ac-text-muted">
              Creates a subscription for this organization. Choosing SCHEDULED creates a future-dated row that does
              not grant access until it transitions to TRIALING/ACTIVE/PAST_DUE — it has no immediate entitlement
              impact. Any other status can immediately change this organization&apos;s effective entitlements.
            </p>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "flex-end", marginTop: 8 }}>
              <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                Plan
                <select
                  className="ac-input"
                  style={{ minWidth: 200 }}
                  value={newPlanId}
                  onChange={(e) => setNewPlanId(e.target.value)}
                  aria-label="New subscription plan"
                  disabled={!plans || plans.length === 0}
                >
                  <option value="">Select a plan…</option>
                  {(plans ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} {p.is_active ? "" : "(inactive)"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                Status
                <select className="ac-input" value={newStatus} onChange={(e) => setNewStatus(e.target.value)} aria-label="New subscription status">
                  {CREATABLE_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                Starts
                <input
                  className="ac-input"
                  type="datetime-local"
                  value={newStartsAt}
                  onChange={(e) => setNewStartsAt(e.target.value)}
                  aria-label="New subscription starts at"
                />
              </label>
              <label className="ac-text-sm" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                Ends (optional)
                <input
                  className="ac-input"
                  type="datetime-local"
                  value={newEndsAt}
                  onChange={(e) => setNewEndsAt(e.target.value)}
                  aria-label="New subscription ends at"
                />
              </label>
              <button className="ac-btn" onClick={submitCreate} disabled={!newPlanId || !newStartsAt}>
                Create Subscription
              </button>
            </div>
            {createError && (
              <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                {createError.message}
              </p>
            )}
          </section>
        </>
      )}

      <ConfirmDialog
        open={pendingAction !== null}
        title={
          pendingAction?.type === "create"
            ? `Create ${pendingAction.status.replace(/_/g, " ")} subscription?`
            : pendingAction?.type === "transition"
              ? `Move subscription to ${pendingAction.newStatus.replace(/_/g, " ")}?`
              : pendingAction?.type === "cancel"
                ? "Cancel this subscription?"
                : pendingAction?.type === "edit"
                  ? "Save subscription changes?"
                  : ""
        }
        body={buildDialogBody()}
        confirmLabel={
          pendingAction?.type === "create"
            ? "Create Subscription"
            : pendingAction?.type === "transition"
              ? `Move to ${pendingAction.newStatus.replace(/_/g, " ")}`
              : pendingAction?.type === "cancel"
                ? "Cancel Subscription (Permanent)"
                : "Save Changes"
        }
        cancelLabel="Back"
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

export default function PlatformOrganizationSubscriptionsPage({
  params,
}: {
  params: { organizationId: string };
}) {
  return <RealSubscriptionAdmin organizationId={params.organizationId} />;
}
