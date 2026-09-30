"use client";

// H1 + H2: HUMS (Health & Usage Monitoring System) panel.
// Renders the telemetry-derived health rollup for one asset, plus (H2) a
// per-sensor feature-history table and a basic frequency spectrum view.
// Shows what hums_service/feature_service actually compute. Diagnostics, prognostics/RUL and health intelligence are
// rendered by their own panels. Operators can also set per-sensor vibration limits here (OEM / maintenance-manual
// values); without them the platform defaults apply.

import { useState } from "react";
import { StatusBadge, humsHealthStatusBadge } from "@/components/status/StatusBadge";
import { humsApi, type HUMSAssetHealthSummary, type HUMSFeature, type HUMSSensor, type HUMSSpectrum } from "@/lib/api/hums";
import { limitsLabel, limitsToInput, parseLimits } from "@/lib/hums/limits";

interface HUMSHealthPanelProps {
  health: HUMSAssetHealthSummary | null;
  accessToken?: string | null;
}

const FEATURE_ORDER = [
  "rms",
  "peak",
  "peak_to_peak",
  "crest_factor",
  "kurtosis",
  "skewness",
  "dominant_frequency",
  "spectral_energy",
  "band_energy",
  "mean",
  "std",
  "trend",
  "rate_of_change",
];

function qualityColor(quality: string): string {
  switch (quality) {
    case "GOOD":
      return "#4ade80";
    case "DEGRADED":
      return "#fbbf24";
    case "INSUFFICIENT_DATA":
      return "#9ca3af";
    default:
      return "#f87171";
  }
}

