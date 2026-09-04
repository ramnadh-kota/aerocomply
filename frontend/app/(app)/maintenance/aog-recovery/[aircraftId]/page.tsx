"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getAircraftRecoveryPlan } from "@/lib/mock/ai/analytics";
import { workOrderRepository } from "@/lib/domain/repositories";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { combinedAuditHistory } from "@/lib/mock/audit";
import { ActionHistory } from "@/components/audit/ActionHistory";

// M14.1 — AOG Recovery detail view. Read-only analysis (getAogRecoveryAnalysis,
// lib/mock/ai/analytics.ts) plus ONE human-approved action: escalating the
// primary blocking work order via the existing escalateWorkOrder mutation.
// This page never auto-executes anything — every recovery option listed is a
// link to an existing workflow (Material Readiness, Planning) or requires the
// explicit button click below, which is itself audited.

export default function AogRecoveryPage() {
  const params = useParams<{ aircraftId: string }>();
  const aircraftId = params.aircraftId;
  const [version, setVersion] = useState(0);
  const { addAuditEvent, auditLog } = useMroState();
  const current = getCurrentUser();
  void version;

  const analysis = getAircraftRecoveryPlan(aircraftId);

  if (!analysis) {
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Control Tower", href: "/maintenance/control-tower" }, { label: "AOG Recovery" }]} />
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Aircraft not found.</p></div>
      </div>
    );
  }

  const escalatePrimary = () => {
    const wo = analysis.criticalWorkOrders[0];
    if (!wo) return;
    const updated = workOrderRepository.escalateWorkOrder(wo.workOrderId);
    if (!updated) return;
    addAuditEvent({
      actor: current?.user.name ?? "Unknown User",
      actorRole: "Maintenance",
      action: "maintenance.work_order_escalated",
      objectType: "WorkOrder",
      objectLabel: wo.workOrderNumber,
      previousState: null,
      newState: "CRITICAL",
      reason: `AOG recovery escalation for ${analysis.registration} — primary blocker: ${analysis.primaryBlocker?.description ?? "unspecified"}`,
    });
    setVersion((v) => v + 1);
  };

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Control Tower", href: "/maintenance/control-tower" }, { label: `${analysis.registration} Recovery` }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">AOG Recovery — {analysis.registration}</h1>
          <p className="ac-subtitle">
            Every figure below is read from the same analytics the Control Tower, Planning, and Material Readiness pages use — no
            recovery action is taken automatically.
          </p>
        </div>
        <StatusBadge status={analysis.isAog ? "NON_COMPLIANT" : "COMPLIANT"} label={analysis.isAog ? "AOG" : "NOT AOG"} />
      </div>

      {!analysis.isAog ? (
        <div className="ac-card"><p className="ac-text-sm" style={{ margin: 0 }}>This aircraft is not currently derived as AOG.</p></div>
      ) : (
        <>
          <section className="ac-section">
            <div className="ac-card">
              <p className="ac-eyebrow" style={{ marginBottom: 6 }}>AOG Reason</p>
              <p className="ac-text-sm" style={{ margin: "0 0 10px" }}>{analysis.aogReason ?? "Insufficient source data."}</p>
              <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Critical / High-Priority Work Orders</p>
              <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
                {analysis.criticalWorkOrders.map((w) => (
                  <li key={w.workOrderId}><Link href={`/maintenance/planning/${w.workOrderId}`} className="ac-mono">{w.workOrderNumber}</Link> — {w.title}</li>
                ))}
                {analysis.criticalWorkOrders.length === 0 && <li>None recorded.</li>}
              </ul>
              <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Data Completeness: {analysis.dataCompleteness}</p>
            </div>
          </section>

          {analysis.workOrderDetails.length > 0 && (
            <section className="ac-section">
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recovery Path — Work Order Readiness</h2>
              <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
                Release readiness, technician authorization, and independent-inspection status for each critical work order —
                the same canonical engines used on the Task Card and Release Readiness dashboard, read together here to show
                what stands between this aircraft and recovery.
              </p>
              <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
                <table className="ac-table">
                  <thead><tr><th>Work Order</th><th>Release Readiness</th><th>Authorized Technicians</th><th>Inspection (RII)</th></tr></thead>
                  <tbody>
                    {analysis.workOrderDetails.map((d) => (
                      <tr key={d.workOrderId}>
                        <td><Link href={`/maintenance/planning/${d.workOrderId}`} className="ac-mono">{d.workOrderNumber}</Link></td>
                        <td>
                          <StatusBadge
                            status={d.releaseReadiness.status === "READY" ? "COMPLIANT" : d.releaseReadiness.status === "BLOCKED" ? "NON_COMPLIANT" : "INSUFFICIENT_DATA"}
                            label={d.releaseReadiness.status}
                          />
                          {d.releaseReadiness.blockers.length > 0 && (
                            <span className="ac-text-sm ac-text-muted"> — {d.releaseReadiness.blockers.length} blocker{d.releaseReadiness.blockers.length === 1 ? "" : "s"}</span>
                          )}
                        </td>
                        <td className="ac-text-sm">{d.authorizedTechnicianCount === 0 ? <span style={{ color: "var(--ac-status-non-compliant)" }}>None authorized</span> : d.authorizedTechnicianCount}</td>
                        <td>
                          <StatusBadge
                            status={d.inspection === "NOT_REQUIRED" || d.inspection === "READY" || d.inspection === "COMPLETED" ? "COMPLIANT" : d.inspection === "BLOCKED" ? "NON_COMPLIANT" : "INSUFFICIENT_DATA"}
                            label={d.inspection.replace(/_/g, " ")}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <div className="ac-grid-2 ac-section">
            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Primary Blocker</h2>
              <div className="ac-card">
                {analysis.primaryBlocker ? (
                  <>
                    <StatusBadge status="NON_COMPLIANT" label={analysis.primaryBlocker.type} />
                    <p className="ac-text-sm" style={{ margin: "8px 0 4px" }}>{analysis.primaryBlocker.description}</p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Source: {analysis.primaryBlocker.source}</p>
                  </>
                ) : (
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No specific blocker identified from current source data — investigate manually.</p>
                )}
              </div>

              {analysis.secondaryBlockers.length > 0 && (
                <>
                  <p className="ac-eyebrow" style={{ margin: "16px 0 6px" }}>Secondary Blockers</p>
                  <div className="ac-card" style={{ padding: 0 }}>
                    <table className="ac-table">
                      <thead><tr><th>Type</th><th>Description</th><th>Source</th></tr></thead>
                      <tbody>
                        {analysis.secondaryBlockers.map((b, i) => (
                          <tr key={i}><td>{b.type}</td><td className="ac-text-sm">{b.description}</td><td className="ac-text-sm">{b.source}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </section>

            <section>
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recovery Options (Human Approval Required)</h2>
              <div className="ac-card" style={{ padding: 0 }}>
                <table className="ac-table">
                  <thead><tr><th>Action</th><th>Responsible Role</th><th></th></tr></thead>
                  <tbody>
                    {analysis.recoveryOptions.map((o, i) => (
                      <tr key={i}>
                        <td className="ac-text-sm">{o.action}</td>
                        <td className="ac-text-sm">{o.responsibleRole}</td>
                        <td>{o.href && <Link href={o.href} className="ac-btn" style={{ padding: "2px 8px" }}>Open</Link>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {analysis.criticalWorkOrders.length > 0 && (
                <button className="ac-btn ac-btn-primary" style={{ marginTop: 10 }} onClick={escalatePrimary}>
                  Escalate {analysis.criticalWorkOrders[0].workOrderNumber} to Maintenance Manager
                </button>
              )}
            </section>
          </div>
        </>
      )}

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recovery-Related History</h2>
        <ActionHistory
          events={analysis.criticalWorkOrders[0] ? combinedAuditHistory(analysis.criticalWorkOrders[0].workOrderNumber, auditLog) : []}
          emptyMessage="No recorded actions yet."
        />
      </section>
    </div>
  );
}
