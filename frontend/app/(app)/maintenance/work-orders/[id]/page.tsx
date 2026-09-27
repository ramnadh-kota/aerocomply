"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import {
  StatusBadge,
  workOrderStatusBadge,
  priorityBadge,
  partStatusBadge,
  inspectorReviewStatusBadge,
  genericStatusBadge,
  tatStatusBadge,
} from "@/components/status/StatusBadge";
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
import { useCallback, useEffect, useState, use } from "react";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import {
  workOrdersApi,
  type BackendWorkOrder,
  type TatStatusResponse,
} from "@/lib/api/workOrders";
import { tasksApi, type BackendTask, type TaskCreatePayload } from "@/lib/api/tasks";
import { partRequirementsApi, type BackendPartRequirement } from "@/lib/api/parts";
import { findingsApi, type BackendFinding } from "@/lib/api/findings";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { RealTaskGatePanel } from "@/components/evidence/RealTaskGatePanel";
import { RealReleaseReadinessPanel } from "@/components/evidence/RealReleaseReadinessPanel";

const LIFECYCLE_STEPS = [
  "DRAFT",
  "OPEN",
  "PLANNED",
  "ASSIGNED",
  "IN_PROGRESS",
  "INSPECTION",
  "COMPLETED",
  "CLOSED",
];

