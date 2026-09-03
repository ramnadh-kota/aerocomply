"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { answerQuestion, CATEGORIZED_QUESTIONS, type AiResponse } from "@/lib/mock/ai/engine";
import { getProjectAnalytics, getAircraftAnalytics, getFleetAnalytics } from "@/lib/mock/ai/analytics";
import { AIResponseView } from "@/components/ai/AIResponseView";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { AI_NAME, AI_DESCRIPTION, COMPANY_NAME } from "@/lib/brand";

interface Turn {
  id: string;
  question: string;
  response: AiResponse;
  askedAt: string;
}

// Lisa UX redesign — split operational-copilot layout. Presentation-only
// restructuring: still calls the SAME answerQuestion() engine, still one
// AiResponse shape, still one audit event per question. What changed is
// how a question and its answer are visually connected: a single, always-
// visible "active" answer pane (question header + full response) instead
// of dumping every turn into one long reversed scroll — plus a compact,
// clearly-newest-first history list beneath it that promotes a past turn
// back into the active pane on click. Question and answer can never be
// ambiguous: the active pane always shows exactly one question and its
// one response together.

export function AIConsole({
  initialProjectId,
  initialAircraftId,
  initialQuestion,
}: {
  initialProjectId?: string;
  initialAircraftId?: string;
  initialQuestion?: string;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const { addAuditEvent, auditLog } = useMroState();
  const askedInitial = useRef(false);

  function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    const previousQuestion = turns.length > 0 ? turns[turns.length - 1].question : undefined;
    const response = answerQuestion(trimmed, { projectId: initialProjectId, aircraftId: initialAircraftId, auditLog, previousQuestion });
    const turn: Turn = { id: response.id, question: trimmed, response, askedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) };
    setTurns((prev) => [...prev, turn]);
    setActiveId(turn.id);
    setDraft("");
    addAuditEvent({
      actor: `${AI_NAME} (Prototype)`,
      actorRole: "AI Assistant",
      action: "ai.analysis_generated",
      objectType: "AiQuery",
      objectLabel: trimmed.length > 80 ? `${trimmed.slice(0, 80)}…` : trimmed,
      previousState: null,
      newState: response.insufficientData ? "INSUFFICIENT_DATA" : "ANSWERED",
      // M5.5 decision traceability: record the recommendation basis without
      // exposing hidden chain-of-thought — just what was concluded.
      reason: response.insufficientData ? (response.missing ?? []).join("; ") : response.headline,
    });
  }

  useEffect(() => {
    if (askedInitial.current || !initialQuestion) return;
    askedInitial.current = true;
    ask(initialQuestion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  // Newest first, always — the active turn defaults to the most recent
  // question asked, never an arbitrary/first one.
  const ordered = [...turns].reverse();
  const active = turns.find((t) => t.id === activeId) ?? turns[turns.length - 1];
  const history = ordered.filter((t) => t.id !== active?.id);

  const projectAnalytics = initialProjectId ? getProjectAnalytics(initialProjectId) : null;
  const aircraftAnalytics = initialAircraftId ? getAircraftAnalytics(initialAircraftId) : null;
  const fleetAnalytics = !projectAnalytics && !aircraftAnalytics ? getFleetAnalytics() : null;
  const hasContext = !!(projectAnalytics || aircraftAnalytics);

  return (
    <div>
      <div className="ac-card" style={{ marginBottom: 12 }}>
        <p className="ac-eyebrow" style={{ marginBottom: 2 }}>{AI_NAME} — MRO Operational Copilot</p>
        <p className="ac-text-sm ac-text-secondary" style={{ margin: 0, fontWeight: 600 }}>{AI_DESCRIPTION}</p>
      </div>

      <div className="ac-lisa-grid">
        {/* LEFT — question / search / suggestions. Never hides the answer. */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="ac-card" style={{ padding: 12 }}>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Ask a Question</p>
            <textarea
              className="ac-input"
              style={{ width: "100%", minHeight: 56, marginBottom: 8, resize: "vertical" }}
              placeholder="How can I help? Ask about an aircraft, work order, part, technician, or inspection…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // Some synthetic/automated input paths dispatch a keydown
                // without a populated `key` — fall back to keyCode 13 so
                // Enter-to-submit is robust across real browsers, IME
                // composition, and automated testing alike.
                if ((e.key === "Enter" || e.keyCode === 13) && !e.shiftKey) {
                  e.preventDefault();
                  ask(draft);
                }
              }}
              aria-label={`Ask ${AI_NAME}`}
            />
            <button className="ac-btn ac-btn-primary" style={{ width: "100%" }} onClick={() => ask(draft)}>
              Ask {AI_NAME}
            </button>
          </div>

          {hasContext && (
            <div className="ac-card" style={{ padding: 12 }}>
              <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Context Used</p>
              {projectAnalytics && (
                <div className="ac-text-sm">
                  <p style={{ margin: "0 0 4px" }}>Project: <Link href={`/maintenance/projects/${projectAnalytics.projectId}`}>{projectAnalytics.projectNumber}</Link></p>
                  <p style={{ margin: "0 0 4px" }}>Aircraft: {projectAnalytics.aircraftRegistration}</p>
                  <p style={{ margin: "0 0 4px" }}>Health: {projectAnalytics.health.replace(/_/g, " ")}</p>
                  <p style={{ margin: 0 }}>Compliance Risk: {projectAnalytics.complianceExposure}</p>
                </div>
              )}
              {aircraftAnalytics && (
                <div className="ac-text-sm">
                  <p style={{ margin: "0 0 4px" }}>Aircraft: <Link href={`/aircraft/${aircraftAnalytics.aircraftId}`}>{aircraftAnalytics.registration}</Link></p>
                  <p style={{ margin: "0 0 4px" }}>Open Work Orders: {aircraftAnalytics.openWorkOrders}</p>
                  <p style={{ margin: "0 0 4px" }}>Open Defects: {aircraftAnalytics.openDefects}</p>
                  <p style={{ margin: 0 }}>Compliance Risk: {aircraftAnalytics.complianceRisk}</p>
                </div>
              )}
              <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0 0" }}>
                Questions that don&apos;t name an aircraft/work order resolve against this context automatically.
              </p>
            </div>
          )}

          <div className="ac-card" style={{ padding: 12 }}>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Suggested Questions</p>
            <div style={{ maxHeight: 420, overflowY: "auto" }}>
              {CATEGORIZED_QUESTIONS.map((cat) => (
                <div key={cat.category} style={{ marginBottom: 10 }}>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px", fontWeight: 600 }}>{cat.category}</p>
                  <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                    {cat.questions.map((q) => (
                      <button key={q} className="ac-btn" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => ask(q)}>
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {!fleetAnalytics ? null : (
            <div className="ac-card" style={{ padding: 12 }}>
              <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Fleet Context</p>
              <div className="ac-text-sm">
                <p style={{ margin: "0 0 4px" }}>Fleet Size: {fleetAnalytics.fleetSize}</p>
                <p style={{ margin: "0 0 4px" }}>Open Work Orders: {fleetAnalytics.openWorkOrders}</p>
                <p style={{ margin: "0 0 4px" }}>Overdue: {fleetAnalytics.overdueWorkOrders}</p>
                <p style={{ margin: 0 }}>Aircraft At Risk: {fleetAnalytics.aircraftAtRisk.length}</p>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT — the persistent, always-visible answer pane. Question and
            answer are rendered as one connected block, never separated. */}
        <div>
          {!active ? (
            <div className="ac-card" style={{ borderStyle: "dashed" }}>
              <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>
                Ask a question on the left, or click a suggestion. Responses are generated from the current {COMPANY_NAME} demo
                dataset — {AI_NAME} explains, summarizes, and ranks; it never makes or overrides a compliance, inspection, release,
                or airworthiness decision.
              </p>
            </div>
          ) : (
            <div className="ac-card" style={{ marginBottom: 16, borderColor: "var(--ac-accent)", borderWidth: 2 }}>
              <div className="ac-flex ac-justify-between" style={{ alignItems: "flex-start", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
                <div>
                  <p className="ac-eyebrow" style={{ marginBottom: 4 }}>Question</p>
                  <p style={{ margin: 0, fontWeight: 700, fontSize: 15 }}>{active.question}</p>
                </div>
                <span className="ac-text-sm ac-text-muted" style={{ whiteSpace: "nowrap" }}>{active.askedAt}</span>
              </div>
              <AIResponseView response={active.response} />
            </div>
          )}

          {history.length > 0 && (
            <div>
              <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Conversation History ({history.length})</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {history.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setActiveId(t.id)}
                    className="ac-card"
                    style={{ textAlign: "left", cursor: "pointer", width: "100%", padding: "10px 12px" }}
                  >
                    <div className="ac-flex ac-justify-between" style={{ alignItems: "baseline", gap: 8 }}>
                      <span className="ac-text-sm" style={{ fontWeight: 600 }}>{t.question}</span>
                      <span className="ac-text-sm ac-text-muted" style={{ whiteSpace: "nowrap" }}>{t.askedAt}</span>
                    </div>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{t.response.headline}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
