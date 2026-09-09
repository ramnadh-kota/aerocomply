# Lisa Architecture — Current State

This document describes what is **actually implemented and verified** as of
commit `8ffbab3`. It does not describe an aspirational target. Where a
capability described in earlier planning prompts is not built, it is listed
explicitly under "Not implemented" rather than omitted.

## Architecture (as built)

```
USER
 ↓
Lisa UI (frontend/components/ai/AIConsole.tsx)
 ↓
DEMO mode?  ──yes──▶ local deterministic engine (frontend/lib/mock/ai/engine.ts)
 │no (REAL mode)
 ↓
POST /lisa/ask (backend/app/api/v1/lisa.py)
 ↓
get_current_user (JWT) → organization_id + roles, never client-supplied
 ↓
ask_lisa (backend/app/services/ai/agent_service.py)
 ↓
deterministic safety pre-check (backend/app/services/ai/safety.py)
 ↓
AIProvider.complete() — AnthropicProvider if ANTHROPIC_API_KEY set,
                         else NotConfiguredProvider (always raises)
 ↓
tool_use loop (max 6 round trips) → execute_tool()
 ↓
per-tool RBAC check (permissions_for_roles(user.roles))
 ↓
domain service (aircraft_service, work_order_service, part_service, ...)
 ↓
PostgreSQL, tenant-scoped by organization_id
 ↓
deterministic safety post-check on tool results and final text
 ↓
structured LisaAskResponse
```

The LLM never computes a business fact (TAT, release readiness, vendor
score, shortage state) itself — those are always the tool's return value,
already computed by the same deterministic domain service the REST API
uses. The LLM only selects tools and synthesizes prose from what they
return.

## Fallback policy (REAL vs DEMO)

This is the single most safety-relevant piece of the frontend integration
and was the subject of two dedicated fixes this session (commits `1892737`
and `42e6c73`).

- **DEMO mode**: always answers from the frontend's local demo dataset.
  This is the expected, honestly-labeled behavior, not a fallback.
