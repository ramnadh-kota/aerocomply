"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import Link from "next/link";
import { answerQuestion, getSuggestedQuestionsForRole, type AiResponse } from "@/lib/mock/ai/engine";
import { getProjectAnalytics, getAircraftAnalytics, getFleetAnalytics, getReleaseQueue } from "@/lib/mock/ai/analytics";
import { getProactiveAlerts, getDailyBrief, type ProactiveAlert } from "@/lib/mock/ai/proactive";
import { AIResponseView } from "@/components/ai/AIResponseView";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { AI_NAME, AI_DESCRIPTION, COMPANY_NAME } from "@/lib/brand";
import { StatusBadge, priorityBadge } from "@/components/status/StatusBadge";

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
  // "View as Role" prototype simulation (see lib/role-sim/RoleSimContext) —
  // used here for relevance/framing only (suggested-question ordering,
  // proactive-alert ordering), never to gate which facts Lisa can answer.
  const { roleId } = useRoleSim();
  const askedInitial = useRef(false);
  // Reuses the SAME proactive engine as the Topbar notification panel and
  // the dashboard's Daily Brief — never a second alert calculation. Role is
  // passed through only to reorder by relevance; the full alert set is
  // still what's fetched (see getProactiveAlerts() role-relevance comment).
  const proactiveAlerts = useMemo(() => getProactiveAlerts(roleId).slice(0, 3), [roleId]);
  const suggestedQuestionCategories = useMemo(() => getSuggestedQuestionsForRole(roleId), [roleId]);

  // "Today's Operational Picture" KPI strip + "Lisa's Priorities" list — both
  // read the SAME canonical engines as the dashboard's Daily Brief and the
  // Topbar notification panel (see getDailyBrief()/getProactiveAlerts() in
  // lib/mock/ai/proactive.ts), never a second/invented aggregate. If a
  // richer priority-ranking engine (getOperationalPriorities()) lands later,
  // only this one call site needs to change — the render below only assumes
  // a {id, severity, title, message, href}-shaped array.
  const allAlerts = useMemo(() => getProactiveAlerts(roleId), [roleId]);
  const dailyBrief = useMemo(() => getDailyBrief(5, roleId), [roleId]);
  const releaseBlockedCount = useMemo(() => getReleaseQueue().length, []);
  const criticalCount = allAlerts.filter((a) => a.severity === "CRITICAL").length;
  const priorities: ProactiveAlert[] = dailyBrief.topPriorities;

  function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    const previousQuestion = turns.length > 0 ? turns[turns.length - 1].question : undefined;
    const recentQuestions = turns.slice(-5).map((t) => t.question);
    const response = answerQuestion(trimmed, { projectId: initialProjectId, aircraftId: initialAircraftId, auditLog, previousQuestion, recentQuestions, role: roleId });
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
        <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8 }}>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 2 }}>{AI_NAME} — MRO Operational Copilot</p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: 0, fontWeight: 600 }}>{AI_DESCRIPTION}</p>
          </div>
          <span className="ac-flex ac-items-center ac-gap-2" style={{ whiteSpace: "nowrap" }}>
            <span
              aria-hidden="true"
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--ac-status-compliant)",
                display: "inline-block",
                boxShadow: "0 0 0 3px color-mix(in srgb, var(--ac-status-compliant) 25%, transparent)",
              }}
            />
            <span className="ac-text-sm" style={{ fontWeight: 600 }}>Operational Intelligence Active</span>
          </span>
        </div>
      </div>

      <div className="ac-section" style={{ marginBottom: 16 }}>
        <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Today&rsquo;s Operational Picture</p>
        <div className="ac-kpi-grid">
          <Link href="/notifications" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Critical</p>
            <p className="ac-kpi-value">{criticalCount}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>alerts requiring attention</p>
          </Link>
          <Link href="/maintenance/control-center" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">AOG</p>
            <p className="ac-kpi-value">{dailyBrief.fleet.aogCount}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>aircraft grounded</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">TAT Risk</p>
            <p className="ac-kpi-value">{dailyBrief.fleet.tatAtRiskCount}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>work orders at risk / delayed</p>
          </Link>
          <Link href="/maintenance/release-readiness" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Release Blocked</p>
            <p className="ac-kpi-value">{releaseBlockedCount}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>work orders awaiting release</p>
          </Link>
        </div>
      </div>

      {priorities.length > 0 && (
        <div className="ac-card" style={{ marginBottom: 16 }}>
          <p className="ac-eyebrow" style={{ marginBottom: 8 }}>{AI_NAME}&rsquo;s Priorities</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {priorities.map((p) => {
              const pb = priorityBadge(p.severity);
              return (
                <Link
                  key={p.id}
                  href={p.href}
                  className="ac-flex ac-items-center ac-gap-2"
                  style={{
                    padding: "8px 10px",
                    borderRadius: 6,
                    border: "1px solid var(--ac-border-subtle)",
                    flexWrap: "wrap",
                  }}
                >
                  <StatusBadge status={pb.status} label={p.severity} />
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{p.title}</span>
                  <span className="ac-text-sm ac-text-muted">— {p.message}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}

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

          {proactiveAlerts.length > 0 && (
            <div className="ac-card" style={{ padding: 12 }}>
              <p className="ac-eyebrow" style={{ marginBottom: 8 }}>{AI_NAME} noticed…</p>
              <div className="ac-flex ac-flex-col ac-gap-2">
                {proactiveAlerts.map((a) => (
                  <div key={a.id} className="ac-flex ac-justify-between ac-items-center" style={{ gap: 8 }}>
                    <span className="ac-text-sm" style={{ flex: 1 }}>{a.message}</span>
                    <button
                      className="ac-btn"
                      style={{ fontSize: 12, padding: "4px 8px", flexShrink: 0 }}
                      onClick={() => setDraft(`Tell me about: ${a.title}`)}
                    >
                      Ask about this
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

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
              {suggestedQuestionCategories.map((cat) => (
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
