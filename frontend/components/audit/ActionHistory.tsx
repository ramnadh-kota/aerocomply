"use client";

import { useState } from "react";
import Link from "next/link";
import type { AuditEvent } from "@/lib/mock/types";

// M12.7 — Maintenance Traceability & Action History. A presentational
// component only: it renders whatever AuditEvent[] it's given (from the ONE
// existing audit system — lib/mock/audit.ts + useMroState().auditLog) and
// never computes history itself. No second event store.

function actionTitle(action: string): string {
  return action.split(".").slice(1).join(" ").replace(/_/g, " ").toUpperCase() || action.toUpperCase();
}

/** Evidence bullets are derived ONLY from fields the event itself recorded
 * (previousState/newState/reason) — never reconstructed from current state
 * or invented. */
function deriveEvidence(event: AuditEvent): string[] {
  const bullets: string[] = [];
  if (event.previousState !== null || event.newState !== null) {
    bullets.push(`Recorded change: ${event.previousState ?? "Unassigned/none"} → ${event.newState ?? "Unassigned/none"}`);
  }
  if (event.reason) bullets.push(`Reason on file: ${event.reason}`);
  return bullets.length > 0 ? bullets : ["Insufficient source data."];
}

export interface ActionHistoryLink {
  label: string;
  href: string;
}

export function ActionHistory({
  events,
  emptyMessage = "No recorded actions.",
  linkFor,
}: {
  events: AuditEvent[];
  emptyMessage?: string;
  linkFor?: (event: AuditEvent) => ActionHistoryLink | null;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (events.length === 0) {
    return <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{emptyMessage}</p>;
  }

  return (
    <div className="ac-flex ac-flex-col ac-gap-2">
      {events.map((e) => {
        const isOpen = openId === e.id;
        const link = linkFor?.(e) ?? null;
        return (
          <div key={e.id} className="ac-card" style={{ padding: 10 }}>
            <button
              onClick={() => setOpenId(isOpen ? null : e.id)}
              style={{ background: "none", border: "none", padding: 0, width: "100%", textAlign: "left", cursor: "pointer" }}
            >
              <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 8 }}>
                <span className="ac-text-sm" style={{ fontWeight: 600 }}>{actionTitle(e.action)}</span>
                <span className="ac-text-sm ac-text-muted">{e.timestamp}</span>
              </div>
              <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>{e.actor} · {e.objectLabel}</p>
            </button>
            {isOpen && (
              <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--ac-border)" }}>
                <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", fontSize: 13 }}>
                  <dt className="ac-text-muted">Action</dt><dd style={{ margin: 0 }}>{e.action}</dd>
                  <dt className="ac-text-muted">Actor</dt><dd style={{ margin: 0 }}>{e.actor} {e.actorRole ? `(${e.actorRole})` : ""}</dd>
                  <dt className="ac-text-muted">Timestamp</dt><dd style={{ margin: 0 }}>{e.timestamp}</dd>
                  <dt className="ac-text-muted">Entity</dt><dd style={{ margin: 0 }}>{e.objectType}</dd>
                  <dt className="ac-text-muted">Entity ID</dt><dd style={{ margin: 0 }}>{e.objectLabel}</dd>
                  <dt className="ac-text-muted">Before</dt><dd style={{ margin: 0 }}>{e.previousState ?? "Not recorded."}</dd>
                  <dt className="ac-text-muted">After</dt><dd style={{ margin: 0 }}>{e.newState ?? "Not recorded."}</dd>
                  <dt className="ac-text-muted">Reason</dt><dd style={{ margin: 0 }}>{e.reason ?? "Reason not recorded."}</dd>
                  <dt className="ac-text-muted">Source</dt><dd style={{ margin: 0 }}>{e.actorRole === "SYSTEM" ? "System" : e.actorRole === "AI Assistant" ? "AI Assistant" : e.action.startsWith("maintenance.") ? "Maintenance Execution" : e.actorRole}</dd>
                </dl>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0 0" }}>Evidence:</p>
                <ul style={{ margin: "2px 0 0", paddingLeft: 18, fontSize: 13 }}>
                  {deriveEvidence(e).map((ev) => <li key={ev}>{ev}</li>)}
                </ul>
                {link && (
                  <Link href={link.href} className="ac-btn" style={{ marginTop: 10, display: "inline-block" }}>
                    {link.label}
                  </Link>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
