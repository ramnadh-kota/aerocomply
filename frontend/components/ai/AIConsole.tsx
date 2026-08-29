"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { answerQuestion, CATEGORIZED_QUESTIONS, type AiResponse } from "@/lib/mock/ai/engine";
import { getProjectAnalytics, getAircraftAnalytics, getFleetAnalytics } from "@/lib/mock/ai/analytics";
import { AIResponseView } from "@/components/ai/AIResponseView";
import { useMroState } from "@/lib/mro-state/MroStateContext";

interface Turn {
  id: string;
  question: string;
  response: AiResponse;
}

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
  const { addAuditEvent } = useMroState();
  const askedInitial = useRef(false);

  function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    const response = answerQuestion(trimmed, { projectId: initialProjectId, aircraftId: initialAircraftId });
    const turn: Turn = { id: response.id, question: trimmed, response };
    setTurns((prev) => [...prev, turn]);
    setActiveId(turn.id);
    setDraft("");
    addAuditEvent({
      actor: "AeroComply AI (Prototype)",
      actorRole: "AI Assistant",
      action: "ai.analysis_generated",
      objectType: "AiQuery",
      objectLabel: trimmed.length > 80 ? `${trimmed.slice(0, 80)}…` : trimmed,
      previousState: null,
      newState: response.insufficientData ? "INSUFFICIENT_DATA" : "ANSWERED",
    });
  }

  useEffect(() => {
    if (askedInitial.current || !initialQuestion) return;
    askedInitial.current = true;
    ask(initialQuestion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  const active = turns.find((t) => t.id === activeId) ?? turns[turns.length - 1];

  const projectAnalytics = initialProjectId ? getProjectAnalytics(initialProjectId) : null;
  const aircraftAnalytics = initialAircraftId ? getAircraftAnalytics(initialAircraftId) : null;
  const fleetAnalytics = !projectAnalytics && !aircraftAnalytics ? getFleetAnalytics() : null;

  return (
    <div className="ac-grid-3" style={{ gridTemplateColumns: "220px 1fr 260px", alignItems: "start", gap: 16 }}>
      {/* LEFT: conversation history */}
      <div className="ac-card" style={{ padding: 12 }}>
        <p className="ac-eyebrow" style={{ marginBottom: 8 }}>History</p>
        {turns.length === 0 && <p className="ac-text-sm ac-text-muted">No questions asked yet this session.</p>}
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {turns.map((t) => (
            <li key={t.id} style={{ marginBottom: 6 }}>
              <button
                className="ac-btn"
                style={{
                  width: "100%",
                  textAlign: "left",
                  fontSize: 12,
                  padding: "6px 8px",
                  background: t.id === active?.id ? "var(--ac-accent-muted)" : undefined,
                }}
                onClick={() => setActiveId(t.id)}
              >
                {t.question.length > 42 ? `${t.question.slice(0, 42)}…` : t.question}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* CENTER: conversation */}
      <div>
        <div className="ac-card" style={{ marginBottom: 12 }}>
          <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 6 }}>
            Ask AeroComply AI — Prototype · Non-authoritative
          </p>
          <div className="ac-flex ac-gap-2" style={{ marginBottom: 8 }}>
            <input
              className="ac-input"
              style={{ flex: 1 }}
              placeholder="Ask about a project, aircraft, work order, or inspection…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") ask(draft);
              }}
              aria-label="Ask AeroComply AI"
            />
            <button className="ac-btn ac-btn-primary" onClick={() => ask(draft)}>
              Ask
            </button>
          </div>
          {CATEGORIZED_QUESTIONS.map((cat) => (
            <div key={cat.category} className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 6 }}>
              <span className="ac-text-sm ac-text-muted" style={{ minWidth: 78 }}>{cat.category}:</span>
              {cat.questions.map((q) => (
                <button key={q} className="ac-btn" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => ask(q)}>
                  {q}
                </button>
              ))}
            </div>
          ))}
        </div>

        {turns.length === 0 && (
          <div className="ac-card" style={{ borderStyle: "dashed" }}>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>
              Ask a question above, or click a suggestion. Responses are generated from the current AeroComply demo
              dataset — the assistant explains, summarizes, and ranks; it never makes or overrides a compliance or
              inspection decision.
            </p>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {[...turns].reverse().map((t) => (
            <div key={t.id}>
              <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
                <strong>You:</strong> {t.question}
              </p>
              <AIResponseView response={t.response} />
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT: context panel */}
      <div className="ac-card" style={{ padding: 12 }}>
        <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Current Context</p>
        {projectAnalytics && (
          <div className="ac-text-sm">
            <p style={{ margin: "0 0 4px" }}>Project: <Link href={`/maintenance/projects/${projectAnalytics.projectId}`}>{projectAnalytics.projectNumber}</Link></p>
            <p style={{ margin: "0 0 4px" }}>Aircraft: {projectAnalytics.aircraftRegistration}</p>
            <p style={{ margin: "0 0 4px" }}>Health: {projectAnalytics.health.replace(/_/g, " ")}</p>
            <p style={{ margin: "0 0 4px" }}>Compliance Risk: {projectAnalytics.complianceExposure}</p>
            <p style={{ margin: "8px 0 0" }}>
              <Link href={`/maintenance/projects/${projectAnalytics.projectId}/intelligence`} className="ac-text-sm">Project Intelligence →</Link>
            </p>
          </div>
        )}
        {aircraftAnalytics && (
          <div className="ac-text-sm">
            <p style={{ margin: "0 0 4px" }}>Aircraft: <Link href={`/aircraft/${aircraftAnalytics.aircraftId}`}>{aircraftAnalytics.registration}</Link></p>
            <p style={{ margin: "0 0 4px" }}>Open Work Orders: {aircraftAnalytics.openWorkOrders}</p>
            <p style={{ margin: "0 0 4px" }}>Open Defects: {aircraftAnalytics.openDefects}</p>
            <p style={{ margin: "0 0 4px" }}>Compliance Risk: {aircraftAnalytics.complianceRisk}</p>
          </div>
        )}
        {fleetAnalytics && (
          <div className="ac-text-sm">
            <p style={{ margin: "0 0 4px" }}>Fleet Size: {fleetAnalytics.fleetSize}</p>
            <p style={{ margin: "0 0 4px" }}>Open Work Orders: {fleetAnalytics.openWorkOrders}</p>
            <p style={{ margin: "0 0 4px" }}>Overdue: {fleetAnalytics.overdueWorkOrders}</p>
            <p style={{ margin: "0 0 4px" }}>Aircraft At Risk: {fleetAnalytics.aircraftAtRisk.length}</p>
          </div>
        )}
        <hr className="ac-divider" />
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          Session-only prototype context. Not backend-persisted.
        </p>
      </div>
    </div>
  );
}
