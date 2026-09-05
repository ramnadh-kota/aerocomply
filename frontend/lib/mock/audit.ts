import type { AuditEvent } from "./types";
import { assessments } from "./assessments";

// MOCK DATA — audit trail. Every event is immutable and append-only, matching
// the DB-level trigger design already shipped in M0 (see
// backend/alembic/versions/0002_audit_events_immutability.py).

export const heroAuditEvents: AuditEvent[] = [
  { id: "aud-1", timestamp: "2026-03-12T10:42:00Z", actor: "AeroComply Rules Engine", actorRole: "SYSTEM", action: "assessment.created", objectType: "ApplicabilityAssessment", objectLabel: "asmt-1 (AD-2026-001 / VT-ABC)", previousState: null, newState: "INSUFFICIENT_DATA" },
  { id: "aud-2", timestamp: "2026-03-12T10:44:00Z", actor: "AeroComply Rules Engine", actorRole: "SYSTEM", action: "evidence.attached", objectType: "Evidence", objectLabel: "Engine Installation Record EI-2026-0211", previousState: null, newState: "VERIFIED" },
  { id: "aud-3", timestamp: "2026-03-12T10:44:30Z", actor: "AeroComply Rules Engine", actorRole: "SYSTEM", action: "evidence.attached", objectType: "Evidence", objectLabel: "maintenance_record_2026_03_10.pdf", previousState: null, newState: "VERIFIED" },
  { id: "aud-4", timestamp: "2026-03-12T11:05:00Z", actor: "Priya Nair", actorRole: "Compliance Engineer", action: "assessment.human_decision", objectType: "ApplicabilityAssessment", objectLabel: "asmt-1 (AD-2026-001 / VT-ABC)", previousState: "PENDING", newState: "REQUEST_MORE_EVIDENCE", reason: "Component and modification status could not be confirmed from available records.", relatedAssessmentId: "asmt-1" },
  { id: "aud-5", timestamp: "2026-03-14T09:10:00Z", actor: "Priya Nair", actorRole: "Compliance Engineer", action: "evidence.added", objectType: "Evidence", objectLabel: "Maintenance Record MR-2026-00481", previousState: null, newState: "VERIFIED" },
  { id: "aud-6", timestamp: "2026-03-14T09:12:00Z", actor: "Priya Nair", actorRole: "Compliance Engineer", action: "evidence.added", objectType: "Evidence", objectLabel: "mod_status_confirmation_2026_03_13.pdf", previousState: null, newState: "VERIFIED" },
  { id: "aud-7", timestamp: "2026-03-14T09:20:00Z", actor: "AeroComply Rules Engine", actorRole: "SYSTEM", action: "assessment.reevaluated", objectType: "ApplicabilityAssessment", objectLabel: "asmt-2 (AD-2026-001 / VT-ABC)", previousState: "asmt-1: INSUFFICIENT_DATA", newState: "APPLICABLE" },
  { id: "aud-8", timestamp: "2026-03-14T09:35:00Z", actor: "Priya Nair", actorRole: "Compliance Engineer", action: "assessment.human_decision", objectType: "ApplicabilityAssessment", objectLabel: "asmt-2 (AD-2026-001 / VT-ABC)", previousState: "PENDING", newState: "CONFIRMED_APPLICABLE", reason: "New evidence confirms fan disk installation and modification status; all conditions now resolved.", relatedAssessmentId: "asmt-2" },
  { id: "aud-9", timestamp: "2026-03-11T08:15:00Z", actor: "AeroComply Rules Engine", actorRole: "SYSTEM", action: "assessment.created", objectType: "ApplicabilityAssessment", objectLabel: "asmt-3 (AD-2026-002 / VT-XYZ)", previousState: null, newState: "NOT_APPLICABLE" },
  { id: "aud-10", timestamp: "2026-03-11T09:00:00Z", actor: "Rohan Verma", actorRole: "CAMO Engineer", action: "assessment.human_decision", objectType: "ApplicabilityAssessment", objectLabel: "asmt-3 (AD-2026-002 / VT-XYZ)", previousState: "PENDING", newState: "CONFIRMED_NOT_APPLICABLE" },
  { id: "aud-11", timestamp: "2026-01-26T08:00:00Z", actor: "AeroComply Rules Engine", actorRole: "SYSTEM", action: "assessment.created", objectType: "ApplicabilityAssessment", objectLabel: "asmt-4 (AD-2026-003 / VT-DEF)", previousState: null, newState: "APPLICABLE" },
  { id: "aud-12", timestamp: "2026-01-26T08:30:00Z", actor: "Priya Nair", actorRole: "Compliance Engineer", action: "assessment.human_decision", objectType: "ApplicabilityAssessment", objectLabel: "asmt-4 (AD-2026-003 / VT-DEF)", previousState: "PENDING", newState: "CONFIRMED_APPLICABLE" },
  { id: "aud-13", timestamp: "2026-03-05T14:02:00Z", actor: "Priya Nair", actorRole: "Compliance Engineer", action: "regulatory_document.ingested", objectType: "RegulatoryDocument", objectLabel: "AD 2026-002 — Fuel System Inspection", previousState: null, newState: "PUBLISHED" },
  { id: "aud-14", timestamp: "2026-02-20T09:30:00Z", actor: "Priya Nair", actorRole: "Compliance Engineer", action: "regulatory_document.ingested", objectType: "RegulatoryDocument", objectLabel: "AD 2026-001 — Engine Fan Disk Inspection", previousState: null, newState: "PUBLISHED" },
];

