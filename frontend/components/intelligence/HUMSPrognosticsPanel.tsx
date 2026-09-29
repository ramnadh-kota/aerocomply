"use client";

// H5: Prognostics & Remaining Useful Life panel. Every RUL value shown here
// is explicitly labeled an ESTIMATE, NOT A CERTIFIED LIFE LIMIT -- never
// rendered as a bare number without its range, confidence, and basis.

import { useEffect, useState } from "react";
import { humsApi, type HUMSPrognosticRecord } from "@/lib/api/hums";

interface HUMSPrognosticsPanelProps {
  assetId: string;
  accessToken?: string | null;
}

const STATUS_COLOR: Record<string, string> = {
  AVAILABLE: "#4ade80",
  LIMITED: "#9ca3af",
  INSUFFICIENT_DATA: "#6b7280",
  LOW_CONFIDENCE: "#fbbf24",
  STALE: "#f87171",
  INVALID: "#f87171",
};

function RulCard({ record }: { record: HUMSPrognosticRecord }) {
  const hasRul = record.rul_estimate !== null && record.rul_lower !== null && record.rul_upper !== null;

  return (
    <div
      style={{
        padding: 14,
        borderLeft: `4px solid ${STATUS_COLOR[record.status] ?? "#6b7280"}`,
        background: "rgba(255,255,255,0.02)",
        borderRadius: 6,
        marginBottom: 10,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <strong style={{ fontSize: 13 }}>{record.feature_type.replace(/_/g, " ")}</strong>
        <span style={{ fontSize: 11, color: STATUS_COLOR[record.status] ?? "#9ca3af" }}>{record.status.replace(/_/g, " ")}</span>
      </div>

      {hasRul ? (
        <>
          <div style={{ fontSize: 24, fontWeight: 700, marginTop: 6 }}>
            {record.rul_estimate} <span style={{ fontSize: 13, fontWeight: 400, color: "#9ca3af" }}>{record.rul_unit?.replace(/_/g, " ").toLowerCase()}</span>
          </div>
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>
            Range: {record.rul_lower}–{record.rul_upper} · Confidence: {record.confidence.toLowerCase()}
          </div>
        </>
      ) : (
        <div style={{ fontSize: 13, color: "#9ca3af", fontStyle: "italic", marginTop: 6 }}>
          {record.status === "INSUFFICIENT_DATA" ? "Not enough history to estimate RUL yet." : "No threshold crossing predicted from current evidence."}
        </div>
      )}

      {record.threshold_value !== null && (
        <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 6 }}>
          Current: {record.current_value} vs. threshold {record.threshold_value} ({record.threshold_type?.replace(/_/g, " ").toLowerCase()})
        </div>
      )}

      {record.extrapolation_distance !== null && record.status === "LOW_CONFIDENCE" && (
        <div style={{ fontSize: 11, color: "#fbbf24", marginTop: 6 }}>
          ⚠ Prediction extrapolates {record.extrapolation_distance} beyond the observed data — low confidence.
        </div>
      )}

      <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, color: "#d1d5db" }}>
        {record.explanation.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>

      <div style={{ marginTop: 8, fontSize: 11, color: "#fbbf24", fontWeight: 600 }}>
        ⚠ Prognostic estimate only — not a certified life limit.
      </div>
    </div>
  );
}

export function HUMSPrognosticsPanel({ assetId, accessToken }: HUMSPrognosticsPanelProps) {
  const [records, setRecords] = useState<HUMSPrognosticRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || !assetId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    humsApi
      .getAssetPrognostics(accessToken, assetId)
      .then(setRecords)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load prognostics"))
      .finally(() => setLoading(false));
  }, [accessToken, assetId]);

  if (loading) return <p style={{ fontSize: 13, color: "#9ca3af" }}>Loading prognostics…</p>;
  if (error) return <p style={{ fontSize: 13, color: "#f87171" }}>{error}</p>;

  if (!records || records.length === 0) {
    return <p style={{ fontSize: 13, color: "#9ca3af", fontStyle: "italic" }}>No prognostic data available for this asset yet.</p>;
  }

  return (
    <div>
      {records.map((r) => (
        <RulCard key={r.id} record={r} />
      ))}
    </div>
  );
}
