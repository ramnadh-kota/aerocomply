// Status is never conveyed by color alone: every badge pairs a color with an
// icon-like glyph and a text label (see docs/ontology — "unknown is not
// false" and the M0.5 accessibility requirement).

export type BadgeKind =
  | "APPLICABLE"
  | "NOT_APPLICABLE"
  | "REVIEW_REQUIRED"
  | "INSUFFICIENT_DATA"
  | "COMPLIANT"
  | "NON_COMPLIANT"
  | "TRUE"
  | "FALSE"
  | "UNKNOWN"
  | "ACTIVE"
  | "STORED"
  | "WRITTEN_OFF"
  | "VERIFIED"
  | "UNVERIFIED"
  | "PENDING";

const LABELS: Record<BadgeKind, string> = {
  APPLICABLE: "Applicable",
  NOT_APPLICABLE: "Not Applicable",
  REVIEW_REQUIRED: "Review Required",
  INSUFFICIENT_DATA: "Insufficient Data",
  COMPLIANT: "Compliant",
  NON_COMPLIANT: "Non-Compliant",
  TRUE: "True",
  FALSE: "False",
  UNKNOWN: "Unknown",
  ACTIVE: "Active",
  STORED: "Stored",
  WRITTEN_OFF: "Written Off",
  VERIFIED: "Verified",
  UNVERIFIED: "Unverified",
  PENDING: "Pending",
};

const CLASS_MAP: Record<BadgeKind, string> = {
  APPLICABLE: "ac-badge-applicable",
  NOT_APPLICABLE: "ac-badge-not_applicable",
  REVIEW_REQUIRED: "ac-badge-review_required",
  INSUFFICIENT_DATA: "ac-badge-insufficient_data",
  COMPLIANT: "ac-badge-compliant",
  NON_COMPLIANT: "ac-badge-non_compliant",
  TRUE: "ac-badge-true",
  FALSE: "ac-badge-false",
  UNKNOWN: "ac-badge-unknown",
  ACTIVE: "ac-badge-active",
  STORED: "ac-badge-stored",
  WRITTEN_OFF: "ac-badge-neutral",
  VERIFIED: "ac-badge-compliant",
  UNVERIFIED: "ac-badge-review_required",
  PENDING: "ac-badge-unknown",
};

export function StatusBadge({ status, label }: { status: BadgeKind; label?: string }) {
  return (
    <span className={`ac-badge ${CLASS_MAP[status]}`} role="status">
      <span className="ac-badge-dot" aria-hidden="true" />
      {label ?? LABELS[status]}
    </span>
  );
}

// --- MRO status mapping helpers ---
// MRO domain statuses reuse the same five semantic colors rather than
// inventing a parallel palette — see docs/ontology design principle that
// status must always pair a color with a label, never rely on color alone.

const WORK_ORDER_STATUS_MAP: Record<string, BadgeKind> = {
  DRAFT: "PENDING",
  ASSIGNED: "PENDING",
  IN_PROGRESS: "REVIEW_REQUIRED",
  WAITING_PARTS: "REVIEW_REQUIRED",
  WAITING_INSPECTION: "INSUFFICIENT_DATA",
  COMPLETED: "COMPLIANT",
  CANCELLED: "UNKNOWN",
};

export function workOrderStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: WORK_ORDER_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

/** "Overdue" is a derived fact (see workOrders.isOverdue), not a status value — this renders it as a distinct badge alongside the real status. */
export function overdueBadge(): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: "NON_COMPLIANT", label: "Overdue" };
}

const WORK_PACKAGE_STATUS_MAP: Record<string, BadgeKind> = {
  NOT_STARTED: "PENDING",
  IN_PROGRESS: "REVIEW_REQUIRED",
  BLOCKED: "NON_COMPLIANT",
  READY_FOR_INSPECTION: "INSUFFICIENT_DATA",
  COMPLETED: "COMPLIANT",
};

export function workPackageStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: WORK_PACKAGE_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

const INSPECTOR_REVIEW_STATUS_MAP: Record<string, BadgeKind> = {
  PENDING_INSPECTION: "INSUFFICIENT_DATA",
  APPROVED: "COMPLIANT",
  REJECTED: "NON_COMPLIANT",
  RETURNED_FOR_CORRECTION: "REVIEW_REQUIRED",
};

export function inspectorReviewStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: INSPECTOR_REVIEW_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

const PROJECT_STATUS_MAP: Record<string, BadgeKind> = {
  PLANNED: "PENDING",
  IN_PROGRESS: "REVIEW_REQUIRED",
  ON_HOLD: "UNKNOWN",
  COMPLETED: "COMPLIANT",
  CANCELLED: "UNKNOWN",
};

