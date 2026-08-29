import type { InspectorReview } from "./types";

// MOCK DATA. Mirrors the Human Review pattern already established for
// compliance assessments (ADR-005): the technician's sign-off is a distinct,
// separate act from the inspector's review — the inspector approves,
// rejects, or returns the work order, never the technician themselves.
export const inspectorReviews: InspectorReview[] = [
  { id: "ir-1", workOrderId: "wo-1042", inspectorId: "tech-3", status: "PENDING_INSPECTION", comments: "", reviewedAt: null },
  { id: "ir-2", workOrderId: "wo-1043", inspectorId: "tech-5", status: "APPROVED", comments: "Leak check satisfactory. Approved.", reviewedAt: "2026-03-08T15:00:00Z" },
  { id: "ir-3", workOrderId: "wo-1047", inspectorId: "tech-5", status: "APPROVED", comments: "Software update verified against release notes.", reviewedAt: "2026-01-25T10:00:00Z" },
  { id: "ir-4", workOrderId: "wo-1048", inspectorId: "tech-3", status: "PENDING_INSPECTION", comments: "", reviewedAt: null },
];

export function getInspectorReviewById(id: string): InspectorReview | undefined {
  return inspectorReviews.find((r) => r.id === id);
}

export function getInspectorReviewForWorkOrder(workOrderId: string): InspectorReview | undefined {
  return inspectorReviews.find((r) => r.workOrderId === workOrderId);
}
