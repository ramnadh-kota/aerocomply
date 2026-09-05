"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { Timeline } from "@/components/timeline/Timeline";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { verifyAuditChain } from "@/lib/mock/audit";

function actorKind(actorRole: string, actor: string): "AI" | "SYSTEM" | "HUMAN" {
  if (actor.toLowerCase().includes("ai") || actorRole.toLowerCase().includes("ai")) return "AI";
  if (actorRole === "SYSTEM" || actor.toLowerCase().includes("rules engine")) return "SYSTEM";
  return "HUMAN";
}

export default function AuditTrailPage() {
  const { auditLog } = useMroState();
  const chainVerification = verifyAuditChain();
  const [actorFilter, setActorFilter] = useState("ALL");
  const [actionFilter, setActionFilter] = useState("ALL");
  const [sourceFilter, setSourceFilter] = useState("ALL");

  const actors = useMemo(() => Array.from(new Set(auditLog.map((e) => e.actor))).sort(), [auditLog]);
  const actionCategories = useMemo(() => Array.from(new Set(auditLog.map((e) => e.action.split(".")[0]))).sort(), [auditLog]);

  const filtered = auditLog.filter((e) => {
    if (actorFilter !== "ALL" && e.actor !== actorFilter) return false;
    if (actionFilter !== "ALL" && !e.action.startsWith(actionFilter)) return false;
    if (sourceFilter !== "ALL" && actorKind(e.actorRole, e.actor) !== sourceFilter) return false;
    return true;
  });

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Audit Trail" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Audit Trail</h1>
          <p className="ac-subtitle">
            {filtered.length} of {auditLog.length} events shown · compliance events are append-only, matching the
            DB-level immutability trigger shipped in M0. MRO/AI/role-simulation events shown here are prototype,
            in-memory events for this session only — not yet backend-persisted.
          </p>
        </div>
      </div>

      <div className="ac-card ac-section">
        <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 6 }}>
          <StatusBadge status={chainVerification.status === "VALID" ? "COMPLIANT" : chainVerification.status === "BROKEN" ? "NON_COMPLIANT" : "INSUFFICIENT_DATA"} label={`Ledger: ${chainVerification.status}`} />
        </div>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          {chainVerification.note} This is a prototype hash chain over the seeded compliance audit events only (M20) — a
          checksum for internal consistency, not a cryptographic or legally compliant electronic record.
        </p>
      </div>

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap" }}>
          <select className="ac-input" style={{ width: 200 }} value={actorFilter} onChange={(e) => setActorFilter(e.target.value)} aria-label="Filter by actor">
            <option value="ALL">All Actors</option>
            {actors.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select className="ac-input" style={{ width: 200 }} value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} aria-label="Filter by action">
            <option value="ALL">All Action Types</option>
            {actionCategories.map((a) => <option key={a} value={a}>{a.replace(/_/g, " ")}</option>)}
          </select>
          <select className="ac-input" style={{ width: 160 }} value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} aria-label="Filter by source">
            <option value="ALL">Human + AI + System</option>
            <option value="HUMAN">Human Only</option>
            <option value="AI">AI Only</option>
            <option value="SYSTEM">System Only</option>
          </select>
        </div>
      </div>

      <div className="ac-card">
        <Timeline
          entries={filtered.map((e) => {
            const kind = actorKind(e.actorRole, e.actor);
            return {
              id: e.id,
              date: new Date(e.timestamp).toLocaleString(),
              title: (
                <span>
                  {e.action.replace(/_/g, " ").replace(/\./g, " — ")}
                  <span className="ac-text-sm ac-text-muted"> · {e.objectType}</span>{" "}
                  <StatusBadge status={kind === "AI" ? "INSUFFICIENT_DATA" : kind === "SYSTEM" ? "UNKNOWN" : "ACTIVE"} label={kind} />
                </span>
              ),
              detail: (
                <span>
                  <strong>{e.actor}</strong> ({e.actorRole}) — {e.objectLabel}
                  {e.previousState && e.newState && (
                    <span className="ac-mono ac-text-sm">
                      {" "}
                      · {e.previousState} → {e.newState}
                    </span>
                  )}
                  {e.reason && <div className="ac-text-sm ac-text-secondary" style={{ marginTop: 2 }}>Reason: {e.reason}</div>}
                  {e.relatedAssessmentId && (
                    <div className="ac-text-sm" style={{ marginTop: 2 }}>
                      <Link href={`/assessments/${e.relatedAssessmentId}`} className="ac-mono">View assessment →</Link>
                    </div>
                  )}
                </span>
              ),
            };
          })}
        />
      </div>
    </div>
  );
}
