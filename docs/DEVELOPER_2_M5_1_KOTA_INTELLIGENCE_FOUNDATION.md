# M5.1 — Kota Intelligence Foundation

## Phase 1 — Audit (performed before any code)

**Existing AI infrastructure found — Lisa is not a stub.** A subagent audit
(verified directly by reading the key files myself) found a fully working
agent stack already in place:

- **Backend**: `POST /api/v1/lisa/ask`, `GET/POST /api/v1/lisa/context`
  (`app/api/v1/lisa.py`). `ask_lisa()` (`app/services/ai/agent_service.py`)
  runs: safety check → deterministic entity/reference resolution
  (`message_resolution_service.py`) → deterministic intent orchestration
  (`orchestration_service.investigate()`, answers a closed set of
  operational questions via direct tool calls, **no LLM involved**) → only
  then a bounded (6 round-trip) real LLM tool-loop for unmatched questions.
- **Provider abstraction already exists**: `AIProvider` (abstract base,
  `app/services/ai/providers/base.py`) with `AnthropicProvider`,
  `OpenAICompatibleProvider`, and `NotConfiguredProvider` (always raises
  `AIProviderNotConfiguredError`, never fabricates) — resolved by
  `get_ai_provider()` from `ANTHROPIC_API_KEY`/`AI_PROVIDER`/`AI_BASE_URL`/
  `AI_MODEL` config, exactly the honest-failure convention this milestone
  asked for.
- **Tool registry already exists**: `app/services/ai/tools.py`, 41 tools
  (now 42) prior to this pass, each a `ToolSpec` wrapping one existing
  service call, each gated by a `required_permission: Permission` checked
  against the caller's actual role grants (`_require_permission`) —
  identical enforcement to the REST API, never trusting model input for
  authorization.
- **System prompt already establishes the "LLM never computes" boundary**:
  "you never calculate or assert a number yourself... those are always
  computed by the tool, never by you" (pre-existing, `agent_service.py`).
- **Deterministic safety layer already exists**: `app/services/ai/safety.py`
  — regex guard applied to the question, every tool result, and the final
  synthesized text, refusing airworthiness/release/bypass-worthy content
  *before* it ever reaches the model.
- **Frontend**: `/ai` page (`AIConsole.tsx`) already has real/mock dual-path
  UX with an explicit `aiNotConfigured` state and fallback-reason tracking
  — the "provider unavailable" UI this milestone asked for already exists.
- **Gap confirmed**: none of the above consumed `IntelligenceContext` or
  any D2.2 service — no reference to `readiness`/`risk`/`priority`/
  `decision`/`recommendation`/`intelligence` anywhere in the Lisa stack
  before this pass (confirmed by direct grep).
- **No conversation/chat transcript model** exists (only
  `lisa_conversation_contexts` — current-entity pointers + recent
  questions, not a full message log) — out of scope for M5.1 per your
  brief ("does not need to build a complete persistent chat history
  system").

**Conclusion:** extending the existing Lisa backend/frontend is clearly
correct and required — a separate "Kota Intelligence" surface would
duplicate the provider abstraction, the permission-gated tool pattern, the
safety layer, and the frontend real/mock UX that already exist and work.
Nothing in M5.1 needed a new surface; it needed one new tool.

**Confirmation: no D1/D2.1/D2.2 intelligence logic was modified.** The
entire backend change is additive to two files already owned by the AI
layer (`app/services/ai/tools.py`, `app/services/ai/agent_service.py`) —
67 lines inserted, zero lines deleted, confirmed by `git diff --stat`.

## M5.1 architecture

```
User
  ↓
POST /api/v1/lisa/ask  (existing endpoint, unchanged)
  ↓
ask_lisa()  (existing orchestration, unchanged except system-prompt addition)
  ↓
LLM tool-loop calls get_intelligence_context(asset_id)  ← NEW (this pass)
  ↓
execute_tool()  (existing dispatcher — permission + organization_id enforced
                 identically to every other tool, unchanged)
  ↓
context_service.get_asset_intelligence_context()  (M4.5, unchanged)
  ↓
IntelligenceContext  (M4.5 contract, unchanged)
  ↓
LLM synthesizes prose from the tool's JSON result
  ↓
Safety layer re-checks the final text  (existing, unchanged)
  ↓
Grounded response with traceable source data
```

This is exactly the mandated chain: Operational Truth → D2.1 → D2.2 →
IntelligenceContext → Kota Intelligence → Explanation. The one new node is
the tool call; everything above and below it is pre-existing, untouched
infrastructure.

## IntelligenceContext integration

`app/services/ai/tools.py::_handle_get_intelligence_context` calls
`app.services.intelligence.context_service.get_asset_intelligence_context`
(M4.5, unchanged) and returns `context.model_dump(mode="json")` — the
entire `IntelligenceContext` contract, unmodified, with one field removed
before it reaches the model (see "Known limitations" below). No new
domain query, no new intelligence rule.

## Provider abstraction

No new abstraction was needed — `AIProvider`/`get_ai_provider()` already
existed and already satisfies "fail honestly and predictably ... never
silently return fabricated/demo AI responses" (confirmed:
`NotConfiguredProvider.complete()` always raises
`AIProviderNotConfiguredError`, and `lisa.py`'s `/ask` endpoint turns that
into an honest `503 ai_not_configured`).