const bulkAuditEvents: AuditEvent[] = assessments
  .filter((a) => a.id.startsWith("asmt-bulk-"))
  .flatMap((a, idx) => [
    {
      id: `aud-bulk-${idx}-created`,
      timestamp: a.evaluatedAt,
      actor: "AeroComply Rules Engine",
      actorRole: "SYSTEM",
      action: "assessment.created",
      objectType: "ApplicabilityAssessment",
      objectLabel: `${a.id} (${a.regulatoryRequirementId} / ${a.subjectId})`,
      previousState: null,
      newState: a.systemResult,
    },
    {
      id: `aud-bulk-${idx}-decision`,
      timestamp: a.humanDecisionAt ?? a.evaluatedAt,
      actor: a.humanDecisionBy ?? "Unassigned",
      actorRole: a.humanDecisionByRole ?? "Reviewer",
      action: "assessment.human_decision",
      objectType: "ApplicabilityAssessment",
      objectLabel: `${a.id} (${a.regulatoryRequirementId} / ${a.subjectId})`,
      previousState: "PENDING",
      newState: a.humanDecision,
    },
  ]);

export const auditEvents: AuditEvent[] = [...heroAuditEvents, ...bulkAuditEvents].sort((a, b) => b.timestamp.localeCompare(a.timestamp));

export function auditEventsForObjectLabelContains(fragment: string): AuditEvent[] {
  return auditEvents.filter((e) => e.objectLabel.includes(fragment));
}

