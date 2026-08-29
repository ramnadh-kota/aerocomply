# ADR-005 — Human Decision Boundary and Auditability

## Status
Accepted

## Context
A single mutable `status` field on a compliance record conflates three distinct things: what the system computed, what a human decided about it, and what the organization's final position is. This makes it impossible to answer "did the human accept or override the system?", loses the system's original determination once a human edits it, and creates a silent path for any actor (including, if not carefully bounded, the AI) to change compliance status without a clear accountability trail.

## Decision
Model the lifecycle as four explicit states/fields on an immutable, append-only assessment lineage (§4b, "Human Decision Boundary" section of FOUNDATION.md):

```
SYSTEM DETERMINATION → HUMAN REVIEW → HUMAN DECISION → FINAL COMPLIANCE STATUS
     system_result                      human_decision         final_status
```

- `system_result`/`confidence`/`reasoning` are written once by the rules engine and never mutated.
- `human_decision` (`ACCEPTED` | `OVERRIDDEN` | `PENDING`) plus `human_decision_by`/`human_decision_at`/`override_reason`/`override_evidence_id` are written only via an authenticated human action against a dedicated endpoint (`POST /applicability/assessments/{id}/decision`), never as a side effect of any other call.
- `final_status` is derived from the human decision (or defaults to mirroring `system_result` while `human_decision = PENDING`).
- Any change — a re-evaluation, a human decision, a later override — inserts a **new** `applicability_assessments` row with `previous_assessment_id` pointing at its predecessor; nothing is ever `UPDATE`d in place.
- Every write to `human_decision`/`final_status` also writes an `AuditEvent` with user identity, timestamp, and (for overrides) the mandatory reason.

## Alternatives Considered
- **Single `status` enum column, mutated in place**: rejected — this is precisely the anti-pattern the CTO directive calls out; loses history, cannot answer "what changed and why," and provides no structural barrier against an unauthorized or automated actor silently changing compliance status.
- **Separate `HumanReview` table joined 1:1 to assessment**: considered, but folding the fields into the same immutable lineage row (rather than a separate mutable side-table) keeps the "what changed between assessments" query a simple lineage-chain diff rather than a multi-table join across mutable and immutable halves.

## Consequences
- Every assessment answers "what did the system say, what did a human do about it, and what's the final position" from one row, and "what changed since last time" via `previous_assessment_id` + `change_reason`.
- Slightly more storage (full row per change rather than in-place update) — acceptable and expected for an auditable compliance system.
- The AI module's database role has no `UPDATE`/`INSERT` grant on `human_decision`/`final_status`, enforced at the DB permission level in addition to the application layer — a human-decision write literally cannot originate from the AI service identity.

## Reversal Conditions
None anticipated — this is a compliance/audit requirement, not a scalability tradeoff. Revisit only the storage strategy (e.g. partitioning old lineages) if assessment-history volume becomes a performance concern, never the append-only/never-overwrite principle itself.
