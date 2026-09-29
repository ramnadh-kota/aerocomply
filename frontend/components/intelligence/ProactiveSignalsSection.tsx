"use client";

import { useState } from "react";
import Link from "next/link";
import {
  StatusBadge,
  signalSeverityBadge,
  signalPriorityBadge,
  signalStatusBadge,
  signalTrendBadge,
} from "@/components/status/StatusBadge";
import {
  type ProactiveSignal,
  type ProactiveIntelligenceSummary,
  type SignalStatus,
  intelligenceApi,
} from "@/lib/api/intelligence";
import { AI_NAME } from "@/lib/brand";

interface ProactiveSignalsSectionProps {
  summary?: ProactiveIntelligenceSummary | null;
  signals: ProactiveSignal[];
  accessToken?: string | null;
  assetId?: string;
  onSignalUpdated?: () => void;
  title?: string;
  subtitle?: string;
}

export function ProactiveSignalsSection({
  summary,
  signals,
  accessToken,
  assetId,
  onSignalUpdated,
  title = "Proactive Intelligence & Emerging Risks",
  subtitle = "Deterministic early-warning signals, predictive degradation indicators, and explainable decision pathways.",
}: ProactiveSignalsSectionProps) {
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [dismissModalSignal, setDismissModalSignal] = useState<ProactiveSignal | null>(null);
  const [dismissReason, setDismissReason] = useState("");
  const [expandedSignalId, setExpandedSignalId] = useState<string | null>(null);

  const filteredSignals = signals.filter((sig) => {
    if (filterStatus !== "ALL" && sig.status !== filterStatus) return false;
    if (filterSeverity !== "ALL" && sig.severity !== filterSeverity) return false;
    return true;
  });

  async function handleAcknowledge(signal: ProactiveSignal) {
    if (!accessToken) return;
    setActionLoadingId(signal.id);
    try {
      await intelligenceApi.acknowledgeSignal(accessToken, signal.id);
      onSignalUpdated?.();
    } catch (err) {
      console.error("Failed to acknowledge signal", err);
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleInReview(signal: ProactiveSignal) {
    if (!accessToken) return;
    setActionLoadingId(signal.id);
    try {
      await intelligenceApi.inReviewSignal(accessToken, signal.id);
      onSignalUpdated?.();
    } catch (err) {
      console.error("Failed to move signal to in-review", err);
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleResolve(signal: ProactiveSignal) {
    if (!accessToken) return;
    setActionLoadingId(signal.id);
    try {
      await intelligenceApi.resolveSignal(accessToken, signal.id);
      onSignalUpdated?.();
    } catch (err) {
      console.error("Failed to resolve signal", err);
    } finally {
      setActionLoadingId(null);
    }
  }

  async function handleDismissSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken || !dismissModalSignal) return;
    setActionLoadingId(dismissModalSignal.id);
    try {
      await intelligenceApi.dismissSignal(accessToken, dismissModalSignal.id, dismissReason.trim() || undefined);
      setDismissModalSignal(null);
      setDismissReason("");
      onSignalUpdated?.();
    } catch (err) {
      console.error("Failed to dismiss signal", err);
    } finally {
      setActionLoadingId(null);
    }
  }

  return (
    <section className="ac-section" style={{ marginBottom: 28 }}>
      <div className="ac-section-header" style={{ marginBottom: 14 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "1.2rem", color: "var(--ac-primary, #38bdf8)" }}>◈</span>
            <h2 className="ac-h2" style={{ margin: 0 }}>
              {title}
            </h2>
          </div>
          <p className="ac-subtitle" style={{ margin: "4px 0 0 0" }}>
            {subtitle}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="ac-text-sm ac-text-muted">
            {signals.length} total signal(s) evaluated
          </span>
        </div>
      </div>

      {/* Summary KPI Ribbon if summary provided */}
      {summary && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 10,
            marginBottom: 16,
          }}
        >
          <div
            className="ac-card"
            style={{
              padding: "12px 16px",
              background: summary.critical_signals > 0 ? "rgba(239, 68, 68, 0.1)" : "rgba(31, 41, 55, 0.6)",
              border: summary.critical_signals > 0 ? "1px solid rgba(239, 68, 68, 0.4)" : "1px solid #374151",
            }}
          >
            <div style={{ fontSize: "0.7rem", color: "#ef4444", textTransform: "uppercase", fontWeight: 700 }}>
              Critical Signals
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#ef4444" }}>
              {summary.critical_signals}
            </div>
          </div>

          <div
            className="ac-card"
            style={{
              padding: "12px 16px",
              background: summary.high_signals > 0 ? "rgba(245, 158, 11, 0.1)" : "rgba(31, 41, 55, 0.6)",
              border: summary.high_signals > 0 ? "1px solid rgba(245, 158, 11, 0.4)" : "1px solid #374151",
            }}
          >
            <div style={{ fontSize: "0.7rem", color: "#f59e0b", textTransform: "uppercase", fontWeight: 700 }}>
              High Priority
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#f59e0b" }}>
              {summary.high_signals}
            </div>
          </div>

          <div
            className="ac-card"
            style={{
              padding: "12px 16px",
              background: "rgba(31, 41, 55, 0.6)",
              border: "1px solid #374151",
            }}
          >
            <div style={{ fontSize: "0.7rem", color: "#38bdf8", textTransform: "uppercase", fontWeight: 700 }}>
              Immediate Action
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#38bdf8" }}>
              {summary.signals_by_priority?.IMMEDIATE ?? 0}
            </div>
          </div>

          <div
            className="ac-card"
            style={{
              padding: "12px 16px",
              background: "rgba(31, 41, 55, 0.6)",
              border: "1px solid #374151",
            }}
          >
            <div style={{ fontSize: "0.7rem", color: "#10b981", textTransform: "uppercase", fontWeight: 700 }}>
              Watchlist / Medium
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#10b981" }}>
              {(summary.medium_signals || 0) + (summary.low_signals || 0)}
            </div>
          </div>
        </div>
      )}

      {/* Fleet Proactive Insights Box */}
      {summary?.fleet_insights && summary.fleet_insights.length > 0 && (
        <div
          className="ac-card"
          style={{
            padding: "14px 18px",
            marginBottom: 16,
            background: "linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 41, 59, 0.7) 100%)",
            border: "1px solid rgba(56, 189, 248, 0.3)",
            borderRadius: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <span style={{ fontSize: "0.9rem" }}>💡</span>
            <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>
              {AI_NAME} Proactive Fleet Insights & Systematic Explanations
            </span>
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.85rem", color: "#e2e8f0" }}>
            {summary.fleet_insights.map((insight, idx) => (
              <li key={idx} style={{ marginBottom: 3 }}>
                {insight}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Filter Controls */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.75rem", color: "#9ca3af", alignSelf: "center", marginRight: 4 }}>Status:</span>
          {["ALL", "OPEN", "ACKNOWLEDGED", "IN_REVIEW", "RESOLVED", "DISMISSED"].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setFilterStatus(s)}
              style={{
                fontSize: "0.75rem",
                padding: "3px 8px",
                borderRadius: 12,
                border: "1px solid #374151",
                background: filterStatus === s ? "var(--ac-primary, #38bdf8)" : "#1f2937",
                color: filterStatus === s ? "#000" : "#9ca3af",
                fontWeight: filterStatus === s ? 700 : 500,
                cursor: "pointer",
              }}
            >
              {s.replace(/_/g, " ")}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.75rem", color: "#9ca3af", alignSelf: "center", marginRight: 4 }}>Severity:</span>
          {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((sev) => (
            <button
              key={sev}
              type="button"
              onClick={() => setFilterSeverity(sev)}
              style={{
                fontSize: "0.75rem",
                padding: "3px 8px",
                borderRadius: 12,
                border: "1px solid #374151",
                background: filterSeverity === sev ? "#f59e0b" : "#1f2937",
                color: filterSeverity === sev ? "#000" : "#9ca3af",
                fontWeight: filterSeverity === sev ? 700 : 500,
                cursor: "pointer",
              }}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Signals List */}
      {filteredSignals.length === 0 ? (
        <div className="ac-card" style={{ padding: "24px", textAlign: "center" }}>
          <p style={{ color: "#10b981", fontWeight: 600, margin: 0 }}>
            ✓ No proactive intelligence risks or early-warning signals match active filters.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {filteredSignals.map((signal) => {
            const isCritical = signal.severity === "CRITICAL";
            const isHigh = signal.severity === "HIGH";
            const isExpanded = expandedSignalId === signal.id;
            const isLoading = actionLoadingId === signal.id;

            return (
              <div
                key={signal.id}
                className="ac-card"
                style={{
                  padding: "18px 20px",
                  background: isCritical
                    ? "rgba(239, 68, 68, 0.05)"
                    : isHigh
                    ? "rgba(245, 158, 11, 0.05)"
                    : "rgba(31, 41, 55, 0.7)",
                  border: isCritical
                    ? "1px solid rgba(239, 68, 68, 0.4)"
                    : isHigh
                    ? "1px solid rgba(245, 158, 11, 0.4)"
                    : "1px solid #374151",
                  borderRadius: 10,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 280 }}>
                    {/* Badges Row */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                      <StatusBadge {...signalSeverityBadge(signal.severity)} />
                      <StatusBadge {...signalPriorityBadge(signal.priority)} />
                      <StatusBadge {...signalStatusBadge(signal.status)} />
                      {signal.trend_direction && (
                        <StatusBadge
                          {...signalTrendBadge(signal.trend_direction)}
                          label={`Trend: ${signal.trend_direction}`}
                        />
                      )}
                      <span
                        style={{
                          fontSize: "0.7rem",
                          background: "#1f2937",
                          color: "#9ca3af",
                          padding: "2px 6px",
                          borderRadius: 4,
                          border: "1px solid #374151",
                          textTransform: "uppercase",
                        }}
                      >
                        {signal.signal_type.replace(/_/g, " ")}
                      </span>
                    </div>

                    {/* Title & Description */}
                    <h4 style={{ margin: "0 0 6px 0", fontSize: "1.05rem", fontWeight: 700, color: "#fff" }}>
                      {signal.title}
                    </h4>
                    <p style={{ margin: "0 0 8px 0", color: "#d1d5db", fontSize: "0.875rem", lineHeight: 1.45 }}>
                      {signal.description}
                    </p>

                    {/* Trigger Condition */}
                    <div style={{ fontSize: "0.8rem", color: "#93c5fd", marginBottom: 6 }}>
                      <strong>Deterministic Trigger:</strong> {signal.trigger_condition}
                    </div>

                    {/* Projected Impact & Horizon */}
                    {(signal.projected_impact || signal.estimated_horizon_days !== null) && (
                      <div style={{ fontSize: "0.8rem", color: "#fcd34d", marginBottom: 8 }}>
                        {signal.projected_impact && <span><strong>Projected Impact:</strong> {signal.projected_impact} </span>}
                        {signal.estimated_horizon_days !== null && (
                          <span style={{ marginLeft: 6 }}>
                            (Horizon: <strong>{signal.estimated_horizon_days} day(s)</strong>)
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Right Action Controls & State Mutations */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                    <button
                      type="button"
                      onClick={() => setExpandedSignalId(isExpanded ? null : signal.id)}
                      className="ac-btn"
                      style={{ fontSize: "0.8rem", padding: "4px 10px" }}
                    >
                      {isExpanded ? "Hide Evidence ▲" : `Trace Evidence (${signal.evidence?.length || 0}) ▼`}
                    </button>

                    {/* Signal Status Mutation Actions */}
                    {accessToken && (
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end", marginTop: 4 }}>
                        {signal.status === "OPEN" && (
                          <button
                            type="button"
                            disabled={isLoading}
                            onClick={() => handleAcknowledge(signal)}
                            className="ac-btn"
                            style={{ fontSize: "0.75rem", padding: "3px 8px" }}
                          >
                            {isLoading ? "..." : "Acknowledge"}
                          </button>
                        )}
                        {(signal.status === "OPEN" || signal.status === "ACKNOWLEDGED") && (
                          <button
                            type="button"
                            disabled={isLoading}
                            onClick={() => handleInReview(signal)}
                            className="ac-btn"
                            style={{ fontSize: "0.75rem", padding: "3px 8px" }}
                          >
                            {isLoading ? "..." : "In Review"}
                          </button>
                        )}
                        {signal.status !== "RESOLVED" && (
                          <button
                            type="button"
                            disabled={isLoading}
                            onClick={() => handleResolve(signal)}
                            className="ac-btn ac-btn-primary"
                            style={{ fontSize: "0.75rem", padding: "3px 8px", background: "#10b981", borderColor: "#10b981" }}
                          >
                            {isLoading ? "..." : "Resolve"}
                          </button>
                        )}
                        {signal.status !== "DISMISSED" && (
                          <button
                            type="button"
                            disabled={isLoading}
                            onClick={() => {
                              setDismissModalSignal(signal);
                              setDismissReason("");
                            }}
                            className="ac-btn"
                            style={{ fontSize: "0.75rem", padding: "3px 8px", color: "#9ca3af" }}
                          >
                            Dismiss
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Recommended Decision Actions */}
                {signal.recommended_actions && signal.recommended_actions.length > 0 && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: "10px 14px",
                      background: "rgba(17, 24, 39, 0.6)",
                      border: "1px solid #374151",
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ fontSize: "0.75rem", color: "#38bdf8", fontWeight: 700, marginBottom: 4, textTransform: "uppercase" }}>
                      Recommended Action Support:
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {signal.recommended_actions.map((act, idx) => (
                        <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, fontSize: "0.825rem" }}>
                          <div>
                            <span style={{ color: "#f3f4f6" }}>{act.description}</span>
                            {act.requires_authorization && (
                              <span style={{ marginLeft: 6, fontSize: "0.7rem", color: "#f59e0b", background: "rgba(245, 158, 11, 0.15)", padding: "1px 5px", borderRadius: 4 }}>
                                🔒 Authorization Required
                              </span>
                            )}
                          </div>
                          {act.target_route && (
                            <Link href={act.target_route} className="ac-btn ac-btn-primary" style={{ fontSize: "0.75rem", padding: "2px 8px" }}>
                              Execute →
                            </Link>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Evidence Traceability Provenance Drawer */}
                {isExpanded && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: "12px 16px",
                      background: "#111827",
                      border: "1px solid #374151",
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ fontSize: "0.8rem", color: "#9ca3af", fontWeight: 700, marginBottom: 8, textTransform: "uppercase" }}>
                      Traceable Evidence Provenance ({signal.evidence?.length || 0} Domain Records):
                    </div>
                    {(!signal.evidence || signal.evidence.length === 0) ? (
                      <p style={{ margin: 0, fontSize: "0.8rem", color: "#9ca3af", fontStyle: "italic" }}>
                        No specific sub-records attached to this signal.
                      </p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {signal.evidence.map((ev, idx) => (
                          <div
                            key={idx}
                            style={{
                              padding: "8px 12px",
                              background: "#1f2937",
                              borderRadius: 6,
                              fontSize: "0.8rem",
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              gap: 10,
                            }}
                          >
                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <strong style={{ color: "#38bdf8" }}>[{ev.entity_type}]</strong>
                                <span style={{ color: "#e5e7eb" }}>{ev.summary}</span>
                              </div>
                              <div style={{ fontSize: "0.75rem", color: "#9ca3af", marginTop: 2 }}>
                                Ref ID: <code className="ac-mono">{ev.entity_id}</code>
                                {ev.observed_value && <span> · Observed: <strong>{ev.observed_value}</strong></span>}
                                {ev.threshold_value && <span> · Limit: <strong>{ev.threshold_value}</strong></span>}
                              </div>
                            </div>
                            {ev.url && (
                              <Link href={ev.url} className="ac-btn" style={{ fontSize: "0.75rem", padding: "2px 8px" }}>
                                Inspect Record →
                              </Link>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Dismissal Modal */}
      {dismissModalSignal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(0, 0, 0, 0.7)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
          onClick={() => setDismissModalSignal(null)}
        >
          <div
            className="ac-card"
            style={{
              width: "100%",
              maxWidth: 440,
              background: "#111827",
              padding: "24px",
              borderRadius: "12px",
              border: "1px solid #374151",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 8px 0", fontSize: "1.1rem", fontWeight: 700 }}>
              Dismiss Proactive Signal
            </h3>
            <p style={{ margin: "0 0 12px 0", fontSize: "0.85rem", color: "#9ca3af" }}>
              Dismissing signal: <strong>{dismissModalSignal.title}</strong>. Please state the justification for audit compliance.
            </p>

            <form onSubmit={handleDismissSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>
                  Dismissal Justification / Audit Reason
                </label>
                <textarea
                  rows={3}
                  required
                  placeholder="e.g. Asset scheduled for phase check next Monday; risk accepted by technical director."
                  value={dismissReason}
                  onChange={(e) => setDismissReason(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px",
                    background: "#1f2937",
                    color: "#fff",
                    borderRadius: 6,
                    border: "1px solid #4b5563",
                    fontSize: "0.85rem",
                  }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setDismissModalSignal(null)}
                  className="ac-btn"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoadingId === dismissModalSignal.id || !dismissReason.trim()}
                  className="ac-btn ac-btn-primary"
                  style={{ background: "#ef4444", borderColor: "#ef4444" }}
                >
                  {actionLoadingId === dismissModalSignal.id ? "Dismissing..." : "Confirm Dismissal"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
