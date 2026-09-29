# Compliance & Readiness Integration (H7)

**H7 does not independently certify compliance or modify authoritative
readiness.**

See `docs/H7_MRO_INTELLIGENCE.md` for the overall H7 architecture,
maintenance-candidate lifecycle, and conflict-detection list. This document
covers how H7 integrates with the existing compliance and readiness
domains specifically: vocabulary reuse, the evidence chain, the
authoritative/advisory split, missing-data handling, freshness, and
reconciliation's effect (or lack thereof) on authoritative tables.

## Compliance integration approach

`get_compliance_impact` (`app/services/mro_intelligence_service.py`) reads
`ComplianceObligation` rows directly and maps each obligation's **verbatim,
existing** `ComplianceState` value to an `ComplianceImpactState` through a
fixed dictionary (`_COMPLIANCE_IMPACT_MAP`):

| `ComplianceState` | H7 `ComplianceImpactState` |
|---|---|
| `NOT_EVALUATED` | `UNKNOWN` |
| `NOT_APPLICABLE` | `NOT_APPLICABLE` |
| `PENDING` | `DUE` |
| `DUE` | `DUE` |
| `OVERDUE` | `OVERDUE` |
| `IN_PROGRESS` | `DUE` |
| `COMPLIANT` | `COMPLIANT` |
| `NON_COMPLIANT` | `NON_COMPLIANT` |
| `BLOCKED` | `REQUIRES_REVIEW` |
| `REVIEW_REQUIRED` | `REQUIRES_REVIEW` |

This is a **direct mapping of the existing `ComplianceState` vocabulary,
never a parallel one** — the module docstring states this explicitly. H7
introduces exactly one new vocabulary layer on top
(`ComplianceImpactState`, itself just a coarser grouping of the existing
states), and every `ComplianceImpactObligation` record still carries the
source obligation's `state` field verbatim alongside the derived `impact`,
so nothing about the original compliance record is lost or paraphrased.

Open diagnostic candidates are correlated in purely for **explanatory
context** — when an obligation's impact is `NON_COMPLIANT`, `OVERDUE`, or
`REQUIRES_REVIEW`, any open `HUMSDiagnosticCandidate`s on the asset are
attached as `correlated_signals` with an explanatory note. This never
changes the obligation's own `state` or `impact` classification; it only
enriches the explanation.

## The evidence chain

`detect_conflicts`'s `COMPLIANCE_VS_EVIDENCE` check is H7's evidence-chain
guard: an obligation whose `status` is `COMPLIANT` but which carries no
`completed_at` **and** no `verified_at` timestamp is flagged as a
`MEDIUM`-severity conflict — `COMPLIANT` with no completion evidence is
treated as a data-integrity concern, not silently accepted. This check
never changes the obligation's status; it only surfaces the gap for a
human reviewer, consistent with H6's "detected, not silently corrected"
convention for consistency issues.

## Readiness integration

`get_readiness_impact` calls
`readiness_intelligence_service.get_asset_readiness_intelligence` for the
asset's authoritative `readiness_state` (`READY` / `BLOCKED` / `UNKNOWN`)
and layers a deterministic classifier on top — **a classifier, not a
score**:

1. Authoritative `readiness_state == "BLOCKED"` → H7 impact
   `RESTRICTED_OPERATION`.
2. Authoritative `readiness_state == "UNKNOWN"` → H7 impact `UNKNOWN`,
   never silently resolved to a positive impact.
3. Otherwise (`readiness_state == "READY"`), H7 layers HUMS/compliance/
   open-candidate signals on top of an otherwise-ready asset, in this
   precedence order:
   - Any `HIGH`-priority `OPEN`/`UNDER_REVIEW` maintenance candidate →
     `READINESS_AT_RISK`.
   - Compliance impact in (`NON_COMPLIANT`, `OVERDUE`) → `REVIEW_REQUIRED`.
   - Any open HUMS diagnostic candidate with severity `HIGH`, or an open
     `MEDIUM`-priority maintenance candidate → `INSPECTION_REQUIRED`.
   - Any `OPEN`/`UNDER_REVIEW` candidate at all, or compliance impact in
     (`DUE`, `REQUIRES_REVIEW`) → `MAINTENANCE_DUE`.
   - Any prognostic record with a near-term/negative RUL estimate or
     `LOW` confidence → `MONITOR`.
   - Otherwise → `NO_IMPACT`.

