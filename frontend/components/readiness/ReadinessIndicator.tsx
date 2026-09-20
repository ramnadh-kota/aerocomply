// Shared readiness/blocker-list primitive. Two call sites rendered the same
// underlying concept (a READY/BLOCKED status badge plus a list of blockers,
// some linking through to a Finding) with independently hand-rolled markup
// and slightly different data shapes:
//   - frontend/app/(app)/drones/[id]/page.tsx (Deployment Readiness section):
//     `readiness.blockers: string[]` plus a parallel `finding_blockers[]`
//     matched by index.
//   - frontend/components/evidence/RealReleaseReadinessPanel.tsx:
//     `readiness.blockers: { category, description, related_record_id }[]`.
// This component does not change either backend response shape or any
// existing blocker category/status semantics (READY/BLOCKED, or the
// FINDING/MATERIAL/COMPLIANCE/EVIDENCE/INSPECTION/TASK_EXECUTION blocker
// categories) -- callers normalize their own real API response into the
// `ReadinessBlocker[]` shape below before rendering.

import type { ReactNode } from "react";
import { StatusBadge, type BadgeKind } from "@/components/status/StatusBadge";

export interface ReadinessBlocker {
  key: string;
  label: ReactNode;
  href?: string;
}

export function readinessStatusBadge(status: string): { status: BadgeKind; label: string } {
  if (status === "READY") return { status: "COMPLIANT", label: "Ready" };
  if (status === "BLOCKED") return { status: "NON_COMPLIANT", label: "Blocked" };
  return { status: "UNKNOWN", label: status };
}

export function ReadinessIndicator({
  status,
  blockers,
  footer,
}: {
  status: string;
  blockers: ReadinessBlocker[];
  footer?: ReactNode;
}) {
  return (
    <div>
      <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: blockers.length ? 8 : 0, flexWrap: "wrap" }}>
        <StatusBadge {...readinessStatusBadge(status)} />
        {blockers.length > 0 && (
          <span className="ac-text-sm ac-text-muted">
            {blockers.length} blocker{blockers.length === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {blockers.length > 0 && (
        <ul style={{ margin: "8px 0 10px", paddingLeft: 18 }}>
          {blockers.map((b) => (
            <li key={b.key} className="ac-text-sm" style={{ marginBottom: 6 }}>
              {b.href ? <a href={b.href}>{b.label}</a> : b.label}
            </li>
          ))}
        </ul>
      )}
      {footer && (
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          {footer}
        </p>
      )}
    </div>
  );
}
