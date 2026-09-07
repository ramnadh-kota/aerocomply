"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { AuditEvent, ChecklistItemResult, InspectorReviewStatus, TechnicianSignOff } from "@/lib/mock/types";
import { auditEvents as seedAuditEvents } from "@/lib/mock/audit";
import { getWorkOrderById } from "@/lib/mock/workOrders";

/**
 * Single source of truth for "what has the technician actually recorded, and
 * what has the inspector actually decided" for every checklist-enabled work
 * order — this is what makes the Inspector Decision screen review the SAME
 * submission the technician produced, rather than two independently-seeded
 * local states (the coherence gap identified in the CTO review).
 *
 * This is still a prototype: everything here is in-memory React state,
 * mounted once in app/(app)/layout.tsx so it survives client-side navigation
 * between Work Order and Inspection pages within a session, but it is never
 * persisted to a backend and resets on a full page reload.
 */

export interface ChecklistItemState {
  result: ChecklistItemResult | null; // null = not yet attempted by the technician
  actualValue: string;
  note: string;
  evidenceAttached: boolean;
}

export interface WorkOrderChecklistRecord {
  checklistId: string;
  workOrderId: string;
  technicianId: string | null;
  submissionStatus: "IN_PROGRESS" | "SUBMITTED";
  items: Record<string, ChecklistItemState>;
  technicianSignOff: TechnicianSignOff | null;
  submittedAt: string | null;
  inspectorId: string | null;
  inspectorDecisionStatus: InspectorReviewStatus;
  inspectorComments: string;
  inspectorReviewedAt: string | null;
}

function blankItem(result: ChecklistItemResult | null = null): ChecklistItemState {
  return { result, actualValue: "", note: "", evidenceAttached: false };
}

/**
 * Hand-authored initial records for the 5 checklist-enabled work orders.
 * Every id referenced here (workOrderId, checklistId, technicianId,
 * inspectorId, item ids) is a real, already-existing mock id — see
 * lib/mock/workOrders.ts / checklists.ts / inspectorReviews.ts.
 */
function buildInitialRecords(): Record<string, WorkOrderChecklistRecord> {
  const records: Record<string, WorkOrderChecklistRecord> = {};

  // WO-1042 — Engine inspection. One FAIL (matches finding-1), one UNKNOWN
  // (demo case: PASS must be blocked while a required item is unresolved).
  records["wo-1042"] = {
    checklistId: "chk-1042",
    workOrderId: "wo-1042",
    technicianId: "tech-1",
    submissionStatus: "SUBMITTED",
    items: {
      i1: blankItem("PASS"), i2: blankItem("PASS"), i3: blankItem("PASS"), i4: blankItem("PASS"), i5: blankItem("PASS"),
      i6: { result: "FAIL", actualValue: "", note: "Minor scoring observed on fan blade root (see finding).", evidenceAttached: true },
      i7: { result: "UNKNOWN", actualValue: "", note: "Borescope measurement tooling was recalibrating — clearance not verified this shift.", evidenceAttached: false },
      i8: blankItem("PASS"), i9: blankItem("PASS"), i10: blankItem("PASS"),
    },
    technicianSignOff: { technicianId: "tech-1", timestamp: "2026-03-16T13:40:00Z", confirmed: true },
    submittedAt: "2026-03-16T13:40:00Z",
    inspectorId: "tech-3",
    inspectorDecisionStatus: "PENDING_INSPECTION",
    inspectorComments: "",
    inspectorReviewedAt: null,
  };

  // WO-1043 — Routine maintenance, all clear. Demonstrates a clean pass.
  records["wo-1043"] = {
    checklistId: "chk-1043",
    workOrderId: "wo-1043",
    technicianId: "tech-4",
    submissionStatus: "SUBMITTED",
    items: Object.fromEntries(["i1", "i2", "i3", "i4", "i5", "i6", "i7", "i8", "i9", "i10"].map((id) => [id, blankItem("PASS")])),
    technicianSignOff: { technicianId: "tech-4", timestamp: "2026-03-08T14:20:00Z", confirmed: true },
    submittedAt: "2026-03-08T14:20:00Z",
    inspectorId: "tech-5",
    inspectorDecisionStatus: "APPROVED",
    inspectorComments: "Leak check satisfactory. Approved.",
    inspectorReviewedAt: "2026-03-08T15:00:00Z",
  };

  // WO-1045 — Structural inspection. FAIL item with an associated (HIGH)
  // finding, awaiting inspection — demonstrates FAIL + finding without being
  // a CRITICAL-defect scenario (none exists in the current mock data).
  records["wo-1045"] = {
    checklistId: "chk-1045",
    workOrderId: "wo-1045",
    technicianId: "tech-3",
    submissionStatus: "SUBMITTED",
    items: {
      s1: blankItem("PASS"),
      s2: blankItem("PASS"),
      s3: { result: "FAIL", actualValue: "", note: "Hairline fatigue indication at station 340 — see finding-2.", evidenceAttached: true },
      s4: blankItem("PASS"),
      s5: blankItem("PASS"),
      s6: blankItem("PASS"),
    },
    technicianSignOff: { technicianId: "tech-3", timestamp: "2026-03-16T17:00:00Z", confirmed: true },
    submittedAt: "2026-03-16T17:00:00Z",
    inspectorId: "tech-5",
    inspectorDecisionStatus: "PENDING_INSPECTION",
    inspectorComments: "",
    inspectorReviewedAt: null,
  };

  // WO-1048 — AD compliance inspection, all clear, awaiting inspection.
  records["wo-1048"] = {
    checklistId: "chk-1048",
    workOrderId: "wo-1048",
    technicianId: "tech-5",
    submissionStatus: "SUBMITTED",
    items: Object.fromEntries(["a1", "a2", "a3", "a4", "a5"].map((id) => [id, blankItem("PASS")])),
    technicianSignOff: { technicianId: "tech-5", timestamp: "2026-03-09T18:00:00Z", confirmed: true },
    submittedAt: "2026-03-09T18:00:00Z",
    inspectorId: "tech-3",
    inspectorDecisionStatus: "PENDING_INSPECTION",
    inspectorComments: "",
    inspectorReviewedAt: null,
  };

  // WO-1044 — Defect rectification follow-up, technician still working, not
  // yet submitted (demonstrates the in-progress technician state).
  records["wo-1044"] = {
    checklistId: "chk-1044",
    workOrderId: "wo-1044",
    technicianId: "tech-1",
    submissionStatus: "IN_PROGRESS",
    items: {
      d1: blankItem("PASS"),
      d2: blankItem("PASS"),
      d3: blankItem(null),
      d4: blankItem(null),
      d5: blankItem(null),
    },
    technicianSignOff: null,
    submittedAt: null,
    inspectorId: null,
    inspectorDecisionStatus: "PENDING_INSPECTION",
    inspectorComments: "",
    inspectorReviewedAt: null,
  };

  return records;
}

