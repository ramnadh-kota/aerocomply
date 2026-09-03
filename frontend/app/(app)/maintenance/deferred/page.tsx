"use client";

import { useState } from "react";
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
