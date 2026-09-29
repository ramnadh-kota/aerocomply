"use client";

// H4: Diagnostics & Fault Isolation panel. Lists rule-based diagnostic
// candidates for one asset -- NEVER collapses competing hypotheses into a
// single conclusion, and NEVER presents a candidate as a confirmed fault
// unless status === "CONFIRMED" (set only by an explicit, authorized
// confirm action taken here by the viewer).

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/status/StatusBadge";
import { humsApi, type HUMSDiagnosticCandidate } from "@/lib/api/hums";

interface HUMSDiagnosticsPanelProps {
  assetId: string;
  accessToken?: string | null;
  canWrite?: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  SUPPORTED: "#f87171",
  CANDIDATE: "#fbbf24",
  WEAK: "#9ca3af",
  CONFIRMED: "#f87171",
  REJECTED: "#6b7280",
  RESOLVED: "#4ade80",
  UNSUPPORTED: "#6b7280",
};

const SEVERITY_LABEL: Record<string, string> = { HIGH: "High", MEDIUM: "Medium", LOW: "Low" };

export function HUMSDiagnosticsPanel({ assetId, accessToken, canWrite = false }: HUMSDiagnosticsPanelProps) {
  const [candidates, setCandidates] = useState<HUMSDiagnosticCandidate[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectDrafts, setRejectDrafts] = useState<Record<string, string>>({});

  function load() {
    if (!accessToken || !assetId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    humsApi
      .getAssetDiagnostics(accessToken, assetId)
      .then(setCandidates)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load diagnostics"))
      .finally(() => setLoading(false));
  }

  useEffect(load, [accessToken, assetId]);

  async function handleConfirm(id: string) {
    if (!accessToken) return;
    await humsApi.confirmDiagnostic(accessToken, id);
    load();
  }

  async function handleReject(id: string) {
    if (!accessToken) return;
    const reason = rejectDrafts[id]?.trim();
    if (!reason) return;
    await humsApi.rejectDiagnostic(accessToken, id, reason);
    load();
  }

  if (loading) return <p style={{ fontSize: 13, color: "#9ca3af" }}>Loading diagnostics…</p>;
  if (error) return <p style={{ fontSize: 13, color: "#f87171" }}>{error}</p>;

  if (!candidates || candidates.length === 0) {
    return (
      <p style={{ fontSize: 13, color: "#9ca3af", fontStyle: "italic" }}>
        No diagnostic candidates. Either the asset is healthy, or current evidence is insufficient to support a diagnostic
        hypothesis — no fault is fabricated in either case.
      </p>
    );
  }

  return (
    <div>
      {candidates.map((c) => (
        <div
          key={c.id}
          style={{
            padding: 12,
            borderLeft: `4px solid ${STATUS_COLOR[c.status] ?? "#6b7280"}`,
            background: "rgba(255,255,255,0.02)",
            borderRadius: 6,
            marginBottom: 10,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <strong style={{ fontSize: 14 }}>{c.fault_name}</strong>
              <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>
                confidence {c.confidence.toLowerCase()} · score {c.score.toFixed(2)} · severity {SEVERITY_LABEL[c.severity]}
              </div>
            </div>
            <StatusBadge
              status={c.status === "CONFIRMED" || c.status === "SUPPORTED" ? "NON_COMPLIANT" : c.status === "REJECTED" || c.status === "RESOLVED" ? "COMPLIANT" : "PENDING"}
              label={c.status.replace(/_/g, " ")}
            />
          </div>

          {c.status !== "CONFIRMED" && c.status !== "REJECTED" && (
            <div style={{ fontSize: 11, color: "#fbbf24", marginTop: 6, fontStyle: "italic" }}>
              Diagnostic candidate — requires engineering confirmation. Not a confirmed fault.
            </div>
          )}

          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12.5, color: "#d1d5db" }}>
            {c.explanation.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>

          {c.contradicting_evidence.length > 0 && (
            <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 6 }}>
              Contradicting evidence present ({c.contradicting_evidence.length}) — confidence reduced accordingly.
            </div>
          )}

          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 6 }}>
            {c.fault_code} · rule v{c.rule_version} · detected {new Date(c.detected_at).toLocaleString()}
          </div>

          {c.status === "REJECTED" && c.rejection_reason && (
            <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 6 }}>Rejected: {c.rejection_reason}</div>
          )}

          {canWrite && c.status !== "CONFIRMED" && c.status !== "REJECTED" && (
            <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <button
                onClick={() => handleConfirm(c.id)}
                style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #27272a", background: "none", color: "#93c5fd", cursor: "pointer" }}
              >
                Confirm
              </button>
              <input
                value={rejectDrafts[c.id] ?? ""}
                onChange={(e) => setRejectDrafts((prev) => ({ ...prev, [c.id]: e.target.value }))}
                placeholder="Rejection reason"
                style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid #27272a", background: "transparent", color: "#d1d5db" }}
              />
              <button
                disabled={!(rejectDrafts[c.id] ?? "").trim()}
                onClick={() => handleReject(c.id)}
                style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #27272a", background: "none", color: "#f87171", cursor: "pointer" }}
              >
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
      <p style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        Diagnostic candidates are rule-based hypotheses, not confirmed faults, RUL predictions, or autonomous decisions. All
        alternative hypotheses are shown — Kota never collapses competing evidence into a single conclusion.
      </p>
    </div>
  );
}