## Authoritative readiness vs. H7's readiness impact — always two fields

`ReadinessImpactResult` (`app/schemas/mro_intelligence.py`) carries **both**
fields, always, and its docstring is explicit that they must never be
merged:

```python
class ReadinessImpactResult(BaseModel):
    """Carries BOTH the authoritative readiness_state (from
    readiness_intelligence_service, unmodified) and H7's own
    readiness_impact classification as separate fields. NEVER merge them --
    see this module's docstring and mro_intelligence_service's derivation
    docstring."""
    asset_id: uuid.UUID
    authoritative_readiness_state: Literal["READY", "BLOCKED", "UNKNOWN"]
    readiness_impact: ReadinessImpactLevel
    ...
```

`authoritative_readiness_state` is read straight from
`readiness_intelligence_service` and is **never mutated** by H7 — it is
passed through unmodified in every result that includes it
(`ReadinessImpactResult`, `AssetMROIntelligence`). `readiness_impact` is
H7's own advisory classification, computed as described above and stored
nowhere — it is recomputed on every call, never persisted, and never
written back to any readiness table.

These stay two separate fields, never merged into one value, because they
answer two different questions with two different authorities behind them:
`authoritative_readiness_state` answers "is this asset certified ready to
fly, according to the system that owns that determination" — a question
only `readiness_intelligence_service` is authorized to answer. `readiness_impact`
answers "given HUMS/compliance/maintenance-candidate signals, what should a
reviewer additionally be aware of" — an advisory H7 opinion layered on top.
Collapsing them into one field would let an advisory classification (e.g.
`READINESS_AT_RISK`, generated from HUMS heuristics) be mistaken for, or
silently override, the authoritative certification-relevant readiness
state — exactly the failure mode this design avoids by construction, the
same way H6's Digital Twin never persists a derived state that could drift
from its authoritative source.

## Compliance impact result shape

`ComplianceImpactResult` returns, per asset:

- `availability` (`AVAILABLE` / `DATA_UNAVAILABLE`)
- `obligations: list[ComplianceImpactObligation]` — each carrying the
  obligation's own `obligation_id`, `requirement_id`, verbatim `state`,
  derived `impact`, `due_date`, `correlated_signals`, and `explanation`
- `overall_impact` — the highest-precedence impact across all obligations
  (precedence order: `NON_COMPLIANT` > `OVERDUE` > `REQUIRES_REVIEW` >
  `DUE` > `UNKNOWN` > `COMPLIANT` > `NOT_APPLICABLE`)
- `explanation` — a human-readable list stating how `overall_impact` was
  derived
- `evaluated_at`

## Missing-evidence behavior

When an asset has **no** compliance obligations at all,
`get_compliance_impact` explicitly returns `overall_impact = "UNKNOWN"`
and `availability = "DATA_UNAVAILABLE"`, with an explanation stating "No
compliance obligations found for this asset; overall impact is UNKNOWN,
not COMPLIANT." The absence of obligation data is **never** rendered as a
positive `COMPLIANT` state — it renders `UNKNOWN`/`DATA_UNAVAILABLE`,
following the same `DataAvailability` convention H6's Digital Twin
established (`app/schemas/digital_twin.py`): any sub-state whose source
data is missing is explicit, never silently defaulted to a positive state.

The same discipline applies to readiness: authoritative `readiness_state
== "UNKNOWN"` propagates to H7's `readiness_impact = "UNKNOWN"` rather than
being resolved to `NO_IMPACT` or any other positive-sounding value.

