"use client";

// H3: Baseline & Health Intelligence panel. Renders the explainable,
// baseline-driven health verdict for one asset -- overall state, per-
// component breakdown, and (crucially) WHY: primary contributing features
// with their deviation from baseline and trend direction. Never renders a
// bare score; every non-healthy state shows its explanation.

import { useEffect, useState } from "react";
import { StatusBadge, humsHealthIntelligenceStateBadge } from "@/components/status/StatusBadge";
import { humsApi, type HUMSAssetHealthIntelligence, type HUMSFeatureHealth } from "@/lib/api/hums";

interface HUMSHealthIntelligencePanelProps {
  assetId: string;
  accessToken?: string | null;
}

function trendLabel(trend: HUMSFeatureHealth["trend"]): string {
  if (!trend || trend.direction === "INSUFFICIENT_DATA") return "trend unknown";
  return trend.direction.toLowerCase();
}

function FeatureRow({ f }: { f: HUMSFeatureHealth }) {
  return (
    <div
      style={{
        padding: "8px 10px",
        borderLeft: `3px solid ${
          f.state === "HEALTHY" ? "#4ade80" : f.state === "WATCH" ? "#fbbf24" : f.state === "INSUFFICIENT_DATA" ? "#6b7280" : "#f87171"
        }`,
        background: "rgba(255,255,255,0.02)",
        borderRadius: 4,
        marginBottom: 6,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <strong>{f.feature_type.replace(/_/g, " ")}</strong>
        <StatusBadge {...humsHealthIntelligenceStateBadge(f.state)} />
      </div>
      {f.deviation && f.deviation.state !== "INSUFFICIENT_DATA" && (
        <div style={{ fontSize: 12, color: "var(--ac-text-secondary)", marginTop: 2 }}>
          current {f.deviation.current_value} vs. baseline {f.deviation.baseline_value} (range [{f.deviation.lower_bound}, {f.deviation.upper_bound}])
          {f.deviation.percentage_deviation !== null ? ` — ${(f.deviation.percentage_deviation * 100).toFixed(1)}% from baseline` : ""}
          {" · "}
          {trendLabel(f.trend)}
          {f.consecutive_deviation_count > 0 ? ` · ${f.consecutive_deviation_count} consecutive` : ""}
        </div>
      )}
      <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--ac-text-secondary)" }}>
        {f.explanation.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </div>
  );
}

export function HUMSHealthIntelligencePanel({ assetId, accessToken }: HUMSHealthIntelligencePanelProps) {
  const [data, setData] = useState<HUMSAssetHealthIntelligence | null>(null);
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
      .getAssetHealthIntelligence(accessToken, assetId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load health intelligence"))
      .finally(() => setLoading(false));
  }, [accessToken, assetId]);

  if (loading) return <p style={{ fontSize: 13, color: "var(--ac-text-secondary)" }}>Loading health intelligence…</p>;
  if (error) return <p style={{ fontSize: 13, color: "var(--ac-status-non-compliant)" }}>{error}</p>;
  if (!data) return <p style={{ fontSize: 13, color: "var(--ac-text-secondary)", fontStyle: "italic" }}>Health intelligence unavailable.</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <strong>Baseline-Driven Health Intelligence</strong>
          <div style={{ fontSize: 12, color: "var(--ac-text-secondary)" }}>Confidence: {data.confidence.toLowerCase()}</div>
        </div>
        <StatusBadge {...humsHealthIntelligenceStateBadge(data.state)} />
      </div>

      {data.state === "INSUFFICIENT_DATA" ? (
        <p style={{ fontSize: 13, color: "var(--ac-text-secondary)", fontStyle: "italic" }}>
          Not enough historical feature data to establish a trustworthy baseline yet. No health state is reported rather than
          guessing one.
        </p>
      ) : (
        <>
          {data.primary_contributors.length > 0 && (
            <div>
              <div style={{ fontSize: 12, color: "var(--ac-text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>
                Why: primary contributors
              </div>
              {data.primary_contributors.map((f, i) => (
                <FeatureRow key={`${f.sensor_id}-${f.feature_type}-${i}`} f={f} />
              ))}
            </div>
          )}

          <div>
            <div style={{ fontSize: 12, color: "var(--ac-text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Components
            </div>
            {data.components.map((comp) => (
              <div key={comp.component_id ?? "unassigned"} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                  <span>{comp.component_id ? `Component ${comp.component_id.slice(0, 8)}` : "Unassigned sensors"}</span>
                  <StatusBadge {...humsHealthIntelligenceStateBadge(comp.state)} />
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <p style={{ fontSize: 11, color: "var(--ac-text-muted)" }}>
        Deterministic, explainable health intelligence derived from historical HUMS feature baselines. This is NOT fault
        diagnosis, prognostics, remaining-useful-life prediction, or an autonomous safety decision — it is one input into
        overall asset readiness, reviewed by a human.
      </p>
    </div>
  );
}
