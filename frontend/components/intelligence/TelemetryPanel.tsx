"use client";

// Phase C: live telemetry for one asset — connection state, the latest reading of every sensor
// (with its own timestamp, age and data quality) and the flights created from telemetry.
// Nothing here is inferred: a sensor that never reported has no row, and a stalled feed shows as
// growing age / STALE, never as a fresh value.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/status/StatusBadge";
import { normalizeApiError } from "@/lib/apiClient";
import {
  telemetryApi,
  type LatestReadings,
  type TelemetryFlight,
  type TelemetryStatus,
} from "@/lib/api/telemetry";
import { formatDuration, readingTone, stateBadge } from "@/lib/telemetry/helpers";

export function TelemetryPanel({ assetId, accessToken }: { assetId: string; accessToken?: string | null }) {
  const [status, setStatus] = useState<TelemetryStatus | null>(null);
  const [latest, setLatest] = useState<LatestReadings | null>(null);
  const [flights, setFlights] = useState<TelemetryFlight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [s, l, f] = await Promise.all([
        telemetryApi.status(accessToken, assetId),
        telemetryApi.latest(accessToken, assetId),
        telemetryApi.flights(accessToken, assetId),
      ]);
      setStatus(s);
      setLatest(l);
      setFlights(f);
    } catch (err) {
      setError(normalizeApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [accessToken, assetId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !status) {
    return <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Loading telemetry…</p>;
  }
  if (error) {
    return (
      <p role="alert" className="ac-text-sm" style={{ margin: 0 }}>
        Telemetry could not be loaded: {error}{" "}
        <button type="button" className="ac-btn" onClick={() => void load()}>Retry</button>
      </p>
    );
  }
  if (!status) return null;

  const badge = stateBadge(status.telemetry_state);
  const warnAfterSeconds = status.freshness_warning_threshold_days * 86400;

  return (
    <div>
      <div className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 12 }}>
        <StatusBadge status={badge.kind} label={badge.label} />
        <span className="ac-text-sm ac-text-muted">
          {status.last_received_at
            ? `Last data ${new Date(status.last_received_at).toLocaleString()}`
            : "No telemetry has been received for this asset."}
          {status.source_system ? ` · source ${status.source_system}` : ""}
        </span>
        <button type="button" className="ac-btn" onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
        <Link href="/data-sources" className="ac-btn">Manage data sources →</Link>
      </div>

      {latest && latest.sensors.length > 0 ? (
        <div style={{ overflowX: "auto" }}>
          <table className="ac-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Sensor</th>
                <th>Type</th>
                <th style={{ textAlign: "right" }}>Latest value</th>
                <th>Quality</th>
                <th>Age</th>
              </tr>
            </thead>
            <tbody>
              {latest.sensors.map((s) => {
                const tone = readingTone(s.data_quality, s.age_seconds, warnAfterSeconds);
                return (
                  <tr key={s.sensor_id}>
                    <td>{s.sensor_code}</td>
                    <td>{s.measurement_type}</td>
                    <td style={{ textAlign: "right" }}>
                      {s.value} {s.unit}
                    </td>
                    <td>
                      <StatusBadge status={tone.kind} label={tone.label} />
                    </td>
                    <td title={s.recorded_at}>{formatDuration(s.age_seconds)} ago</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          No sensor readings recorded yet. Connect a data source and send data to see live values here.
        </p>
      )}

      {flights.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>
            Flights from telemetry
          </div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {flights.map((f) => (
              <li key={f.flight_id} className="ac-text-sm">
                {f.flight_number ?? "(unnumbered)"} — {new Date(f.flown_at).toLocaleString()} —{" "}
                {f.duration_minutes} min · {f.cycles} cycle{f.cycles === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
