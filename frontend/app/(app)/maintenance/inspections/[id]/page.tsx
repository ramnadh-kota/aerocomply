"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, priorityBadge, defectStatusBadge, checklistResultBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { InspectorReviewPanel } from "@/components/maintenance/InspectorReviewPanel";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAssessmentById } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { findingsForWorkOrder } from "@/lib/mock/findings";
import { defectsForWorkOrder } from "@/lib/mock/defects";
import { useChecklistRecord } from "@/lib/mro-state/MroStateContext";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";
import { Timeline } from "@/components/timeline/Timeline";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { workOrdersApi, type BackendWorkOrder } from "@/lib/api/workOrders";
import { inspectionsApi, type BackendInspectionRequirement } from "@/lib/api/inspections";
import { usersApi, type BackendOrganizationUser } from "@/lib/api/technicians";

const REQUIREMENT_BADGE: Record<string, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  PENDING: { status: "PENDING", label: "PENDING" },
  COMPLETED: { status: "COMPLIANT", label: "COMPLETED" },
  NOT_REQUIRED: { status: "COMPLIANT", label: "NOT REQUIRED" },
  REJECTED: { status: "NON_COMPLIANT", label: "REJECTED" },
};

function RealInspectionDetail({ workOrderId }: { workOrderId: string }) {
  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const [workOrder, setWorkOrder] = useState<BackendWorkOrder | null>(null);
  const [requirements, setRequirements] = useState<BackendInspectionRequirement[]>([]);
  const [users, setUsers] = useState<BackendOrganizationUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [inspectorByReq, setInspectorByReq] = useState<Record<string, string>>({});
  const [rejectReasonByReq, setRejectReasonByReq] = useState<Record<string, string>>({});
  const [busyReqId, setBusyReqId] = useState<string | null>(null);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      workOrdersApi.get(accessToken, workOrderId),
      inspectionsApi.listForWorkOrder(accessToken, workOrderId),
      usersApi.list(accessToken),
    ])
      .then(([wo, reqs, u]) => {
        setWorkOrder(wo);
        setRequirements(reqs);
        setUsers(u);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [accessToken, isAuthenticated, workOrderId]);

  const userName = (id: string | null) => (id ? users.find((u) => u.id === id)?.full_name ?? id : "—");

  const doTransition = async (
    req: BackendInspectionRequirement,
    targetStatus: string,
    opts?: { inspectorUserId?: string; rejectionReason?: string }
  ) => {
    if (!accessToken) return;
    setActionError(null);
    setBusyReqId(req.id);
    try {
      await inspectionsApi.transition(accessToken, req.id, targetStatus, opts);
      load();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setBusyReqId(null);
    }
  };

  const createRequirement = async (required: boolean) => {
    if (!accessToken) return;
    setActionError(null);
    try {
      await inspectionsApi.create(accessToken, { work_order_id: workOrderId, required });
      load();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    }
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Inspection Queue", href: "/maintenance/inspections" },
          { label: workOrder?.work_order_number ?? workOrderId },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{workOrder ? workOrder.work_order_number : workOrderId} — Inspection</h1>
          <p className="ac-subtitle">REAL data mode — connected to {apiBaseUrl}</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            REAL data mode requires signing in. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel loading={loading} error={error} isEmpty={false} emptyMessage="">
          {actionError && (
            <div className="ac-card ac-section" style={{ borderColor: "var(--ac-status-noncompliant)", padding: "var(--ac-space-3)" }}>
              <p className="ac-text-sm" style={{ margin: 0 }}>{actionError}</p>
            </div>
          )}

          <section className="ac-section">
            <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8 }}>
              <h2 className="ac-h2">Inspection Requirements</h2>
              <div className="ac-flex ac-gap-2">
                <button className="ac-btn" onClick={() => createRequirement(false)}>+ Checklist Review</button>
                <button className="ac-btn" onClick={() => createRequirement(true)}>+ RII (Independent)</button>
              </div>
            </div>

            {requirements.length === 0 && (
              <p className="ac-text-sm ac-text-muted">No inspection requirements recorded for this work order yet.</p>
            )}

            <div className="ac-flex ac-flex-col ac-gap-3">
              {requirements.map((req) => {
                const badge = REQUIREMENT_BADGE[req.status] ?? { status: "INSUFFICIENT_DATA" as const, label: req.status };
                const isBusy = busyReqId === req.id;
                return (
                  <div key={req.id} className="ac-card">
                    <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                      <p style={{ fontWeight: 600, margin: 0 }}>
                        {req.required ? "RII — Independent Inspection Required" : "Checklist Review"}
                      </p>
                      <StatusBadge {...badge} />
                    </div>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>
                      Inspector on record: {userName(req.inspector_user_id)}
                      {req.rejection_reason && <> · Rejection reason: &ldquo;{req.rejection_reason}&rdquo;</>}
                    </p>

                    {req.status === "PENDING" && (
                      <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center" }}>
                        {req.required && (
                          <select
                            className="ac-input"
                            style={{ width: 220 }}
                            value={inspectorByReq[req.id] ?? ""}
                            onChange={(e) => setInspectorByReq((s) => ({ ...s, [req.id]: e.target.value }))}
                            aria-label="Select independent inspector"
                          >
                            <option value="">Select inspector…</option>
                            {users.map((u) => (
                              <option key={u.id} value={u.id}>{u.full_name}</option>
                            ))}
                          </select>
                        )}
                        <button
                          className="ac-btn"
                          disabled={isBusy || (req.required && !inspectorByReq[req.id])}
                          onClick={() => doTransition(req, "COMPLETED", { inspectorUserId: inspectorByReq[req.id] })}
                        >
                          Complete
                        </button>
                        <button className="ac-btn" disabled={isBusy} onClick={() => doTransition(req, "NOT_REQUIRED")}>
                          Mark Not Required
                        </button>
                        <input
                          className="ac-input"
                          style={{ width: 220 }}
                          placeholder="Rejection reason"
                          value={rejectReasonByReq[req.id] ?? ""}
                          onChange={(e) => setRejectReasonByReq((s) => ({ ...s, [req.id]: e.target.value }))}
                        />
                        <button
                          className="ac-btn"
                          disabled={isBusy}
                          onClick={() => doTransition(req, "REJECTED", { rejectionReason: rejectReasonByReq[req.id] })}
                        >
                          Reject
                        </button>
                      </div>
                    )}

                    {req.status === "REJECTED" && (
                      <button className="ac-btn" disabled={isBusy} onClick={() => doTransition(req, "PENDING")}>
                        Reopen for Re-inspection
                      </button>
                    )}

                    {(req.status === "COMPLETED" || req.status === "NOT_REQUIRED") && (
                      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Terminal state — no further action.</p>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>
              The independence rule for RII completion (inspector must not be the technician who
              uploaded evidence for this work) is enforced by the backend, not re-derived here — a
              rejected Complete action surfaces the backend&rsquo;s error above.
            </p>
          </section>
        </RealDataPanel>
      )}
    </div>
  );
}

function DemoInspectionDetailPage({ params }: { params: { id: string } }) {
  const wo = getWorkOrderById(params.id);
  if (!wo || !wo.inspectorReviewId) notFound();

  const record = useChecklistRecord(wo.id);
  const aircraft = getAircraftById(wo.aircraftId)!;
  const project = wo.projectId ? getProjectById(wo.projectId) : undefined;
  const technician = wo.assignedTechnicianId ? getTechnicianById(wo.assignedTechnicianId) : undefined;
  const requirement = wo.relatedRequirementId ? getRequirementById(wo.relatedRequirementId) : undefined;
  const assessment = wo.relatedAssessmentId ? getAssessmentById(wo.relatedAssessmentId) : undefined;
  const evidence = assessment ? evidenceForAssessment(assessment.id) : [];
  const checklist = getChecklistByWorkOrderId(wo.id);
  const findings = findingsForWorkOrder(wo.id);
  const defects = defectsForWorkOrder(wo.id);

  const unknownItems = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "UNKNOWN") : [];
  const openCriticalDefects = defects.filter((d) => d.severity === "CRITICAL" && d.status === "OPEN");
  const blockPassReasons: string[] = [];
  if (unknownItems.length > 0) {
    blockPassReasons.push(`${unknownItems.length} checklist item${unknownItems.length > 1 ? "s are" : " is"} marked UNKNOWN (${unknownItems.map((i) => i.label).join(", ")}) — unknown is never treated as pass.`);
  }
  if (openCriticalDefects.length > 0) {
    blockPassReasons.push(`${openCriticalDefects.length} unresolved CRITICAL defect${openCriticalDefects.length > 1 ? "s" : ""} exist on this work order.`);
  }

  // Tool & calibration status: the domain model has no calibration record
  // (tools are tracked as plain name strings on the checklist), so status is
  // honestly UNKNOWN rather than assumed valid — never silently "assumed OK".
  const requiredTools = checklist?.requiredTools ?? [];

  const passCount = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "PASS").length : 0;
  const failCount = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "FAIL").length : 0;
  const naCount = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "NOT_APPLICABLE").length : 0;
  const unknownCount = unknownItems.length;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Inspection Queue", href: "/maintenance/inspections" },
          { label: wo.workOrderNumber },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{wo.workOrderNumber} — Inspection</h1>
          <p className="ac-subtitle">
            {wo.title} · <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{currentRegistration(aircraft)}</Link>
            {project && <> · <Link href={`/maintenance/projects/${project.id}`}>{project.projectNumber}</Link></>}
          </p>
        </div>
        <div className="ac-flex ac-gap-2">
          <StatusBadge {...priorityBadge(wo.priority)} />
          <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-btn">Open Work Order →</Link>
        </div>
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Technician</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{technician ? <Link href={`/maintenance/technicians/${technician.id}`}>{technician.name}</Link> : "Unassigned"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Submitted At</p>
          <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{record?.submittedAt ? new Date(record.submittedAt).toLocaleString() : "—"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Compliance Requirement</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {requirement ? <Link href={`/regulations/${requirement.id}`} className="ac-mono">{requirement.requirementNumber}</Link> : "None linked"}
          </p>
        </div>
      </div>

      {checklist && record && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Technician Submission</h2>
          <div className="ac-card">
            <p style={{ fontWeight: 600, margin: "0 0 6px" }}>{checklist.title}</p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 12px" }}>
              Technician: {technician?.name ?? record.technicianId} · Status: {record.submissionStatus.replace(/_/g, " ")}
            </p>
            <div className="ac-flex ac-gap-6" style={{ flexWrap: "wrap", marginBottom: 14 }}>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("PASS")} label={`${passCount} Pass`} /></span>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("FAIL")} label={`${failCount} Fail`} /></span>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("NOT_APPLICABLE")} label={`${naCount} N/A`} /></span>
              <span className="ac-text-sm"><StatusBadge {...checklistResultBadge("UNKNOWN")} label={`${unknownCount} Unknown`} /></span>
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {checklist.items.map((item) => {
                const state = record.items[item.id];
                return (
                  <li key={item.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                    <div className="ac-flex ac-justify-between ac-items-center">
                      <span className="ac-text-sm">{item.label}</span>
                      <StatusBadge {...checklistResultBadge(state?.result ?? "UNKNOWN")} label={state?.result ? undefined : "Not yet attempted"} />
                    </div>
                    {state?.actualValue && <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>Measurement: {state.actualValue} {item.unit}</p>}
                    {state?.note && <p className="ac-text-sm ac-text-secondary" style={{ margin: "2px 0 0" }}>&ldquo;{state.note}&rdquo;</p>}
                    {state?.evidenceAttached && (
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0" }}>
                        Evidence attached ✓ — source: technician note/attachment · by {technician?.name ?? record.technicianId ?? "unknown"}
                        {record.submittedAt && <> · {new Date(record.submittedAt).toLocaleString()}</>}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>
              This is the technician&rsquo;s actual submission (shared state) — not a separate re-entered copy.
              Technician sign-off: {record.technicianSignOff ? `confirmed by ${record.technicianSignOff.technicianId} at ${new Date(record.technicianSignOff.timestamp).toLocaleString()}` : "not yet signed off"}.
            </p>
          </div>
        </section>
      )}

      {findings.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Findings</h2>
          <div className="ac-card">
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {findings.map((f) => (
                <li key={f.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <span className="ac-text-sm">{f.description}</span>
                  <StatusBadge {...priorityBadge(f.severity)} />
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {defects.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Defect Count: {defects.length}</h2>
          <div className="ac-card">
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {defects.map((d) => (
                <li key={d.id} className="ac-flex ac-justify-between ac-items-center" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)" }}>
                  <span className="ac-text-sm">ATA {d.ataChapter} — {d.description}</span>
                  <StatusBadge {...defectStatusBadge(d.status)} />
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {evidence.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence</h2>
          <div className="ac-grid-2">
            {evidence.map((e) => (
              <EvidenceCard key={e.id} evidence={e} />
            ))}
          </div>
        </section>
      )}

      {record && record.inspectorDecisionStatus !== "PENDING_INSPECTION" && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Decision History</h2>
          <div className="ac-card">
            <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 6 }}>
              <StatusBadge {...inspectorReviewStatusBadge(record.inspectorDecisionStatus)} />
              <span className="ac-text-sm ac-text-muted">
                {record.inspectorReviewedAt ? new Date(record.inspectorReviewedAt).toLocaleString() : ""}
              </span>
            </div>
            {record.inspectorComments && <p className="ac-text-sm">{record.inspectorComments}</p>}
          </div>
        </section>
      )}

      {requiredTools.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Tool &amp; Calibration Status</h2>
          <div className="ac-card" style={{ borderColor: "var(--ac-status-insufficient)", background: "var(--ac-status-insufficient-bg)" }}>
            <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
              {requiredTools.map((tool) => (
                <li key={tool} className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4 }}>
                  <span>{tool}</span>
                  <StatusBadge status="INSUFFICIENT_DATA" label="Calibration: UNKNOWN" />
                </li>
              ))}
            </ul>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              No calibration record exists in source data for these tools — status is shown as UNKNOWN rather than
              assumed valid. Verify current calibration before relying on measurements from this task.
            </p>
          </div>
        </section>
      )}

      <section className="ac-section">
        <InspectorReviewPanel workOrderId={wo.id} inspectorId={wo.inspectorId ?? ""} blockPassReasons={blockPassReasons} />
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Audit Timeline</h2>
        <div className="ac-card">
          {auditEventsForObjectLabelContains(wo.workOrderNumber).length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No audit events recorded yet for this inspection.</p>
          ) : (
            <Timeline
              entries={auditEventsForObjectLabelContains(wo.workOrderNumber).map((e) => ({
                id: e.id,
                date: new Date(e.timestamp).toLocaleString(),
                title: e.action.replace(/_/g, " ").replace(/\./g, " — "),
                detail: `${e.actor} (${e.actorRole})`,
              }))}
            />
          )}
        </div>
      </section>
    </div>
  );
}

export default function InspectionDetailPage({ params }: { params: { id: string } }) {
  const { isReal, hydrated } = useDataMode();
  if (!hydrated) return null;
  return isReal ? <RealInspectionDetail workOrderId={params.id} /> : <DemoInspectionDetailPage params={params} />;
}
