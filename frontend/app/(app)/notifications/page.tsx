"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { PLATFORM_AI_NAME } from "@/lib/brand";
import { getProactiveAlerts, type AlertCategory, type AlertSeverity, type ProactiveAlert } from "@/lib/mock/ai/proactive";
import { useAlertState } from "@/lib/mock/ai/alertState";

// Same severity→badge mapping as Topbar.tsx (components/layout/Topbar.tsx) —
// never a second color mapping for alert severity.
const SEVERITY_BADGE: Record<AlertSeverity, { status: "NON_COMPLIANT" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA" | "COMPLIANT"; label: string }> = {
  CRITICAL: { status: "NON_COMPLIANT", label: "Critical" },
  HIGH: { status: "REVIEW_REQUIRED", label: "High" },
  MEDIUM: { status: "INSUFFICIENT_DATA", label: "Medium" },
  LOW: { status: "COMPLIANT", label: "Low" },
};

const CATEGORY_LABELS: Record<AlertCategory, string> = {
  AOG: "AOG",
  TAT: "Turnaround Time",
  EVIDENCE: "Execution Evidence",
  RII: "Independent Inspection",
  AUTHORIZATION: "Technician Authorization",
  PART: "Parts",
  VENDOR: "Vendor",
  REGULATORY: "Regulatory",
  RELEASE: "Release",
};

const ALL_CATEGORIES = Object.keys(CATEGORY_LABELS) as AlertCategory[];
const ALL_SEVERITIES: AlertSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function groupByCategory(alerts: ProactiveAlert[]): { category: AlertCategory; alerts: ProactiveAlert[] }[] {
  const groups = new Map<AlertCategory, ProactiveAlert[]>();
  for (const a of alerts) {
    const arr = groups.get(a.category) ?? [];
    arr.push(a);
    groups.set(a.category, arr);
  }
  // Preserve the severity-ranked order already applied by getProactiveAlerts()
  // — categories ordered by their most severe member, alerts within a
  // category keep their incoming (severity-first) order.
  return ALL_CATEGORIES.filter((c) => groups.has(c)).map((c) => ({ category: c, alerts: groups.get(c)! }));
}

