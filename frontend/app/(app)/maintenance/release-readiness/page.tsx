"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getReleaseQueue, getReleaseReadinessForWorkOrder, getWorkOrderTatStatus, type ReleaseReadinessStatus, type ReleaseBlocker, type TatStatus } from "@/lib/mock/ai/analytics";

// M0.7 — dedicated fleet-wide Release Readiness dashboard. Reuses the M26
// canonical engine exactly as-is (getReleaseReadinessForWorkOrder) over the
// same candidate set the Control Center's "Release Queue" KPI already uses
// (getReleaseQueue) — no new business logic, purely a presentation surface
// that was previously only reachable one work order at a time from the Task
// Card. This page reports gate/data completeness only; it is explicitly not
// an airworthiness or dispatch determination — see the SAFETY_REFUSAL text
// in Lisa's release-readiness answers for the same boundary.

const STATUS_BADGE: Record<ReleaseReadinessStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  READY: { status: "COMPLIANT", label: "READY" },
  BLOCKED: { status: "NON_COMPLIANT", label: "BLOCKED" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

const CATEGORY_LABEL: Record<ReleaseBlocker["category"], string> = {
  MATERIAL: "Material",
  QUALIFICATION: "Technician Authorization",
  INSPECTION: "Inspection",
  EVIDENCE: "Evidence",
  DEFERRED: "Deferred Item",
  REGULATORY: "Regulatory",
  AUDIT: "Audit",
  UNKNOWN: "Unknown",
};

const TAT_BADGE: Record<TatStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  ON_TRACK: { status: "COMPLIANT", label: "ON TRACK" },
  AT_RISK: { status: "PENDING", label: "TAT AT RISK" },
  DELAYED: { status: "NON_COMPLIANT", label: "DELAYED" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

type Filter = "ALL" | ReleaseReadinessStatus;

export default function ReleaseReadinessPage() {
  const [filter, setFilter] = useState<Filter>("ALL");

  const rows = useMemo(() => {
    return getReleaseQueue().map((q) => ({ ...q, readiness: getReleaseReadinessForWorkOrder(q.workOrderId), tat: getWorkOrderTatStatus(q.workOrderId) }));
  }, []);

  const counts = useMemo(
    () => ({
      READY: rows.filter((r) => r.readiness.status === "READY").length,
      BLOCKED: rows.filter((r) => r.readiness.status === "BLOCKED").length,
      UNKNOWN: rows.filter((r) => r.readiness.status === "UNKNOWN").length,
    }),
    [rows]
  );

  const filtered = filter === "ALL" ? rows : rows.filter((r) => r.readiness.status === filter);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/control-tower" }, { label: "Release Readiness" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Release Readiness</h1>
          <p className="ac-subtitle">
            Whether each work order approaching release has satisfied this application&apos;s known operational gates —
            material, technician authorization, inspection, evidence, deferred items, and regulatory assessments. This is
            gate/data completeness only, never an airworthiness or dispatch determination; release remains a human,
            authorized-signatory decision.
          </p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          {(["ALL", "BLOCKED", "READY", "UNKNOWN"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`ac-btn${filter === f ? " ac-btn-primary" : ""}`}
              style={{ fontSize: 13, padding: "6px 12px", minHeight: 36 }}
            >
              {f === "ALL" ? `All (${rows.length})` : `${STATUS_BADGE[f].label} (${counts[f]})`}
            </button>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <div style={{ display: "grid", gap: 10 }}>
          {filtered.map((r) => {
            const badge = STATUS_BADGE[r.readiness.status];
            return (
              <div key={r.workOrderId} className="ac-card" style={{ borderColor: r.readiness.status === "BLOCKED" ? "var(--ac-status-non-compliant)" : undefined }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap" }}>
                    <Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-mono" style={{ fontWeight: 700, fontSize: 15 }}>{r.workOrderNumber}</Link>
                    <span className="ac-text-sm ac-text-muted">{r.aircraftRegistration}</span>
                    <span className="ac-text-sm ac-text-muted">· {r.executionState.replace(/_/g, " ")}</span>
                  </div>
                  <div className="ac-flex ac-items-center ac-gap-2">
                    {r.tat && <StatusBadge {...TAT_BADGE[r.tat.status]} />}
                    <StatusBadge status={badge.status} label={badge.label} />
                  </div>
                </div>

                {r.tat && r.tat.status !== "ON_TRACK" && (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>{r.tat.reason}</p>
                )}

                {r.readiness.blockers.length > 0 ? (
                  <div>
                    <p className="ac-eyebrow" style={{ marginBottom: 6 }}>{r.readiness.blockers.length} blocker{r.readiness.blockers.length === 1 ? "" : "s"}</p>
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {r.readiness.blockers.map((b, i) => (
                        <li key={i} className="ac-text-sm" style={{ marginBottom: 4 }}>
                          <strong>[{CATEGORY_LABEL[b.category]}]</strong> {b.explanation} — <em>{b.requiredAction}</em>{" "}
                          <span className="ac-text-muted">(source: {b.source})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="ac-text-sm" style={{ margin: 0 }}>No outstanding blockers in the current dataset.</p>
                )}

                <div className="ac-flex ac-gap-2" style={{ marginTop: 10, flexWrap: "wrap" }}>
                  <Link href={`/maintenance/planning/${r.workOrderId}`} className="ac-btn">View Work Order</Link>
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && (
            <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No work order in this category.</p></div>
          )}
        </div>
      </section>
    </div>
  );
}
