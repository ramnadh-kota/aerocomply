"""Structured response schema for the Lisa agent endpoint. Field names
mirror frontend/lib/mock/ai/engine.ts::AiResponse (whatIFound/whyItMatters/
priority/... in camelCase) so AIResponseView can render both the
deterministic mock engine's output and this backend's output through the
same component without a fork."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AiButton(BaseModel):
    label: str
    href: str


class LisaAskRequest(BaseModel):
    question: str
    conversation_history: list[str] | None = None
    current_entity: str | None = None


class LisaAskResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    question: str
    headline: str
    narrative: list[str] = Field(default_factory=list)
    priority: str | None = None
    whatIFound: list[str] = Field(default_factory=list)
    whyItMatters: str | None = None
    recommendedNextStep: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    whoShouldAct: str | None = None
    relatedRecords: list[AiButton] = Field(default_factory=list)
    confidenceState: str = "PARTIAL_DATA"
    actionCategory: str = "INFORMATION"
    source: str = "AI_AGENT"
    # M5.2 -- populated only when a get_intelligence_context tool call
    # occurred during this request; reuses the frontend's existing
    # `missing` field name/semantics (frontend/lib/mock/ai/engine.ts's
    # `insufficient()` helper) rather than inventing a competing
    # "uncertainty" field. Verbatim from IntelligenceContext.uncertainty --
    # never derived from or overridable by the model's own prose.
    missing: list[str] = Field(default_factory=list)
    # Machine-readable pointer to which authoritative context grounded this
    # answer, independent of whatever the model's narrative text says.
    grounding: dict | None = None
