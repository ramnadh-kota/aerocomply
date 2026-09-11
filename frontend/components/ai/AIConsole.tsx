"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import Link from "next/link";
import { answerQuestion, isGeneralKnowledgeQuestion, getSuggestedQuestionsForRole, type AiResponse } from "@/lib/mock/ai/engine";
import { getProjectAnalytics, getAircraftAnalytics, getFleetAnalytics, getReleaseQueue } from "@/lib/mock/ai/analytics";
import { getProactiveAlerts, getDailyBrief } from "@/lib/mock/ai/proactive";
import { AIResponseView } from "@/components/ai/AIResponseView";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { useRoleSim } from "@/lib/role-sim/RoleSimContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { lisaApi } from "@/lib/api/lisa";
import { lisaContextApi, type BackendLisaConversationContext } from "@/lib/api/lisaContext";
import { proactiveApi, type BackendProactiveAlert } from "@/lib/api/proactive";
import { ApiError } from "@/lib/apiClient";
import { AI_NAME, AI_DESCRIPTION, COMPANY_NAME } from "@/lib/brand";
import { StatusBadge, priorityBadge } from "@/components/status/StatusBadge";

// Honest capability boundary shown on the Lisa page (Part 8 of the AI-agent
// build). Backend-tool-covered areas are answered by the real agent when
// configured; frontend-only areas are still answered, but only via the
// existing deterministic engine (lib/mock/ai/engine.ts) — never invented by
// the agent. See backend/app/services/ai/tools.py for the authoritative list.
const LISA_CAN: string[] = [
  "Look up aircraft, work orders, tasks, evidence, and inspection/RII records (real backend data when in REAL mode)",
  "Summarize recorded execution state, open safety gates, and open discrepancies",
  "Explain TAT, vendor/procurement, regulatory deadlines, and operational priority using the demo dataset (deterministic engine, not agent-tool-backed yet)",
  "Rank, compare, and highlight risk across the data it can see",
];
const LISA_CANNOT: string[] = [
  "Certify an aircraft or determine airworthiness",
  "Approve or perform a release to service",
  "Bypass, skip, or waive any safety gate (inspection, RII, evidence, checklist, sign-off)",
  "Calculate or assert a business fact the underlying tools don't return",
];

// "demo_local" (not "AI Connected · Demo Data") is deliberate: DEMO mode
// never calls the backend agent at all — it always answers from the local
// deterministic engine — so claiming an "AI Connected" status here would be
// false regardless of whether ANTHROPIC_API_KEY happens to be set anywhere.
// Only a REAL-mode call that actually succeeds may claim "real_data".
type LisaAiStatus = "checking" | "real_data" | "demo_local" | "not_configured";

let fallbackResponseCounter = 0;

