# M4.5 — Intelligence Context Contract

> **IntelligenceContext is a read-only projection of deterministic aerospace
> intelligence. It does not create, override, or reinterpret aerospace
> truth.**

## 1. Purpose

M4.5 establishes the formal, versioned, read-only handoff between the
completed deterministic intelligence chain (D1 → D2.1 → D2.2) and the
future Kota Intelligence / AI Assistant (M5), so M5 can be built against
one stable contract instead of coupling directly to five separate
endpoints or, worse, to D1/D2.1/D2.2 database tables.

## 2. Architectural position

```
Developer 1 (Operational Truth)
    ↓
Developer 2.1 (Aerospace Intelligence Foundation)
    ↓
Developer 2.2 (Readiness / Risk / Priority / Decision / Recommendation)
    ↓
M4 Integration (Asset Intelligence View, Fleet Intelligence Control Center)
    ↓
M4.5 (Intelligence Context Contract)  ← this milestone
    ↓
M5 (Kota Intelligence / AI Assistant) — not built here
```

## 3. Contract ownership

`IntelligenceContext` is owned by D2.2 (`app/schemas/intelligence.py`,
`app/services/intelligence/context_service.py`) — it is a composition
layer over D2.2's own five services plus one read-only call into D2.1's
`AerospaceIntelligenceState`. It creates no new ownership boundary and no
new intelligence engine.

## 4. Repository audit findings (Phase 1, performed before implementation)

| Section | Source | Notes |
|---|---|---|
| `asset` | D1 (`asset_service`) + D2.1 (`AerospaceIntelligenceState.asset_type/registration/aircraft_id`, `operational_dimension.operational_state`) | `operational_state` is D1's `compute_operational_state()` output, consumed unchanged via D2.1's own passthrough — never recomputed here. |
| `aerospace_state` | D2.1, verbatim (`evaluate_aerospace_intelligence_state`) | Reuses D2.1's own `IntelligenceBlocker`/`IntelligenceWarning` types directly (imported, not redefined) — see gap below. |
| `readiness` | D2.2 Pass 1 (`get_asset_readiness_intelligence`) | Unchanged. |
| `risk` | D2.2 Pass 1 (`get_asset_risk_intelligence`) | Unchanged. |
| `priority` | D2.2 Pass 2 (`get_asset_priority_intelligence`) | Unchanged. |
| `decision` | D2.2 Pass 2 (`get_asset_decision`) | Unchanged. |
| `recommendation` | D2.2 Pass 3 (`get_asset_recommendation`) | Unchanged. |

**Gap identified:** D2.2's own `ReadinessIntelligenceBlocker` (the type
`readiness`/`decision`/`recommendation` sections use) flattens D2.1's
`IntelligenceBlocker` and drops two fields — `blocker_id` and
`what_condition` — that are part of your required traceability field list.
Rather than adding those two fields to `ReadinessIntelligenceBlocker`
(which would touch three already-shipped Pass 1-3 schemas and their
consumers for a purely additive-but-unnecessary reason), the
`aerospace_state` section of the context reuses D2.1's own
`IntelligenceBlocker`/`IntelligenceWarning` types **directly** — full
detail, zero duplication, zero new vocabulary. This was the one concrete
design decision the audit produced; everything else is a straight
composition.

**Fields deliberately excluded:** raw D1 model rows (Task, WorkOrder,
Finding, Evidence, ComplianceObligation) — the context contract only ever
carries the *evaluated conclusions* about them (blocker descriptions,
`related_record_id`/`related_record_type` pointers), never the rows
themselves. An AI consumer that needs the full source record follows the
pointer back through the existing D1 read APIs — it does not get a second
copy of operational data baked into the context.

## 5. Contract schema (as implemented)

```python
class IntelligenceContext(BaseModel):
    contract_version: str = "1.0"
    generated_at: datetime
    tenant: IntelligenceTenantContext          # organization_id
    asset: IntelligenceAssetContext            # asset_id, aircraft_id, asset_type, registration, operational_state
    aerospace_state: IntelligenceAerospaceStateContext  # status, blockers[], warnings[], evaluation_version, disclaimer
    readiness: IntelligenceReadinessContext    # state, blockers[], data_completeness
    risk: IntelligenceRiskContext              # level, factors[]
    priority: IntelligencePriorityContext      # level, escalated, rationale[]
    decision: IntelligenceDecisionContext      # state, rationale, required_information[]
    recommendation: IntelligenceRecommendationContext  # state, items[]
    uncertainty: list[str]                     # always present, possibly empty
```

`aerospace_state.blockers`/`warnings` are D2.1's own `IntelligenceBlocker`/
`IntelligenceWarning` (full detail: `blocker_id`, `category`, `dimension`,
`what_condition`, `why_condition`, `source_ref{source_type,source_id,
source_label}`, `regulatory_ref_number/title`, `required_action`,
`resolution_action`). `readiness.blockers` and `recommendation.items[
].source_blocker` are D2.2's own `ReadinessIntelligenceBlocker`
(`source_domain`, `category`, `description`, `related_record_id/type`,
`required_action`, `resolution_action`, `regulatory_reference`) — same
types Pass 1-3 already expose, not redefined.

## 6. Versioning