function SensorFeatureHistory({ sensorId, accessToken }: { sensorId: string; accessToken: string }) {
  const [features, setFeatures] = useState<HUMSFeature[] | null>(null);
  const [spectrum, setSpectrum] = useState<HUMSSpectrum | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [feats, spec] = await Promise.all([
        humsApi.getSensorFeatures(accessToken, sensorId),
        humsApi.getSensorSpectrum(accessToken, sensorId).catch(() => null),
      ]);
      setFeatures(feats);
      setSpectrum(spec);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load feature history");
    } finally {
      setLoading(false);
    }
  }

  if (features === null && !loading) {
    return (
      <button
        onClick={load}
        style={{
          fontSize: 12,
          color: "#93c5fd",
          background: "none",
          border: "1px solid #27272a",
          borderRadius: 6,
          padding: "4px 10px",
          cursor: "pointer",
        }}
      >
        Show feature history
      </button>
    );
  }

  if (loading) return <p style={{ fontSize: 12, color: "#9ca3af" }}>Loading feature history…</p>;
  if (error) return <p style={{ fontSize: 12, color: "#f87171" }}>{error}</p>;
  if (!features || features.length === 0) return <p style={{ fontSize: 12, color: "#9ca3af" }}>No feature history yet.</p>;

  // Latest value per feature_type, ordered by FEATURE_ORDER then anything else alphabetically.
  const latestByType = new Map<string, HUMSFeature>();
  for (const f of features) {
    const existing = latestByType.get(f.feature_type);
    if (!existing || new Date(f.window_end) > new Date(existing.window_end)) {
      latestByType.set(f.feature_type, f);
    }
  }
  const orderedTypes = [
    ...FEATURE_ORDER.filter((t) => latestByType.has(t)),
    ...[...latestByType.keys()].filter((t) => !FEATURE_ORDER.includes(t)).sort(),
  ];

  const maxMagnitude = spectrum && spectrum.magnitudes.length > 0 ? Math.max(...spectrum.magnitudes, 1e-9) : 0;

  return (
    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ textAlign: "left", color: "#9ca3af" }}>
            <th style={{ padding: "4px 6px" }}>Feature</th>
            <th style={{ padding: "4px 6px" }}>Current</th>
            <th style={{ padding: "4px 6px" }}>Quality</th>
            <th style={{ padding: "4px 6px" }}>Window End</th>
          </tr>
        </thead>
        <tbody>
          {orderedTypes.map((type) => {
            const f = latestByType.get(type)!;
            return (
              <tr key={type} style={{ borderTop: "1px solid #27272a" }}>
                <td style={{ padding: "4px 6px" }}>{type.replace(/_/g, " ")}</td>
                <td style={{ padding: "4px 6px" }}>{f.value} {f.unit !== "unitless" ? f.unit : ""}</td>
                <td style={{ padding: "4px 6px", color: qualityColor(f.quality) }}>{f.quality.replace(/_/g, " ")}</td>
                <td style={{ padding: "4px 6px", color: "#6b7280" }}>{new Date(f.window_end).toLocaleString()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {spectrum && spectrum.quality === "GOOD" && spectrum.magnitudes.length > 0 ? (
        <div>
          <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>
            Frequency spectrum — dominant {spectrum.dominant_frequency_hz} Hz
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 60 }}>
            {spectrum.magnitudes.slice(0, 40).map((m, i) => (
              <div
                key={i}
                title={`${spectrum.frequencies_hz[i]} Hz: ${m}`}
                style={{
                  flex: 1,
                  height: `${Math.max(2, (m / maxMagnitude) * 100)}%`,
                  background:
                    spectrum.dominant_frequency_hz !== null && spectrum.frequencies_hz[i] === spectrum.dominant_frequency_hz
                      ? "#38bdf8"
                      : "#3f3f46",
                }}
              />
            ))}
          </div>
        </div>
      ) : (
        <p style={{ fontSize: 11, color: "#6b7280", fontStyle: "italic" }}>
          Frequency spectrum unavailable (insufficient samples or no sampling-rate estimate for this window).
        </p>
      )}
    </div>
  );
}

function SensorLimitsEditor({ assetId, sensorId, accessToken }: { assetId: string; sensorId: string; accessToken: string }) {
  const [sensor, setSensor] = useState<HUMSSensor | null>(null);
  const [form, setForm] = useState({ warning: "", critical: "" });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function openEditor() {
    setMsg(null);
    try {
      const list = await humsApi.getSensors(accessToken, assetId);
      const s = list.find((x) => x.id === sensorId) ?? null;
      setSensor(s);
      setForm(limitsToInput(s?.warning_threshold, s?.critical_threshold));
      setOpen(true);
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Could not load sensor limits" });
    }
  }

  async function save() {
    const parsed = parseLimits(form);
    if (!parsed.ok) {
      setMsg({ ok: false, text: parsed.error });
      return;
    }
    setBusy(true);
    try {
      const updated = await humsApi.setSensorThresholds(accessToken, sensorId, parsed.payload);
      setSensor(updated);
      setMsg({ ok: true, text: `Saved: ${limitsLabel(updated.warning_threshold, updated.critical_threshold)}.` });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Could not save limits" });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <>
        <button onClick={openEditor} style={{ fontSize: 12, color: "#93c5fd", background: "none", border: "1px solid #27272a", borderRadius: 6, padding: "4px 10px", cursor: "pointer", marginLeft: 8 }}>
          Vibration limits
        </button>
        {msg && !msg.ok && <span role="alert" style={{ fontSize: 12, color: "#f87171", marginLeft: 8 }}>{msg.text}</span>}
      </>
    );
  }
  return (
    <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
      <span style={{ color: "#9ca3af" }}>Current: {limitsLabel(sensor?.warning_threshold, sensor?.critical_threshold)}</span>
      <input aria-label="Warning limit" placeholder="Warning" inputMode="decimal" value={form.warning} onChange={(e) => setForm({ ...form, warning: e.target.value })} style={{ width: 90 }} />
      <input aria-label="Critical limit" placeholder="Critical" inputMode="decimal" value={form.critical} onChange={(e) => setForm({ ...form, critical: e.target.value })} style={{ width: 90 }} />
      <button onClick={save} disabled={busy}>{busy ? "Saving…" : "Save limits"}</button>
      <span style={{ color: "#6b7280" }}>Leave both empty for the platform defaults (not OEM limits).</span>
      {msg && <span role={msg.ok ? "status" : "alert"} style={{ color: msg.ok ? "#4ade80" : "#f87171" }}>{msg.text}</span>}
    </div>
  );
}

export function HUMSHealthPanel({ health, accessToken }: HUMSHealthPanelProps) {
  if (!health) {
    return (
      <div style={{ padding: 16, color: "#9ca3af", fontStyle: "italic" }}>
        HUMS telemetry unavailable for this asset.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <strong>Overall HUMS Health</strong>
          <div style={{ fontSize: 13, color: "#9ca3af" }}>
            {health.sensor_count} sensor{health.sensor_count === 1 ? "" : "s"} monitored
            {health.active_exceedance_count > 0
              ? ` — ${health.active_exceedance_count} active exceedance${health.active_exceedance_count === 1 ? "" : "s"}`
              : ""}
          </div>
        </div>
        <StatusBadge {...humsHealthStatusBadge(health.overall_status)} />
      </div>

      {health.components.length === 0 ? (
        <p style={{ color: "#9ca3af", fontStyle: "italic" }}>No HUMS sensors installed on this asset.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {health.components.map((c) => (
            <div key={c.sensor_id} style={{ borderTop: "1px solid #27272a", paddingTop: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 13 }}>
                  <span>{c.parameter.replace(/_/g, " ")}</span>
                  <StatusBadge {...humsHealthStatusBadge(c.status)} />
                  <span style={{ color: "#9ca3af" }}>
                    {c.latest_feature ? `${c.latest_feature.value} ${c.latest_feature.unit}` : "no data"}
                  </span>
                  {c.health_score !== null && <span style={{ color: "#9ca3af" }}>score {c.health_score}</span>}
                  {c.active_exceedance_count > 0 && (
                    <span style={{ color: "#f87171" }}>{c.active_exceedance_count} exceedance(s)</span>
                  )}
                </div>
              </div>
              {accessToken && <SensorFeatureHistory sensorId={c.sensor_id} accessToken={accessToken} />}
              {accessToken && <SensorLimitsEditor assetId={health.asset_id} sensorId={c.sensor_id} accessToken={accessToken} />}
            </div>
          ))}
        </div>
      )}

      <p style={{ fontSize: 12, color: "#6b7280" }}>
        HUMS health is one input into overall asset readiness, not a substitute for it. Limits without a configured
        value use generic platform defaults; set OEM or maintenance-manual limits per sensor.
      </p>
    </div>
  );
}