## Freshness handling

`MaintenanceIntelligenceCandidate.data_freshness` is stamped `"AVAILABLE"`
at candidate-generation time (`generate_maintenance_candidates`), recording
the freshness state of the data that produced the candidate.

For prognostics specifically, `detect_conflicts`'s `PROGNOSTIC_FRESHNESS`
check flags (severity `LOW`) any `HUMSPrognosticRecord` whose `quality` or
`confidence` is `STALE` while authoritative readiness is `READY` —
surfacing the case where a readiness determination may be resting on
degradation data that is no longer current. This check is report-only; it
never blocks or overrides the readiness read.

## Conflicts relevant to compliance/readiness

Two of H7's six conflict checks (see `docs/H7_MRO_INTELLIGENCE.md` for the
full list) are compliance/readiness-specific:

- **`READINESS_VS_COMPLIANCE`** (severity `HIGH`) — authoritative readiness
  is `READY` while a compliance obligation's impact is `NON_COMPLIANT` or
  `OVERDUE`. This is the highest-severity check H7 defines, because it
  represents authoritative readiness data and authoritative compliance
  data pointing in contradictory directions.
- **`COMPLIANCE_VS_EVIDENCE`** (severity `MEDIUM`) — a `COMPLIANT`
  obligation with no completion evidence timestamp, as described above.

Both are reported via `IntegrationConflict` rows with `source_a`/`source_b`
`SourceLineageRef`s pointing at the specific obligation/readiness records
involved — never auto-resolved.

## Reconciliation's effect on authoritative tables

`reconcile_asset_mro_intelligence` operates **only** on
`MaintenanceIntelligenceCandidate` rows (setting `status = RESOLVED` and
stamping `resolved_at` when the underlying signal has cleared, or flagging
a candidate for human review when it can no longer be corroborated). It
does **not** touch `ComplianceObligation`, readiness state, `WorkOrder`,
`Finding`, or any HUMS record — reconciliation never writes to any table
outside H7's own candidate table, and it never changes a
`ComplianceObligation.status` or an asset's authoritative readiness
determination.

## Safety boundaries

- H7 never writes to `ComplianceObligation.status` or any readiness-state
  field — both are read-only inputs.
- `authoritative_readiness_state` is always passed through unmodified,
  never merged with or overwritten by H7's `readiness_impact`.
- Compliance impact is always a direct mapping of the existing
  `ComplianceState` vocabulary — H7 never invents a competing compliance
  taxonomy.
- Missing compliance or readiness data always renders `UNKNOWN`/
  `DATA_UNAVAILABLE`, never a fabricated `COMPLIANT`/`READY`/`NO_IMPACT`
  value.
- Conflicts touching compliance or readiness are reported only, never
  auto-resolved, and reconciliation never mutates an authoritative table.
- **H7 does not independently certify compliance or modify authoritative
  readiness.**

## Known limitations

- The `overall_impact` precedence order and the readiness-impact
  classifier's rule ordering are documented deterministic heuristics, not
  derived from any regulatory compliance-scoring or reliability-engineering
  standard.
- Compliance/readiness correlation with HUMS signals is limited to
  presence/absence and severity counts (e.g. "N open diagnostic
  candidates") — there is no weighted or probabilistic combination of
  compliance and HUMS evidence.
- The `MONITOR` readiness-impact branch's RUL threshold (`rul_estimate <
  0`, i.e. already past the estimated threshold-crossing point) and the
  operational-impact RUL threshold (`< 25` usage-units) are placeholder
  values, not derived from any certified maintenance-interval standard.
- H7 does not evaluate compliance requirements that have no corresponding
  `ComplianceObligation` row for the asset — it correlates only what the
  authoritative compliance domain has already recorded.
- No async/background recomputation: compliance impact, readiness impact,
  and operational impact are all computed synchronously on read, with no
  persisted cache — consistent with every other HUMS/H6/H7 milestone's
  documented async boundary.
