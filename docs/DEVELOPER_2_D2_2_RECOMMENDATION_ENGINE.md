# D2.2 Pass 3 — Recommendation Engine

## Architecture

```
Developer 1 (operational truth: compute_operational_state, work orders, tasks)
    -> D2.1 / D2-4 (Aerospace Intelligence State: applicability, compliance,
       evidence, inspection, finding dimensions -- app/services/
       aerospace_state_service.py)
    -> D2.2 Pass 1: Readiness Intelligence (readiness_intelligence_service.py)
    -> D2.2 Pass 1: Risk Intelligence (risk_intelligence_service.py)
    -> D2.2 Pass 2: Priority Intelligence (priority_intelligence_service.py)
    -> D2.2 Pass 2: Decision Engine (decision_service.py)
    -> D2.2 Pass 3: Recommendation Engine (recommendation_service.py)  <- this document
    -> (future) AI Assistant: explains/summarizes the above, never replaces it
```

Each stage consumes only the previous stage's own output. The Recommendation
Engine runs zero domain queries of its own — every field in
`AssetRecommendation` is either copied verbatim from `AssetDecision` or
classified deterministically from it.

## Ownership boundaries (unchanged this pass)

- **Developer 1** still owns `compute_operational_state`, work orders, tasks,
  and all operational CRUD. Untouched.
- **D2.1** still owns applicability, compliance, evidence, inspection/finding
  intelligence, and the `AerospaceIntelligenceState` contract
  (`app/services/aerospace_state_service.py`, `app/schemas/aerospace_state.py`).
  Untouched.
- **D2.2** now owns Readiness, Risk, Priority, Decision, and Recommendation —
  all five stages complete as of this pass.

## Recommendation contract (`app/schemas/intelligence.py`)

```python
class RecommendationItem(BaseModel):
    action_category: RecommendationActionCategory
    action: str
    resolution_condition: str | None
    source_blocker: ReadinessIntelligenceBlocker | None

class AssetRecommendation(BaseModel):
    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    recommendation_state: DecisionState          # reused, not a 4th vocabulary
    priority_level: PriorityLevel                # reused from Pass 2
    risk_level: RiskLevel                         # reused from Pass 1
    readiness_state: ReadinessState               # reused from Pass 1
    items: list[RecommendationItem]
    required_information: list[str]               # passthrough from AssetDecision
    blockers: list[ReadinessIntelligenceBlocker]   # ALL blockers, never a subset
    warnings: list[IntelligenceWarningRef]
    explanation: list[str]
    evaluated_at: datetime
```

`RecommendationActionCategory` is a small, domain-grounded vocabulary, not an
invented taxonomy:

```python
RecommendationActionCategory = Literal[
    "OBTAIN_MISSING_INFORMATION",
    "PERFORM_REQUIRED_ACTION",
    "RESOLVE_BLOCKER",
    "MONITOR_CONDITION",
    "NO_ACTION_REQUIRED",
]
```

`NO_ACTION_REQUIRED` reuses the exact literal already established by
`app/models/finding.py`'s `DispositionType` (`CORRECTIVE_ACTION` /
`NO_ACTION_REQUIRED` / `DEFERRED`) and by `DecisionState` — it is not a new
value invented for this pass. The remaining four categories are grounded
directly in what a source blocker/decision branch either does or does not
carry, not chosen for aesthetic completeness.

### A Pass-1 gap closed (additive, non-breaking)

Auditing Pass 1 before writing the Recommendation Engine surfaced a real
gap: `ReadinessIntelligenceBlocker` (Pass 1) dropped D2.1's own
`required_action` / `resolution_action` / regulatory-reference fields when
flattening `AerospaceIntelligenceState.blockers`. The master directive for
this pass is explicit that an authoritative required action must be
surfaced, not reinvented — so three optional fields were added to
`ReadinessIntelligenceBlocker` (`required_action`, `resolution_action`,
`regulatory_reference`, all defaulting to `None`) and
`readiness_intelligence_service.py` was updated to copy them from D2.1's
`IntelligenceBlocker` for `AEROSPACE_STATE`-domain blockers. This is
additive only — no existing field was renamed or removed, and all 26
pre-existing Pass-1/Pass-2 tests were re-run and continued to pass
unchanged after the edit. `WORK_ORDER` and `DEPLOYMENT`-domain blockers
carry no such field in their own source schemas
(`release_readiness_service.Blocker`, `readiness_service`'s blocker
strings), so those stay `None` — never fabricated.

