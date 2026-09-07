"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, workOrderStatusBadge, priorityBadge, partStatusBadge, inspectorReviewStatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { ChecklistPanel } from "@/components/maintenance/ChecklistPanel";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import type { WorkOrderStatus } from "@/lib/mock/types";
import { findingsForWorkOrder } from "@/lib/mock/findings";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getProjectById, getWorkPackageById } from "@/lib/mock/maintenanceProjects";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getPartById } from "@/lib/mock/parts";
import { defectsForWorkOrder } from "@/lib/mock/defects";
import { getRequirementById } from "@/lib/mock/regulations";
import { getAssessmentById } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getChecklistByWorkOrderId } from "@/lib/mock/checklists";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";
import { Timeline } from "@/components/timeline/Timeline";
import { useEffect, useState as useReactState } from "react";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { workOrdersApi, type BackendWorkOrder } from "@/lib/api/workOrders";
import { tasksApi, type BackendTask } from "@/lib/api/tasks";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

function RealWorkOrderDetail({ workOrderId }: { workOrderId: string }) {
  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const [wo, setWo] = useReactState<BackendWorkOrder | null>(null);
  const [tasks, setTasks] = useReactState<BackendTask[]>([]);
  const [loading, setLoading] = useReactState(true);
  const [error, setError] = useReactState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([workOrdersApi.get(accessToken, workOrderId), tasksApi.listForWorkOrder(accessToken, workOrderId)])
      .then(([woData, taskData]) => {
        if (!cancelled) {
          setWo(woData);
          setTasks(taskData);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(normalizeApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, isAuthenticated, workOrderId]);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Work Orders", href: "/maintenance/work-orders" },
          { label: wo?.work_order_number ?? workOrderId },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{wo?.work_order_number ?? "Work Order"}</h1>
          <p className="ac-subtitle">REAL data mode — connected to {apiBaseUrl}</p>
        </div>
        {wo && (
          <div className="ac-flex ac-gap-2">
            <StatusBadge {...priorityBadge(wo.priority)} />
            <StatusBadge {...workOrderStatusBadge(wo.status)} />
          </div>
        )}
      </div>
      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            REAL data mode requires signing in. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel loading={loading} error={error} isEmpty={!wo} emptyMessage="This work order could not be found in the connected database.">
          {wo && (
            <>
              <div className="ac-card" style={{ marginBottom: 16 }}>
                <p><strong>Aircraft ID:</strong> <span className="ac-mono">{wo.aircraft_id}</span></p>
                <p><strong>Created:</strong> {new Date(wo.created_at).toLocaleString()}</p>
              </div>
              <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>Tasks ({tasks.length})</h2>
              {tasks.length === 0 ? (
                <div className="ac-card"><p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No tasks recorded on this work order yet.</p></div>
              ) : (
                <div className="ac-flex ac-flex-col ac-gap-2">
                  {tasks.map((t) => (
                    <div key={t.id} className="ac-card">
                      <div className="ac-flex ac-justify-between ac-items-center">
                        <span>{t.description}</span>
                        <StatusBadge {...genericStatusBadge(t.execution_state)} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}

export default function WorkOrderDetailPage({ params }: { params: { id: string } }) {
  const { isReal, hydrated } = useDataMode();
  // See identical comment in app/(app)/aircraft/[id]/page.tsx — must wait
  // for hydration before choosing a branch to avoid an irrecoverable
  // notFound() on the DEMO branch for a REAL-only id.
  if (!hydrated) return null;
  if (isReal) return <RealWorkOrderDetail workOrderId={params.id} />;
  return <DemoWorkOrderDetailPage params={params} />;
}

function DemoWorkOrderDetailPage({ params }: { params: { id: string } }) {
  const wo = getWorkOrderById(params.id);
  if (!wo) notFound();

  const aircraft = getAircraftById(wo.aircraftId)!;
  const registration = currentRegistration(aircraft);
  const project = wo.projectId ? getProjectById(wo.projectId) : undefined;
  const workPackage = wo.workPackageId ? getWorkPackageById(wo.workPackageId) : undefined;
  const technician = wo.assignedTechnicianId ? getTechnicianById(wo.assignedTechnicianId) : undefined;
  const requirement = wo.relatedRequirementId ? getRequirementById(wo.relatedRequirementId) : undefined;
  const assessment = wo.relatedAssessmentId ? getAssessmentById(wo.relatedAssessmentId) : undefined;
  const evidence = assessment ? evidenceForAssessment(assessment.id) : [];
  const checklist = getChecklistByWorkOrderId(wo.id);
  const auditEvents = auditEventsForObjectLabelContains(wo.workOrderNumber);
  const findings = findingsForWorkOrder(wo.id);
  const { submissions } = useMroState();
  const record = submissions[wo.id];

  const STEPS: WorkOrderStatus[] = ["DRAFT", "ASSIGNED", "IN_PROGRESS", wo.status === "WAITING_PARTS" ? "WAITING_PARTS" : "WAITING_INSPECTION", "COMPLETED"];
  const currentStepIndex = STEPS.indexOf(wo.status);

  const unresolvedPart = wo.requiredPartIds.map((id) => getPartById(id)).find((p) => p && p.status !== "IN_STOCK");
  const openDefects = defectsForWorkOrder(wo.id).filter((d) => d.status === "OPEN");
  const unknownItems = checklist && record ? checklist.items.filter((i) => record.items[i.id]?.result === "UNKNOWN") : [];
  let nextAction: string | null = null;
  if (wo.status === "CANCELLED") nextAction = null;
  else if (wo.status === "COMPLETED") nextAction = null;
  else if (!wo.assignedTechnicianId) nextAction = "Assign a technician to begin work.";
  else if (wo.status === "WAITING_PARTS" && unresolvedPart) nextAction = `Expedite receipt of ${unresolvedPart.partNumber} (${unresolvedPart.status.replace(/_/g, " ")}).`;
  else if (unknownItems.length > 0) nextAction = `Resolve ${unknownItems.length} UNKNOWN checklist item(s) before this can proceed to approval.`;
  else if (openDefects.length > 0) nextAction = `${openDefects.length} open defect(s) require disposition.`;
  else if (record && record.submissionStatus === "IN_PROGRESS") nextAction = "Technician checklist is in progress — complete and sign off to submit for inspection.";
  else if (wo.inspectorReviewId && record?.inspectorDecisionStatus === "PENDING_INSPECTION") nextAction = "Awaiting inspector decision.";
  else if (wo.status === "ASSIGNED" || wo.status === "DRAFT") nextAction = "Begin technician checklist execution.";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Work Orders", href: "/maintenance/work-orders" },
          { label: wo.workOrderNumber },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{wo.workOrderNumber}</h1>
          <p className="ac-subtitle">{wo.title}</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <StatusBadge {...priorityBadge(wo.priority)} />
          <StatusBadge {...workOrderStatusBadge(wo.status)} />
        </div>
      </div>

      {wo.status === "CANCELLED" ? (
        <div className="ac-card ac-section">
          <StatusBadge {...workOrderStatusBadge("CANCELLED")} />
        </div>
      ) : (
        <div className="ac-card ac-section">
          <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Status</p>
          <div className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap" }}>
            {STEPS.map((s, idx) => (
              <span key={s} className="ac-flex ac-items-center ac-gap-2">
                <StatusBadge {...workOrderStatusBadge(s)} label={s.replace(/_/g, " ")} />
                {idx < STEPS.length - 1 && <span className="ac-text-muted" style={{ opacity: idx < currentStepIndex ? 1 : 0.35 }}>→</span>}
              </span>
            ))}
          </div>
        </div>
      )}

      {nextAction && (
        <div className="ac-card ac-section" style={{ borderColor: "var(--ac-status-review)", background: "var(--ac-status-review-bg)" }}>
          <p className="ac-eyebrow" style={{ color: "var(--ac-status-review)", marginBottom: 4 }}>Next Action</p>
          <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>{nextAction}</p>
        </div>
      )}

      {(requirement || assessment) && (
        <div className="ac-card ac-section" style={{ background: "var(--ac-accent-muted)", border: "1px solid var(--ac-accent)" }}>
          <p className="ac-eyebrow" style={{ marginBottom: 6 }}>Compliance Chain</p>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{registration}</Link>
            {project && <> → <Link href={`/maintenance/projects/${project.id}`} className="ac-mono">{project.title}</Link></>}
            {" → "}
            <span className="ac-mono">{wo.workOrderNumber}</span>
            {technician && <> → {technician.name}</>}
            {wo.inspectorReviewId && <> → <Link href={`/maintenance/inspections/${wo.id}`} className="ac-mono">Inspection</Link></>}
            {requirement && <> → <Link href={`/regulations/${requirement.id}`} className="ac-mono">{requirement.requirementNumber}</Link></>}
            {assessment && (
              <>
                {" → "}<Link href={`/assessments/${assessment.id}`} className="ac-mono">Assessment</Link>
                {" → "}<Link href={`/assessments/${assessment.id}`} className="ac-mono">Human Review</Link>
                {" → "}<Link href="/audit" className="ac-mono">Audit Trail</Link>
              </>
            )}
          </p>
        </div>
      )}

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Aircraft</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}><Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{registration}</Link></p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Project / Work Package</p>
          <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>
            {project ? <Link href={`/maintenance/projects/${project.id}`}>{project.title}</Link> : "Ad hoc (no project)"}
            {workPackage && <> · {workPackage.title}</>}
          </p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Due Date</p>
          <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">{wo.dueDate}</p>
        </div>
      </div>

      <div className="ac-grid-2 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Assigned Technician</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {technician ? <Link href={`/maintenance/technicians/${technician.id}`}>{technician.name} ({technician.role})</Link> : "Unassigned"}
          </p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Required Tools</p>
          <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>{wo.requiredTools.length > 0 ? wo.requiredTools.join(", ") : "None"}</p>
        </div>
      </div>

      {wo.requiredPartIds.length > 0 && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Required Parts</h2>
          <div className="ac-card">
            <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
              {wo.requiredPartIds.map((id) => {
                const p = getPartById(id);
                if (!p) return null;
                return (
                  <li key={id} className="ac-flex ac-justify-between" style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)", fontSize: 13 }}>
                    <span className="ac-mono">{p.partNumber} — {p.description}</span>
                    <StatusBadge {...partStatusBadge(p.status)} />
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      )}

      {wo.inspectorReviewId && (
        <div className="ac-card ac-section" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="ac-text-sm">This work order has been submitted for inspection.</span>
          <Link href={`/maintenance/inspections/${wo.id}`} className="ac-btn ac-btn-primary">Open Inspection →</Link>
        </div>
      )}

      {checklist && (
        <section className="ac-section">
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>Task Checklist</h2>
          <ChecklistPanel checklist={checklist} workOrderId={wo.id} />
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
                  <StatusBadge {...priorityBadge(f.severity)} label={f.requiresDefect ? `${f.severity} · Defect Raised` : f.severity} />
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {record && (
        <div className="ac-grid-2 ac-section">
          <div className="ac-card">
            <p className="ac-kpi-label">Technician Sign-off</p>
            {record.technicianSignOff ? (
              <p style={{ marginTop: 4, fontSize: 13 }}>
                {getTechnicianById(record.technicianSignOff.technicianId)?.name ?? record.technicianSignOff.technicianId} confirmed on{" "}
                {new Date(record.technicianSignOff.timestamp).toLocaleString()}
              </p>
            ) : (
              <p className="ac-text-sm ac-text-muted" style={{ marginTop: 4 }}>Not yet signed off.</p>
            )}
          </div>
          <div className="ac-card">
            <p className="ac-kpi-label">Inspector Decision</p>
            <div className="ac-flex ac-items-center ac-gap-2" style={{ marginTop: 4 }}>
              <StatusBadge {...inspectorReviewStatusBadge(record.inspectorDecisionStatus)} />
            </div>
            {record.inspectorComments && <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>{record.inspectorComments}</p>}
          </div>
        </div>
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

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Activity History</h2>
        <div className="ac-card">
          {auditEvents.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No audit events recorded yet for this work order.</p>
          ) : (
            <Timeline
              entries={auditEvents.map((e) => ({
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