export function projectStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: PROJECT_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

const PRIORITY_MAP: Record<string, BadgeKind> = {
  LOW: "COMPLIANT",
  MEDIUM: "PENDING",
  HIGH: "REVIEW_REQUIRED",
  CRITICAL: "NON_COMPLIANT",
};

export function priorityBadge(priority: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: PRIORITY_MAP[priority] ?? "UNKNOWN", label: priority };
}

// Checklist item result: UNKNOWN is explicitly distinct from FAIL — never
// coerced together (see docs/ontology "unknown is not false" invariant,
// applied here to technical checklist results, not just applicability).
const CHECKLIST_RESULT_MAP: Record<string, BadgeKind> = {
  PASS: "COMPLIANT",
  FAIL: "NON_COMPLIANT",
  NOT_APPLICABLE: "UNKNOWN",
  UNKNOWN: "INSUFFICIENT_DATA",
};

export function checklistResultBadge(result: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: CHECKLIST_RESULT_MAP[result] ?? "UNKNOWN", label: result.replace(/_/g, " ") };
}

const DEFECT_STATUS_MAP: Record<string, BadgeKind> = {
  OPEN: "NON_COMPLIANT",
  DEFERRED: "UNKNOWN",
  RESOLVED: "COMPLIANT",
};

export function defectStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: DEFECT_STATUS_MAP[status] ?? "UNKNOWN", label: status };
}

const PART_STATUS_MAP: Record<string, BadgeKind> = {
  IN_STOCK: "COMPLIANT",
  ORDERED: "PENDING",
  AWAITING_RECEIPT: "REVIEW_REQUIRED",
};

export function partStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: PART_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

// M7.3 — Certificate verification status is deliberately NOT collapsed into
// compliant/non-compliant: "missing" and "reference unknown" are distinct
// facts, and neither implies the part itself is non-compliant.
const CERTIFICATE_VERIFICATION_MAP: Record<string, BadgeKind> = {
  PRESENT: "COMPLIANT",
  MISSING: "REVIEW_REQUIRED",
  REFERENCE_UNKNOWN: "INSUFFICIENT_DATA",
  NOT_VERIFIED: "UNVERIFIED",
};

export function certificateVerificationBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: CERTIFICATE_VERIFICATION_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

const TRACEABILITY_STATUS_MAP: Record<string, BadgeKind> = {
  TRACEABLE: "COMPLIANT",
  PARTIAL: "REVIEW_REQUIRED",
  UNKNOWN: "INSUFFICIENT_DATA",
};

export function traceabilityStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: TRACEABILITY_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

// M12.1 — Operational risk level (lib/mock/ai/analytics.ts RiskLevel).
const RISK_LEVEL_MAP: Record<string, BadgeKind> = {
  LOW: "COMPLIANT",
  MEDIUM: "REVIEW_REQUIRED",
  HIGH: "NON_COMPLIANT",
};

export function riskLevelBadge(risk: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: RISK_LEVEL_MAP[risk] ?? "UNKNOWN", label: risk };
}

// M12.1 — Derived operational status for the Control Tower fleet view. Not a
// real AircraftStatus value (see analytics.ts OperationalStatus comment) —
// AOG/Under Maintenance/Operational are heuristics computed from open
// defects and work orders, always rendered with a note explaining that.
const OPERATIONAL_STATUS_MAP: Record<string, BadgeKind> = {
  OPERATIONAL: "COMPLIANT",
  UNDER_MAINTENANCE: "REVIEW_REQUIRED",
  AOG: "NON_COMPLIANT",
  STORED: "STORED",
  WRITTEN_OFF: "WRITTEN_OFF",
};

export function operationalStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: OPERATIONAL_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

// Generic fallback for arbitrary backend status strings (e.g. REAL data-mode
// aircraft.status, task.execution_state) that don't have a bespoke mapping
// above — best-effort color guess by common vocabulary, always paired with
// the real label text so meaning is never lost to color alone.
const GENERIC_STATUS_MAP: Record<string, BadgeKind> = {
  ACTIVE: "ACTIVE",
  OPEN: "PENDING",
  PENDING: "PENDING",
  IN_PROGRESS: "REVIEW_REQUIRED",
  COMPLETED: "COMPLIANT",
  DONE: "COMPLIANT",
  CANCELLED: "UNKNOWN",
  CLOSED: "COMPLIANT",
};

export function genericStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: GENERIC_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

