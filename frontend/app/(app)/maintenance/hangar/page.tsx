"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, workOrderStatusBadge, checklistResultBadge } from "@/components/status/StatusBadge";
import { workOrders, isOverdue } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { defectsForWorkOrder } from "@/lib/mock/defects";
import { getPartById } from "@/lib/mock/parts";
import { getInspectorReviewById } from "@/lib/mock/inspectorReviews";
import { getTechnicianWorkload } from "@/lib/mock/ai/analytics";
import { useMroState } from "@/lib/mro-state/MroStateContext";

export default function HangarFloorPage() {
  const { submissions } = useMroState();

  // "Under maintenance" = any aircraft with a work order that is not
  // COMPLETED/CANCELLED — same definition used by getOperationsAnalytics,
  // computed inline here since we need the underlying work orders too.
  const activeWos = workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED");
  const aircraftIds = Array.from(new Set(activeWos.map((w) => w.aircraftId)));

  const cards = activeWos.map((wo) => {
    const aircraft = getAircraftById(wo.aircraftId);
    const technician = wo.assignedTechnicianId ? getTechnicianById(wo.assignedTechnicianId) : undefined;
    const checklist = getChecklistByWorkOrderId(wo.id);
    const record = submissions[wo.id];
    const items = record ? Object.values(record.items) : [];
    const completed = items.filter((i) => i.result !== null).length;
    const progressPercent = items.length > 0 ? Math.round((completed / items.length) * 100) : null;
    const unknownCount = items.filter((i) => i.result === "UNKNOWN").length;
    const openDefects = defectsForWorkOrder(wo.id).filter((d) => d.status === "OPEN");
    const unresolvedPart = wo.requiredPartIds.map((id) => getPartById(id)).find((p) => p && p.status !== "IN_STOCK");
    const review = wo.inspectorReviewId ? getInspectorReviewById(wo.inspectorReviewId) : undefined;

    let nextAction = "Awaiting technician assignment.";
    if (technician) {
      if (wo.status === "WAITING_PARTS" && unresolvedPart) nextAction = `Waiting on part ${unresolvedPart.partNumber}.`;
      else if (unknownCount > 0) nextAction = `Resolve ${unknownCount} UNKNOWN checklist item(s).`;
      else if (record?.submissionStatus === "IN_PROGRESS") nextAction = "Continue checklist execution.";
      else if (review?.status === "PENDING_INSPECTION") nextAction = "Awaiting inspector decision.";
      else if (record?.submissionStatus === "SUBMITTED") nextAction = "Submitted — awaiting next step.";
      else nextAction = "Begin checklist execution.";
    }

    const tatRisk: "LOW" | "MEDIUM" | "HIGH" = isOverdue(wo) ? "HIGH" : wo.priority === "HIGH" || wo.priority === "CRITICAL" ? "MEDIUM" : "LOW";

    return { wo, aircraft, technician, checklist, record, progressPercent, unknownCount, openDefects, unresolvedPart, nextAction, tatRisk };
  });

  const blockedTasks = cards.filter((c) => c.unknownCount > 0);
  const waitingParts = cards.filter((c) => c.wo.status === "WAITING_PARTS");
  const waitingInspection = cards.filter((c) => c.wo.status === "WAITING_INSPECTION");
  const overdueCards = cards.filter((c) => isOverdue(c.wo));
  const evidenceGaps = cards.filter((c) => c.record && Object.values(c.record.items).some((i) => i.result === "FAIL" && !i.evidenceAttached));
  const workload = getTechnicianWorkload().filter((t) => t.openWorkOrders > 0);
  const bottleneckTechs = workload.filter((t) => t.openWorkOrders > 1);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Hangar Floor" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Hangar Floor</h1>
          <p className="ac-subtitle">{aircraftIds.length} aircraft under maintenance · {activeWos.length} active work order(s). Technician execution view.</p>
        </div>
        <Link href="/maintenance/operations" className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Operations Command Center →</Link>
      </div>

      {/* M3.6 — Hangar Risk Board */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Hangar Risk Board</h2>
        <div className="ac-kpi-grid">
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Blocked (UNKNOWN)</p>
            <p className="ac-kpi-value">{blockedTasks.length}</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Overdue</p>
            <p className="ac-kpi-value">{overdueCards.length}</p>
          </Link>
          <Link href="/maintenance/parts" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Waiting Parts</p>
            <p className="ac-kpi-value">{waitingParts.length}</p>
          </Link>
          <Link href="/maintenance/inspections" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Waiting Inspection</p>
            <p className="ac-kpi-value">{waitingInspection.length}</p>
          </Link>
          <Link href="/maintenance/defects" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Evidence Gaps</p>
            <p className="ac-kpi-value">{evidenceGaps.length}</p>
          </Link>
          <Link href="/maintenance/planning" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Technician Bottlenecks</p>
            <p className="ac-kpi-value">{bottleneckTechs.length}</p>
          </Link>
        </div>
      </section>

      {/* M3.0 / M3.1 — Digital Task Cards, one per active work order */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Active Work — Task Cards</h2>
        {cards.length === 0 ? (
          <p className="ac-text-sm ac-text-muted">Insufficient source data.</p>
        ) : (
          <div className="ac-grid-2">
            {cards.map(({ wo, aircraft, technician, checklist, progressPercent, unknownCount, openDefects, unresolvedPart, nextAction, tatRisk }) => (
              <div key={wo.id} className="ac-card">
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                  <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-mono" style={{ fontWeight: 600 }}>{wo.workOrderNumber}</Link>
                  <div className="ac-flex ac-gap-2">
                    <StatusBadge {...priorityBadge(wo.priority)} />
                    <StatusBadge {...workOrderStatusBadge(wo.status)} />
                  </div>
                </div>
                <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>{wo.title}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 6px" }}>
                  Aircraft: {aircraft ? <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{currentRegistration(aircraft)}</Link> : wo.aircraftId}
                  {" · "}Technician: {technician ? <Link href={`/maintenance/technicians/${technician.id}`}>{technician.name}</Link> : "Unassigned"}
                </p>

                {checklist ? (
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 6 }}>
                    <div style={{ width: 100, height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
                      <div style={{ width: `${progressPercent ?? 0}%`, height: "100%", background: "var(--ac-accent)" }} />
                    </div>
                    <span className="ac-text-sm ac-text-muted">{progressPercent === null ? "—" : `${progressPercent}%`} checklist</span>
                    {unknownCount > 0 && <StatusBadge {...checklistResultBadge("UNKNOWN")} label={`${unknownCount} UNKNOWN`} />}
                  </div>
                ) : (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 6px" }}>No checklist attached — Insufficient source data.</p>
                )}

                <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 6 }}>
                  {unresolvedPart && <span className="ac-badge ac-badge-review_required">Blocked: part {unresolvedPart.partNumber}</span>}
                  {openDefects.length > 0 && <span className="ac-badge ac-badge-non_compliant">{openDefects.length} open defect(s)</span>}
                  <StatusBadge status={tatRisk === "HIGH" ? "NON_COMPLIANT" : tatRisk === "MEDIUM" ? "REVIEW_REQUIRED" : "COMPLIANT"} label={`TAT Risk: ${tatRisk}`} />
                </div>

                <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600, color: "var(--ac-status-review)" }}>Next: {nextAction}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
