"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import {
  getFleetDeferredItems,
  getDeferredRiskSummary,
  getDeferredClosureReadiness,
  type DeferredItemOperationalStatus,
} from "@/lib/mock/ai/analytics";
import { closeDeferredItem } from "@/lib/mock/deferredItems";
import { getDefectById } from "@/lib/mock/defects";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { deferredItemsApi, type BackendDeferredItem } from "@/lib/api/deferred-items";
import { aircraftApi, type BackendAircraft } from "@/lib/api/aircraft";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

// Phase 3 (Deferred/MEL REAL mode) — display bucketing below (ACTIVE/DUE
// SOON/OVERDUE/CLOSED) is a same-day string comparison against the backend's
// own due_at and status fields for grouping/filtering only. It never
// determines whether an item CAN be closed — that gate is entirely
// server-side (deferred_item_service.close_deferred_item: approval_required
// + approval_status). No second deferred-item data model, no invented
// compliance signal.
type RealBucket = "ACTIVE" | "DUE_SOON" | "OVERDUE" | "CLOSED";

function bucketFor(item: BackendDeferredItem): RealBucket {
  if (item.status === "CLOSED") return "CLOSED";
  if (!item.due_at) return "ACTIVE";
  const today = new Date().toISOString().slice(0, 10);
  const daysUntilDue = Math.floor(
    (new Date(item.due_at).getTime() - new Date(today).getTime()) / (1000 * 60 * 60 * 24)
  );
  if (daysUntilDue < 0) return "OVERDUE";
  if (daysUntilDue <= 7) return "DUE_SOON";
  return "ACTIVE";
}

const REAL_BUCKET_BADGE: Record<RealBucket, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  ACTIVE: { status: "COMPLIANT", label: "ACTIVE" },
  DUE_SOON: { status: "PENDING", label: "DUE SOON" },
  OVERDUE: { status: "NON_COMPLIANT", label: "OVERDUE" },
  CLOSED: { status: "COMPLIANT", label: "CLOSED" },
};