// M16.7 — EvidenceFile physical storage state (backend/app/models/evidence.py
// EvidenceFileStatus). DELETED deliberately maps to the neutral "Written Off"
// visual (grey, not red) — a soft-deleted file is an intentional, successful
// action, not a failure, and must stay visually distinct from FAILED.
const EVIDENCE_FILE_STATUS_MAP: Record<string, BadgeKind> = {
  PENDING: "PENDING",
  STORED: "COMPLIANT",
  FAILED: "NON_COMPLIANT",
  DELETED: "WRITTEN_OFF",
};

export function evidenceFileStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: EVIDENCE_FILE_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

// M17.2C — Battery/Component lifecycle event types (backend
// app/services/installation_service.py's LifecycleEventType, exposed via
// GET /drones/{asset_id}/lifecycle-history). Installations render as the
// neutral "Active" (still-in-service) look; removals as the non-compliant
// look — matching the existing precedent of pairing every status color
// with an explicit text label, never color alone.
const LIFECYCLE_EVENT_STATUS_MAP: Record<string, BadgeKind> = {
  BATTERY_INSTALLATION: "ACTIVE",
  COMPONENT_INSTALLATION: "ACTIVE",
  BATTERY_REMOVAL: "NON_COMPLIANT",
  COMPONENT_REMOVAL: "NON_COMPLIANT",
};

const LIFECYCLE_EVENT_LABEL_MAP: Record<string, string> = {
  BATTERY_INSTALLATION: "Battery Installed",
  COMPONENT_INSTALLATION: "Component Installed",
  BATTERY_REMOVAL: "Battery Removed",
  COMPONENT_REMOVAL: "Component Removed",
};

export function lifecycleEventBadge(eventType: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return {
    status: LIFECYCLE_EVENT_STATUS_MAP[eventType] ?? "UNKNOWN",
    label: LIFECYCLE_EVENT_LABEL_MAP[eventType] ?? eventType.replace(/_/g, " "),
  };
}

// M17.4C — real backend maintenance due_status (backend
// app/services/maintenance_service.py's _due_status_for /
// _usage_due_status_for): OVERDUE | DUE_SOON | NOT_DUE | UNKNOWN. Reuses
// this project's existing five-color vocabulary rather than a maintenance-
// specific palette.
const MAINTENANCE_DUE_STATUS_MAP: Record<string, BadgeKind> = {
  NOT_DUE: "COMPLIANT",
  DUE_SOON: "REVIEW_REQUIRED",
  OVERDUE: "NON_COMPLIANT",
  UNKNOWN: "INSUFFICIENT_DATA",
};

export function maintenanceDueStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: MAINTENANCE_DUE_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

// M21.3 -- extracted from independently hand-rolled local `statusBadge()`
// helpers that had converged on the same asset-status mapping in both
// frontend/app/(app)/drones/page.tsx and frontend/app/(app)/drones/[id]/page.tsx
// (and a superset used for battery/component/readiness status strings on the
// drone detail page: GOOD/READY treated as compliant, CRITICAL/BLOCKED as
// non-compliant). Not a new status vocabulary -- same ACTIVE/GROUNDED/GOOD/
// READY/CRITICAL/BLOCKED strings the backend already returns.
const ASSET_STATUS_MAP: Record<string, BadgeKind> = {
  ACTIVE: "COMPLIANT",
  GOOD: "COMPLIANT",
  READY: "COMPLIANT",
  GROUNDED: "NON_COMPLIANT",
  CRITICAL: "NON_COMPLIANT",
  BLOCKED: "NON_COMPLIANT",
};

export function assetStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: ASSET_STATUS_MAP[status] ?? "UNKNOWN", label: status };
}

// M21.3 -- extracted from frontend/app/(app)/findings/[id]/page.tsx's local
// `severityBadge()`/`statusBadge()` helpers. Preserves the exact prior
// mapping (does not introduce or merge severity/status values): Finding
// severity is CRITICAL/MAJOR/MINOR/OBSERVATION and Finding status is
// OPEN/IN_PROGRESS/CLOSED, both real backend-persisted enums
// (backend/app/models/finding.py) -- unchanged here.
export function findingSeverityBadge(severity: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return { status: severity === "CRITICAL" || severity === "MAJOR" ? "NON_COMPLIANT" : "PENDING", label: severity };
}

export function findingStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  return {
    status: status === "CLOSED" ? "COMPLIANT" : status === "IN_PROGRESS" ? "REVIEW_REQUIRED" : "PENDING",
    label: status.replace(/_/g, " "),
  };
}