function RealWorkOrderDetail({ workOrderId }: { workOrderId: string }) {
  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();

  const [wo, setWo] = useState<BackendWorkOrder | null>(null);
  const [tasks, setTasks] = useState<BackendTask[]>([]);
  const [parts, setParts] = useState<BackendPartRequirement[]>([]);
  const [findings, setFindings] = useState<BackendFinding[]>([]);
  const [tat, setTat] = useState<TatStatusResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [readinessRefreshKey, setReadinessRefreshKey] = useState(0);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);

  // Modal Dialogs
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assigneeId, setAssigneeId] = useState("");
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancellationReason, setCancellationReason] = useState("");
  const [showAddTaskModal, setShowAddTaskModal] = useState(false);
  const [newTaskNumber, setNewTaskNumber] = useState("");
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskDesc, setNewTaskDesc] = useState("");
  const [newTaskHours, setNewTaskHours] = useState("");
  const [newTaskEvidence, setNewTaskEvidence] = useState(false);
  const [newTaskNotes, setNewTaskNotes] = useState("");

  const loadData = useCallback(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    Promise.allSettled([
      workOrdersApi.get(accessToken, workOrderId),
      tasksApi.listForWorkOrder(accessToken, workOrderId),
      partRequirementsApi.listForWorkOrder(accessToken, workOrderId),
      findingsApi.listForWorkOrder(accessToken, workOrderId),
      workOrdersApi.getTat(accessToken, workOrderId),
    ])
      .then(([woRes, tasksRes, partsRes, findingsRes, tatRes]) => {
        if (woRes.status === "fulfilled") setWo(woRes.value);
        else setError(normalizeApiError(woRes.reason));

        if (tasksRes.status === "fulfilled") setTasks(tasksRes.value);
        if (partsRes.status === "fulfilled") setParts(partsRes.value);
        if (findingsRes.status === "fulfilled") setFindings(findingsRes.value);
        if (tatRes.status === "fulfilled") setTat(tatRes.value);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [accessToken, isAuthenticated, workOrderId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Transition handler
  const handleTransition = async (targetStatus: string, reason?: string) => {
    if (!accessToken || isSubmitting) return;
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(true);
    try {
      const updated = await workOrdersApi.transition(accessToken, workOrderId, {
        target_status: targetStatus,
        reason,
      });
      setWo(updated);
      setActionSuccess(`Status transitioned to ${targetStatus.replace(/_/g, " ")}.`);
      setReadinessRefreshKey((k) => k + 1);
      loadData();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Complete handler
  const handleComplete = async () => {
    if (!accessToken || isSubmitting) return;
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(true);
    try {
      const updated = await workOrdersApi.complete(accessToken, workOrderId);
      setWo(updated);
      setActionSuccess("Work order marked as COMPLETED.");
      setReadinessRefreshKey((k) => k + 1);
      loadData();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Close handler
  const handleClose = async () => {
    if (!accessToken || isSubmitting) return;
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(true);
    try {
      const updated = await workOrdersApi.close(accessToken, workOrderId);
      setWo(updated);
      setActionSuccess("Work order successfully CLOSED. Release readiness verified.");
      setReadinessRefreshKey((k) => k + 1);
      loadData();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Assign handler
  const handleAssignSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !assigneeId.trim() || isSubmitting) return;
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(true);
    try {
      const updated = await workOrdersApi.assign(accessToken, workOrderId, {
        assigned_to_user_id: assigneeId.trim(),
      });
      setWo(updated);
      setShowAssignModal(false);
      setAssigneeId("");
      setActionSuccess("Technician successfully assigned.");
      loadData();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Cancel handler
  const handleCancelSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || cancellationReason.trim().length < 3 || isSubmitting) return;
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(true);
    try {
      const updated = await workOrdersApi.cancel(accessToken, workOrderId, {
        cancellation_reason: cancellationReason.trim(),
      });
      setWo(updated);
      setShowCancelModal(false);
      setCancellationReason("");
      setActionSuccess("Work order CANCELLED.");
      loadData();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Add Task handler
  const handleAddTaskSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !newTaskDesc.trim() || isSubmitting) return;
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(true);
    try {
      const payload: TaskCreatePayload = {
        description: newTaskDesc.trim(),
        task_number: newTaskNumber.trim() || undefined,
        title: newTaskTitle.trim() || undefined,
        estimated_hours: newTaskHours ? parseFloat(newTaskHours) : undefined,
        evidence_required: newTaskEvidence,
        notes: newTaskNotes.trim() || undefined,
      };
      await tasksApi.create(accessToken, workOrderId, payload);
      setShowAddTaskModal(false);
      setNewTaskDesc("");
      setNewTaskNumber("");
      setNewTaskTitle("");
      setNewTaskHours("");
      setNewTaskEvidence(false);
      setNewTaskNotes("");
      setActionSuccess("Task added successfully.");
      setReadinessRefreshKey((k) => k + 1);
      loadData();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Complete Task handler
  const completeTask = async (taskId: string) => {
    if (!accessToken || busyTaskId) return;
    setActionError(null);
    setActionSuccess(null);
    setBusyTaskId(taskId);
    try {
      await tasksApi.complete(accessToken, workOrderId, taskId);
      setActionSuccess("Task completed.");
      setReadinessRefreshKey((k) => k + 1);
      loadData();
    } catch (err) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setBusyTaskId(null);
    }
  };

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

      <div className="ac-section-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 className="ac-h1">{wo?.work_order_number ?? "Work Order"}</h1>
          <p className="ac-subtitle">{wo?.title || "MRO Work Order"}</p>
        </div>
        {wo && (
          <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
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
        <RealDataPanel
          loading={loading}
          error={error}
          isEmpty={!wo}
          emptyMessage="This work order could not be found in the connected database."
        >
          {wo && (
            <>
              {/* Feedback Notifications */}
              {actionError && (
                <div
                  className="ac-card ac-section"
                  style={{
                    borderColor: "var(--ac-status-noncompliant)",
                    background: "rgba(239, 68, 68, 0.08)",
                    color: "var(--ac-status-noncompliant)",
                    padding: "var(--ac-space-3)",
                    marginBottom: 16,
                  }}
                >
                  <p className="ac-text-sm" style={{ margin: 0, fontWeight: 600 }}>
                    Gate check / transition prevented: {actionError}
                  </p>
                </div>
              )}
              {actionSuccess && (
                <div
                  className="ac-card ac-section"
                  style={{
                    borderColor: "var(--ac-status-compliant)",
                    background: "rgba(16, 185, 129, 0.08)",
                    color: "var(--ac-status-compliant)",
                    padding: "var(--ac-space-3)",
                    marginBottom: 16,
                  }}
                >
                  <p className="ac-text-sm" style={{ margin: 0 }}>
                    {actionSuccess}
                  </p>
                </div>
              )}

              {/* Lifecycle Action Bar & Visual Pipeline */}
              <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)", marginBottom: 16 }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
                  <div>
                    <span className="ac-eyebrow" style={{ display: "block", marginBottom: 4 }}>
                      Lifecycle State
                    </span>
                    <div className="ac-flex ac-items-center ac-gap-2">
                      <StatusBadge {...workOrderStatusBadge(wo.status)} />
                      {wo.status === "ON_HOLD" && (
                        <span className="ac-badge ac-badge--warning">Work Suspended</span>
                      )}
                    </div>
                  </div>

                  {/* Contextual Action Buttons */}
                  <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                    {wo.status === "DRAFT" && (
                      <button
                        className="ac-btn ac-btn-primary ac-btn-sm"
                        disabled={isSubmitting}
                        onClick={() => handleTransition("OPEN")}
                      >
                        Open Work Order
                      </button>
                    )}
                    {wo.status === "OPEN" && (
                      <button
                        className="ac-btn ac-btn-primary ac-btn-sm"
                        disabled={isSubmitting}
                        onClick={() => handleTransition("PLANNED")}
                      >
                        Plan Work Order
                      </button>
                    )}
                    {wo.status === "PLANNED" && (
                      <button
                        className="ac-btn ac-btn-primary ac-btn-sm"
                        disabled={isSubmitting}
                        onClick={() => setShowAssignModal(true)}
                      >
                        Assign Technician
                      </button>
                    )}
                    {wo.status === "ASSIGNED" && (
                      <>
                        <button
                          className="ac-btn ac-btn-primary ac-btn-sm"
                          disabled={isSubmitting}
                          onClick={() => handleTransition("IN_PROGRESS")}
                        >
                          Start Work (In Progress)
                        </button>
                        <button
                          className="ac-btn ac-btn-sm"
                          disabled={isSubmitting}
                          onClick={() => setShowAssignModal(true)}
                        >
                          Reassign
                        </button>
                      </>
                    )}
                    {wo.status === "IN_PROGRESS" && (
                      <>
                        <button
                          className="ac-btn ac-btn-primary ac-btn-sm"
                          disabled={isSubmitting}
                          onClick={() => handleTransition("INSPECTION")}
                        >
                          Submit for Inspection
                        </button>
                        <button
                          className="ac-btn ac-btn-sm"
                          disabled={isSubmitting}
                          onClick={() => handleTransition("ON_HOLD", "Awaiting parts / hold")}
                        >
                          Put on Hold
                        </button>
                      </>
                    )}
                    {wo.status === "ON_HOLD" && (
                      <button
                        className="ac-btn ac-btn-primary ac-btn-sm"
                        disabled={isSubmitting}
                        onClick={() => handleTransition("IN_PROGRESS")}
                      >
                        Resume Work
                      </button>
                    )}
                    {wo.status === "INSPECTION" && (
                      <>
                        <button
                          className="ac-btn ac-btn-primary ac-btn-sm"
                          disabled={isSubmitting}
                          onClick={handleComplete}
                        >
                          Complete (Sign off)
                        </button>
                        <button
                          className="ac-btn ac-btn-sm"
                          disabled={isSubmitting}
                          onClick={() => handleTransition("IN_PROGRESS", "Returned for rework")}
                        >
                          Return to Work
                        </button>
                      </>
                    )}
                    {wo.status === "COMPLETED" && (
                      <button
                        className="ac-btn ac-btn-primary ac-btn-sm"
                        disabled={isSubmitting}
                        onClick={handleClose}
                      >
                        Verify & Close Work Order
                      </button>
                    )}
                    {wo.status !== "CLOSED" && wo.status !== "CANCELLED" && (
                      <button
                        className="ac-btn ac-btn-sm"
                        style={{ color: "var(--ac-status-noncompliant)" }}
                        disabled={isSubmitting}
                        onClick={() => setShowCancelModal(true)}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>

                {/* Pipeline Steps Indicator */}
                {wo.status !== "CANCELLED" ? (
                  <div
                    className="ac-flex ac-items-center ac-gap-2"
                    style={{ flexWrap: "wrap", paddingTop: 8, borderTop: "1px solid var(--ac-border-subtle)" }}
                  >
                    {LIFECYCLE_STEPS.map((s, idx) => {
                      const isCurrent = wo.status === s;
                      const isPast = LIFECYCLE_STEPS.indexOf(wo.status) > idx;
                      return (
                        <div key={s} className="ac-flex ac-items-center ac-gap-2">
                          <span
                            className="ac-badge"
                            style={{
                              fontSize: 11,
                              fontWeight: isCurrent ? 700 : 500,
                              background: isCurrent
                                ? "var(--ac-accent)"
                                : isPast
                                ? "rgba(59, 130, 246, 0.15)"
                                : "var(--ac-card-subtle)",
                              color: isCurrent
                                ? "#ffffff"
                                : isPast
                                ? "var(--ac-accent)"
                                : "var(--ac-text-muted)",
                            }}
                          >
                            {s.replace(/_/g, " ")}
                          </span>
                          {idx < LIFECYCLE_STEPS.length - 1 && (
                            <span className="ac-text-muted" style={{ opacity: isPast ? 0.8 : 0.3 }}>
                              →
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div
                    style={{
                      paddingTop: 8,
                      borderTop: "1px solid var(--ac-border-subtle)",
                      color: "var(--ac-status-noncompliant)",
                    }}
                  >
                    <strong>CANCELLED:</strong> {wo.cancellation_reason || "No reason specified."}
                    {wo.cancelled_at && (
                      <span className="ac-text-muted" style={{ marginLeft: 8 }}>
                        ({new Date(wo.cancelled_at).toLocaleString()})
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Work Order Overview Grid */}
              <div className="ac-grid-3 ac-section" style={{ marginBottom: 16 }}>
                <div className="ac-card">
                  <p className="ac-kpi-label">Asset / Aircraft</p>
                  <p style={{ fontWeight: 600, marginTop: 4 }} className="ac-mono">
                    {wo.asset_id ? (
                      <Link href={`/drones/${wo.asset_id}`}>Drone: {wo.asset_id.slice(0, 8)}…</Link>
                    ) : wo.aircraft_id ? (
                      <Link href={`/aircraft/${wo.aircraft_id}`}>Aircraft: {wo.aircraft_id.slice(0, 8)}…</Link>
                    ) : (
                      "Ad hoc / None"
                    )}
                  </p>
                  <p className="ac-text-muted ac-text-sm" style={{ margin: 0 }}>
                    Location: {wo.location || "Unspecified"}
                  </p>
                </div>

                <div className="ac-card">
                  <p className="ac-kpi-label">Type & Category</p>
                  <p style={{ fontWeight: 600, marginTop: 4 }}>
                    {wo.work_order_type ? wo.work_order_type.replace(/_/g, " ") : "Standard"}
                  </p>
                  <p className="ac-text-muted ac-text-sm" style={{ margin: 0 }}>
                    Category: {wo.maintenance_category || "General"}
                  </p>
                </div>

                <div className="ac-card">
                  <p className="ac-kpi-label">TAT & Due Date</p>
                  <div className="ac-flex ac-items-center ac-gap-2" style={{ marginTop: 4 }}>
                    {tat ? (
                      <StatusBadge {...tatStatusBadge(tat.status)} />
                    ) : (
                      <span className="ac-text-sm">—</span>
                    )}
                    <span className="ac-mono ac-text-sm">
                      {wo.due_at ? new Date(wo.due_at).toLocaleDateString() : "No due date"}
                    </span>
                  </div>
                  {tat?.reason && (
                    <p className="ac-text-muted ac-text-sm" style={{ margin: "4px 0 0 0" }}>
                      {tat.reason}
                    </p>
                  )}
                </div>
              </div>

              {/* Assignment & Operational Timestamps Grid */}
              <div className="ac-grid-2 ac-section" style={{ marginBottom: 16 }}>
                <div className="ac-card">
                  <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                    <p className="ac-kpi-label" style={{ margin: 0 }}>
                      Assigned Technician
                    </p>
                    {wo.status !== "CLOSED" && wo.status !== "CANCELLED" && (
                      <button
                        className="ac-btn ac-btn--sm"
                        onClick={() => setShowAssignModal(true)}
                      >
                        {wo.assigned_to_user_id ? "Reassign" : "Assign"}
                      </button>
                    )}
                  </div>
                  <p style={{ fontWeight: 600, margin: 0 }} className="ac-mono">
                    {wo.assigned_to_user_id ? wo.assigned_to_user_id : "Unassigned"}
                  </p>
                  {wo.source_type && (
                    <p className="ac-text-muted ac-text-sm" style={{ marginTop: 6, marginBottom: 0 }}>
                      Source: {wo.source_type} ({wo.source_reference || "N/A"})
                    </p>
                  )}
                </div>

                <div className="ac-card">
                  <p className="ac-kpi-label">Labour & Schedule</p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                    <div>
                      <span className="ac-text-muted ac-text-sm">Est. Hours:</span>{" "}
                      <strong>{wo.estimated_hours ?? "—"}</strong>
                    </div>
                    <div>
                      <span className="ac-text-muted ac-text-sm">Actual Hours:</span>{" "}
                      <strong>{wo.actual_hours ?? "—"}</strong>
                    </div>
                    <div>
                      <span className="ac-text-muted ac-text-sm">Started:</span>{" "}
                      <span>{wo.actual_start ? new Date(wo.actual_start).toLocaleDateString() : "—"}</span>
                    </div>
                    <div>
                      <span className="ac-text-muted ac-text-sm">Completed:</span>{" "}
                      <span>{wo.completed_at ? new Date(wo.completed_at).toLocaleDateString() : "—"}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Release Readiness Panel */}
              <div style={{ marginBottom: 16 }}>
                <RealReleaseReadinessPanel key={readinessRefreshKey} workOrderId={workOrderId} />
              </div>

              {/* Tasks Section */}
              <section className="ac-section" style={{ marginBottom: 16 }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
                  <h2 className="ac-h2" style={{ margin: 0 }}>
                    Work Order Tasks ({tasks.length})
                  </h2>
                  {wo.status !== "CLOSED" && wo.status !== "CANCELLED" && (
                    <button
                      className="ac-btn ac-btn--sm ac-btn-primary"
                      onClick={() => setShowAddTaskModal(true)}
                    >
                      + Add Task
                    </button>
                  )}
                </div>

                {tasks.length === 0 ? (
                  <div className="ac-card">
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                      No tasks recorded for this work order yet. Add tasks to define maintenance operations.
                    </p>
                  </div>
                ) : (
                  <div className="ac-flex ac-flex-col ac-gap-2">
                    {tasks.map((t) => (
                      <div key={t.id} className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
                        <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8 }}>
                          <div>
                            <div className="ac-flex ac-items-center ac-gap-2">
                              {t.task_number && <span className="ac-mono ac-badge">{t.task_number}</span>}
                              <strong style={{ fontSize: 14 }}>{t.title || t.description}</strong>
                            </div>
                            {t.title && t.description && (
                              <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0 0" }}>
                                {t.description}
                              </p>
                            )}
                            {t.estimated_hours && (
                              <span className="ac-text-muted ac-text-sm" style={{ marginRight: 12 }}>
                                Est: {t.estimated_hours}h
                              </span>
                            )}
                            {t.actual_hours && (
                              <span className="ac-text-muted ac-text-sm">
                                Actual: {t.actual_hours}h
                              </span>
                            )}
                          </div>

                          <div className="ac-flex ac-items-center ac-gap-2">
                            <StatusBadge {...genericStatusBadge(t.execution_state)} />
                            {t.execution_state !== "COMPLETED" && wo.status !== "CLOSED" && wo.status !== "CANCELLED" && (
                              <button
                                className="ac-btn ac-btn-sm ac-btn-primary"
                                disabled={busyTaskId === t.id}
                                onClick={() => completeTask(t.id)}
                              >
                                {busyTaskId === t.id ? "Completing…" : "Complete Task"}
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Task Evidence Gate */}
                        <div style={{ marginTop: 8 }}>
                          <RealTaskGatePanel taskId={t.id} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* Parts & Findings Grid */}
              <div className="ac-grid-2 ac-section" style={{ marginBottom: 16 }}>
                {/* Parts Requirement Panel */}
                <div className="ac-card">
                  <h3 className="ac-h3" style={{ marginBottom: 10, fontSize: 16 }}>
                    Required Parts ({parts.length})
                  </h3>
                  {parts.length === 0 ? (
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                      No specific part requirements linked to this work order.
                    </p>
                  ) : (
                    <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                      {parts.map((p) => (
                        <li
                          key={p.id}
                          className="ac-flex ac-justify-between ac-items-center"
                          style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)", fontSize: 13 }}
                        >
                          <span className="ac-mono">
                            Part: {p.part_id.slice(0, 8)}… (Req: {p.required_quantity}, Issued: {p.fulfilled_quantity})
                          </span>
                          <StatusBadge {...genericStatusBadge(p.status)} />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Findings Panel */}
                <div className="ac-card">
                  <h3 className="ac-h3" style={{ marginBottom: 10, fontSize: 16 }}>
                    Linked Findings ({findings.length})
                  </h3>
                  {findings.length === 0 ? (
                    <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                      No defect or inspection findings linked to this work order.
                    </p>
                  ) : (
                    <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                      {findings.map((f) => (
                        <li
                          key={f.id}
                          className="ac-flex ac-justify-between ac-items-center"
                          style={{ padding: "6px 0", borderBottom: "1px solid var(--ac-border-subtle)", fontSize: 13 }}
                        >
                          <div>
                            <Link href={`/findings/${f.id}`} style={{ fontWeight: 500 }}>
                              {f.title}
                            </Link>
                            <span className="ac-text-muted ac-text-sm" style={{ display: "block" }}>
                              {f.severity}
                            </span>
                          </div>
                          <StatusBadge {...genericStatusBadge(f.status)} />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              {/* Operational Activity Timeline */}
              <section className="ac-section">
                <h2 className="ac-h2" style={{ marginBottom: 10 }}>
                  Activity & Milestone Timeline
                </h2>
                <div className="ac-card">
                  <Timeline
                    entries={[
                      {
                        id: "created",
                        date: new Date(wo.created_at).toLocaleString(),
                        title: "Work Order Created",
                        detail: `Initial state: DRAFT | Created by user: ${wo.created_by_user_id || "System"}`,
                      },
                      ...(wo.actual_start
                        ? [
                            {
                              id: "started",
                              date: new Date(wo.actual_start).toLocaleString(),
                              title: "Work Started (In Progress)",
                              detail: `Execution initiated | Technician: ${wo.assigned_to_user_id || "Unassigned"}`,
                            },
                          ]
                        : []),
                      ...(wo.completed_at
                        ? [
                            {
                              id: "completed",
                              date: new Date(wo.completed_at).toLocaleString(),
                              title: "Maintenance Completed",
                              detail: "All required tasks signed off and verified.",
                            },
                          ]
                        : []),
                      ...(wo.closed_at
                        ? [
                            {
                              id: "closed",
                              date: new Date(wo.closed_at).toLocaleString(),
                              title: "Work Order Closed",
                              detail: "Release readiness confirmed. Record sealed.",
                            },
                          ]
                        : []),
                      ...(wo.cancelled_at
                        ? [
                            {
                              id: "cancelled",
                              date: new Date(wo.cancelled_at).toLocaleString(),
                              title: "Work Order Cancelled",
                              detail: `Reason: ${wo.cancellation_reason || "None"}`,
                            },
                          ]
                        : []),
                    ]}
                  />
                </div>
              </section>

              {/* Assign Modal */}
              {showAssignModal && (
                <div
                  className="ac-modal-backdrop"
                  onMouseDown={(e) => e.target === e.currentTarget && setShowAssignModal(false)}
                >
                  <div
                    className="ac-modal"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="assign-wo-title"
                    style={{ maxWidth: 460, width: "100%" }}
                  >
                    <h2 id="assign-wo-title" className="ac-modal-title">
                      Assign Technician
                    </h2>
                    <form onSubmit={handleAssignSubmit}>
                      <div className="ac-modal-body">
                        <label className="ac-label" style={{ display: "block", marginBottom: 6 }}>
                          Technician User ID (UUID) *
                        </label>
                        <input
                          className="ac-input"
                          style={{ width: "100%" }}
                          placeholder="e.g. 7b3117fe-b1ff-4848-9bbd-327c9550e509"
                          value={assigneeId}
                          onChange={(e) => setAssigneeId(e.target.value)}
                          required
                        />
                        <p className="ac-text-muted ac-text-sm" style={{ marginTop: 6, margin: 0 }}>
                          Must belong to the same organization and possess technician role.
                        </p>
                      </div>
                      <div className="ac-modal-actions" style={{ marginTop: 16 }}>
                        <button
                          type="button"
                          className="ac-btn"
                          onClick={() => setShowAssignModal(false)}
                          disabled={isSubmitting}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="ac-btn ac-btn-primary"
                          disabled={isSubmitting || !assigneeId.trim()}
                        >
                          {isSubmitting ? "Assigning…" : "Confirm Assignment"}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}

              {/* Cancel Work Order Modal */}
              {showCancelModal && (
                <div
                  className="ac-modal-backdrop"
                  onMouseDown={(e) => e.target === e.currentTarget && setShowCancelModal(false)}
                >
                  <div
                    className="ac-modal"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="cancel-wo-title"
                    style={{ maxWidth: 480, width: "100%" }}
                  >
                    <h2 id="cancel-wo-title" className="ac-modal-title" style={{ color: "var(--ac-status-noncompliant)" }}>
                      Cancel Work Order
                    </h2>
                    <form onSubmit={handleCancelSubmit}>
                      <div className="ac-modal-body">
                        <p className="ac-text-sm">
                          Cancelling is a terminal action. Please provide a mandatory cancellation reason.
                        </p>
                        <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                          Cancellation Reason (min 3 chars) *
                        </label>
                        <textarea
                          className="ac-input"
                          style={{ width: "100%", minHeight: 70 }}
                          placeholder="e.g. Aircraft grounded permanently / work superseded..."
                          value={cancellationReason}
                          onChange={(e) => setCancellationReason(e.target.value)}
                          required
                        />
                      </div>
                      <div className="ac-modal-actions" style={{ marginTop: 16 }}>
                        <button
                          type="button"
                          className="ac-btn"
                          onClick={() => setShowCancelModal(false)}
                          disabled={isSubmitting}
                        >
                          Back
                        </button>
                        <button
                          type="submit"
                          className="ac-btn"
                          style={{
                            background: "var(--ac-status-noncompliant)",
                            color: "#ffffff",
                            borderColor: "var(--ac-status-noncompliant)",
                          }}
                          disabled={isSubmitting || cancellationReason.trim().length < 3}
                        >
                          {isSubmitting ? "Cancelling…" : "Confirm Cancellation"}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}

              {/* Add Task Modal */}
              {showAddTaskModal && (
                <div
                  className="ac-modal-backdrop"
                  onMouseDown={(e) => e.target === e.currentTarget && setShowAddTaskModal(false)}
                >
                  <div
                    className="ac-modal"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="add-task-title"
                    style={{ maxWidth: 500, width: "100%" }}
                  >
                    <h2 id="add-task-title" className="ac-modal-title">
                      Add Work Order Task
                    </h2>
                    <form onSubmit={handleAddTaskSubmit}>
                      <div className="ac-modal-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        <div>
                          <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                            Description *
                          </label>
                          <textarea
                            className="ac-input"
                            style={{ width: "100%", minHeight: 60 }}
                            placeholder="Detailed operational steps..."
                            value={newTaskDesc}
                            onChange={(e) => setNewTaskDesc(e.target.value)}
                            required
                          />
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                          <div>
                            <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                              Task Number
                            </label>
                            <input
                              className="ac-input"
                              style={{ width: "100%" }}
                              placeholder="e.g. T-01"
                              value={newTaskNumber}
                              onChange={(e) => setNewTaskNumber(e.target.value)}
                            />
                          </div>
                          <div>
                            <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                              Estimated Hours
                            </label>
                            <input
                              type="number"
                              step="0.5"
                              min="0"
                              className="ac-input"
                              style={{ width: "100%" }}
                              placeholder="e.g. 2.0"
                              value={newTaskHours}
                              onChange={(e) => setNewTaskHours(e.target.value)}
                            />
                          </div>
                        </div>
                        <div>
                          <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                            Title
                          </label>
                          <input
                            className="ac-input"
                            style={{ width: "100%" }}
                            placeholder="Short task label"
                            value={newTaskTitle}
                            onChange={(e) => setNewTaskTitle(e.target.value)}
                          />
                        </div>
                        <label className="ac-flex ac-items-center ac-gap-2" style={{ cursor: "pointer", fontSize: 13 }}>
                          <input
                            type="checkbox"
                            checked={newTaskEvidence}
                            onChange={(e) => setNewTaskEvidence(e.target.checked)}
                          />
                          <span>Evidence Required for Completion Gate</span>
                        </label>
                        <div>
                          <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                            Notes
                          </label>
                          <input
                            className="ac-input"
                            style={{ width: "100%" }}
                            placeholder="Any special tooling or precautions"
                            value={newTaskNotes}
                            onChange={(e) => setNewTaskNotes(e.target.value)}
                          />
                        </div>
                      </div>
                      <div className="ac-modal-actions" style={{ marginTop: 16 }}>
                        <button
                          type="button"
                          className="ac-btn"
                          onClick={() => setShowAddTaskModal(false)}
                          disabled={isSubmitting}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="ac-btn ac-btn-primary"
                          disabled={isSubmitting || !newTaskDesc.trim()}
                        >
                          {isSubmitting ? "Adding…" : "Add Task"}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}

export default function WorkOrderDetailPage(props: { params: Promise<{ id: string }> }) {
  const params = use(props.params);
  const { isReal, hydrated } = useDataMode();
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