- **REAL mode** (`isRealModeSession` in `AIConsole.tsx` — authenticated,
  has a token, `DataMode === "REAL"`): a question is classified before
  anything else as either **general knowledge** (glossary terms, "tell me
  what not to do" — see `isGeneralKnowledgeQuestion` in `engine.ts`) or
  **record-specific**.
  - General-knowledge questions always answer locally, regardless of
    backend availability — this is not demo data, it's the same
    deterministic safety/glossary logic the backend agent would use.
  - Record-specific questions in REAL mode **never** fall back to the
    demo dataset, on any failure: backend unreachable
    (`BACKEND_UNAVAILABLE`), AI provider not configured
    (`AI_PROVIDER_UNAVAILABLE`), or a 403
    (`PERMISSION_DENIED`) all produce an explicit failure-state answer
    instead. This holds even after the AI-provider-unconfigured state is
    already known for the session (the bug fixed in `42e6c73`: once
    `aiNotConfigured` was sticky, every subsequent question — not just the
    first — was silently falling through to the demo engine).

## Tool registry

`backend/app/services/ai/tools.py` — 26 tools as of this commit, one per
domain read operation. Every tool:
- wraps an existing domain service function (never recomputes business
  logic)
- takes `organization_id` from the authenticated `CurrentUser` only
- is gated by a `required_permission` enforced in `execute_tool()` via
  `permissions_for_roles()` — the same permission its equivalent REST
  endpoint requires

Domains covered: Aircraft, WorkOrder/Task, Evidence, InspectionRequirement,
TAT, ReleaseReadiness, Part, PartRequirement (shortages),
InventoryTransaction, Vendor, VendorPartAvailability (vendor fit),
ProcurementRequest, PurchaseOrder, AogEvent, MaintenanceRequirement
(due status), DeferredItem, ComplianceAssessment, RegulatoryDocument, MRO
Control Center.

**All 26 tools are read-only.** Lisa has no mutation capability today —
enforced structurally by `test_no_mutation_tools_exist_in_registry` in
`tests/integration/test_ai_tools.py`. This means the "Lisa Actions"
READ/RECOMMEND/PREPARE/EXECUTE/APPROVE/RELEASE separation described in
planning prompts is trivially satisfied on the EXECUTE/APPROVE/RELEASE
side: those don't exist as Lisa capabilities, so there is nothing to gate
further. If a mutation tool is ever added, it must go through the same
explicit-intent + permission + deterministic-validation + audit-event
requirement, and the structural test above must be updated deliberately
(not silently pass).

## Safety layer

`backend/app/services/ai/safety.py` (backend) and the mirrored
`AIRWORTHINESS_GUARD_PATTERNS` (`frontend/lib/mock/ai/engine.ts`, DEMO
mode / REAL-mode general-knowledge fallback). Runs **outside** the model:
against the raw question, against tool results before they reach the
model, and against the model's final synthesized text. Refuses:
airworthiness/certification/release-to-service questions, and bypass
requests for inspection/RII/evidence/checklist/sign-off/authorization/MEL/
unapproved-part/open-finding-release. See
`backend/tests/unit/test_ai_safety.py` and the safety-matrix block in
`frontend/tests/ai/lisa-matrix.test.ts` for the exact covered phrasings —
these are the actual regression contract, not this document.

General safety-guidance meta-questions ("tell me what not to do") and
glossary questions (RII, TAT, MEL, evidence gate, release readiness) are
answered directly without any tool call or record dependency — see
`isGeneralKnowledgeQuestion`/`answerGeneralSafetyGuidance`/
`answerGlossaryQuestion` in `engine.ts`.

## AI provider configuration

`backend/app/core/config.py`:
- `ANTHROPIC_API_KEY` — env var, empty string default. Empty →
  `NotConfiguredProvider`, whose `complete()` always raises
  `AIProviderNotConfiguredError`. It never fabricates a response.
- `anthropic_model` — env-overridable, defaults to `claude-sonnet-4-5`.
- `ai_request_timeout_seconds` — defaults to `30.0`.

**In this development environment, `ANTHROPIC_API_KEY` is not set.**
`POST /lisa/ask` returns an honest `503 {"error": {"code":
"ai_not_configured", ...}}` for every question, verified live via curl
against a running local backend instance and via
`tests/integration/test_ai_not_configured.py`.

## Multi-turn context

`conversation_history` (last 5 questions) and `current_entity` are passed
from the frontend to `/lisa/ask` and included in the model's context. The
model resolves "it"/"that aircraft" pronoun references itself using this
history — there is no separate backend entity-resolution service. This has
not been exercised against a real model response in this environment
(no `ANTHROPIC_API_KEY` configured here), only verified structurally (the
context is correctly assembled and sent).

## Not implemented (stated explicitly, not silently absent)

- **Proactive intelligence / daily brief wired to backend data.** The
  frontend's `getProactiveAlerts`/`getDailyBrief`/`getOperationalPriorities`
  (`frontend/lib/mock/ai/proactive.ts`) still compute entirely from the
  frontend demo dataset. No backend equivalent exists, and the Lisa UI's
  "Today's Operational Picture" / "Lisa's Priorities" panels are not
  connected to `get_control_center_summary` or any other backend tool.
- **Regulatory applicability rule evaluation** (condition-tree AND/OR/NOT
  over aircraft-type/MSN-range/engine-type) — see
  `backend/app/models/compliance.py`'s docstring. `ComplianceAssessment`
  records applicability directly; nothing evaluates a rule tree.
- **Aircraft flight-hour/flight-cycle utilization tracking** — see
  `backend/app/services/maintenance_service.py`'s docstring.
  FLIGHT_HOURS/FLIGHT_CYCLES maintenance requirements always report
  `UNKNOWN`.
- **Live regulatory synchronization** — `get_regulatory_provider_status`
  always returns `NOT_CONFIGURED` for every authority (DGCA/FAA/EASA/
  CASA/UK_CAA). No provider adapter exists.
- **Frontend integration for the M3 domains beyond Lisa's tool access.**
  Parts/Inventory/Vendor Fit/Procurement/AOG/Maintenance/Deferred/
  Compliance/Regulatory pages in the frontend still render entirely from
  `frontend/lib/mock/*` — none of the M3 backend REST endpoints are called
  by any page outside of Lisa's own tool calls in REAL mode.
- **End-to-end multi-turn / proactive / role-aware verification against a
  real model response.** Everything downstream of "the model produces a
  tool call" is structurally correct and unit-testable (context assembly,
  RBAC gate, tenant scoping), but has not been observed running against
  an actual Anthropic API call in this environment, because no API key is
  configured here. This is a genuine verification gap, not a claim that
  it doesn't work — it means "verified by code review and unit tests," not
  "verified end-to-end."
- **Production deployment.** The backend is not deployed anywhere the
  production Vercel frontend can reach. `NEXT_PUBLIC_API_BASE_URL` in
  production is unset, so REAL mode on the live site cannot reach any
  backend at all — it will correctly show `BACKEND_UNAVAILABLE` for
  record-specific questions (per the fallback policy above) rather than a
  demo answer, but no real Lisa capability is usable in production today.
