"use client";

import Link from "next/link";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { getOperationalPriorities, type OperationalPriorityTier, type AlertCategory } from "@/lib/mock/ai/proactive";
import { getWorkOrderTatStatus } from "@/lib/mock/ai/analytics";
import { StatusBadge } from "@/components/status/StatusBadge";
import { AI_NAME } from "@/lib/brand";

// Renders the FULL ranked list from getOperationalPriorities() — the same
// P0-P3 tiered, explainable priority engine that already powers Lisa's
// "what should I do next?" answers and the Daily Brief card's top-N slice.
// This component is the deeper, complete view: every item, not just the
// top few, plus a TAT cross-reference for any work-order-scoped item. It
// never recomputes severity, tier, or blocker reason — those are read
// verbatim from the engine's output.

const TIER_BADGE: Record<OperationalPriorityTier, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  P0: { status: "NON_COMPLIANT", label: "P0 · Critical" },
  P1: { status: "REVIEW_REQUIRED", label: "P1 · High" },
  P2: { status: "PENDING", label: "P2 · Medium" },
  P3: { status: "UNKNOWN", label: "P3 · Low" },
};

const TAT_BADGE: Record<string, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  ON_TRACK: { status: "COMPLIANT", label: "TAT On Track" },
  AT_RISK: { status: "REVIEW_REQUIRED", label: "TAT At Risk" },
  DELAYED: { status: "NON_COMPLIANT", label: "TAT Delayed" },
  UNKNOWN: { status: "UNKNOWN", label: "TAT Unknown" },
};

// Presentational-only label mapping from the real alert `category` (already
// computed by getProactiveAlerts) to the role that would typically act on
// it — mirrors the same category groupings ROLE_ALERT_CATEGORY_PRIORITY in
// lib/mock/ai/proactive.ts already uses for relevance ordering. This never
// changes which items appear or their rank; it only labels who should act.
const OWNER_BY_CATEGORY: Record<AlertCategory, string> = {
  AOG: "Maintenance Manager",
  TAT: "Maintenance Planner",
  EVIDENCE: "Technician",
  RII: "Inspector",
  AUTHORIZATION: "Maintenance Planner",
  PART: "Procurement",
  VENDOR: "Procurement",
  REGULATORY: "Compliance Manager",
  RELEASE: "Maintenance Manager",
};

export function OperationalPriorityQueue() {
  const { roleId } = useRoleSim();
  const priorities = getOperationalPriorities(roleId);

  return (
    <div className="ac-card">
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>What Needs Attention Now</p>
        <span className="ac-text-sm ac-text-muted">{priorities.length} item(s) · ranked by {AI_NAME}&apos;s priority engine</span>
      </div>
      {priorities.length === 0 ? (
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Nothing requires attention right now.</p>
      ) : (
        <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
          {priorities.map((item, idx) => {
            const tatAssessment = item.relatedEntity.type === "WORK_ORDER" ? getWorkOrderTatStatus(item.relatedEntity.id) : null;
            return (
              <li
                key={`${item.relatedEntity.type}-${item.relatedEntity.id}-${idx}`}
                style={{ padding: "10px 0", borderBottom: idx < priorities.length - 1 ? "1px solid var(--ac-border-subtle)" : "none" }}
              >
                <Link href={item.href} className="ac-flex ac-flex-col ac-gap-2" style={{ fontSize: 13 }}>
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap" }}>
                    <StatusBadge {...TIER_BADGE[item.tier]} />
                    {tatAssessment && <StatusBadge {...TAT_BADGE[tatAssessment.status]} />}
                    <span style={{ fontWeight: 600 }}>{item.title}</span>
                  </div>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{item.reason}</p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    Owner: {OWNER_BY_CATEGORY[item.category]} · {item.relatedEntity.type.replace(/_/g, " ")} {item.relatedEntity.id}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