// The explicit, non-demo-data answer shown for a record-specific/
// operational question in REAL mode when the backend call itself failed.
// Never routes through answerQuestion()/demo records — see ask()'s
// MANDATORY FALLBACK POLICY comment.
function backendUnavailableResponse(
  question: string,
  reason: "AI_PROVIDER_UNAVAILABLE" | "PERMISSION_DENIED" | "BACKEND_UNAVAILABLE"
): AiResponse {
  fallbackResponseCounter += 1;
  const headline =
    reason === "AI_PROVIDER_UNAVAILABLE"
      ? "AI_PROVIDER_UNAVAILABLE"
      : reason === "PERMISSION_DENIED"
        ? "PERMISSION_DENIED"
        : "BACKEND_UNAVAILABLE";
  const explanation =
    reason === "AI_PROVIDER_UNAVAILABLE"
      ? "The backend AI provider is not configured, so this question cannot be answered from authoritative operational data right now."
      : reason === "PERMISSION_DENIED"
        ? "Your role does not have permission to retrieve the backend data this question requires."
        : "The backend could not be reached, so this question cannot be answered from authoritative operational data right now.";
  return {
    id: `lisa-fallback-${fallbackResponseCounter}`,
    question,
    headline,
    narrative: [
      explanation,
      "This is a record-specific/operational question, so Lisa will not answer it from demo data while in Real Data mode — that would present frontend demo state as if it were live aircraft, work order, AOG, or release data.",
      reason === "BACKEND_UNAVAILABLE"
        ? "Try again once the backend is reachable, or switch to Demo Mode to explore with sample data (clearly labeled as such)."
        : reason === "AI_PROVIDER_UNAVAILABLE"
          ? "General knowledge and safety-guidance questions still work without the AI provider — ask a glossary question or 'tell me what not to do'."
          : "Contact an administrator if you believe you should have access to this data.",
    ],
    whatIFound: [explanation],
    confidenceState: "NOT_CONFIGURED",
    actionCategory: "INFORMATION",
  };
}

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
  const [asking, setAsking] = useState(false);
  const [showCapabilities, setShowCapabilities] = useState(false);
  // Once a real /lisa/ask call comes back 503 ai_not_configured, stop
  // retrying the network on every question for the rest of this session —
  // fall back to the deterministic engine immediately, same as DEMO mode.
  const [aiNotConfigured, setAiNotConfigured] = useState(false);
  // Whether the one-time REAL-mode configuration probe (below) has
  // resolved yet. Starts false so the status indicator never optimistically
  // claims "AI Connected · Real Data" before that's actually confirmed —
  // it shows "checking" instead until the probe settles either way.
  const [realAgentProbed, setRealAgentProbed] = useState(false);
  // Why the MOST RECENT question fell back to the local deterministic
  // engine, if it did — cleared at the start of every new ask() so a stale
  // reason never lingers on an answer that actually succeeded. null means
  // either the last question succeeded against the backend, or DEMO mode
  // never attempted the backend at all (no fallback to explain).
  const [lastFallbackReason, setLastFallbackReason] = useState<
    "AI_PROVIDER_UNAVAILABLE" | "PERMISSION_DENIED" | "BACKEND_UNAVAILABLE" | null
  >(null);
  const { addAuditEvent, auditLog } = useMroState();
  const { mode: dataMode } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  // A genuine REAL-mode session — the no-mock-fallback policy in ask()
  // applies whenever this is true, REGARDLESS of aiNotConfigured. Whether
  // or not the AI provider itself is configured is a separate question
  // from whether this is a real authenticated session that must never
  // silently answer a record-specific question from demo data.
  const isRealModeSession = dataMode === "REAL" && isAuthenticated && !!accessToken;
  const useRealAgent = isRealModeSession && !aiNotConfigured;
  const aiStatus: LisaAiStatus =
    dataMode === "REAL" && isAuthenticated && accessToken
      ? aiNotConfigured
        ? "not_configured"
        : realAgentProbed
          ? "real_data"
          : "checking"
      : "demo_local";

  // Probe once per REAL-mode session whether the backend agent is actually
  // configured, so the status indicator is honest before the user asks
  // anything — never silently claim "Real Data" and then fall back mid-turn
  // without telling them.
  useEffect(() => {
    if (dataMode !== "REAL" || !isAuthenticated || !accessToken || aiNotConfigured) return;
    let cancelled = false;
    lisaApi
      .ask(accessToken, { question: "status probe: are you configured?" })
      .then((res) => {
        if (cancelled) return;
        // A configured agent returned a real answer to the probe — confirmed.
        void res;
        setRealAgentProbed(true);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.code === "ai_not_configured") {
          setAiNotConfigured(true);
        } else {
          // Any other failure (network, auth, timeout) is also not a
          // confirmed connection — stay honest and fall back rather than
          // claim "real_data" on an error we don't understand.
          setAiNotConfigured(true);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataMode, isAuthenticated, accessToken]);

  // Backend-authoritative proactive alerts (REAL mode only). Deterministic
  // — derived entirely from persisted domain records, requires no LLM/AI
  // provider — so this fetch is independent of aiNotConfigured and still
  // runs even when the AI agent itself is not configured (see
  // proactive_service.py). null = not yet loaded; "unavailable" = REAL
  // mode session but the fetch failed — never silently substituted with
  // demo alerts (same no-mock-fallback policy as ask()).
  const [lisaContext, setLisaContext] = useState<BackendLisaConversationContext | null>(null);

  function refreshLisaContext() {
    if (!isRealModeSession || !accessToken) return;
    lisaContextApi
      .get(accessToken)
      .then(setLisaContext)
      .catch(() => setLisaContext(null));
  }

  useEffect(() => {
    refreshLisaContext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRealModeSession, accessToken]);

  async function resetLisaContext() {
    if (!accessToken) return;
    try {
      const reset = await lisaContextApi.reset(accessToken);
      setLisaContext(reset);
    } catch {
      // Context reset failing is non-fatal to the chat itself — just leave
      // the displayed context as-is rather than showing a misleading state.
    }
  }

  const [backendAlerts, setBackendAlerts] = useState<BackendProactiveAlert[] | null>(null);
  const [backendAlertsStatus, setBackendAlertsStatus] = useState<
    "idle" | "loading" | "loaded" | "unavailable"
  >("idle");

  useEffect(() => {
    if (!isRealModeSession || !accessToken) {
      setBackendAlerts(null);
      setBackendAlertsStatus("idle");
      return;
    }
    let cancelled = false;
    setBackendAlertsStatus("loading");
    proactiveApi
      .getAlerts(accessToken)
      .then((alerts) => {
        if (cancelled) return;
        setBackendAlerts(alerts);
        setBackendAlertsStatus("loaded");
      })
      .catch(() => {
        if (cancelled) return;
        setBackendAlerts(null);
        setBackendAlertsStatus("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [isRealModeSession, accessToken]);

  // "View as Role" prototype simulation (see lib/role-sim/RoleSimContext) —
  // used here for relevance/framing only (suggested-question ordering,
  // proactive-alert ordering), never to gate which facts Lisa can answer.
  const { roleId } = useRoleSim();
  const askedInitial = useRef(false);

  function backendAlertHref(a: BackendProactiveAlert): string {
    if (a.work_order_id) return `/maintenance/work-orders/${a.work_order_id}`;
    if (a.aircraft_id) return `/aircraft/${a.aircraft_id}`;
    return "/ai";
  }

  // "Today's Operational Picture" KPI strip, "Lisa's Priorities", and
  // "Lisa noticed…" — all three read ONE alert source, chosen once here:
  // backend-authoritative alerts in a REAL-mode session (never demo data,
  // per the no-mock-fallback policy — see ask() above), or the existing
  // frontend demo engine in DEMO mode. Never a second/invented aggregate.
  const allAlerts: { id: string; severity: string; title: string; message: string; href: string }[] =
    isRealModeSession
      ? (backendAlerts ?? []).map((a) => ({
          id: a.id,
          severity: a.severity,
          title: a.title,
          message: a.message,
          href: backendAlertHref(a),
        }))
      : getProactiveAlerts(roleId);
  const suggestedQuestionCategories = useMemo(() => getSuggestedQuestionsForRole(roleId), [roleId]);
  const proactiveAlerts = allAlerts.slice(0, 3);
  const dailyBrief = useMemo(() => getDailyBrief(5, roleId), [roleId]);
  const releaseBlockedCount = isRealModeSession
    ? allAlerts.filter((a) => a.href.includes("/work-orders/")).length
    : getReleaseQueue().length;
  const criticalCount = allAlerts.filter((a) => a.severity === "CRITICAL").length;
  const aogCount = isRealModeSession
    ? (backendAlerts ?? []).filter((a) => a.category === "AOG").length
    : dailyBrief.fleet.aogCount;
  // TAT risk has no backend equivalent yet (no due_date column anywhere in
  // this schema — see tat_service.py) — honestly UNKNOWN in REAL mode
  // rather than borrowing the DEMO dataset's fabricated-looking count.
  const tatAtRiskDisplay: number | "—" = isRealModeSession ? "—" : dailyBrief.fleet.tatAtRiskCount;
  const priorities = isRealModeSession ? allAlerts.slice(0, 5) : dailyBrief.topPriorities;

  function commitTurn(trimmed: string, response: AiResponse) {
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

  // Shared by every REAL-mode failure/known-unconfigured path below: general
  // knowledge answers locally (not a "demo data" fallback — the same
  // deterministic glossary/safety logic the backend agent itself would
  // use); anything record-specific gets the explicit failure-state answer,
  // never demo operational data. See MANDATORY FALLBACK POLICY below.
  function answerInRealModeWithoutBackend(
    trimmed: string,
    previousQuestion: string | undefined,
    recentQuestions: string[],
    reason: "AI_PROVIDER_UNAVAILABLE" | "PERMISSION_DENIED" | "BACKEND_UNAVAILABLE"
  ): AiResponse {
    if (isGeneralKnowledgeQuestion(trimmed)) {
      return answerQuestion(trimmed, {
        projectId: initialProjectId,
        aircraftId: initialAircraftId,
        auditLog,
        previousQuestion,
        recentQuestions,
        role: roleId,
      });
    }
    return backendUnavailableResponse(trimmed, reason);
  }

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    const previousQuestion = turns.length > 0 ? turns[turns.length - 1].question : undefined;
    const recentQuestions = turns.slice(-5).map((t) => t.question);
    setLastFallbackReason(null);

    if (isRealModeSession) {
      // MANDATORY FALLBACK POLICY: a genuine REAL-mode session must never
      // silently answer a record-specific/operational question from DEMO
      // mock data — neither on a network failure below, nor here when the
      // AI provider is already known to be unconfigured (aiNotConfigured
      // is sticky for the session; without this branch every subsequent
      // question would silently fall through to the demo-mode branch at
      // the bottom of this function, which is the exact bug this fixes).
      if (!useRealAgent || !accessToken) {
        setLastFallbackReason("AI_PROVIDER_UNAVAILABLE");
        commitTurn(
          trimmed,
          answerInRealModeWithoutBackend(
            trimmed,
            previousQuestion,
            recentQuestions,
            "AI_PROVIDER_UNAVAILABLE"
          )
        );
        return;
      }

      setAsking(true);
      try {
        const backendResponse = await lisaApi.ask(accessToken, {
          question: trimmed,
          conversation_history: recentQuestions,
          current_entity: initialAircraftId ?? initialProjectId,
        });
        // LisaAskResponse already matches the AiResponse field shape
        // (whatIFound/whyItMatters/priority/... in camelCase) so it renders
        // through the exact same AIResponseView with no fork.
        commitTurn(trimmed, backendResponse as unknown as AiResponse);
        setAsking(false);
        refreshLisaContext();
        return;
      } catch (err) {
        let reason: "AI_PROVIDER_UNAVAILABLE" | "PERMISSION_DENIED" | "BACKEND_UNAVAILABLE";
        if (err instanceof ApiError && err.code === "ai_not_configured") {
          setAiNotConfigured(true);
          reason = "AI_PROVIDER_UNAVAILABLE";
        } else if (err instanceof ApiError && err.status === 403) {
          reason = "PERMISSION_DENIED";
        } else {
          // fetch() throws TypeError on network failure (backend down/
          // unreachable); any other ApiError (5xx, timeout-shaped, etc.)
          // is likewise treated as the backend being unavailable rather
          // than guessed at more specifically.
          reason = "BACKEND_UNAVAILABLE";
        }
        setLastFallbackReason(reason);
        setAsking(false);
        // Entity/reference resolution runs before the AI provider call on
        // the backend, so context may have been persisted even though this
        // request itself failed (e.g. AI_PROVIDER_UNAVAILABLE) — refresh to
        // reflect that rather than leaving a stale indicator.
        refreshLisaContext();
        commitTurn(
          trimmed,
          answerInRealModeWithoutBackend(trimmed, previousQuestion, recentQuestions, reason)
        );
        return;
      }
    }

    // True DEMO mode: the deterministic local engine and its demo dataset
    // are the EXPECTED, honestly-labeled behavior here, not a fallback
    // from a failure.
    const response = answerQuestion(trimmed, { projectId: initialProjectId, aircraftId: initialAircraftId, auditLog, previousQuestion, recentQuestions, role: roleId });
    commitTurn(trimmed, response);
  }

  useEffect(() => {
    if (askedInitial.current || !initialQuestion) return;
    askedInitial.current = true;
    void ask(initialQuestion);
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
            <p className="ac-eyebrow" style={{ marginBottom: 2 }}>{AI_NAME} — MRO Operational AI Agent</p>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: 0, fontWeight: 600 }}>{AI_DESCRIPTION}</p>
          </div>
          <span className="ac-flex ac-items-center ac-gap-2" style={{ whiteSpace: "nowrap" }}>
            <span
              aria-hidden="true"
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background:
                  aiStatus === "real_data"
                    ? "var(--ac-status-compliant)"
                    : aiStatus === "checking"
                      ? "var(--ac-status-unknown)"
                      : "var(--ac-status-review)",
                display: "inline-block",
                boxShadow:
                  aiStatus === "real_data"
                    ? "0 0 0 3px color-mix(in srgb, var(--ac-status-compliant) 25%, transparent)"
                    : aiStatus === "checking"
                      ? "0 0 0 3px color-mix(in srgb, var(--ac-status-unknown) 25%, transparent)"
                      : "0 0 0 3px color-mix(in srgb, var(--ac-status-review) 25%, transparent)",
              }}
            />
            <span className="ac-text-sm" style={{ fontWeight: 600 }}>
              {aiStatus === "real_data" && "AI Connected · Real Data"}
              {aiStatus === "checking" && "Checking AI connection…"}
              {aiStatus === "demo_local" && "Demo Mode · Local Reasoning Engine"}
              {aiStatus === "not_configured" && "AI Not Configured"}
            </span>
            <button
              className="ac-btn"
              style={{ fontSize: 11, padding: "2px 8px" }}
              onClick={() => setShowCapabilities((v) => !v)}
            >
              Lisa can / cannot
            </button>
          </span>
        </div>
        {showCapabilities && (
          <div
            className="ac-text-sm"
            style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--ac-border-subtle)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}
          >
            <div>
              <p style={{ margin: "0 0 4px", fontWeight: 700 }}>Lisa can</p>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {LISA_CAN.map((item) => (
                  <li key={item} style={{ marginBottom: 4 }}>{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <p style={{ margin: "0 0 4px", fontWeight: 700 }}>Lisa cannot</p>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {LISA_CANNOT.map((item) => (
                  <li key={item} style={{ marginBottom: 4 }}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {isRealModeSession && lisaContext && (
        <div className="ac-card" style={{ marginBottom: 12, padding: "8px 12px" }}>
          <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8 }}>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {lisaContext.current_aircraft_id || lisaContext.current_work_order_id ? (
                <>
                  Lisa is using:{" "}
                  {lisaContext.current_aircraft_id && (
                    <span className="ac-mono">aircraft {lisaContext.current_aircraft_id.slice(0, 8)}…</span>
                  )}
                  {lisaContext.current_aircraft_id && lisaContext.current_work_order_id && " · "}
                  {lisaContext.current_work_order_id && (
                    <span className="ac-mono">work order {lisaContext.current_work_order_id.slice(0, 8)}…</span>
                  )}
                </>
              ) : (
                "Lisa has no active aircraft/work order context yet."
              )}
            </p>
            <button
              className="ac-btn"
              style={{ fontSize: 11, padding: "2px 8px" }}
              onClick={resetLisaContext}
            >
              Reset context
            </button>
          </div>
        </div>
      )}

      <div className="ac-section" style={{ marginBottom: 16 }}>
        <p className="ac-eyebrow" style={{ marginBottom: 8 }}>
          Today&rsquo;s Operational Picture
          {isRealModeSession && backendAlertsStatus === "loaded" && " · Backend Authoritative"}
        </p>
        {isRealModeSession && backendAlertsStatus === "unavailable" && (
          <p
            className="ac-text-sm"
            style={{
              marginBottom: 8,
              padding: "8px 10px",
              borderRadius: 6,
              border: "1px solid var(--ac-status-review)",
              background: "color-mix(in srgb, var(--ac-status-review) 10%, transparent)",
            }}
          >
            BACKEND_UNAVAILABLE — operational alerts could not be retrieved. Not showing demo
            counts in their place.
          </p>
        )}
        <div className="ac-kpi-grid">
          <Link href="/notifications" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Critical</p>
            <p className="ac-kpi-value">
              {isRealModeSession && backendAlertsStatus === "unavailable" ? "—" : criticalCount}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>alerts requiring attention</p>
          </Link>
          <Link href="/maintenance/control-center" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">AOG</p>
            <p className="ac-kpi-value">
              {isRealModeSession && backendAlertsStatus === "unavailable" ? "—" : aogCount}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>aircraft grounded</p>
          </Link>
          <Link href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">TAT Risk</p>
            <p className="ac-kpi-value">{tatAtRiskDisplay}</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              {isRealModeSession ? "not tracked in this system" : "work orders at risk / delayed"}
            </p>
          </Link>
          <Link href="/maintenance/release-readiness" className="ac-kpi-card" style={{ display: "block" }}>
            <p className="ac-kpi-label">Release Blocked</p>
            <p className="ac-kpi-value">
              {isRealModeSession && backendAlertsStatus === "unavailable" ? "—" : releaseBlockedCount}
            </p>
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
            <button className="ac-btn ac-btn-primary" style={{ width: "100%" }} onClick={() => void ask(draft)}>
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
                      <button key={q} className="ac-btn" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => void ask(q)}>
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
              {active.id === turns[turns.length - 1]?.id &&
                lastFallbackReason &&
                // Suppress this banner when the answer itself IS the
                // explicit failure state (headline already says
                // BACKEND_UNAVAILABLE/etc. — see backendUnavailableResponse
                // in ask()); only show it for the general-knowledge case,
                // where the active answer is a real glossary/safety-
                // guidance response and the banner explains why it did not
                // come from the backend.
                !["AI_PROVIDER_UNAVAILABLE", "PERMISSION_DENIED", "BACKEND_UNAVAILABLE"].includes(
                  active.response.headline
                ) && (
                  <div
                    className="ac-text-sm"
                    style={{
                      marginBottom: 10,
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--ac-status-review)",
                      background: "color-mix(in srgb, var(--ac-status-review) 10%, transparent)",
                    }}
                  >
                    {lastFallbackReason === "AI_PROVIDER_UNAVAILABLE" &&
                      "The backend AI provider is not configured — this general-knowledge answer did not require it."}
                    {lastFallbackReason === "PERMISSION_DENIED" &&
                      "Your role does not have permission to retrieve backend data for this question — this general-knowledge answer did not require it."}
                    {lastFallbackReason === "BACKEND_UNAVAILABLE" &&
                      "The backend could not be reached — this general-knowledge answer did not require it."}
                  </div>
                )}
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