## Recommendation rule table (exact logic)

```python
if decision.decision_state == "INSUFFICIENT_DATA":
    # One item per decision.required_information entry, verbatim.
    # No source_blocker: decision_service checks readiness/risk UNKNOWN
    # before ever branching into blockers.
    items = [
        RecommendationItem(
            action_category="OBTAIN_MISSING_INFORMATION",
            action=info,
        )
        for info in decision.required_information
    ]

elif decision.decision_state in ("IMMEDIATE_ACTION_REQUIRED", "ACTION_REQUIRED"):
    # ALL blockers preserved, never a subset. Ordered AEROSPACE_STATE ->
    # WORK_ORDER -> DEPLOYMENT (D2.1's own determination is the most
    # authoritative), ties broken by stable original order.
    for blocker in sorted(decision.blockers, key=domain_priority):
        if blocker.required_action:
            item = RecommendationItem(
                action_category="PERFORM_REQUIRED_ACTION",
                action=blocker.required_action,               # verbatim
                resolution_condition=blocker.resolution_action, # verbatim
                source_blocker=blocker,
            )
        else:
            item = RecommendationItem(
                action_category="RESOLVE_BLOCKER",
                action=blocker.description,                    # verbatim
                resolution_condition=None,                      # none exists
                source_blocker=blocker,
            )

elif decision.decision_state == "MONITOR":
    # One item per warning, verbatim message.
    items = [
        RecommendationItem(action_category="MONITOR_CONDITION", action=w.message)
        for w in decision.warnings
    ]

else:  # NO_ACTION_REQUIRED
    items = [RecommendationItem(action_category="NO_ACTION_REQUIRED", action="No action required.")]
```

`recommendation_state = decision.decision_state`, unchanged — Recommendation
answers "what deterministic next-step items follow," Decision already
answered "what state are we in." No fourth competing state vocabulary is
introduced.

## UNKNOWN semantics

- `readiness_state == "UNKNOWN"` or `risk_level == "UNKNOWN"` always
  produces `decision_state == "INSUFFICIENT_DATA"` upstream (Pass 2's own
  rule, unchanged), which this pass renders as
  `recommendation_state == "INSUFFICIENT_DATA"` with
  `action_category == "OBTAIN_MISSING_INFORMATION"` items only.
- Verified by test: `test_unknown_intel_yields_insufficient_data_recommendation`
  asserts `recommendation_state` is never `NO_ACTION_REQUIRED`, `MONITOR`,
  `ACTION_REQUIRED`, or `IMMEDIATE_ACTION_REQUIRED` when readiness/risk are
  `UNKNOWN`, and asserts no item text claims readiness, low risk, or
  "continue operation."

## Blocker handling

- **Never discarded**: `AssetRecommendation.blockers` carries the full,
  unfiltered list from `AssetDecision.blockers`; `items` covers every
  blocker in the ACTION_REQUIRED/IMMEDIATE_ACTION_REQUIRED branches (see
  `test_multiple_blockers_are_all_preserved_and_ordered`).
- **Deterministic ordering, with an explicit reason**: AEROSPACE_STATE
  before WORK_ORDER before DEPLOYMENT, because D2.1's own determination is
  the most authoritative source; the rule and its rationale are in the
  module docstring, not just in code.
- **Traceability preserved**: `RecommendationItem.source_blocker` carries
  the full `ReadinessIntelligenceBlocker` (category, description,
  `related_record_id`, `related_record_type`, and now `required_action`/
  `resolution_action`/`regulatory_reference` where D2.1 provides them) —
  verified end-to-end by `test_restricted_state_surfaces_authoritative_required_action`,
  which asserts the returned blocker's `related_record_id` equals the
  actual `ComplianceObligation.id` created in the test.

