# ADR-001 — Modular Monolith Architecture

## Status
Accepted

## Context
AeroComply MVP needs to ship a coherent set of tightly-related capabilities (fleet data, regulatory data, rules engine, evidence, AI explanation) with a small team, under a hard requirement that certain layers (rules engine vs. AI) never share write paths. A microservices split at this stage would multiply operational surface (deployment, service discovery, distributed tracing, network failure modes) before the domain boundaries have proven stable through real usage.

## Decision
Build a single deployable FastAPI application organized into internal modules with enforced boundaries (`rules_engine/`, `ai/`, `graph/`, `document_intel/`, `services/`, `api/`), each with its own restricted access to the database layer. Module boundaries are enforced by code review and import-linting rules, not network boundaries.

## Alternatives Considered
- **Microservices from day one**: rejected — premature given unproven domain boundaries and small team; would slow M0–M6 delivery substantially with deployment/ops overhead unrelated to product risk.
- **Single undifferentiated app with no internal module boundaries**: rejected — the "AI must never write compliance data" requirement is a correctness/safety property, not just a style preference; it needs enforced separation even inside one deployable, or it silently erodes over time.

## Consequences
- Faster initial delivery, simpler local dev (`docker-compose up`), simpler transactions across modules (e.g. rules engine writing an assessment and audit event in one DB transaction).
- Scaling is coarse-grained (the whole app scales together) until/unless split later.
- Requires discipline (linting, code review, tests) to keep the AI module's DB access genuinely read-only, since there's no network boundary forcing it.

## Reversal Conditions
Reconsider if: a specific module (e.g. document ingestion, or AI/RAG) develops meaningfully different scaling, deployment cadence, or team-ownership needs than the rest of the app; or if the enforced-by-convention boundary around AI write access proves insufficient in practice and needs a hard network/process boundary instead.
