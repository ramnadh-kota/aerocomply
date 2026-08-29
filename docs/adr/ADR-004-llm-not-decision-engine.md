# ADR-004 — LLM Is Not the Compliance Decision Engine

## Status
Accepted

## Context
AeroComply's conclusions can affect airworthiness determinations. LLMs are fluent but not deterministic, not reliably faithful to structured source data, and cannot be audited step-by-step the way a rule evaluation can. Aviation compliance requires reproducible, explainable, appealable decisions. Using an LLM as the decision-maker would make every compliance conclusion probabilistic and non-reproducible — unacceptable for this domain and explicitly prohibited by CTO directive.

## Decision
Compliance decisions flow exclusively through the deterministic rules engine (§12 of FOUNDATION.md):

```
User/Aviation Data → Structured Data → Rules Engine → System Determination → AI Explanation → Human Decision
```

Never:

```
User Data → LLM → Compliance Decision
```

The AI layer is invoked only after a `system_result` already exists, operates read-only against already-computed assessments and retrieved source text, and has no code path — no database credential, no API route, no service-to-service call — capable of writing to `applicability_assessments.system_result`, `applicability_rules`, or `regulatory_requirements`. This is enforced structurally (separate service identity/DB role for the AI module, per ADR-001), not just by prompt instructions.

## Alternatives Considered
- **LLM-assisted rule authoring with LLM-as-verifier of its own output**: rejected — still places the LLM in the causal chain of a compliance decision, even if "double-checked"; the CTO directive's Core Engineering Principle is explicit that AeroComply must be deterministic before it is intelligent.
- **LLM decision with mandatory human sign-off on every single case**: rejected as the *sole* control — human review fatigue leads to rubber-stamping; the deterministic engine must produce the candidate decision so human review is reviewing a traceable, reproducible artifact rather than an opaque LLM judgment.

## Consequences
- Every compliance conclusion is reproducible: re-running the same rule version against the same data version yields the same `system_result`, always.
- Rule-authoring work (translating regulatory text into `ApplicabilityRule.predicate`) is a human/engineering task, potentially AI-*assisted* as a drafting aid, but never AI-*decided* — drafts always land in a human review queue (§11).
- AI value is real but bounded: explanation, retrieval, comparison, gap-identification — never verdict generation.

## Reversal Conditions
This is a foundational safety principle, not a scalability or convenience tradeoff, and should not be reversed as the product matures — only the *scope* of what the deterministic engine can express should grow (richer predicates, more requirement types), never the requirement that it, not the LLM, produces `system_result`.