## API contract

No new endpoint. `POST /api/v1/lisa/ask` (pre-existing) gains one new tool
in its registry. The request/response shape (`LisaAskRequest`/
`LisaAskResponse`, `app/schemas/ai.py`) is unchanged — a readiness/risk/
priority/decision/recommendation question now flows through the exact same
`headline`/`narrative`/`confidenceState`/`source` shape every other
question already uses, satisfying "do not blindly use a new path if
repository conventions indicate another structure."

## Security model

- The server, not the client, resolves tenant identity: `execute_tool`
  receives `user.organization_id` from the authenticated `CurrentUser`
  only; the tool call's `asset_id` argument (which the model supplies) is
  never trusted as an authority for tenant scope — `context_service`
  re-derives everything from `organization_id` and raises `NotFoundError`
  for any asset outside it.
- The client cannot submit a trusted `IntelligenceContext` — there is no
  code path anywhere that accepts one from the request; it is always
  server-constructed from the authoritative service.
- No credentials/secrets/internal authorization details are ever placed in
  a tool result — `IntelligenceContext` contains only aerospace intelligence
  fields (already reviewed for this in M4.5).

## Tenant isolation — verified by test, including the adversarial case

`test_cross_tenant_tool_call_attempt_never_leaks_another_orgs_asset`
(`tests/integration/test_lisa_intelligence_context_tool.py`) uses a
scripted fake `AIProvider` that requests **another tenant's** asset_id —
simulating a model that was tricked (by a crafted question or a prompt-
injection attempt) into asking for it. The test proves the tool call fails
safely (`NotFoundError` → tool-error content) and the response never
contains the other tenant's real intelligence data. This is the concrete,
deterministic guarantee behind "prompt injection resistance": the boundary
is enforced by `execute_tool`'s own `organization_id` derivation, not by
trusting or filtering the model's language.
`test_unrecognized_tool_name_from_a_compromised_provider_is_rejected`
additionally proves a scripted "ignore all prior instructions" attempt that
requests a nonexistent tool is rejected outright (`Unknown tool`), not
silently ignored or hallucinated around.

## AI authority boundary

Enforced two ways, per your Section 3:
1. **Structurally**: the tool is read-only (calls only
   `get_asset_intelligence_context`, itself read-only per M4.5's own
   verification); there is no tool anywhere in the registry that could let
   the model mutate compliance/evidence/readiness/operational state (see
   the pre-existing `test_no_mutation_tools_exist_in_registry` structural
   test, which now also covers this new tool by name-pattern).
2. **In the system prompt** (the new addition): explicit instruction to
   distinguish FACT / DETERMINISTIC DECISION / DETERMINISTIC RECOMMENDATION
   / AI EXPLANATION, to never override or recompute any of the five
   deterministic values, and to never invent a blocker/citation not
   present in the tool's own data.

## UNKNOWN semantics

