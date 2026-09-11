"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getAircraftRecoveryPlan, getWorkOrderTatStatus, type TatStatus, type AogBlocker, type AogBlockerType } from "@/lib/mock/ai/analytics";
import { workOrderRepository } from "@/lib/domain/repositories";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { combinedAuditHistory } from "@/lib/mock/audit";
import { ActionHistory } from "@/components/audit/ActionHistory";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { aircraftApi } from "@/lib/api/aircraft";
import { aogRecoveryApi, type BackendAogRecoveryStatus, type BackendCriticalPathStage } from "@/lib/api/aogRecovery";

// M14.1 — AOG Recovery detail view. Read-only analysis (getAogRecoveryAnalysis,
// lib/mock/ai/analytics.ts) plus ONE human-approved action: escalating the
// primary blocking work order via the existing escalateWorkOrder mutation.
// This page never auto-executes anything — every recovery option listed is a
// link to an existing workflow (Material Readiness, Planning) or requires the
// explicit button click below, which is itself audited.

const TAT_BADGE: Record<TatStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  ON_TRACK: { status: "COMPLIANT", label: "ON TRACK" },
  AT_RISK: { status: "PENDING", label: "TAT AT RISK" },
  DELAYED: { status: "NON_COMPLIANT", label: "DELAYED" },
  UNKNOWN: { status: "INSUFFICIENT_DATA", label: "UNKNOWN" },
};

// Owner/next-action lookups below are a transparent derivation, not
// fabricated data: they mirror — verbatim — the responsibleRole/action text
// getAogRecoveryAnalysis already assigns per AogBlockerType when it builds
// recoveryOptions (lib/mock/ai/analytics.ts). No new business logic, just a
// per-blocker-row view of the same mapping so the RECOVERY PLAN table below
// can show an owner/next-action next to each individual blocker rather than
// only the de-duplicated action list.
const OWNER_BY_BLOCKER_TYPE: Record<AogBlockerType, string> = {
  MATERIAL: "Procurement",
  PROCUREMENT: "Procurement",
  TECHNICIAN: "Maintenance Manager",
  INSPECTION: "Maintenance Manager",
  EVIDENCE: "Maintenance Manager",
  DEFERRED: "Maintenance Manager",
  REGULATORY: "Compliance",
  SAFETY: "Maintenance Manager",
  EXECUTION: "Maintenance Manager",
  UNKNOWN: "Maintenance Manager",
};

const NEXT_ACTION_BY_BLOCKER_TYPE: Record<AogBlockerType, string> = {
  MATERIAL: "Investigate approved vendor sourcing (Procurement)",
  PROCUREMENT: "Investigate approved vendor sourcing (Procurement)",
  TECHNICIAN: "Assign a qualified technician",
  INSPECTION: "Assign an independent inspector",
  EVIDENCE: "Resolve missing evidence/reference before proceeding",
  DEFERRED: "Review deferred item / MEL restriction",
  REGULATORY: "Resolve non-compliant/review-required assessment (Compliance)",
  SAFETY: "Escalate blocker to maintenance manager",
  EXECUTION: "Escalate blocker to maintenance manager",
  UNKNOWN: "Escalate blocker to maintenance manager",
};

const CRITICAL_PATH_GLYPH: Record<BackendCriticalPathStage["status"], string> = {
  COMPLETE: "✓",
  ACTIVE: "●",
  BLOCKED: "⚠",
  WAITING: "○",
  UNKNOWN: "?",
};

const CRITICAL_PATH_COLOR: Record<BackendCriticalPathStage["status"], string> = {
  COMPLETE: "var(--ac-status-compliant)",
  ACTIVE: "var(--ac-accent)",
  BLOCKED: "var(--ac-status-non-compliant)",
  WAITING: "var(--ac-text-muted)",
  UNKNOWN: "var(--ac-status-review)",
};

type StepStatus = "DONE" | "BLOCKED" | "PENDING";
const STEP_BADGE: Record<StepStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  DONE: { status: "COMPLIANT", label: "DONE" },
  BLOCKED: { status: "NON_COMPLIANT", label: "BLOCKED" },
  PENDING: { status: "INSUFFICIENT_DATA", label: "PENDING" },
};

// Backend-authoritative identity reconciliation status for the panel below.
// "matched" means a real backend Aircraft was found whose registration
// equals the demo/mock aircraft's registration — the only shared, real
// identity field between the two datasets. This is a live lookup against
// the real Aircraft table, never a hard-coded/fabricated id mapping table:
// if no backend aircraft shares the registration, that is reported plainly
// rather than guessing.
type IdentityState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "matched"; aircraftId: string }
  | { kind: "unmatched" }
  | { kind: "unavailable" };

