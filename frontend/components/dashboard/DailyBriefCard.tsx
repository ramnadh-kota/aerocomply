"use client";

import Link from "next/link";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { getDailyBrief } from "@/lib/mock/ai/proactive";
import { AI_NAME } from "@/lib/brand";

// Client boundary so the Daily Brief can react to the "Viewing as" role
// simulation (see Topbar.tsx / RoleSimContext.tsx) the same way the Topbar's
// notification panel and the AI console's "Lisa noticed…" strip already do —
// getDailyBrief() already accepted an optional roleId, it just wasn't wired
// through here yet. Relevance-only reordering, same as everywhere else this
// simulation touches; never hides or fabricates a priority.
export function DailyBriefCard() {
  const { roleId } = useRoleSim();
  const dailyBrief = getDailyBrief(4, roleId);

  return (
    <div className="ac-card" style={{ borderColor: "var(--ac-accent)" }}>
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>{AI_NAME}&apos;s Daily Brief — Good Morning</p>
        <span className="ac-text-sm ac-text-muted">As of {dailyBrief.generatedAt}</span>
      </div>
      <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 10px" }}>
        Fleet: {dailyBrief.fleet.aircraftCount} aircraft · {dailyBrief.fleet.aogCount} AOG · {dailyBrief.fleet.maintenanceDueCount} under maintenance · {dailyBrief.fleet.tatAtRiskCount} TAT at risk
      </p>
      {dailyBrief.topPriorities.length > 0 && (
        <>
          <p className="ac-text-sm" style={{ margin: "0 0 6px", fontWeight: 600 }}>Top priorities</p>
          <ul style={{ margin: "0 0 10px", padding: 0, listStyle: "none" }}>
            {dailyBrief.topPriorities.map((a) => (
              <li key={a.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                <Link href={a.href} className="ac-flex ac-items-center ac-gap-2" style={{ fontSize: 13 }}>
                  <span aria-hidden="true" style={{ color: "var(--ac-status-review)" }}>⚠</span>
                  <span style={{ fontWeight: 600 }}>{a.title}</span>
                  <span className="ac-text-muted">— {a.message}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
        Procurement: {dailyBrief.procurement.criticalPartsCount} critical part(s) out of stock · Compliance: {dailyBrief.compliance.recentRegulatoryCount} recent regulatory record(s)
      </p>
      <div className="ac-flex ac-gap-2" style={{ marginTop: 10 }}>
        <Link href="/ai" className="ac-btn ac-btn-primary">Ask {AI_NAME}</Link>
      </div>
    </div>
  );
}
