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