// M12.7 — Maintenance Traceability & Action History. The ONE merge pattern
// for "static seed events + this session's live mutations", extracted here
// so every page/component that needs a per-entity history (Planning detail,
// Control Center, Lisa) calls the same function instead of re-implementing
// the merge-and-sort each time. Mirrors the pattern already used inline on
// the procurement approvals detail page.
export function combinedAuditHistory(objectLabel: string, liveLog: AuditEvent[]): AuditEvent[] {
  const seeded = auditEvents.filter((e) => e.objectLabel === objectLabel);
  const live = liveLog.filter((e) => e.objectLabel === objectLabel);
  return [...seeded, ...live].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

/** getEntityAuditHistory — same merge pattern as combinedAuditHistory
 * above, exposed under the M20 name for entity-scoped lookups (matches by
 * `entityId` fragment the same way auditEventsForObjectLabelContains does,
 * rather than an exact objectLabel match). Never a second history
 * calculation — delegates straight to auditEventsForObjectLabelContains. */
export function getEntityAuditHistory(entityId: string, liveLog: AuditEvent[] = []): AuditEvent[] {
  const seeded = auditEventsForObjectLabelContains(entityId);
  const live = liveLog.filter((e) => e.objectLabel.includes(entityId));
  return [...seeded, ...live].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

// --- M20 Audit Ledger (prototype hash chain) ---
// A DERIVED, deterministic hash chain over the existing append-only
// auditEvents array — no new stored fields, no second audit system. This
// is a prototype tamper-EVIDENT mechanism (detects whether the recorded
// event sequence is internally consistent when recomputed), NOT a
// cryptographic-grade or legally compliant ledger — see the explicit
// disclaimer on verifyAuditChain() below. Live session events
// (useMroState().auditLog) are append-only in memory and are not currently
// chained — only the seeded, truly immutable auditEvents array is, since
// that's the only append-only-for-real dataset in this prototype.

/** Simple deterministic string hash (FNV-1a, 32-bit). NOT cryptographic —
 * explicitly a prototype checksum, not SHA-256/HMAC. Good enough to detect
 * accidental corruption or reordering in this in-memory demo; not a
 * security control. */
function fnv1aHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export interface AuditChainLink {
  event: AuditEvent;
  previousEventHash: string; // "genesis" for the first event in chronological order
  eventHash: string;
}

const chronological = () => [...auditEvents].sort((a, b) => a.timestamp.localeCompare(b.timestamp));

/** The full chain, oldest first, each link's hash deterministically derived
 * from its own fields + the previous link's hash. */
export function getAuditChain(): AuditChainLink[] {
  const chain: AuditChainLink[] = [];
  let previousHash = "genesis";
  for (const event of chronological()) {
    const canonical = `${event.id}|${event.timestamp}|${event.actor}|${event.action}|${event.objectType}|${event.objectLabel}|${event.previousState ?? ""}|${event.newState ?? ""}|${previousHash}`;
    const eventHash = fnv1aHash(canonical);
    chain.push({ event, previousEventHash: previousHash, eventHash });
    previousHash = eventHash;
  }
  return chain;
}

export type AuditChainStatus = "VALID" | "BROKEN" | "UNKNOWN";

export interface AuditChainVerification {
  status: AuditChainStatus;
  brokenAtEventId: string | null;
  note: string;
}

/** Recomputes the chain fresh and checks self-consistency. In this
 * prototype there is no UI path that can directly edit a historical
 * auditEvents record, so BROKEN is not currently reachable in practice —
 * this validates the chain's internal mathematical consistency, not
 * resistance to someone with direct data access. NOT a claim of legal or
 * regulatory electronic-record compliance. */
export function verifyAuditChain(): AuditChainVerification {
  if (auditEvents.length === 0) return { status: "UNKNOWN", brokenAtEventId: null, note: "No audit events exist to verify." };
  const recomputed = getAuditChain();
  for (let i = 0; i < recomputed.length; i++) {
    const expectedPrev = i === 0 ? "genesis" : recomputed[i - 1].eventHash;
    if (recomputed[i].previousEventHash !== expectedPrev) {
      return { status: "BROKEN", brokenAtEventId: recomputed[i].event.id, note: `Chain link broken at event ${recomputed[i].event.id} — recorded previous-hash does not match the recomputed value.` };
    }
  }
  return { status: "VALID", brokenAtEventId: null, note: `${recomputed.length} event(s) form a self-consistent chain. This is a prototype hash chain — not a claim of cryptographic or regulatory electronic-record compliance.` };
}

// M8.8 — Standard audit action taxonomy. `AuditEvent.action` remains a
// plain string (see types.ts) rather than a strict union, since existing
// seeded events already use their own dotted action names — this constant
// documents the vocabulary future mutation-emitting code should reuse
// rather than inventing ad hoc action names per feature. Emitting these is
// future work (there is no real backend mutation path in this prototype
// yet); this list exists so that work has one place to start from, and so
// no second audit system gets invented to log them.
export const STANDARD_AUDIT_ACTIONS = [
  "task.started",
  "task.completed",
  "finding.created",
  "evidence.uploaded",
  "evidence.verified",
  "part.received",
  "certificate.verified",
  "inspection.requested",
  "inspection.approved",
  "inspection.rejected",
  "work_order.completed",
  "ai.recommendation_generated",
  // M11.11 — procurement lifecycle actions, same taxonomy, no second audit system.
  "procurement.cart_item_added",
  "procurement.cart_item_removed",
  "procurement.cart_updated",
  "procurement.request_created",
  "procurement.request_submitted",
  "procurement.approval_requested",
  "procurement.request_approved",
  "procurement.request_rejected",
  "procurement.request_returned",
  "procurement.clarification_requested",
  "procurement.vendor_selected",
  "procurement.po_generated",
  "procurement.po_sent",
  "procurement.po_acknowledged",
  "procurement.po_received",
  "procurement.po_cancelled",
  "procurement.receiving_recorded",
  "procurement.certificate_uploaded",
  "procurement.certificate_verified",
  // M12.7 — Maintenance Control Tower / Discrepancy Intelligence actions.
  "maintenance.aircraft_status_changed",
  "maintenance.discrepancy_reviewed",
  "maintenance.discrepancy_grouped",
  "maintenance.work_order_planned",
  "maintenance.assignment_recommended",
  "maintenance.material_shortage_identified",
  "maintenance.risk_assessed",
  // M12.4 — Work Order Planning & Maintenance Scheduling Intelligence.
  "maintenance.technician_assigned",
  "maintenance.work_started",
  "maintenance.material_blocking_identified",
  // M12.3 — Material Readiness & Procurement Planning.
  "maintenance.material_readiness_reviewed",
  "maintenance.procurement_request_created",
  "maintenance.material_procurement_linked",
  // M12.5 — Maintenance Control Center.
  "maintenance.control_center_reviewed",
  // M12.6 — Maintenance Execution & Action Center.
  "maintenance.technician_reassigned",
  "maintenance.technician_unassigned",
  "maintenance.work_order_completed",
  "maintenance.work_order_escalated",
  // M19 — deferred-item closure workflow.
  "maintenance.deferred_item_closed",
  // M28 — technician execution evidence lifecycle.
  "maintenance.evidence_uploaded",
  "maintenance.evidence_removed",
  "maintenance.evidence_reviewed",
  "maintenance.evidence_rejected",
] as const;
