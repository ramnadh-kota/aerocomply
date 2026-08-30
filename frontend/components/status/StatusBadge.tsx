// Status is never conveyed by color alone: every badge pairs a color with an
// icon-like glyph and a text label (see docs/ontology — "unknown is not
// false" and the M0.5 accessibility requirement).

type BadgeKind =
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
