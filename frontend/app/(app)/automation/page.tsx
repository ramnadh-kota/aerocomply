"use client";

import Link from "next/link";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getAutomationQueue } from "@/lib/mock/ai/analytics";
import type { AutomationQueueCategory } from "@/lib/mock/types";

// M14.2 — Automation Queue. A HUMAN-APPROVAL action queue, not an
// autonomous automation engine: every row is derived fresh from
// getAutomationQueue() (lib/mock/ai/analytics.ts), which itself only reads
// existing analytics (material readiness, safety gates, deferred items,
// quarantine, cannibalization, AOG, technician assignment). Nothing on this
// page executes an action — "Review" always routes to the existing
// workflow page where the actual, already-audited mutation lives.

const CATEGORY_LABEL: Record<AutomationQueueCategory, string> = {
  MATERIAL_BLOCKER: "Material Blocker",
  TECHNICIAN_RECOMMENDATION: "Technician Recommendation",
  AOG_ESCALATION: "AOG Escalation",
  RII_INSPECTOR_RECOMMENDATION: "RII Inspector Recommendation",
  QUARANTINE_REVIEW: "Quarantine Review",
  DEFERRED_ITEM_REVIEW: "Deferred Item Review",
  CANNIBALIZATION_REVIEW: "Cannibalization Review",
  SAFETY_GATE_FAILURE: "Safety Gate Failure",
  MISSING_EVIDENCE: "Missing Evidence",
  RELEASE_PACKAGE_INCOMPLETE: "Release Package Incomplete",
};

export default function AutomationQueuePage() {
  const queue = getAutomationQueue();
  const [filter, setFilter] = useState<AutomationQueueCategory | "ALL">("ALL");
  const filtered = filter === "ALL" ? queue : queue.filter((i) => i.category === filter);
  const categories = Array.from(new Set(queue.map((i) => i.category)));

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Automation Queue" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Automation Queue</h1>
          <p className="ac-subtitle">
            A human-approval action queue — every item is detected from existing analytics. Nothing here executes automatically;
            &quot;Review&quot; opens the existing workflow where the action is actually taken and audited.
          </p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <button className={`ac-btn ${filter === "ALL" ? "ac-btn-primary" : ""}`} style={{ padding: "2px 10px" }} onClick={() => setFilter("ALL")}>
            All ({queue.length})
          </button>
          {categories.map((c) => (
            <button key={c} className={`ac-btn ${filter === c ? "ac-btn-primary" : ""}`} style={{ padding: "2px 10px" }} onClick={() => setFilter(c)}>
              {CATEGORY_LABEL[c]} ({queue.filter((i) => i.category === c).length})
            </button>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <div className="ac-flex ac-flex-col ac-gap-3">
          {filtered.map((item) => (
            <div key={item.id} className="ac-card">
              <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10 }}>
                <div>
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
                    <StatusBadge status="REVIEW_REQUIRED" label={CATEGORY_LABEL[item.category]} />
                    <span className="ac-mono ac-text-sm">{item.source}</span>
                  </div>
                  <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>{item.title}</p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>{item.detection}</p>
                  <p className="ac-text-sm" style={{ margin: "0 0 2px" }}>Impact: {item.impact}</p>
                  <p className="ac-text-sm" style={{ margin: "0 0 2px" }}>Recommended: {item.recommendedAction}</p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Responsible: {item.responsibleRole} · Approval required before any action.</p>
                </div>
                <Link href={item.destinationHref} className="ac-btn ac-btn-primary" style={{ alignSelf: "flex-start" }}>Review →</Link>
              </div>
            </div>
          ))}
          {filtered.length === 0 && <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No items in this category.</p></div>}
        </div>
      </section>
    </div>
  );
}