export default function AogRecoveryPage() {
  const params = useParams<{ aircraftId: string }>();
  const aircraftId = params.aircraftId;
  const [version, setVersion] = useState(0);
  const { addAuditEvent, auditLog } = useMroState();
  const current = getCurrentUser();
  void version;

  const analysis = getAircraftRecoveryPlan(aircraftId);

  const { mode: dataMode } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const isRealModeSession = dataMode === "REAL" && isAuthenticated && !!accessToken;

  const [identity, setIdentity] = useState<IdentityState>({ kind: "idle" });
  const [recoveryStatus, setRecoveryStatus] = useState<BackendAogRecoveryStatus | null>(null);
  const [recoveryFetchState, setRecoveryFetchState] = useState<"idle" | "loading" | "loaded" | "unavailable">("idle");

  useEffect(() => {
    if (!isRealModeSession || !accessToken || !analysis) {
      setIdentity({ kind: "idle" });
      return;
    }
    setIdentity({ kind: "loading" });
    aircraftApi
      .list(accessToken)
      .then((aircraft) => {
        const match = aircraft.find((a) => a.registration === analysis.registration);
        setIdentity(match ? { kind: "matched", aircraftId: match.id } : { kind: "unmatched" });
      })
      .catch(() => setIdentity({ kind: "unavailable" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRealModeSession, accessToken, analysis?.registration]);

  useEffect(() => {
    if (identity.kind !== "matched" || !accessToken) {
      setRecoveryStatus(null);
      setRecoveryFetchState("idle");
      return;
    }
    setRecoveryFetchState("loading");
    aogRecoveryApi
      .getRecoveryStatus(accessToken, identity.aircraftId)
      .then((result) => {
        setRecoveryStatus(result);
        setRecoveryFetchState("loaded");
      })
      .catch(() => {
        setRecoveryStatus(null);
        setRecoveryFetchState("unavailable");
      });
  }, [identity, accessToken]);

  if (!analysis) {
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Control Tower", href: "/maintenance/control-tower" }, { label: "AOG Recovery" }]} />
        <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Aircraft not found.</p></div>
      </div>
    );
  }

  const allBlockers: AogBlocker[] = analysis.primaryBlocker ? [analysis.primaryBlocker, ...analysis.secondaryBlockers] : analysis.secondaryBlockers;
  const hasBlockerType = (types: AogBlockerType[]) => allBlockers.some((b) => types.includes(b.type));
  const primaryWoDetail = analysis.workOrderDetails[0] ?? null;

  // Step chain — a visual read of the same real fields shown above (blocker
  // types from getAogRecoveryAnalysis, plus the primary critical work
  // order's release-readiness/inspection status from getAircraftRecoveryPlan).
  // No scripted/fake statuses: a step is BLOCKED only when a blocker of that
  // type is actually present, DONE only when the underlying field says so,
  // and PENDING when the source data doesn't confirm either way.
  const materialBlocked = hasBlockerType(["MATERIAL", "PROCUREMENT"]);
  const technicianBlocked = hasBlockerType(["TECHNICIAN"]);
  const evidenceBlocked = hasBlockerType(["EVIDENCE"]) || (primaryWoDetail?.releaseReadiness.blockers.some((b) => b.category === "EVIDENCE") ?? false);
  const inspectionStatus: StepStatus =
    hasBlockerType(["INSPECTION"]) || primaryWoDetail?.inspection === "BLOCKED"
      ? "BLOCKED"
      : primaryWoDetail && ["NOT_REQUIRED", "READY", "COMPLETED"].includes(primaryWoDetail.inspection)
      ? "DONE"
      : "PENDING";
  const releaseStatus: StepStatus =
    primaryWoDetail?.releaseReadiness.status === "READY" ? "DONE" : primaryWoDetail?.releaseReadiness.status === "BLOCKED" ? "BLOCKED" : "PENDING";

  const stepChain: { label: string; status: StepStatus }[] = [
    { label: "Work Order", status: analysis.criticalWorkOrders.length > 0 ? "DONE" : "PENDING" },
    { label: "Missing Part", status: materialBlocked ? "BLOCKED" : "DONE" },
    { label: "Vendor / Procurement", status: materialBlocked ? "BLOCKED" : "DONE" },
    { label: "Installation", status: technicianBlocked ? "BLOCKED" : "DONE" },
    { label: "Evidence", status: evidenceBlocked ? "BLOCKED" : "DONE" },
    { label: "Inspection / RII", status: inspectionStatus },
    { label: "Release", status: releaseStatus },
  ];

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

      {isRealModeSession && (
        <section className="ac-section">
          <div className="ac-card">
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>
              Backend AOG Recovery Status
              {recoveryFetchState === "loaded" && " · Live Postgres Data"}
            </p>
            {identity.kind === "loading" && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Reconciling this aircraft against real backend records…</p>
            )}
            {identity.kind === "unmatched" && (
              <p className="ac-text-sm" style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid var(--ac-status-review)", background: "color-mix(in srgb, var(--ac-status-review) 10%, transparent)" }}>
                NO_MATCHING_BACKEND_AIRCRAFT — no real Aircraft record shares registration {analysis.registration}. This
                page is showing demo/mock analysis below; nothing is fabricated to fill the gap.
              </p>
            )}
            {identity.kind === "unavailable" && (
              <p className="ac-text-sm" style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid var(--ac-status-review)", background: "color-mix(in srgb, var(--ac-status-review) 10%, transparent)" }}>
                BACKEND_UNAVAILABLE — could not reach the backend to reconcile aircraft identity.
              </p>
            )}
            {identity.kind === "matched" && recoveryFetchState === "unavailable" && (
              <p className="ac-text-sm" style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid var(--ac-status-review)", background: "color-mix(in srgb, var(--ac-status-review) 10%, transparent)" }}>
                BACKEND_UNAVAILABLE — real recovery status could not be retrieved for aircraft {identity.aircraftId}.
              </p>
            )}
            {identity.kind === "matched" && recoveryFetchState === "loaded" && recoveryStatus && (
              <div>
                <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>
                  Reconciled to real Aircraft <span className="ac-mono">{identity.aircraftId.slice(0, 8)}…</span> by matching registration.
                </p>
                <StatusBadge status={recoveryStatus.is_aog ? "NON_COMPLIANT" : "COMPLIANT"} label={recoveryStatus.is_aog ? "AOG (real)" : "NOT AOG (real)"} />
                {recoveryStatus.is_aog && (
                  <div style={{ marginTop: 10 }}>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
                      Event {recoveryStatus.aog_event_id?.slice(0, 8)}… · {recoveryStatus.aog_status} · {recoveryStatus.severity}
                      {recoveryStatus.work_order_id && <> · Work Order <span className="ac-mono">{recoveryStatus.work_order_id.slice(0, 8)}…</span></>}
                    </p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
                      Release Readiness: {recoveryStatus.release_readiness_status ?? "N/A"} · TAT: {recoveryStatus.tat_status ?? "N/A"}
                      {recoveryStatus.tat_reason && ` (${recoveryStatus.tat_reason})`}
                    </p>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>
                      Technician Authorization: {recoveryStatus.technician_authorization} · ETA: {recoveryStatus.eta} · Compliance: {recoveryStatus.compliance_status}
                    </p>
                    {recoveryStatus.critical_path.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <p className="ac-eyebrow" style={{ margin: "0 0 6px" }}>Critical Path</p>
                        <div style={{ overflowX: "auto" }}>
                          <table className="ac-table">
                            <thead><tr><th>Stage</th><th>Status</th><th>Reason</th><th>Record</th><th>Next Action</th></tr></thead>
                            <tbody>
                              {recoveryStatus.critical_path.map((stage) => (
                                <tr key={stage.stage}>
                                  <td className="ac-mono ac-text-sm">{stage.stage.replace(/_/g, " ")}</td>
                                  <td>
                                    <span style={{ color: CRITICAL_PATH_COLOR[stage.status], fontWeight: 700, marginRight: 6 }} aria-hidden>
                                      {CRITICAL_PATH_GLYPH[stage.status]}
                                    </span>
                                    <span className="ac-text-sm">{stage.status}</span>
                                  </td>
                                  <td className="ac-text-sm">{stage.reason}</td>
                                  <td className="ac-mono ac-text-sm">
                                    {stage.record_type && stage.record_id
                                      ? `${stage.record_type} ${stage.record_id.slice(0, 8)}…`
                                      : "—"}
                                  </td>
                                  <td className="ac-text-sm">{stage.next_action ?? "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {recoveryStatus.blockers.length > 0 ? (
                      <div style={{ overflowX: "auto" }}>
                        <table className="ac-table">
                          <thead><tr><th>Category</th><th>Description</th><th>Who Should Act</th><th>Dependency</th></tr></thead>
                          <tbody>
                            {recoveryStatus.blockers.map((b, i) => (
                              <tr key={i} style={recoveryStatus.next_best_action === b ? { outline: "2px solid var(--ac-accent)" } : undefined}>
                                <td className="ac-mono ac-text-sm">{b.category}</td>
                                <td className="ac-text-sm">{b.description}</td>
                                <td className="ac-text-sm">{b.who_should_act}</td>
                                <td className="ac-text-sm">{b.dependency}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No real blockers recorded for this aircraft&apos;s active AOG event.</p>
                    )}
                    {recoveryStatus.next_best_action && (
                      <p className="ac-text-sm" style={{ marginTop: 8 }}>
                        <strong>Next best action:</strong> {recoveryStatus.next_best_action.dependency} ({recoveryStatus.next_best_action.who_should_act})
                      </p>
                    )}
                    <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>{recoveryStatus.data_completeness}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {analysis.isAog && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recovery Path — Critical Chain</h2>
          <div className="ac-card">
            <div className="ac-flex ac-items-center" style={{ flexWrap: "wrap", gap: 0 }}>
              {stepChain.map((s, i) => (
                <div key={s.label} className="ac-flex ac-items-center" style={{ gap: 0 }}>
                  <div
                    style={{
                      border: `1px solid ${s.status === "BLOCKED" ? "var(--ac-status-non-compliant)" : s.status === "DONE" ? "var(--ac-status-compliant)" : "var(--ac-border)"}`,
                      borderRadius: 8,
                      padding: "8px 12px",
                      minWidth: 120,
                      textAlign: "center",
                    }}
                  >
                    <p className="ac-text-sm" style={{ margin: "0 0 4px", fontWeight: 600 }}>{s.label}</p>
                    <StatusBadge {...STEP_BADGE[s.status]} />
                  </div>
                  {i < stepChain.length - 1 && (
                    <span className="ac-text-muted" style={{ padding: "0 6px", fontSize: 16 }} aria-hidden>→</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

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
                  <thead><tr><th>Work Order</th><th>TAT</th><th>Release Readiness</th><th>Authorized Technicians</th><th>Inspection (RII)</th></tr></thead>
                  <tbody>
                    {analysis.workOrderDetails.map((d) => {
                      const tat = getWorkOrderTatStatus(d.workOrderId);
                      return (
                      <tr key={d.workOrderId}>
                        <td><Link href={`/maintenance/planning/${d.workOrderId}`} className="ac-mono">{d.workOrderNumber}</Link></td>
                        <td>
                          {tat ? (
                            <>
                              <StatusBadge {...TAT_BADGE[tat.status]} />
                              <p className="ac-text-sm ac-mono ac-text-muted" style={{ margin: "4px 0 0" }}>
                                {tat.dueDate ? `Due ${tat.dueDate}` : "No due date recorded"}
                                {tat.daysOverdue !== null && ` · ${tat.daysOverdue}d overdue`}
                                {tat.daysRemaining !== null && ` · ${tat.daysRemaining}d remaining`}
                              </p>
                              <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{tat.reason}</p>
                              {tat.contributingBlockers.length > 0 && (
                                <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
                                  {tat.contributingBlockers.map((b, i) => (
                                    <li key={i} className="ac-text-sm ac-text-muted">{b}</li>
                                  ))}
                                </ul>
                              )}
                            </>
                          ) : (
                            <StatusBadge status="INSUFFICIENT_DATA" label="UNKNOWN" />
                          )}
                        </td>
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
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {allBlockers.length > 0 && (
            <section className="ac-section">
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recovery Plan</h2>
              <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
                Every row below is a real blocker from the analysis above. Owner and next action are a direct read of the
                same responsible-role/action mapping getAogRecoveryAnalysis already uses to build the Recovery Options list
                — shown here per blocker instead of de-duplicated by category.
              </p>
              <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
                <table className="ac-table">
                  <thead><tr><th>Blocker</th><th>Owner</th><th>Dependency</th><th>Next Action</th></tr></thead>
                  <tbody>
                    {allBlockers.map((b, i) => (
                      <tr key={i}>
                        <td>
                          <StatusBadge status="NON_COMPLIANT" label={b.type} />
                          <p className="ac-text-sm" style={{ margin: "4px 0 0" }}>{b.description}</p>
                        </td>
                        <td className="ac-text-sm">{OWNER_BY_BLOCKER_TYPE[b.type]}</td>
                        <td className="ac-text-sm">{b.source}</td>
                        <td className="ac-text-sm">{NEXT_ACTION_BY_BLOCKER_TYPE[b.type]}</td>
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
              <p style={{ marginTop: 10 }}>
                <Link href="/maintenance/release-readiness" className="ac-text-sm">View fleet-wide Release Readiness →</Link>
              </p>
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