function RealDeferredItemsList() {
  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const [items, setItems] = useState<BackendDeferredItem[]>([]);
  const [aircraftById, setAircraftById] = useState<Record<string, BackendAircraft>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [filter, setFilter] = useState<RealBucket | "ALL">("ALL");
  const [closingId, setClosingId] = useState<string | null>(null);
  const [closureNotes, setClosureNotes] = useState("");
  const [actionError, setActionError] = useState<NormalizedApiError | null>(null);
  const [actionPending, setActionPending] = useState(false);

  const [reloadToken, setReloadToken] = useState(0);
  const load = () => setReloadToken((v) => v + 1);

  useEffect(() => {
    let cancelled = false;
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([deferredItemsApi.listForFleet(accessToken), aircraftApi.list(accessToken)])
      .then(([deferredItems, aircraft]) => {
        if (cancelled) return;
        setItems(deferredItems);
        setAircraftById(Object.fromEntries(aircraft.map((a) => [a.id, a])));
      })
      .catch((err) => {
        if (!cancelled) setError(normalizeApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated, reloadToken]);

  const filtered = filter === "ALL" ? items : items.filter((i) => bucketFor(i) === filter);
  const counts: Record<RealBucket, number> = { ACTIVE: 0, DUE_SOON: 0, OVERDUE: 0, CLOSED: 0 };
  for (const item of items) counts[bucketFor(item)] += 1;

  const startClose = (itemId: string) => {
    setClosingId(itemId);
    setClosureNotes("");
    setActionError(null);
  };

  const submitClose = (itemId: string) => {
    if (!accessToken) return;
    setActionPending(true);
    setActionError(null);
    const today = new Date().toISOString().slice(0, 10);
    deferredItemsApi
      .close(accessToken, itemId, { closed_at: today, closure_notes: closureNotes.trim() || null })
      .then(() => {
        setClosingId(null);
        setClosureNotes("");
        load();
      })
      .catch((err) => setActionError(normalizeApiError(err)))
      .finally(() => setActionPending(false));
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/control-tower" }, { label: "Deferred / MEL" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Deferred Items / MEL Operations</h1>
          <p className="ac-subtitle">REAL data mode — connected to {apiBaseUrl}</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            REAL data mode requires signing in. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel loading={loading} error={error} isEmpty={items.length === 0} emptyMessage="No deferred items are recorded for this organization's fleet yet.">
          <section className="ac-section">
            <div className="ac-kpi-grid">
              {(["ACTIVE", "DUE_SOON", "OVERDUE", "CLOSED"] as RealBucket[]).map((b) => (
                <button
                  key={b}
                  className="ac-kpi-card"
                  style={{ display: "block", textAlign: "left", cursor: "pointer", borderColor: filter === b ? "var(--ac-accent)" : undefined }}
                  onClick={() => setFilter(filter === b ? "ALL" : b)}
                >
                  <p className="ac-kpi-label">{REAL_BUCKET_BADGE[b].label}</p>
                  <p className="ac-kpi-value">{counts[b]}</p>
                </button>
              ))}
            </div>
          </section>

          <section className="ac-section">
            <div className="ac-flex ac-flex-col ac-gap-3">
              {filtered.map((item) => {
                const bucket = bucketFor(item);
                const badge = REAL_BUCKET_BADGE[bucket];
                const aircraft = aircraftById[item.aircraft_id];
                const canClose =
                  item.status === "OPEN" &&
                  (!item.approval_required || item.approval_status === "APPROVED");
                return (
                  <div key={item.id} className="ac-card">
                    <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10 }}>
                      <div>
                        <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
                          <StatusBadge status={badge.status} label={badge.label} />
                          <Link href={`/aircraft/${item.aircraft_id}`} className="ac-mono ac-text-sm">
                            {aircraft?.registration ?? item.aircraft_id}
                          </Link>
                        </div>
                        <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>{item.description}</p>
                        <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>
                          Category {item.category} · Basis {item.deferral_basis} · Due {item.due_at ?? "Not recorded"} · MEL Ref {item.mel_reference ?? "Not recorded"}
                        </p>
                        {item.operational_limitations && (
                          <p className="ac-text-sm" style={{ margin: "0 0 2px" }}>Limitation: {item.operational_limitations}</p>
                        )}
                        {item.required_actions && (
                          <p className="ac-text-sm" style={{ margin: "0 0 2px" }}>Required actions: {item.required_actions}</p>
                        )}
                        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                          Approval: {item.approval_status.replace(/_/g, " ")}
                          {item.status === "CLOSED" && ` · Closed ${item.closed_at ?? ""}`}
                        </p>
                        {item.status === "CLOSED" && item.closure_notes && (
                          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Closure notes: {item.closure_notes}</p>
                        )}
                      </div>
                      <div style={{ minWidth: 220 }}>
                        {item.status === "CLOSED" ? (
                          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Already closed.</p>
                        ) : !canClose ? (
                          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                            Blocked — approval required before closure (currently {item.approval_status.replace(/_/g, " ")}).
                          </p>
                        ) : closingId === item.id ? (
                          <div>
                            <textarea
                              className="ac-input"
                              style={{ width: "100%", marginBottom: 6, fontSize: 12 }}
                              placeholder="Closure notes (optional)"
                              value={closureNotes}
                              onChange={(e) => setClosureNotes(e.target.value)}
                            />
                            {actionError && (
                              <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", margin: "0 0 6px" }}>
                                {actionError.message}
                              </p>
                            )}
                            <div className="ac-flex ac-gap-2">
                              <button className="ac-btn ac-btn-primary" disabled={actionPending} onClick={() => submitClose(item.id)}>
                                {actionPending ? "Closing…" : "Confirm Close"}
                              </button>
                              <button className="ac-btn" disabled={actionPending} onClick={() => setClosingId(null)}>Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <button className="ac-btn ac-btn-primary" onClick={() => startClose(item.id)}>Close Deferred Item</button>
                        )}
                        <p className="ac-text-sm" style={{ marginTop: 8 }}>
                          <Link href={`/aircraft/${item.aircraft_id}`} className="ac-mono">View Aircraft →</Link>
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No deferred item in this category.</p></div>
              )}
            </div>
          </section>
        </RealDataPanel>
      )}
    </div>
  );
}

// M18/M19/PhaseC — dedicated Deferred/MEL operations page. Reuses
// getFleetDeferredItems/getDeferredRiskSummary/getDeferredClosureReadiness/
// closeDeferredItem exactly as-is (all already exist — no second deferred
// engine). Previously this data was only visible scattered on individual
// Aircraft detail pages; this is the fleet-wide operational view.

const STATUS_BADGE: Record<DeferredItemOperationalStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  ACTIVE: { status: "COMPLIANT", label: "ACTIVE" },
  DUE_SOON: { status: "PENDING", label: "DUE SOON" },
  OVERDUE: { status: "NON_COMPLIANT", label: "OVERDUE" },
  CLOSED: { status: "COMPLIANT", label: "CLOSED" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

export default function DeferredItemsPage() {
  const { isReal, hydrated } = useDataMode();
  if (!hydrated) return null;
  return isReal ? <RealDeferredItemsList /> : <DemoDeferredItemsPage />;
}

function DemoDeferredItemsPage() {
  const [filter, setFilter] = useState<DeferredItemOperationalStatus | "ALL">("ALL");
  const [, setVersion] = useState(0);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();

  const items = getFleetDeferredItems();
  const summary = getDeferredRiskSummary();
  const filtered = filter === "ALL" ? items : items.filter((i) => i.operationalStatus === filter);

  const close = (itemId: string, aircraftReg: string) => {
    const updated = closeDeferredItem(itemId);
    if (!updated) return;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.deferred_item_closed",
      objectType: "DeferredItem",
      objectLabel: itemId,
      previousState: "OPEN",
      newState: "CLOSED",
      reason: `Closure readiness evaluated as READY for deferred item ${itemId} on ${aircraftReg}.`,
    });
    setVersion((v) => v + 1);
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/control-tower" }, { label: "Deferred / MEL" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Deferred Items / MEL Operations</h1>
          <p className="ac-subtitle">
            Fleet-wide view of every deferred item, its operational status, and closure readiness. Closure is human-gated — it
            never happens merely because a linked work order is completed, and it never implies an airworthiness determination.
          </p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          {(["ACTIVE", "DUE_SOON", "OVERDUE", "CLOSED", "UNKNOWN"] as DeferredItemOperationalStatus[]).map((s) => (
            <button
              key={s}
              className="ac-kpi-card"
              style={{ display: "block", textAlign: "left", cursor: "pointer", borderColor: filter === s ? "var(--ac-accent)" : undefined }}
              onClick={() => setFilter(filter === s ? "ALL" : s)}
            >
              <p className="ac-kpi-label">{STATUS_BADGE[s].label}</p>
              <p className="ac-kpi-value">{s === "ACTIVE" ? summary.active : s === "DUE_SOON" ? summary.dueSoon : s === "OVERDUE" ? summary.overdue : s === "CLOSED" ? summary.closed : summary.unknown}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-flex ac-flex-col ac-gap-3">
          {filtered.map((item) => {
            const badge = STATUS_BADGE[item.operationalStatus];
            const defect = getDefectById(item.defectId);
            const closure = getDeferredClosureReadiness(item.id);
            return (
              <div key={item.id} className="ac-card">
                <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
                      <StatusBadge status={badge.status} label={badge.label} />
                      <Link href={`/aircraft/${item.aircraftId}`} className="ac-mono ac-text-sm">{item.registration}</Link>
                      <span className="ac-text-sm ac-text-muted">{item.id}</span>
                    </div>
                    <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>{defect?.description ?? "Insufficient source data."}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 2px" }}>
                      Category {item.category} · Basis {item.deferralBasis} · Due {item.dueAt ?? "UNKNOWN"} · MEL Ref {item.melReference ?? "Insufficient source data."}
                    </p>
                    {item.operationalLimitations && (
                      <p className="ac-text-sm" style={{ margin: "0 0 2px" }}>Limitation: {item.operationalLimitations}</p>
                    )}
                    {item.requiredActions.length > 0 && (
                      <p className="ac-text-sm" style={{ margin: "0 0 2px" }}>Required actions: {item.requiredActions.join("; ")}</p>
                    )}
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                      Approval: {item.approvalStatus.replace(/_/g, " ")} · Evidence on file: {item.evidenceReferences.length > 0 ? item.evidenceReferences.join("; ") : "None"}
                    </p>
                  </div>
                  <div style={{ minWidth: 220 }}>
                    <p className="ac-eyebrow" style={{ marginBottom: 4 }}>Closure Readiness: {closure.readiness}</p>
                    {closure.readiness === "READY" && item.status === "OPEN" ? (
                      <button className="ac-btn ac-btn-primary" onClick={() => close(item.id, item.registration)}>Close Deferred Item</button>
                    ) : item.status === "CLOSED" ? (
                      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Already closed.</p>
                    ) : (
                      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                        {closure.blockers.map((b, i) => <li key={i} className="ac-text-muted">{b}</li>)}
                      </ul>
                    )}
                    <p className="ac-text-sm" style={{ marginTop: 8 }}>
                      <Link href={`/aircraft/${item.aircraftId}`} className="ac-mono">View Aircraft →</Link>
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && (
            <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No deferred item in this category.</p></div>
          )}
        </div>
      </section>
    </div>
  );
}
