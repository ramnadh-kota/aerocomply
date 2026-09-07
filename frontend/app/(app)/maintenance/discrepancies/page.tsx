"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, defectStatusBadge } from "@/components/status/StatusBadge";
import { PLATFORM_AI_NAME, PLATFORM_NAME } from "@/lib/brand";
import { getDiscrepancyGroups, getDiscrepancyGroupAnalysis } from "@/lib/mock/ai/analytics";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";

// M12.2 — AI Discrepancy Intelligence. "Discrepancy" is the existing Defect
// entity (lib/mock/defects.ts) grouped by ATA chapter — no new entity, no
// second AI engine. Grouping/analysis logic lives in
// lib/mock/ai/analytics.ts (getDiscrepancyGroups/getDiscrepancyGroupAnalysis)
// so this page and Lisa's recurring-discrepancy answers share one source.

export default function DiscrepancyIntelligencePage() {
  const [openChapter, setOpenChapter] = useState<string | null>(null);
  const { addAuditEvent } = useMroState();
  const current = getCurrentUser();

  const groups = useMemo(() => getDiscrepancyGroups(), []);

  function investigate(ataChapter: string) {
    const opening = openChapter !== ataChapter;
    setOpenChapter(opening ? ataChapter : null);
    if (opening) {
      addAuditEvent({
        actor: current?.user.name ?? "Unknown User",
        actorRole: "Maintenance",
        action: "maintenance.discrepancy_reviewed",
        objectType: "DiscrepancyGroup",
        objectLabel: `ATA ${ataChapter}`,
        previousState: null,
        newState: "REVIEWED",
      });
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/operations" }, { label: "Discrepancy Intelligence" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">AI Discrepancy Intelligence</h1>
          <p className="ac-subtitle">
            Open defects grouped by ATA chapter to surface recurring patterns. This demo dataset has a small number of seeded defects, so
            group sizes are real but modest — nothing here is inflated to look more dramatic than the source data.
          </p>
        </div>
        <Link href="/maintenance/defects" className="ac-btn">View All Defects</Link>
      </div>

      <section className="ac-section">
        <div className="ac-flex ac-flex-col ac-gap-3">
          {groups.map((g) => {
            const isOpen = openChapter === g.ataChapter;
            return (
              <div key={g.ataChapter} className="ac-card">
                <div className="ac-flex ac-justify-between" style={{ flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <p className="ac-mono" style={{ fontWeight: 700, margin: 0 }}>ATA {g.ataChapter}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      {g.occurrences} occurrence{g.occurrences === 1 ? "" : "s"} · {g.aircraftCount} aircraft ·{" "}
                      {g.recurringAircraftCount} recurring · {g.highSeverityCount} high severity
                    </p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      First: {g.firstOccurrence} · Latest: {g.latestOccurrence} · Open {g.openCount} / Deferred {g.deferredCount} / Resolved {g.resolvedCount}
                    </p>
                  </div>
                  <button className="ac-btn ac-btn-primary" onClick={() => investigate(g.ataChapter)}>
                    {isOpen ? "Close" : "Investigate"}
                  </button>
                </div>

                {isOpen && (
                  <div className="ac-card" style={{ marginTop: 12, background: "var(--ac-bg-surface-hover)" }}>
                    <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Affected Aircraft</p>
                    <ul style={{ margin: "0 0 12px", paddingLeft: 18, fontSize: 13 }}>
                      {g.aircraftIds.map((id) => {
                        const a = getAircraftById(id);
                        return <li key={id}>{a ? <Link href={`/aircraft/${a.id}`}>{currentRegistration(a)}</Link> : id}</li>;
                      })}
                    </ul>

                    <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Occurrences</p>
                    <table className="ac-table" style={{ marginBottom: 12 }}>
                      <thead><tr><th>Aircraft</th><th>Date</th><th>Severity</th><th>Status</th><th>Work Order</th><th>Description</th></tr></thead>
                      <tbody>
                        {g.defects.map((d) => {
                          const a = getAircraftById(d.aircraftId);
                          const badge = defectStatusBadge(d.status);
                          return (
                            <tr key={d.id}>
                              <td>{a ? currentRegistration(a) : d.aircraftId}</td>
                              <td>{d.reportedDate}</td>
                              <td>{d.severity}</td>
                              <td><StatusBadge status={badge.status} label={badge.label} /></td>
                              <td>{d.workOrderId ? <Link href={`/maintenance/work-orders/${d.workOrderId}`} className="ac-mono">{d.workOrderId}</Link> : "—"}</td>
                              <td className="ac-text-sm">{d.description}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>

                    <p className="ac-eyebrow" style={{ marginBottom: 6 }}>{PLATFORM_AI_NAME}&apos;s Analysis</p>
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                      {getDiscrepancyGroupAnalysis(g.ataChapter).map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
          {groups.length === 0 && <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No defects recorded in the current demo dataset.</p></div>}
        </div>
      </section>
    </div>
  );
}