interface MroState {
  submissions: Record<string, WorkOrderChecklistRecord>;
  auditLog: AuditEvent[];
}

interface MroStateContextValue extends MroState {
  updateChecklistItem: (workOrderId: string, itemId: string, patch: Partial<ChecklistItemState>) => void;
  technicianSignOff: (workOrderId: string, technicianId: string) => void;
  submitForInspection: (workOrderId: string) => void;
  submitInspectorDecision: (workOrderId: string, status: InspectorReviewStatus, comments: string) => void;
  addAuditEvent: (event: Omit<AuditEvent, "id" | "timestamp"> & { timestamp?: string }) => void;
}

const MroStateContext = createContext<MroStateContextValue | null>(null);

let auditEventCounter = 1000;

export function MroStateProvider({ children }: { children: ReactNode }) {
  const [submissions, setSubmissions] = useState<Record<string, WorkOrderChecklistRecord>>(buildInitialRecords);
  const [auditLog, setAuditLog] = useState<AuditEvent[]>(seedAuditEvents);

  const addAuditEvent = useCallback((event: Omit<AuditEvent, "id" | "timestamp"> & { timestamp?: string }) => {
    auditEventCounter += 1;
    const full: AuditEvent = { id: `aud-live-${auditEventCounter}`, timestamp: event.timestamp ?? new Date().toISOString(), ...event };
    setAuditLog((log) => [full, ...log]);
  }, []);

  const updateChecklistItem = useCallback(
    (workOrderId: string, itemId: string, patch: Partial<ChecklistItemState>) => {
      setSubmissions((s) => {
        const record = s[workOrderId];
        if (!record) return s;
        const nextItem = { ...record.items[itemId], ...patch };
        return { ...s, [workOrderId]: { ...record, items: { ...record.items, [itemId]: nextItem } } };
      });
      if (patch.result) {
        const wo = getWorkOrderById(workOrderId);
        addAuditEvent({
          actor: "Prototype Technician", // demo identity; not tied to real auth
          actorRole: "Technician",
          action: "checklist.item_updated",
          objectType: "ChecklistItem",
          objectLabel: `${itemId} on ${wo?.workOrderNumber ?? workOrderId}`,
          previousState: null,
          newState: patch.result,
        });
        if (patch.result === "FAIL") {
          addAuditEvent({
            actor: "Prototype Technician",
            actorRole: "Technician",
            action: "finding.created",
            objectType: "Finding",
            objectLabel: `${itemId} on ${wo?.workOrderNumber ?? workOrderId}`,
            previousState: null,
            newState: "FAIL",
          });
        }
      }
      if (patch.evidenceAttached) {
        const wo = getWorkOrderById(workOrderId);
        addAuditEvent({
          actor: "Prototype Technician",
          actorRole: "Technician",
          action: "evidence.attached",
          objectType: "Evidence",
          objectLabel: `${itemId} on ${wo?.workOrderNumber ?? workOrderId}`,
          previousState: null,
          newState: "ATTACHED",
        });
      }
    },
    [addAuditEvent]
  );

  const technicianSignOff = useCallback(
    (workOrderId: string, technicianId: string) => {
      const timestamp = new Date().toISOString();
      setSubmissions((s) => {
        const record = s[workOrderId];
        if (!record) return s;
        return { ...s, [workOrderId]: { ...record, technicianSignOff: { technicianId, timestamp, confirmed: true } } };
      });
      const wo = getWorkOrderById(workOrderId);
      addAuditEvent({
        actor: "Prototype Technician",
        actorRole: "Technician",
        action: "checklist.technician_signoff",
        objectType: "WorkOrder",
        objectLabel: wo?.workOrderNumber ?? workOrderId,
        previousState: null,
        newState: "SIGNED_OFF",
      });
    },
    [addAuditEvent]
  );

  const submitForInspection = useCallback(
    (workOrderId: string) => {
      const timestamp = new Date().toISOString();
      setSubmissions((s) => {
        const record = s[workOrderId];
        if (!record) return s;
        return { ...s, [workOrderId]: { ...record, submissionStatus: "SUBMITTED", submittedAt: timestamp } };
      });
      const wo = getWorkOrderById(workOrderId);
      addAuditEvent({
        actor: "Prototype Technician",
        actorRole: "Technician",
        action: "work_order.submitted_for_inspection",
        objectType: "WorkOrder",
        objectLabel: wo?.workOrderNumber ?? workOrderId,
        previousState: "IN_PROGRESS",
        newState: "WAITING_INSPECTION",
      });
      addAuditEvent({
        actor: wo?.inspectorId ? "Prototype Inspector" : "System",
        actorRole: "Inspector",
        action: "inspection.review_started",
        objectType: "Inspection",
        objectLabel: wo?.workOrderNumber ?? workOrderId,
        previousState: null,
        newState: "PENDING_INSPECTION",
      });
    },
    [addAuditEvent]
  );

  const submitInspectorDecision = useCallback(
    (workOrderId: string, status: InspectorReviewStatus, comments: string) => {
      const timestamp = new Date().toISOString();
      setSubmissions((s) => {
        const record = s[workOrderId];
        if (!record) return s;
        return { ...s, [workOrderId]: { ...record, inspectorDecisionStatus: status, inspectorComments: comments, inspectorReviewedAt: timestamp } };
      });
      const wo = getWorkOrderById(workOrderId);
      const actionMap: Record<InspectorReviewStatus, string> = {
        PENDING_INSPECTION: "inspection.review_started",
        APPROVED: "inspection.approved",
        REJECTED: "inspection.rejected",
        RETURNED_FOR_CORRECTION: "inspection.returned_for_correction",
      };
      addAuditEvent({
        actor: "Prototype Inspector",
        actorRole: "Inspector",
        action: actionMap[status],
        objectType: "Inspection",
        objectLabel: wo?.workOrderNumber ?? workOrderId,
        previousState: "PENDING_INSPECTION",
        newState: status,
        reason: comments || undefined,
      });
    },
    [addAuditEvent]
  );

  const value = useMemo<MroStateContextValue>(
    () => ({ submissions, auditLog, updateChecklistItem, technicianSignOff, submitForInspection, submitInspectorDecision, addAuditEvent }),
    [submissions, auditLog, updateChecklistItem, technicianSignOff, submitForInspection, submitInspectorDecision, addAuditEvent]
  );

  return <MroStateContext.Provider value={value}>{children}</MroStateContext.Provider>;
}

export function useMroState(): MroStateContextValue {
  const ctx = useContext(MroStateContext);
  if (!ctx) throw new Error("useMroState must be used within MroStateProvider");
  return ctx;
}

/** Convenience accessor for one work order's checklist record, or undefined if none exists. */
export function useChecklistRecord(workOrderId: string): WorkOrderChecklistRecord | undefined {
  const { submissions } = useMroState();
  return submissions[workOrderId];
}