export default function NotificationsPage() {
  const { roleId } = useRoleSim();
  // roleId passed through for relevance-only reordering — see the
  // getProactiveAlerts() doc comment in lib/mock/ai/proactive.ts. This page
  // still always shows the FULL fleet-wide alert set, unlike the Topbar's
  // top-8 dropdown.
  const allAlerts = useMemo(() => getProactiveAlerts(roleId), [roleId]);
  // Acknowledge/resolve is local, demo-only state — see the note on
  // lib/mock/ai/alertState.ts. It is never synced to a backend; it just
  // lets this browser remember which alert ids have been handled, matched
  // by id even though the alert list itself is recomputed every render.
  const { statusFor, acknowledge, resolve, reopen } = useAlertState();

  const [categoryFilter, setCategoryFilter] = useState<AlertCategory | "ALL">("ALL");
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | "ALL">("ALL");
  const [hideResolved, setHideResolved] = useState(false);

  const filtered = allAlerts.filter((a) => {
    if (categoryFilter !== "ALL" && a.category !== categoryFilter) return false;
    if (severityFilter !== "ALL" && a.severity !== severityFilter) return false;
    if (hideResolved && statusFor(a.id) === "RESOLVED") return false;
    return true;
  });

  const grouped = groupByCategory(filtered);

  const categoriesPresent = useMemo(() => new Set(allAlerts.map((a) => a.category)), [allAlerts]);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Notifications" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow">{PLATFORM_AI_NAME}&apos;s Alerts</p>
          <h1 className="ac-h1">Notification Center</h1>
          <p className="ac-subtitle">
            {filtered.length} of {allAlerts.length} alert(s) shown — every alert here is derived directly from a
            real fleet condition (AOG status, TAT risk, evidence gaps, inspection/authorization blocks, part
            shortages, vendor gaps, regulatory publications, and release queue state). Nothing is randomly
            generated.
          </p>
        </div>
      </div>

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap" }}>
          <select
            className="ac-input"
            style={{ width: 220 }}
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value as AlertCategory | "ALL")}
            aria-label="Filter by category"
          >
            <option value="ALL">All Categories</option>
            {ALL_CATEGORIES.filter((c) => categoriesPresent.has(c)).map((c) => (
              <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
            ))}
          </select>
          <select
            className="ac-input"
            style={{ width: 160 }}
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as AlertSeverity | "ALL")}
            aria-label="Filter by severity"
          >
            <option value="ALL">All Severities</option>
            {ALL_SEVERITIES.map((s) => (
              <option key={s} value={s}>{SEVERITY_BADGE[s].label}</option>
            ))}
          </select>
          {(categoryFilter !== "ALL" || severityFilter !== "ALL") && (
            <button className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { setCategoryFilter("ALL"); setSeverityFilter("ALL"); }}>
              Clear filters
            </button>
          )}
          <label className="ac-flex ac-items-center ac-gap-2 ac-text-sm" style={{ marginLeft: "auto" }}>
            <input type="checkbox" checked={hideResolved} onChange={(e) => setHideResolved(e.target.checked)} />
            Hide resolved
          </label>
        </div>
        <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0 0" }}>
          Acknowledge/resolve is local to this browser only (saved in localStorage) — it is not synced to a backend or
          any other device.
        </p>
      </div>

      {grouped.length === 0 ? (
        <div className="ac-card">
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No alerts match the current filters.</p>
        </div>
      ) : (
        grouped.map(({ category, alerts }) => (
          <section key={category} className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>
              {CATEGORY_LABELS[category]} <span className="ac-text-sm ac-text-muted">({alerts.length})</span>
            </h2>
            <div className="ac-card" style={{ padding: 0 }}>
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {alerts.map((a, idx) => {
                  const badge = SEVERITY_BADGE[a.severity];
                  const alertStatus = statusFor(a.id);
                  const handled = alertStatus !== "OPEN";
                  return (
                    <li
                      key={a.id}
                      style={{
                        borderTop: idx > 0 ? "1px solid var(--ac-border)" : undefined,
                        opacity: handled ? 0.55 : 1,
                        padding: "12px 16px",
                      }}
                    >
                      <div className="ac-flex ac-justify-between ac-items-start ac-gap-3">
                        <Link href={a.href} style={{ textDecoration: "none", color: "inherit", flex: 1 }}>
                          <span className="ac-text-sm" style={{ fontWeight: 600, display: "block", textDecoration: alertStatus === "RESOLVED" ? "line-through" : undefined }}>
                            {a.title}
                          </span>
                          <span className="ac-text-sm ac-text-muted">{a.message}</span>
                        </Link>
                        <span style={{ flexShrink: 0 }}>
                          <StatusBadge status={badge.status} label={badge.label} />
                        </span>
                      </div>
                      <div className="ac-flex ac-items-center ac-gap-2" style={{ marginTop: 8 }}>
                        {alertStatus === "OPEN" && (
                          <>
                            <button className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => acknowledge(a.id)}>
                              Acknowledge
                            </button>
                            <button className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => resolve(a.id)}>
                              Resolve
                            </button>
                          </>
                        )}
                        {alertStatus === "ACKNOWLEDGED" && (
                          <>
                            <span className="ac-text-sm ac-text-muted">Acknowledged (local only)</span>
                            <button className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => resolve(a.id)}>
                              Resolve
                            </button>
                            <button className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => reopen(a.id)}>
                              Reopen
                            </button>
                          </>
                        )}
                        {alertStatus === "RESOLVED" && (
                          <>
                            <span className="ac-text-sm ac-text-muted">Resolved (local only)</span>
                            <button className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => reopen(a.id)}>
                              Reopen
                            </button>
                          </>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