`contract_version: "1.0"`, set once in `context_service.py`, distinct from
D2.1's own `evaluation_version` (`"D2.4.1"`, passed through unchanged
inside `aerospace_state.evaluation_version`) — the two version fields track
different things: `contract_version` is M4.5's own handoff-shape version
(what M5 depends on), `evaluation_version` is D2.1's internal engine
version (what invalidates a cached D2.1 evaluation).

## 7. UNKNOWN semantics

Verified end-to-end by test (`test_unknown_intel_never_becomes_nominal_in_context`):
a fresh asset with zero compliance obligations yields
`aerospace_state.status == "UNKNOWN_INTEL"` (never `"NOMINAL"`),
`readiness.state == "UNKNOWN"`, `risk.level == "UNKNOWN"`,
`decision.state == "INSUFFICIENT_DATA"` (never `"NO_ACTION_REQUIRED"`), and
a non-empty `uncertainty` list. The `uncertainty` field is **always
present** (an empty list when nothing is uncertain) so a consumer can
check it directly rather than inferring uncertainty from the absence of a
field.

## 8. Traceability

`test_blocker_and_source_traceability_survive_context_construction` builds
a real `ComplianceObligation`, drives it `NON_COMPLIANT`, and asserts the
same obligation's id is traceable through all three layers of the context:
`aerospace_state.blockers[].source_ref.source_id` (D2.1, full detail
including `blocker_id`/`what_condition`),
`readiness.blockers[].related_record_id` (D2.2, plus `required_action`),
and `recommendation.items[].source_blocker.related_record_id` (D2.2 Pass
3). Nothing is re-labeled or summarized on the way through.

## 9. Tenant isolation

Identical pattern to every other D2.2 endpoint:
`require_permission(Permission.AIRCRAFT_READ)`, `organization_id` from
JWT-derived `CurrentUser` only, never client-supplied. Verified by
`test_context_is_tenant_scoped` (org A's asset, queried as org B, raises
`NotFoundError` → 404) and `test_context_invalid_asset_raises_not_found`.

## 10. Read-only boundary

`context_service.get_asset_intelligence_context` calls six functions, all
of which are themselves read-only (no `db.commit()`/`db.add()` anywhere in
the call chain), and returns a Pydantic model with no mutation methods.
There is no code path — in this service or in the API layer — through
which a caller could write back into aerospace state, compliance,
evidence, readiness, risk, priority, decision, or recommendation via this
endpoint.

## 11. AI boundary (Section 7 of your brief)

```
Deterministic System (State, Compliance, Readiness, Risk, Priority, Decision, Recommendation)
        ↓
   IntelligenceContext (READ-ONLY CONTRACT)
        ↓
   Kota Intelligence (Explain, Summarize, Answer, Navigate, Present)
```

Made explicit in `context_service.py`'s own docstring: the future AI must
never determine compliance, applicability, airworthiness, readiness,
blocker status, safety classification, or override risk/decision/
recommendation — every one of those already arrives pre-computed in this
contract, and the contract exposes no method to write any of them back.

## 12. API contract

```
GET /api/v1/intelligence/assets/{asset_id}/context -> IntelligenceContext
```
No collision with Developer 1's existing `GET /assets/{asset_id}/context`
(operational-context endpoint, different router prefix `/assets` vs
`/intelligence/assets`) — confirmed before choosing this path, per your
instruction not to create a duplicate endpoint unnecessarily. Same
authorization/tenant pattern as the other 6 intelligence endpoints
(readiness, risk, priority, decision, recommendations, fleet).

## 13. Test coverage (10 tests, all passing)

Contract: version + required fields present; JSON round-trip
(`model_dump_json` → `model_validate_json`) proves the schema serializes
and deserializes cleanly. Composition: all five D2.2 sections plus
aerospace_state present and correctly populated for a NOMINAL asset.
UNKNOWN: `UNKNOWN_INTEL`/`UNKNOWN`/`INSUFFICIENT_DATA` all verified never
to collapse to a positive state. GROUNDED_INTEL/CRITICAL priority
surfacing. DEGRADED (open warning, no blocker) → `MONITOR`. Blocker/source
traceability through all three blocker representations. Tenant isolation.
Invalid asset. Deterministic repeated execution.

## 14. Known limitations

- The context re-evaluates the full six-call chain on every request (no
  caching) — consistent with every prior D2.2 pass's documented
  no-caching precedent, not a new limitation introduced here.
- `source_refs[]`/`evidence_refs[]` as a single flattened, deduplicated
  cross-section list (as sketched in your conceptual structure) was not
  built as a separate top-level field — every blocker already carries its
  own `source_ref`/`related_record_id`+`type` inline, so a consumer can
  collect them by walking `aerospace_state.blockers`/`readiness.blockers`/
  `recommendation.items[].source_blocker` directly. Adding a second,
  flattened, deduplicated view of the same pointers was judged to be
  presentation convenience rather than a genuine gap — flagged here rather
  than built speculatively.

## 15. M5 handoff

An engineer building the Kota AI Assistant can now call
`GET /api/v1/intelligence/assets/{asset_id}/context` once and answer "why
is this aircraft not ready," "what is currently blocking this asset,"
"what action has been recommended," "why is this asset high priority," and
"what evidence supports this finding" entirely from the returned
`IntelligenceContext` — without a single direct query against any D1/D2.1/
D2.2 table. `contract_version` lets M5 detect a future shape change without
coupling to internal service signatures.