`test_get_intelligence_context_tool_never_collapses_unknown_to_positive`
proves the tool passes `UNKNOWN_INTEL`/`UNKNOWN`/`INSUFFICIENT_DATA`
through unchanged for a fresh asset with no evaluated obligations. The
system prompt separately instructs the model: "If any field is UNKNOWN,
UNKNOWN_INTEL, or INSUFFICIENT_DATA, say so explicitly... never restate it
as ready, safe, low risk, or nominal." The former is a hard, tested
guarantee; the latter (whether the model's own prose honors this) is
necessarily a soft, prompt-level guarantee, same as every other existing
Lisa boundary (e.g. "never calculate TAT yourself") — no test environment
here has a configured `ANTHROPIC_API_KEY`, so the model's actual prose
compliance cannot be exercised end-to-end in CI; documented as a known
limitation below.

## Traceability

The tool result carries D2.1's full-detail blockers (`blocker_id`,
`what_condition`, `why_condition`, `source_ref`, `regulatory_ref_number/
title`, `required_action`, `resolution_action`) via `IntelligenceContext`'s
`aerospace_state` section, and D2.2's blockers (with `related_record_id`/
`related_record_type`) via the `readiness`/`recommendation` sections — the
same traceability M4.5 already verified, now reachable through the tool
loop unchanged.

## Prompt / grounding design

The system-prompt addition (see `agent_service.py`) does exactly what
Section 11 asks: it enforces grounding, uncertainty preservation, no
decision override, and no unsupported claims — it does not itself state
any aerospace rule (no thresholds, no compliance logic); those remain
entirely in the deterministic backend the tool calls.

## Test coverage (8 new tests)

`test_ai_tools.py` (+5): tool returns the full contract; UNKNOWN never
collapses; tenant isolation; permission enforcement (`ForbiddenError` for
a role with zero grants); tool appears in `anthropic_tool_schemas()`.
`test_lisa_intelligence_context_tool.py` (new, 3): cross-tenant tool-call
attempt fails safely (the prompt-injection-resistance test); a legitimate
same-tenant call flows UNKNOWN data through the tool loop into the final
synthesized text unaltered; an unrecognized/compromised tool name is
rejected. Full regression: **1499 passed, 0 failed** (baseline 1491 + 8
new), ruff clean, mypy clean on both touched files.

## Known limitations

- **The safety-layer false positive this pass discovered and fixed**:
  D2.1's `AerospaceIntelligenceState.disclaimer` field contains the phrase
  "Release to Service (RTS) signature," which matches
  `safety.py`'s `release( it| the aircraft)? to service` guard regardless
  of the surrounding negation — meaning every single call to this new tool
  would have had its entire result withheld by the safety layer as a false
  positive (confirmed by test before the fix). Fixed by dropping the
  `disclaimer` field specifically from this tool's returned payload (the
  system prompt already conveys the same non-authoritative boundary
  directly) — the shared safety-layer regex itself was not touched, since
  it is correctly conservative for genuinely user-authored free-text
  fields elsewhere in the tool registry.
- **No end-to-end real-model test**: no `ANTHROPIC_API_KEY` is configured
  in this environment (confirmed by existing test
  `test_ask_falls_through_to_provider_for_non_operational_question`
  asserting `503 ai_not_configured`), so the model's actual prose
  compliance with the new system-prompt instructions cannot be verified in
  CI — only the deterministic tool-boundary guarantees (tenant isolation,
  permission enforcement, UNKNOWN passthrough) are hard-tested; the
  prose-level guarantees are the same class of soft, prompt-level
  guarantee every other existing Lisa boundary already relies on.
- **No persistent chat/transcript log** — out of scope per your brief;
  `lisa_conversation_contexts` (current-entity pointer + recent questions)
  is unchanged and sufficient for this milestone.
- Frontend was not touched this pass — the existing `/ai` console already
  routes real questions through `/lisa/ask`, so a readiness/risk/priority/
  decision/recommendation question now works through the existing UI with
  zero frontend changes required.

## M5.2 handoff

A future pass can: (a) exercise the real model path once a provider key is
configured (staging/demo environment), to validate prose-level UNKNOWN/
boundary compliance beyond the deterministic guarantees tested here; (b)
extend `orchestration_service.investigate()` with a deterministic intent
for common intelligence questions (e.g. "why is X not ready") so they
resolve without an LLM call at all, mirroring how AOG/release-readiness
questions already do — consistent with this repo's stated preference for
deterministic-first answering; (c) consider whether `IntelligenceContext`
should be summarized/truncated for very large fleets before reaching the
model, if a future "explain the whole fleet" question is added (out of
scope today — the tool is per-asset only, matching the existing per-asset
tool pattern).