## Known limitation (discovered, not fixed — reported per instruction)

While testing, a pre-existing D2.1 quirk was found: `aerospace_state_service.py`'s
`_evaluate_evidence_dimension` gates its `MISSING_EVIDENCE` blocker on
`ComplianceObligation.evidence_requirements.is_not(None)`, but a
`ComplianceObligation` created with `evidence_requirements=None` still
triggers that blocker. This is very likely SQLAlchemy's default JSONB
behavior storing a Python `None` as the JSON scalar `null` rather than a
true SQL `NULL` (so `IS NOT NULL` still matches) — a one-line fix would be
`evidence_requirements: Mapped[...] = mapped_column(JSONB(none_as_null=True), ...)`
on the model, or an explicit `and_(..., cast(evidence_requirements, JSONB) != null())`
in the query. **This was not touched.** Per this pass's explicit
instruction ("if a genuine contract defect is discovered... report the
exact contract defect and propose the smallest compatible change... do not
silently modify D2.1"), it is reported here for the D2.1 owner to
triage. D2.2's own tests were adjusted to assert the actual (current,
authoritative) upstream behavior rather than an idealized one — the
Recommendation Engine still preserves *both* blockers correctly regardless
of which is "correct" upstream.

## API

```
GET /api/v1/intelligence/assets/{asset_id}/recommendations -> AssetRecommendation
```

Same router (`app/api/v1/intelligence.py`), same permission
(`Permission.AIRCRAFT_READ`), same tenant-isolation pattern as every other
D2.2 endpoint — `organization_id` from `current_user` only, `NotFoundError`
(→ 404) for cross-tenant or nonexistent assets.

## Tenant isolation / authorization

Identical to Pass 1/2: `require_permission(Permission.AIRCRAFT_READ)`,
verified by `test_recommendation_is_tenant_scoped` and
`test_recommendation_invalid_asset_raises_not_found`.

## Tests (12, all passing)

1. NOMINAL → `NO_ACTION_REQUIRED`
2. DEGRADED (open MINOR finding) → `MONITOR`
3. RESTRICTED (NON_COMPLIANT obligation) → `ACTION_REQUIRED`, authoritative
   `required_action`/`resolution_action`/traceability verified
4. GROUNDED_INTEL (active AOG) → `IMMEDIATE_ACTION_REQUIRED`
5. UNKNOWN_INTEL (zero obligations) → `INSUFFICIENT_DATA`, UNKNOWN preserved
6. Multiple blockers preserved and deterministically ordered
7. DEPLOYMENT-domain blocker with no authoritative action → `RESOLVE_BLOCKER`
   fallback using the blocker's own description
8. Unresolved CRITICAL finding surfaced as an action item
9. Priority/risk/readiness context propagation
10. Deterministic repeated execution (same inputs → byte-identical outputs)
11. Tenant isolation
12. Invalid asset

## Non-autonomous guarantee

The Recommendation Engine performs zero writes. It calls only
`get_asset_decision` (read-only) and classifies its output in memory. It
never creates, updates, or closes a `WorkOrder`/`Task`/`ComplianceObligation`/
`Evidence`/`Finding`/`InspectionRequirement` row, never changes
`Asset.status` or any operational/compliance/readiness state, and calls no
LLM.

## Future AI Assistant integration boundary

The AI Assistant (not built in this pass) will consume
`AssetRecommendation` (and its full upstream chain: readiness, risk,
priority, decision, and the Aerospace Intelligence State beneath all of
them) to **explain and summarize** — e.g. turning
`action_category="PERFORM_REQUIRED_ACTION"`, `action="Execute corrective
action and attach verified evidence."` into a natural-language brief. The
LLM must never determine `recommendation_state`, choose `action_category`,
or invent an `action`/`resolution_condition` — those remain exclusively the
deterministic backend's responsibility, as verified by this pass's tests.
